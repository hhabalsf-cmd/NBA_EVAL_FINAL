"""Line-anchored NBA player prop predictor.

Predicts the *residual* from the betting line rather than raw stat values.
The line already encodes ~80-90% of the information (season averages, opponent,
venue). This model only needs to find the remaining signal, which is a much
easier learning problem for 50-80 game datasets.

Architecture:
  - Target: actual_stat - proxy_line (ROLL_15 as training proxy for line)
  - Features: 12 carefully chosen from FeatureEngineer output
  - Model: ElasticNetCV (L1+L2 regularization, built-in feature selection)
  - Probability: Normal CDF on predicted residual / OOF residual std
"""

import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.linear_model import ElasticNet, ElasticNetCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

import model_storage

logger = logging.getLogger(__name__)

MODEL_DIR = Path("./models/line_anchored")
MIN_GAMES = 25
PROB_FLOOR = 20.0
PROB_CEIL = 80.0
MAX_RESIDUAL_PCT = 0.20  # clip residual to ±20% of line

# Features shared across all stats (9 common)
_COMMON_FEATURES = [
    "IS_HOME",
    "DAYS_REST",
    "B2B",
    "OPP_DEF_RATING_NORM",
    "OPP_PACE_NORM",
    "OPP_NET_RATING_NORM",
    "ROLL_5_MIN_NUMERIC",
    "MIN_TREND",
    "INJURIES_OPP",
]

# Per-stat: common + recent_form (computed) + volatility + shooting context
_STAT_FEATURES = {
    "PTS": _COMMON_FEATURES + ["recent_form", "STD_10_PTS", "FT_RATE"],
    "REB": _COMMON_FEATURES + ["recent_form", "STD_10_REB", "OREB_RATE"],
    "AST": _COMMON_FEATURES + ["recent_form", "STD_10_AST", "FG3_RATE"],
    "PRA": _COMMON_FEATURES + ["recent_form", "STD_10_PTS", "FT_RATE"],
}

STATS = ["PTS", "REB", "AST", "PRA"]


