"""``MLPredictor``-shaped facade over the pooled league model.

The API, the SSE prediction service and the backtest harness all drive a
predictor through the same fixed sequence:

    load -> train / update -> save -> _update_recent_averages -> predict
         -> apply_injury_boost -> apply_blowout_discount
         -> get_confidence -> get_prediction_uncertainty

``PooledPredictor`` answers every one of those with the same shapes, so
swapping it in behind the ``NBA_EVAL_POOLED_MODEL`` flag changes nothing above
it. Subclassing ``MLPredictor`` is deliberate: it makes the interface parity a
property of the type rather than of a checklist, and it inherits the injury and
blowout adjustments unchanged.

There is **no per-player fitted state**. The league model is fitted once,
offline, by ``scripts/train_pooled_model.py``; a player contributes only their
own game log, from which the six recency features per stat are recomputed at
serve. That removes the whole class of "written in the training process, absent
from ``save()``" bugs by removing per-player persistence entirely — ``load()``
returns False and ``save()`` is a no-op, so the caller's existing
load-or-train-then-save flow still works and simply costs nothing.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

import pooled_features as pf
from nba_evaluator import MLPredictor
from pooled_model import PooledLeagueModel

logger = logging.getLogger(__name__)

#: Confidence shown for a pooled prediction is derived from its served sigma.
#: The bounds are deliberately tighter than ``MLPredictor.CONFIDENCE_CAPS``
#: (PTS 88%): the pooled model's measured median-line AUC is 0.55-0.63, and a
#: number above the low seventies would overstate that.
POOLED_CONFIDENCE_CAP: float = 72.0
POOLED_CONFIDENCE_FLOOR: float = 52.0

#: Half-width of the served interval, in sigmas. 1.2816 sigma each side is the
#: 80% band, matching what ``get_confidence`` returns from the quantile path.
INTERVAL_SIGMAS: float = 1.2816


class PooledPredictor(MLPredictor):
    """Serves the pooled cross-player model behind ``MLPredictor``'s interface."""

    def __init__(self, model_type: str = "pooled", use_ensemble: bool = False,
                 league_model: Optional[PooledLeagueModel] = None):
        super().__init__(model_type=model_type, use_ensemble=use_ensemble)
        self.league_model = league_model or PooledLeagueModel.load()
        self.feature_names = list(pf.all_feature_names())
        self.probability_calibrator = {
            stat: self.league_model.calibrator_entry(stat)
            for stat in pf.POOLED_STATS
        }
        self.training_metrics = {
            stat: {"mae": self.league_model.stats[stat].train_mae,
                   "n_train": self.league_model.stats[stat].n_train}
            for stat in pf.POOLED_STATS
        }
        # Per-player serve inputs, recomputed from the game log on every entry
        # point that receives one. None until then, and predict() refuses to
        # run rather than inventing a vector.
        self.pooled_inputs: Optional[Dict[str, float]] = None
        self.pooled_dispersion: Optional[Dict[str, float]] = None

    # ── absorbing a player's history ─────────────────────────────────────────

    def _absorb(self, df: pd.DataFrame) -> None:
        """Recompute the served features from a player's completed games.

        Called from every entry point that receives a game log, so no single
        call site can be forgotten. Raises rather than degrading: a pooled
        prediction built from a partly-missing feature vector is exactly the
        silent zero-fill this model was built to remove.
        """
        self.pooled_inputs = pf.serve_features(df)
        self.pooled_dispersion = {
            stat: pf.dispersion(df, stat) for stat in pf.POOLED_STATS
        }
        completed = pf.normalize_game_log(df)
        self.games_trained_on = len(completed)
        if "GAME_DATE" in completed.columns:
            self.last_game_date = completed["GAME_DATE"].iloc[-1]

    def _require_inputs(self) -> Dict[str, float]:
        features = self.pooled_inputs
        if not features:
            raise RuntimeError(
                "pooled predictor has seen no game log — call train(), update() "
                "or _update_recent_averages() with the player's frame before "
                "predict()")
        return features

    # ── MLPredictor interface ────────────────────────────────────────────────

    def train(self, df, stats=None):
        """No per-player fitting happens; the league model is already fitted."""
        self._absorb(df)
        return True

    def update(self, df, stats=None):
        """Refresh the served features from a newer log. Same cost as train."""
        self._absorb(df)
        return True

    def _update_recent_averages(self, df, stats=None):
        super()._update_recent_averages(df, stats=stats)
        self._absorb(df)

    def predict(self, features_df, bias_correction=None, estimated_minutes=None):
        """Point predictions for PTS / REB / AST / PRA.

        ``features_df`` is the 81-column served frame the per-player path
        consumes. The pooled model reads none of it — its inputs come from the
        player's own game log — but the argument is kept so the call site is
        unchanged.
        """
        return self.league_model.predict(self._require_inputs())

    def get_confidence(self, df, stat, prediction, features_df=None):
        std = self._served_sigma(stat)
        confidence = max(POOLED_CONFIDENCE_FLOOR,
                         min(POOLED_CONFIDENCE_CAP, 100.0 - std * 3.0))
        half = INTERVAL_SIGMAS * std
        return {
            "low": round(prediction - half, 1),
            "high": round(prediction + half, 1),
            "confidence": round(confidence, 0),
            "std": round(std, 2),
        }

    def get_prediction_uncertainty(self, features_df, stat):
        std = self._served_sigma(stat)
        return {"mean": None, "std": std,
                "quantile_25": None, "quantile_75": None}

    def save(self, player_name):
        """No-op: the pooled path holds no per-player state worth persisting."""
        logger.debug("pooled model is league-wide; nothing to save for %s",
                     player_name)

    def load(self, player_name):
        """Always False, so the caller falls through to the free ``train``."""
        return False

    def needs_retrain(self):
        """Per-player retraining is meaningless for a league-wide fit."""
        return False

    # ── helpers ──────────────────────────────────────────────────────────────

    def _served_sigma(self, stat: str) -> float:
        dispersions = self.pooled_dispersion
        if not dispersions or stat not in dispersions:
            raise RuntimeError(
                "pooled predictor has seen no game log — cannot size the "
                "uncertainty for {}".format(stat))
        return self.league_model.sigma(stat, dispersions[stat])
