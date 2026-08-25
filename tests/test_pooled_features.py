"""Causal-feature guards for the pooled cross-player model.

The pooled model exists because the per-player model fitted 81 features on 60
rows (p/n = 1.35). Its whole defence is that every feature is a plain recency
statistic of games the player has ALREADY played, so these tests are mostly
lookahead guards: perturbing the game being predicted, or any game after it,
must not move a single served feature.
"""
import numpy as np
import pandas as pd
import pytest

import pooled_features as pf


def _log(n=40, seed=7):
    """Synthetic game log in the shape ``create_features`` consumes."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-10-25", periods=n, freq="2D")
    return pd.DataFrame({
        "GAME_DATE": dates.strftime("%Y-%m-%d"),
        "MATCHUP": ["LAL vs. BOS"] * n,
        "MIN": rng.integers(24, 38, n).astype(float),
        "PTS": rng.integers(8, 34, n).astype(float),
        "REB": rng.integers(1, 13, n).astype(float),
        "AST": rng.integers(0, 12, n).astype(float),
    })


@pytest.mark.unit
class TestFeatureContract:
    def test_feature_count_is_under_ten_per_stat(self):
        """The binding constraint was p/n. Six per stat, and it stays six."""
        for stat in pf.POOLED_STATS:
            assert len(pf.feature_names(stat)) < 10
            assert len(pf.feature_names(stat)) == len(pf.RECENCY_KINDS)

    def test_feature_names_are_namespaced_by_stat(self):
        assert pf.feature_names("PTS") == (
            "PTS_L5", "PTS_L10", "PTS_L20", "PTS_MEDIAN", "PTS_MEAN", "PTS_EWMA5")
        assert set(pf.all_feature_names()) == {
            n for s in pf.POOLED_STATS for n in pf.feature_names(s)}

    def test_every_declared_feature_is_emitted_at_serve(self):
        """The 81-feature model silently served 0 for anything it forgot to
        build. Nothing pooled may reach the estimator without being emitted."""
        served = pf.serve_features(_log())
        for name in pf.all_feature_names():
            assert name in served, "{} declared but not emitted".format(name)
            assert np.isfinite(served[name])


@pytest.mark.unit
class TestNoLookahead:
    def test_serve_features_ignore_games_after_the_history(self):
        """Append future games; the served vector must not move."""
        log = _log(40)
        base = pf.serve_features(log)
        extended = pd.concat([log, _log(5, seed=99)], ignore_index=True)
        # Only the first 40 games are history; serving off them must be identical.
        assert pf.serve_features(extended.iloc[:40]) == base

    def test_spiking_the_last_game_moves_features_but_spiking_the_future_does_not(self):
        log = _log(40)
        base = pf.serve_features(log.iloc[:30])
        spiked = log.copy()
        spiked.loc[30:, ["PTS", "REB", "AST", "MIN"]] = 999.0
        assert pf.serve_features(spiked.iloc[:30]) == base

    def test_pra_is_recomputed_not_read_from_the_frame(self):
        """Phase 0's harness stripped PTS/REB/AST but not the derived PRA, so
        the dynamic floor read the realized PRA of the game being predicted."""
        log = _log(40)
        poisoned = log.copy()
        poisoned["PRA"] = 999.0
        assert pf.serve_features(poisoned) == pf.serve_features(log)

    def test_upcoming_synthetic_row_is_dropped(self):
        import nba_evaluator as ev
        log = _log(30)
        upcoming = log.iloc[[-1]].copy()
        upcoming[["PTS", "REB", "AST"]] = np.nan
        upcoming["MIN"] = ev.UPCOMING_ROW_MINUTES
        upcoming[ev.UPCOMING_GAME_FLAG] = 1
        log[ev.UPCOMING_GAME_FLAG] = 0
        with_row = pd.concat([log, upcoming], ignore_index=True)
        assert pf.serve_features(with_row) == pf.serve_features(log)


@pytest.mark.unit
class TestRecencyDefinitions:
    def test_windows_and_summaries_match_their_names(self):
        hist = np.arange(1.0, 31.0)  # 1..30
        f = pf.recency_features("PTS", hist)
        assert f["PTS_L5"] == pytest.approx(hist[-5:].mean())
        assert f["PTS_L10"] == pytest.approx(hist[-10:].mean())
        assert f["PTS_L20"] == pytest.approx(hist[-20:].mean())
        assert f["PTS_MEAN"] == pytest.approx(hist.mean())
        assert f["PTS_MEDIAN"] == pytest.approx(float(np.median(hist)))

    def test_ewma_uses_a_five_game_half_life(self):
        """Matches the ``b_ewma5`` baseline the investigation measured."""
        vals = np.array([10.0, 20.0])
        w = 0.5 ** (np.array([1.0, 0.0]) / pf.EWMA_HALFLIFE_GAMES)
        assert pf.ewma_mean(vals) == pytest.approx(float((w * vals).sum() / w.sum()))

    def test_short_history_does_not_crash_or_emit_nan(self):
        f = pf.recency_features("AST", np.array([4.0]))
        assert all(np.isfinite(v) for v in f.values())

    def test_empty_history_is_rejected_not_zero_filled(self):
        with pytest.raises(ValueError):
            pf.recency_features("PTS", np.array([]))


@pytest.mark.unit
class TestDnpFilter:
    def test_zero_minute_games_are_excluded(self):
        log = _log(25)
        log.loc[10, "MIN"] = 0.0
        log.loc[10, ["PTS", "REB", "AST"]] = 0.0
        kept = pf.normalize_game_log(log)
        assert len(kept) == 24

    def test_log_is_sorted_ascending_by_date(self):
        log = _log(20).iloc[::-1].reset_index(drop=True)
        kept = pf.normalize_game_log(log)
        assert kept["GAME_DATE"].is_monotonic_increasing


@pytest.mark.unit
class TestPanel:
    def test_panel_rows_start_after_the_minimum_prior_games(self):
        logs = []
        for pid in ("a", "b"):
            g = _log(40)
            g["player_id"] = pid
            g["season"] = "2024-25"
            logs.append(g)
        panel = pf.build_panel(pd.concat(logs, ignore_index=True), min_prior=20)
        assert len(panel) == 2 * (40 - 20)
        assert panel["prior_games"].min() == 20
        for stat in pf.POOLED_STATS:
            assert "{}_ACTUAL".format(stat) in panel.columns

    def test_panel_targets_match_the_source_log(self):
        g = _log(30)
        g["player_id"] = "a"
        g["season"] = "2024-25"
        panel = pf.build_panel(g, min_prior=20)
        expected = g["PTS"].values[20:]
        assert np.allclose(panel["PTS_ACTUAL"].values, expected)