class LineAnchoredPredictor:
    """Predicts residual from betting line using ElasticNetCV."""

    VERSION = "1.0"

    def __init__(self):
        self.models = {}       # stat -> ElasticNet
        self.scalers = {}      # stat -> StandardScaler
        self.residual_stds = {}  # stat -> float
        self.feature_names = {}  # stat -> list[str]
        self.games_trained_on = 0
        self.training_metrics = {}  # stat -> dict

    # ── Feature extraction ───────────────────────────────────────────────

    @staticmethod
    def _compute_recent_form(df: pd.DataFrame, stat: str) -> pd.Series:
        """Hot/cold relative to 15-game baseline: (EMA5 - ROLL15) / (ROLL15 + 0.1)."""
        ema_col = f"EMA_5_{stat}"
        roll_col = f"ROLL_15_{stat}"
        if stat == "PRA":
            # PRA uses PTS EMA and PRA ROLL_15
            ema_col = "EMA_5_PRA"
            roll_col = "ROLL_15_PRA"
        ema = df[ema_col] if ema_col in df.columns else pd.Series(0, index=df.index)
        roll = df[roll_col] if roll_col in df.columns else pd.Series(0, index=df.index)
        return (ema - roll) / (roll.abs() + 0.1)

    @staticmethod
    def _extract_features(
        df: pd.DataFrame,
        stat: str,
        injuries_opp: int = 0,
    ) -> pd.DataFrame:
        """Extract the 12-feature matrix from an already-engineered DataFrame.

        Args:
            df: Output of FeatureEngineer.create_features()
            stat: One of PTS, REB, AST, PRA
            injuries_opp: Opponent injury count (used at prediction time)

        Returns:
            DataFrame with 12 columns, same row count as input df.
        """
        feature_names = _STAT_FEATURES[stat]
        out = pd.DataFrame(index=df.index)

        for feat in feature_names:
            if feat == "recent_form":
                out["recent_form"] = LineAnchoredPredictor._compute_recent_form(df, stat)
            elif feat == "INJURIES_OPP":
                out["INJURIES_OPP"] = injuries_opp
            elif feat == "DAYS_REST":
                out["DAYS_REST"] = df["DAYS_REST"].clip(upper=4) if "DAYS_REST" in df.columns else 2
            elif feat in df.columns:
                out[feat] = df[feat]
            else:
                out[feat] = 0

        return out.fillna(0)

    # ── Training ─────────────────────────────────────────────────────────

    def _proxy_line(self, df: pd.DataFrame, stat: str) -> pd.Series:
        """ROLL_15 as training proxy for 'what the line would have been'."""
        col = f"ROLL_15_{stat}"
        if col in df.columns:
            return df[col]
        # Fallback for PRA if ROLL_15_PRA not present
        if stat == "PRA":
            return (
                df.get("ROLL_15_PTS", pd.Series(0, index=df.index))
                + df.get("ROLL_15_REB", pd.Series(0, index=df.index))
                + df.get("ROLL_15_AST", pd.Series(0, index=df.index))
            )
        return pd.Series(np.nan, index=df.index)

    def train(self, df: pd.DataFrame, stat: str) -> Optional[dict]:
        """Train line-anchored model for a single stat.

        Returns dict with metrics, or None if insufficient data.
        """
        proxy = self._proxy_line(df, stat)
        valid_mask = proxy.notna() & df[stat if stat != "PRA" else "PTS"].notna()

        if stat == "PRA" and "PRA" not in df.columns:
            df = df.copy()
            df["PRA"] = df["PTS"] + df["REB"] + df["AST"]

        target_col = stat
        y_full = df[target_col] - proxy
        valid_mask = valid_mask & y_full.notna()

        df_valid = df[valid_mask].copy()
        y = y_full[valid_mask].values

        if len(df_valid) < MIN_GAMES:
            logger.info(
                "  %s: only %d valid games (need %d) — skipping",
                stat, len(df_valid), MIN_GAMES,
            )
            return None

        X_df = self._extract_features(df_valid, stat)
        feature_list = list(X_df.columns)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_df.values)

        # ElasticNetCV: automatic alpha + l1_ratio selection via TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=5)
        model = ElasticNetCV(
            l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9],
            alphas=np.logspace(-3, 1, 50),
            cv=tscv,
            max_iter=5000,
            tol=1e-4,
            random_state=42,
        )
        model.fit(X_scaled, y)

        # Compute OOF residual std for probability calibration
        oof_residuals = []
        for train_idx, val_idx in tscv.split(X_scaled):
            fold_model = ElasticNet(
                alpha=model.alpha_, l1_ratio=model.l1_ratio_,
                max_iter=5000, random_state=42,
            )
            fold_model.fit(X_scaled[train_idx], y[train_idx])
            fold_preds = fold_model.predict(X_scaled[val_idx])
            oof_residuals.extend(y[val_idx] - fold_preds)

        residual_std = float(np.std(oof_residuals)) if oof_residuals else 5.0
        # Floor to prevent overconfident probs on tiny std
        residual_std = max(residual_std, 1.0)

        # CV MAE from OOF
        cv_mae = float(np.mean(np.abs(oof_residuals))) if oof_residuals else 0

        self.models[stat] = model
        self.scalers[stat] = scaler
        self.residual_stds[stat] = residual_std
        self.feature_names[stat] = feature_list
        self.games_trained_on = len(df_valid)

        metrics = {
            "cv_mae": cv_mae,
            "residual_std": residual_std,
            "n_games": len(df_valid),
            "alpha": float(model.alpha_),
            "l1_ratio": float(model.l1_ratio_),
            "n_nonzero_coefs": int(np.sum(model.coef_ != 0)),
        }
        self.training_metrics[stat] = metrics

        logger.info(
            "  %s: CV MAE=%.2f, residual_std=%.2f, alpha=%.4f, l1=%.1f, "
            "coefs=%d/%d, n=%d",
            stat, cv_mae, residual_std, model.alpha_, model.l1_ratio_,
            metrics["n_nonzero_coefs"], len(feature_list), len(df_valid),
        )
        return metrics

    def train_all(self, df: pd.DataFrame) -> dict[str, dict]:
        """Train models for all stats. Returns metrics dict."""
        all_metrics = {}
        for stat in STATS:
            result = self.train(df, stat)
            if result is not None:
                all_metrics[stat] = result
        return all_metrics

    # ── Prediction ───────────────────────────────────────────────────────

    def predict(
        self,
        features_row: pd.DataFrame,
        stat: str,
        betting_line: float,
    ) -> Optional[dict]:
        """Predict using line-anchored model.

        Args:
            features_row: Single-row DataFrame of 12 features
            stat: Target stat (PTS, REB, AST, PRA)
            betting_line: The BDL prop line

        Returns:
            Dict with prediction, residual, prob_over, edge_pct, residual_std.
            None if model not available for this stat.
        """
        if stat not in self.models:
            return None

        model = self.models[stat]
        scaler = self.scalers[stat]
        residual_std = self.residual_stds[stat]

        X = scaler.transform(features_row.values)
        raw_residual = float(model.predict(X)[0])

        # Clip residual to ±20% of line
        max_dev = MAX_RESIDUAL_PCT * betting_line
        residual = float(np.clip(raw_residual, -max_dev, max_dev))

        prediction = round(betting_line + residual, 1)

        # Probability: P(actual > line) using normal CDF
        # residual = E[actual - line], so P(actual > line) = P(Z > -residual/std)
        z = -residual / (residual_std + 0.1)
        raw_prob_over = float(1 - scipy_stats.norm.cdf(z)) * 100
        prob_over = max(PROB_FLOOR, min(PROB_CEIL, raw_prob_over))

        edge_pct = round(residual / betting_line * 100, 1) if betting_line > 0 else 0

        return {
            "prediction": prediction,
            "residual": round(residual, 2),
            "prob_over": round(prob_over, 1),
            "edge_pct": edge_pct,
            "residual_std": round(residual_std, 2),
        }

    # ── Persistence ──────────────────────────────────────────────────────

    def save(self, player_name: str) -> None:
        """Save model to disk and upload to Supabase."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        filename = MODEL_DIR / f"{player_name.replace(' ', '_')}_line_model.pkl"

        data = {
            "models": self.models,
            "scalers": self.scalers,
            "residual_stds": self.residual_stds,
            "feature_names": self.feature_names,
            "version": self.VERSION,
            "trained_at": datetime.now().strftime("%Y-%m-%d"),
            "games_trained_on": self.games_trained_on,
            "training_metrics": self.training_metrics,
        }
        with open(filename, "wb") as f:
            pickle.dump(data, f)

        logger.debug("Saved line model to %s", filename)

        # Upload to Supabase in background (non-blocking)
        try:
            model_storage.upload_line_model(player_name, filename)
        except Exception as exc:
            logger.debug("Supabase upload skipped for line:%s: %s", player_name, exc)

    def load(self, player_name: str) -> bool:
        """Load model from disk or Supabase. Returns True if successful."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        filename = MODEL_DIR / f"{player_name.replace(' ', '_')}_line_model.pkl"

        # L1: local disk
        if filename.exists():
            return self._load_from_file(filename)

        # L2: Supabase
        try:
            if model_storage.download_line_model(player_name, filename):
                return self._load_from_file(filename)
        except Exception:
            pass

        return False

    def _load_from_file(self, path: Path) -> bool:
        """Load pickle and populate instance attributes."""
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.models = data.get("models", {})
            self.scalers = data.get("scalers", {})
            self.residual_stds = data.get("residual_stds", {})
            self.feature_names = data.get("feature_names", {})
            self.games_trained_on = data.get("games_trained_on", 0)
            self.training_metrics = data.get("training_metrics", {})
            return bool(self.models)
        except Exception as exc:
            logger.warning("Failed to load line model from %s: %s", path, exc)
            return False

    def has_stat(self, stat: str) -> bool:
        """Check if a model is available for the given stat."""
        return stat in self.models
