"""The pooled cross-player prop model: one ridge per stat, fitted league-wide.

Why this exists
---------------
``MLPredictor`` fits 81 features on ~60 rows per player (p/n = 1.35). The
2026-08 investigation established that the result has no usable edge: it loses
to a ten-game rolling average on all four stats and went 40-66 against real
lines. Pooling every player into one fit turns n = 60 into n ~ 25,000-33,000
and fixes p/n directly, which is the only intervention in that investigation
that measured better than the model it replaces.

Specification, fixed in advance on a validation split that mirrors the holdout
one season earlier (late 2023-24, >= 60 prior in-season games, >= 28 mpg) and
never tuned against the holdout itself:

* six recency features per stat (``pooled_features``), so p/n ~ 0.0002;
* ``StandardScaler`` + ``Ridge(alpha=3.0)``, one model per stat;
* PRA fitted directly rather than summed from the components;
* trained on every league game strictly before the serving cut date.

The uncertainty model is deliberately separate and deliberately dull: sigma is
an affine function of the player's own in-season dispersion, and probabilities
are shrunk toward the realized base rate by a two-parameter logistic. That is a
truthfulness fix (plan item 6), not an attempt to manufacture edge — the
investigation's verdict on chasing calibration stands.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import optimize as scipy_optimize
from scipy import stats as scipy_stats
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import pooled_features as pf

#: Ridge penalty. Selected on the mirror-holdout validation split; the sweep was
#: flat across 0.3-30, so this is not a tuned knob.
RIDGE_ALPHA: float = 3.0

#: Lower bound on the served sigma, per stat. Stops a player with a freak run of
#: identical box scores from producing a near-zero interval.
SIGMA_FLOOR: Mapping[str, float] = {"PTS": 3.0, "REB": 1.2, "AST": 1.0, "PRA": 4.0}

#: Hard ceiling on the shrinkage slope. A freely-fitted Platt map SHARPENS
#: whenever the served sigma is wider than the realized error, which is exactly
#: what Phase 2 of the investigation did: it manufactured confidence out of a
#: prediction with AUC ~ 0.50. Clamping at 1.0 makes this a shrinkage operator
#: by construction -- it can pull a probability toward the base rate and can
#: never push it away.
MAX_SHRINK_SLOPE: float = 1.0

#: E|X| for a zero-mean normal is sigma * sqrt(2/pi); the sigma model is fitted
#: on absolute residuals, so it is divided back out.
_HALF_NORMAL_SCALE: float = float(np.sqrt(2.0 / np.pi))

#: Where the fitted league artifact lives. ``models/`` is gitignored; the
#: artifact is rebuilt by ``scripts/train_pooled_model.py``.
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "pooled" / "league_model.pkl"

#: Overrides the artifact location without a code change (deploys, tests).
MODEL_PATH_ENV_VAR = "NBA_EVAL_POOLED_MODEL_PATH"


def resolve_model_path(path: Optional[Path] = None) -> Path:
    """Artifact location: explicit argument, then env override, then default.

    Resolved at call time rather than captured as a default argument, so an
    override set after import is still honoured.
    """
    if path is not None:
        return Path(path)
    override = os.environ.get(MODEL_PATH_ENV_VAR)
    return Path(override) if override else DEFAULT_MODEL_PATH

#: Artifact schema version. Bump when a field changes meaning.
ARTIFACT_VERSION = "pooled-1"


class ProbabilityShrinker:
    """Pulls a raw normal-CDF probability toward the realized base rate.

    Duck-types the Platt calibrator ``ProbabilityCalculator.calculate`` expects,
    so the pooled model plugs into the existing serving path unchanged: that
    function hands over ``raw_prob_over`` and calls ``predict_proba``.

    The raw probability is mapped back to its z-score and pushed through a
    two-parameter logistic. ``slope < 1`` is the shrinkage; ``intercept``
    carries the 51-53% over base rate the investigation measured.
    """

    __slots__ = ("intercept", "slope")

    def __init__(self, intercept: float, slope: float):
        self.intercept = float(intercept)
        self.slope = float(slope)

    def predict_proba(self, X) -> np.ndarray:
        raw = np.clip(np.asarray(X, dtype=float).reshape(-1), 1e-6, 1 - 1e-6)
        z = scipy_stats.norm.ppf(raw)
        over = 1.0 / (1.0 + np.exp(-(self.intercept + self.slope * z)))
        over = np.clip(over, 1e-6, 1 - 1e-6)
        return np.column_stack([1.0 - over, over])

    def __eq__(self, other) -> bool:
        return (isinstance(other, ProbabilityShrinker)
                and self.intercept == other.intercept
                and self.slope == other.slope)

    def __repr__(self) -> str:
        return "ProbabilityShrinker(intercept={:.4f}, slope={:.4f})".format(
            self.intercept, self.slope)


@dataclass(frozen=True)
class StatFit:
    """Everything needed to serve one stat. Immutable by construction."""

    stat: str
    feature_names: Tuple[str, ...]
    center: Tuple[float, ...]       # StandardScaler mean_
    scale: Tuple[float, ...]        # StandardScaler scale_
    coef: Tuple[float, ...]         # ridge coefficients in scaled space
    intercept: float
    sigma_intercept: float
    sigma_slope: float
    shrinker: ProbabilityShrinker
    n_train: int
    train_mae: float

    def predict(self, features: Mapping[str, float]) -> float:
        x = np.array([_require(features, name, self.stat)
                      for name in self.feature_names], dtype=float)
        scaled = (x - np.asarray(self.center)) / np.asarray(self.scale)
        return float(np.dot(scaled, np.asarray(self.coef)) + self.intercept)


def _require(features: Mapping[str, float], name: str, stat: str) -> float:
    """Read one feature or fail loudly.

    ``MLPredictor.predict`` substitutes 0 for any declared feature the served
    frame does not carry, which is how a feature can silently stop existing.
    The pooled path refuses that trade.
    """
    if name not in features:
        raise KeyError(
            "{}: pooled feature {!r} absent from the served frame; refusing to "
            "substitute 0".format(stat, name))
    value = float(features[name])
    if not np.isfinite(value):
        raise ValueError("{}: pooled feature {!r} is not finite".format(stat, name))
    return value


@dataclass(frozen=True)
class PooledLeagueModel:
    """One ridge per stat, fitted across every player in the league."""

    stats: Mapping[str, StatFit]
    trained_through: str
    n_players: int
    version: str = ARTIFACT_VERSION

    # ── serving ──────────────────────────────────────────────────────────────

    def predict(self, features: Mapping[str, float]) -> Dict[str, float]:
        """Point predictions for every served stat."""
        return {stat: fit.predict(features) for stat, fit in self.stats.items()}

    def sigma(self, stat: str, dispersion: float) -> float:
        """Served standard deviation for ``stat`` at a player's own dispersion."""
        fit = self._fit(stat)
        raw = fit.sigma_intercept + fit.sigma_slope * float(dispersion)
        return float(max(SIGMA_FLOOR.get(stat, 1.0), raw))

    def prob_over(self, stat: str, prediction: float, line: float,
                  sigma: float) -> float:
        """Shrunk probability (0-100) that the stat finishes over ``line``."""
        raw = 1.0 - scipy_stats.norm.cdf((line - prediction) / (sigma + 0.1))
        return float(round(
            self._fit(stat).shrinker.predict_proba([[raw]])[0, 1] * 100.0, 1))

    def calibrator_entry(self, stat: str) -> Dict[str, object]:
        """``probability_calibrator[stat]`` in the shape the serve path reads."""
        return {"calibrator": self._fit(stat).shrinker,
                "method": "platt",
                "std_estimate": None,
                "source": "pooled"}

    def _fit(self, stat: str) -> StatFit:
        if stat not in self.stats:
            raise KeyError("pooled model has no fit for {!r}".format(stat))
        return self.stats[stat]

    # ── fitting ──────────────────────────────────────────────────────────────

    @classmethod
    def fit(cls, panel: pd.DataFrame, trained_through: str,
            alpha: float = RIDGE_ALPHA,
            kinds: Sequence[str] = pf.RECENCY_KINDS) -> "PooledLeagueModel":
        """Fit one ridge per stat on a league panel from ``build_panel``."""
        if panel is None or panel.empty:
            raise ValueError("pooled fit needs a non-empty panel")
        fits = {}
        for stat in pf.POOLED_STATS:
            fits[stat] = _fit_one(panel, stat, alpha, kinds)
        n_players = int(panel["player_id"].nunique()) if "player_id" in panel else 0
        return cls(stats=dict(fits), trained_through=str(trained_through),
                   n_players=n_players)

    # ── persistence ──────────────────────────────────────────────────────────

    def save(self, path: Optional[Path] = None) -> Path:
        path = resolve_model_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as handle:
            pickle.dump(self, handle)
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "PooledLeagueModel":
        path = resolve_model_path(path)
        if not path.exists():
            raise FileNotFoundError(
                "pooled league model not found at {}. Train it with "
                "`NBA_EVAL_DISABLE_TF=1 python3 scripts/train_pooled_model.py` "
                "before enabling NBA_EVAL_POOLED_MODEL.".format(path))
        with open(path, "rb") as handle:
            model = pickle.load(handle)
        if not isinstance(model, cls):
            raise ValueError("{} does not hold a PooledLeagueModel".format(path))
        if model.version != ARTIFACT_VERSION:
            raise ValueError(
                "pooled artifact version {!r} != {!r}; retrain it".format(
                    model.version, ARTIFACT_VERSION))
        return model


