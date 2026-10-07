"""Shared model selection for interactive predictions and scheduled picks."""
from api.config import pooled_model_enabled


def build_predictor(ev, model_type="gradient_boost", use_ensemble=False):
    if pooled_model_enabled():
        from pooled_predictor import PooledPredictor
        # Fail loudly if the artifact is unavailable; never downgrade silently.
        return PooledPredictor()
    return ev.MLPredictor(model_type=model_type, use_ensemble=use_ensemble)
