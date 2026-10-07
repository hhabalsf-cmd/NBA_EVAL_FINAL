"""Small candidate set, temporal calibration, and discrete predictive distributions."""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import platform
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from forecasting.features import FEATURES, STATS, SUMMARY_KINDS

VERSION = "forecast-1"
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "models" / "forecast" / "league.pkl"
BASELINES = ("l5", "l10", "l20", "mean", "ewma5", "ewma10", "pooled_ridge")
CANDIDATES = BASELINES + ("ridge", "boost", "minutes_rate")
FLOORS = {"MIN": 3.0, "PTS": 3.0, "REB": 1.2, "AST": 1.0, "PRA": 4.0}


def feature_matrix(frame: pd.DataFrame) -> np.ndarray:
    values = frame.loc[:, list(FEATURES)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Forecast inputs contain non-finite features")
    return values


def booster():
    return HistGradientBoostingRegressor(loss="squared_error", max_iter=150,
                                        max_leaf_nodes=15, min_samples_leaf=100,
                                        learning_rate=0.05, l2_regularization=10,
                                        early_stopping=False, random_state=240924)


@dataclass
class PointModel:
    stat: str
    kind: str
    estimator: object = None
    minute_estimator: object = None

    @classmethod
    def fit(cls, frame: pd.DataFrame, stat: str, kind: str):
        if kind not in CANDIDATES:
            raise ValueError(f"Unknown candidate {kind}")
        obj = cls(stat, kind)
        target = frame[f"{stat}_actual"].to_numpy(float)
        if kind == "pooled_ridge":
            columns = [f"{stat}_{k}" for k in SUMMARY_KINDS if k != "std"]
            obj.estimator = make_pipeline(StandardScaler(), Ridge(alpha=3))
            obj.estimator.fit(frame[columns].to_numpy(float), target)
        elif kind == "ridge":
            obj.estimator = make_pipeline(StandardScaler(), Ridge(alpha=100))
            # Predict a correction to the rolling mean, avoiding identity learning.
            obj.estimator.fit(feature_matrix(frame), target - frame[f"{stat}_l20"].to_numpy())
        elif kind == "boost":
            obj.estimator = booster()
            obj.estimator.fit(feature_matrix(frame), target - frame[f"{stat}_l20"].to_numpy())
        elif kind == "minutes_rate":
            if stat == "MIN":
                raise ValueError("Minutes-rate is a count model")
            x = feature_matrix(frame)
            actual_minutes = frame.MIN_actual.to_numpy(float)
            obj.minute_estimator = booster().fit(x, actual_minutes - frame.MIN_l20.to_numpy())
            obj.estimator = booster().fit(x, target / actual_minutes - frame[f"{stat}_rate20"].to_numpy(),
                                         sample_weight=actual_minutes / 30)
        return obj

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if self.kind == "pooled_ridge":
            columns = [f"{self.stat}_{k}" for k in SUMMARY_KINDS if k != "std"]
            result = self.estimator.predict(frame[columns].to_numpy(float))
        elif self.kind in ("ridge", "boost"):
            result = frame[f"{self.stat}_l20"].to_numpy() + self.estimator.predict(feature_matrix(frame))
        elif self.kind == "minutes_rate":
            x = feature_matrix(frame)
            mins = np.clip(frame.MIN_l20.to_numpy() + self.minute_estimator.predict(x), 0, 48)
            rate = np.maximum(0, frame[f"{self.stat}_rate20"].to_numpy() + self.estimator.predict(x))
            result = mins * rate
        else:
            result = frame[f"{self.stat}_{self.kind}"].to_numpy(float)
        return np.maximum(0, result)


def scale(frame: pd.DataFrame, stat: str) -> np.ndarray:
    # Stabilize short histories without looking at the target game.
    return np.maximum(FLOORS[stat], frame[f"{stat}_std"].to_numpy(float))


@dataclass
class CountDistribution:
    center: float
    scale: float
    residuals: np.ndarray

    def __post_init__(self):
        if not np.isfinite([self.center, self.scale]).all() or self.center < 0 or self.scale <= 0:
            raise ValueError("Distribution center/scale invalid")
        self.residuals = np.asarray(self.residuals, dtype=float)
        if (self.residuals.ndim != 1 or self.residuals.size == 0 or not np.isfinite(self.residuals).all()
                or (np.diff(self.residuals) < 0).any()):
            raise ValueError("Residuals must be finite, sorted, and nonempty")

    def cdf(self, count: int) -> float:
        if count < 0:
            return 0.0
        # Round continuous samples to integer counts, then censor below zero.
        threshold = (count + 0.5 - self.center) / self.scale
        return float(np.searchsorted(self.residuals, threshold, side="left") / len(self.residuals))

    def probabilities(self, line: float) -> dict:
        if not np.isfinite(line) or line < 0:
            raise ValueError("Line must be finite and nonnegative")
        under = self.cdf(int(np.ceil(line)) - 1)
        over = 1 - self.cdf(int(np.floor(line)))
        return {"over": over, "under": under, "push": max(0.0, 1 - under - over)}

    def quantile(self, q: float) -> float:
        if not 0 <= q <= 1:
            raise ValueError("Quantile must be in [0, 1]")
        residual = np.quantile(self.residuals, q, method="inverted_cdf")
        return float(max(0, np.floor(self.center + self.scale * residual + 0.5)))

    def summary(self) -> dict:
        samples = np.maximum(0, np.floor(self.center + self.scale * self.residuals + 0.5))
        return {"prediction": float(self.center), "mean": float(samples.mean()),
                "median": self.quantile(0.5), "range_low": self.quantile(0.1),
                "range_high": self.quantile(0.9), "interval_level": 0.8,
                "uncertainty_std": float(samples.std()),
                "calibration_count": len(samples)}


class ForecastModel:
    def __init__(self, models: dict, residuals: dict, metadata: dict):
        self.models, self.residuals, self.metadata = models, residuals, metadata

    @classmethod
    def fit(cls, training: pd.DataFrame, calibration: pd.DataFrame, selected: dict,
            provenance: dict | None = None):
        if training.empty or calibration.empty:
            raise ValueError("Training and calibration must both contain rows")
        if training.game_date.max() >= calibration.game_date.min():
            raise ValueError("Calibration must be strictly later than all training dates")
        if set(selected) != set(STATS):
            raise ValueError("Select exactly one model for each stat")
        models, residuals = {}, {}
        for stat in STATS:
            models[stat] = PointModel.fit(training, stat, selected[stat])
            errors = (calibration[f"{stat}_actual"].to_numpy() - models[stat].predict(calibration)) / scale(calibration, stat)
            residuals[stat] = np.sort(errors)
        meta = {"version": VERSION, "features": list(FEATURES), "selected": selected,
                "trained_through": str(training.game_date.max().date()),
                "calibrated_through": str(calibration.game_date.max().date()),
                "train_rows": len(training), "calibration_rows": len(calibration),
                "sklearn_version": sklearn.__version__, "python_version": platform.python_version(),
                "conditional_on_participation": True, "betting_validated": False,
                "provenance": provenance or {}}
        return cls(models, residuals, meta)

    def distributions(self, features: dict, game_date) -> dict[str, CountDistribution]:
        if pd.Timestamp(game_date).normalize() <= pd.Timestamp(self.metadata["calibrated_through"]):
            raise ValueError("Forecast date must be after the artifact's training/calibration cutoff")
        frame = pd.DataFrame([features])
        feature_matrix(frame)
        return {stat: CountDistribution(float(model.predict(frame)[0]), float(scale(frame, stat)[0]), self.residuals[stat])
                for stat, model in self.models.items()}

    def save(self, path=DEFAULT_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = pickle.dumps(self, protocol=pickle.HIGHEST_PROTOCOL)
        digest = hashlib.sha256(payload).hexdigest()
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(payload)
        os.replace(temp, path)
        path.with_suffix(".json").write_text(json.dumps({**self.metadata, "sha256": digest}, indent=2), encoding="utf-8")
        return digest

    def validate(self):
        if set(self.models) != set(STATS) or set(self.residuals) != set(STATS):
            raise ValueError('Forecast artifact must contain all four stat models and calibrations')
        selected = self.metadata.get('selected', {})
        if set(selected) != set(STATS):
            raise ValueError('Forecast artifact selection metadata is incomplete')
        for stat in STATS:
            point = self.models[stat]
            if not isinstance(point, PointModel) or point.stat != stat or point.kind != selected[stat] or point.kind not in CANDIDATES:
                raise ValueError('Forecast artifact stat/model identity mismatch')
            CountDistribution(0, 1, self.residuals[stat])
            if len(self.residuals[stat]) != self.metadata.get('calibration_rows'):
                raise ValueError('Forecast artifact calibration count mismatch')
        trained = pd.Timestamp(self.metadata['trained_through'])
        calibrated = pd.Timestamp(self.metadata['calibrated_through'])
        if pd.isna(trained) or pd.isna(calibrated) or trained >= calibrated:
            raise ValueError('Forecast artifact cutoff dates are invalid')

    @classmethod
    def load(cls, path=DEFAULT_PATH):
        path = Path(path)
        payload = path.read_bytes()
        manifest = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if hashlib.sha256(payload).hexdigest() != manifest.get("sha256"):
            raise ValueError("Forecast artifact digest mismatch")
        # WARNING: pickle executes code. Only load artifacts from trusted storage;
        # the adjacent checksum detects corruption, not a malicious publisher.
        try:
            model = pickle.loads(payload)
        except (pickle.UnpicklingError, EOFError, AttributeError, ImportError, TypeError) as exc:
            raise ValueError('Forecast artifact cannot be loaded; restore a trusted artifact or rebuild it') from exc
        if not isinstance(model, cls) or model.metadata.get("version") != VERSION:
            raise ValueError("Incompatible forecast artifact")
        if model.metadata.get("features") != list(FEATURES):
            raise ValueError("Forecast feature schema mismatch")
        if model.metadata.get("sklearn_version") != sklearn.__version__:
            raise ValueError("Retrain the forecast artifact for the installed scikit-learn version")
        try:
            model.validate()
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError('Forecast artifact has incomplete model or calibration metadata') from exc
        if any(manifest.get(key) != value for key, value in model.metadata.items() if key != 'artifact_sha256'):
            raise ValueError('Forecast artifact metadata differs from its manifest')
        model.metadata["artifact_sha256"] = manifest["sha256"]
        return model