def _columns_for(panel: pd.DataFrame, stat: str,
                 kinds: Sequence[str]) -> Tuple[str, ...]:
    names = pf.feature_names(stat, kinds)
    missing = [n for n in names if n not in panel.columns]
    if missing:
        raise ValueError("panel is missing pooled feature(s): {}".format(
            ", ".join(missing)))
    target = "{}_ACTUAL".format(stat)
    if target not in panel.columns:
        raise ValueError("panel is missing target {}".format(target))
    return names


def _fit_one(panel: pd.DataFrame, stat: str, alpha: float,
             kinds: Sequence[str]) -> StatFit:
    names = _columns_for(panel, stat, kinds)
    X = panel[list(names)].to_numpy(dtype=float)
    y = panel["{}_ACTUAL".format(stat)].to_numpy(dtype=float)
    pipeline = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(X, y)
    scaler, ridge = pipeline[0], pipeline[1]
    predictions = pipeline.predict(X)
    residuals = y - predictions

    dispersion_col = "{}_DISPERSION".format(stat)
    dispersion = (panel[dispersion_col].to_numpy(dtype=float)
                  if dispersion_col in panel.columns
                  else np.full(len(panel), float(np.std(y, ddof=1))))
    sigma_intercept, sigma_slope = _fit_sigma(np.abs(residuals), dispersion)
    shrinker = _fit_shrinker(panel, stat, predictions,
                             _sigma_values(sigma_intercept, sigma_slope, dispersion, stat))

    return StatFit(
        stat=stat,
        feature_names=tuple(names),
        center=tuple(float(v) for v in scaler.mean_),
        scale=tuple(float(v) for v in scaler.scale_),
        coef=tuple(float(v) for v in ridge.coef_),
        intercept=float(ridge.intercept_),
        sigma_intercept=sigma_intercept,
        sigma_slope=sigma_slope,
        shrinker=shrinker,
        n_train=int(len(y)),
        train_mae=float(np.abs(residuals).mean()),
    )


def _fit_sigma(abs_residuals: np.ndarray,
               dispersion: np.ndarray) -> Tuple[float, float]:
    """Affine map from a player's own dispersion to a served sigma."""
    model = LinearRegression().fit(dispersion.reshape(-1, 1), abs_residuals)
    return (float(model.intercept_ / _HALF_NORMAL_SCALE),
            float(model.coef_[0] / _HALF_NORMAL_SCALE))


def _sigma_values(intercept: float, slope: float, dispersion: np.ndarray,
                  stat: str) -> np.ndarray:
    return np.maximum(SIGMA_FLOOR.get(stat, 1.0), intercept + slope * dispersion)


def _fit_shrinker(panel: pd.DataFrame, stat: str, predictions: np.ndarray,
                  sigma: np.ndarray) -> ProbabilityShrinker:
    """Two-parameter logistic on the z-score, at the season-median line.

    The line is the player's own season-to-date median — a pseudo-line, and the
    investigation showed pseudo-line ROI is an artifact of how the line is
    built. This fit therefore claims nothing about edge; it only stops the
    served probability from asserting more confidence than the point prediction
    carries.
    """
    line_col = "{}_MEDIAN".format(stat)
    target_col = "{}_ACTUAL".format(stat)
    line = panel[line_col].to_numpy(dtype=float)
    actual = panel[target_col].to_numpy(dtype=float)
    live = actual != line
    if live.sum() < 100:
        return ProbabilityShrinker(intercept=0.0, slope=1.0)
    z = ((predictions[live] - line[live]) / (sigma[live] + 0.1)).reshape(-1, 1)
    outcome = (actual[live] > line[live]).astype(int)
    if len(np.unique(outcome)) < 2:
        return ProbabilityShrinker(intercept=0.0, slope=1.0)
    logistic = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000).fit(z, outcome)
    free_slope = float(logistic.coef_[0][0])
    slope = min(MAX_SHRINK_SLOPE, max(0.0, free_slope))
    if slope == free_slope:
        return ProbabilityShrinker(intercept=float(logistic.intercept_[0]), slope=slope)
    # The slope was clamped, so the jointly-fitted intercept no longer belongs
    # to it: keeping it would bias every served probability. Refit the intercept
    # alone at the clamped slope, which is what makes this a pure shrinkage.
    return ProbabilityShrinker(
        intercept=_intercept_at_slope(z.reshape(-1), outcome, slope), slope=slope)


def _intercept_at_slope(z: np.ndarray, outcome: np.ndarray, slope: float) -> float:
    """Log-loss-minimising intercept with the slope held fixed."""
    def loss(intercept: float) -> float:
        logit = intercept + slope * z
        # log(1 + exp(-logit)) evaluated stably.
        return float(np.mean(np.logaddexp(0.0, -logit) * outcome
                             + np.logaddexp(0.0, logit) * (1 - outcome)))

    result = scipy_optimize.minimize_scalar(loss, bounds=(-5.0, 5.0), method="bounded")
    return float(result.x)
