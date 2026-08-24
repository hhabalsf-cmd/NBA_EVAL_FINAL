"""Phase 1: the backtest harness must exercise production's serve path.

Before this phase ``scripts/backtest_unbiased.py`` read the feature row of the
game being predicted directly out of a full-log frame. That row already carries
the correct lag-1 values, so the harness never reproduced -- and could not
measure -- the one-game staleness production served. It also never called
``get_prediction_features`` at all, leaving the entire serve path unmeasured.

The replay now truncates the raw log to games played strictly before the test
game, appends a synthetic row built from that game's schedule facts alone, and
serves through ``get_prediction_features``. These tests pin the two properties
that make that safe: no future data reaches the served vector, and the
``--stale-serve`` mode differs from the default in nothing but which row is
read.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import nba_evaluator as ev  # noqa: E402
import backtest_unbiased as bt  # noqa: E402

TEAM_STATS = {
    "BOS": {"def_rating": 108.0, "pace": 98.0, "opp_ast": 24.0, "off_rating": 115.0,
            "net_rating": 7.0, "efg_pct": 0.55, "tov_pct": 12.0,
            "oreb_pct": 0.28, "dreb_pct": 0.74},
    "OKC": {"def_rating": 104.0, "pace": 101.0, "opp_ast": 22.0, "off_rating": 118.0,
            "net_rating": 14.0, "efg_pct": 0.56, "tov_pct": 11.0,
            "oreb_pct": 0.30, "dreb_pct": 0.76},
    "MIA": {"def_rating": 113.0, "pace": 96.0, "opp_ast": 27.0, "off_rating": 111.0,
            "net_rating": -2.0, "efg_pct": 0.52, "tov_pct": 14.5,
            "oreb_pct": 0.25, "dreb_pct": 0.71},
}
OPPONENTS = ("BOS", "OKC", "MIA")


def _log(n=40, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-10-25", periods=n, freq="2D")
    rows = []
    for i, d in enumerate(dates):
        opp = OPPONENTS[i % len(OPPONENTS)]
        fga = int(rng.integers(12, 24))
        fgm = int(rng.binomial(fga, 0.48))
        fg3a = int(rng.integers(4, 11))
        fg3m = int(rng.binomial(fg3a, 0.37))
        fta = int(rng.integers(2, 9))
        ftm = int(rng.binomial(fta, 0.8))
        oreb, dreb = int(rng.integers(0, 4)), int(rng.integers(3, 9))
        mins = float(rng.uniform(28, 38))
        rows.append({
            "SEASON_ID": "22024", "Game_ID": "002240{:04d}".format(i),
            "GAME_DATE": d.strftime("%Y-%m-%d"),
            "MATCHUP": "LAL vs. {}".format(opp) if i % 2 else "LAL @ {}".format(opp),
            "WL": "W", "MIN": mins,
            "PTS": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
            "REB": oreb + dreb, "AST": int(rng.integers(3, 12)),
            "FGM": fgm, "FGA": fga, "FG_PCT": fgm / fga,
            "FG3M": fg3m, "FG3A": fg3a, "FTM": ftm, "FTA": fta,
            "OREB": oreb, "DREB": dreb,
            "STL": int(rng.integers(0, 4)), "BLK": int(rng.integers(0, 3)),
            "TOV": int(rng.integers(0, 6)), "PF": int(rng.integers(0, 5)),
            "PLUS_MINUS": int(rng.integers(-15, 16)),
        })
    return pd.DataFrame(rows)


def _build_serve(history_log, target_row, _as_of=None):
    team = str(target_row["MATCHUP"]).split(" ")[0]
    frame = ev.FeatureEngineer.create_features(
        history_log,
        game_info=bt.schedule_game_info(target_row, team),
        team_stats=TEAM_STATS,
    )
    return frame, TEAM_STATS


@pytest.fixture(scope="module")
def replay():
    """(log, played labels, step, serve frame, history, served vector)."""
    log = _log().reset_index(drop=True)
    probe = ev.FeatureEngineer.create_features(log, team_stats=TEAM_STATS)
    played = list(probe.index)
    step = 30
    frame, stats = _build_serve(log.loc[played[:step]], log.loc[played[step]])
    history = frame.iloc[:-1]
    served = bt.serve_features(frame, bt.game_context(frame), stats, history)
    return log, played, step, frame, history, served


class TestHarnessUsesTheProductionServePath:
    def test_serves_through_get_prediction_features(self, replay):
        _, _, _, _, _, served = replay
        assert len(served) == 1
        missing = [f for f in ev.MLPredictor.FEATURE_COLS if f not in served.columns]
        assert not missing, f"declared but never served: {missing}"

    def test_frame_ends_in_the_synthetic_next_game_row(self, replay):
        _, _, step, frame, history, _ = replay
        assert ev.has_upcoming_row(frame)
        assert len(frame) == step + 1
        assert len(history) == step
        assert pd.to_datetime(history["GAME_DATE"]).max() < pd.to_datetime(
            frame["GAME_DATE"].iloc[-1]
        )

    def test_no_realized_outcome_on_the_served_row(self, replay):
        _, _, _, frame, _, _ = replay
        for stat in ("PTS", "REB", "AST"):
            assert pd.isna(frame[stat].iloc[-1])

    def test_served_rolling_values_are_the_last_k_completed_games(self, replay):
        log, played, step, _, _, served = replay
        hist = log.loc[played[:step]]
        assert served["ROLL_5_PTS"].iloc[0] == pytest.approx(hist["PTS"].tail(5).mean())
        assert served["ROLL_10_AST"].iloc[0] == pytest.approx(hist["AST"].tail(10).mean())


class TestNoFutureDataReachesTheServedVector:
    def test_rewriting_the_future_changes_nothing(self, replay):
        """The runtime guard, as a unit test: every realized number from the
        target game and every game after it is replaced, and the served vector
        must not move by a single float."""
        log, played, step, _, _, served = replay
        problem = bt.lookahead_probe(
            log, played, step, None, _build_serve, served
        )
        assert problem is None, problem

    def test_the_probe_is_not_vacuous(self, replay):
        """Feed it a served vector built from the FULL log and it must object --
        otherwise a real leak would slip through unnoticed."""
        log, played, step, _, _, _ = replay
        leaky_frame = ev.FeatureEngineer.create_features(log, team_stats=TEAM_STATS)
        leaky_history = leaky_frame.iloc[:step]
        leaky_served = bt.serve_features(
            leaky_frame, bt.game_context(leaky_frame), TEAM_STATS, leaky_history
        )
        assert bt.lookahead_probe(
            log, played, step, None, _build_serve, leaky_served
        ) is not None

    def test_head_to_head_is_scoped_to_history(self, replay):
        """scraper.get_vs_team_stats reads the FULL multi-season log and would
        pull the rest of the season into every replay step."""
        log, played, step, _, history, _ = replay
        opponent = "OKC"
        scoped = bt.history_vs_stats(history, opponent)
        full = bt.history_vs_stats(
            ev.FeatureEngineer.create_features(log, team_stats=TEAM_STATS), opponent
        )
        assert scoped["games"] < full["games"]
        expected = log.loc[played[:step]]
        expected = expected[expected["MATCHUP"].str.contains(opponent)]
        assert scoped["games"] == len(expected)
        assert scoped["avg_pts"] == pytest.approx(expected["PTS"].mean())

    def test_schedule_context_carries_no_box_score(self, replay):
        log, played, step, _, _, _ = replay
        info = bt.schedule_game_info(log.loc[played[step]], "LAL")
        assert set(info) == {"matchup", "game_date", "is_home", "opponent", "team"}


class TestStaleServeMode:
    def test_stale_mode_reproduces_the_pre_phase1_frame_exactly(self, replay):
        """create_features(history) is bit-identical to the synthetic-row frame
        minus its last row -- which is what makes --stale-serve an exact
        reproduction of the old serve path rather than an approximation."""
        log, played, step, frame, _, _ = replay
        standalone = ev.FeatureEngineer.create_features(
            log.loc[played[:step]], team_stats=TEAM_STATS
        )
        prefix = frame.iloc[:-1]
        assert list(prefix.columns) == list(standalone.columns)
        numeric = [c for c in standalone.columns
                   if pd.api.types.is_numeric_dtype(standalone[c])]
        for col in numeric:
            np.testing.assert_allclose(
                prefix[col].astype(float).values,
                standalone[col].astype(float).values,
                equal_nan=True, err_msg=col,
            )

    def test_stale_mode_serves_the_one_game_stale_value(self, replay):
        log, played, step, frame, history, served = replay
        stale = bt.serve_features(
            frame.iloc[:-1], bt.game_context(frame), TEAM_STATS, history
        )
        hist = log.loc[played[:step]]
        assert stale["ROLL_5_PTS"].iloc[0] == pytest.approx(
            hist["PTS"].iloc[-6:-1].mean()
        )
        assert served["ROLL_5_PTS"].iloc[0] == pytest.approx(hist["PTS"].tail(5).mean())

    def test_schedule_context_is_identical_in_both_modes(self, replay):
        """So the stale/fresh delta isolates feature staleness and nothing else."""
        _, _, _, frame, history, served = replay
        ctx = bt.game_context(frame)
        stale = bt.serve_features(frame.iloc[:-1], ctx, TEAM_STATS, history)
        for col in ("IS_HOME", "DAYS_REST", "B2B", "GAMES_IN_LAST_7",
                    "TRAVEL_MILES_NORM", "TIMEZONE_SHIFT",
                    "OPP_DEF_RATING_NORM", "OPP_PACE_NORM",
                    "VS_OPP_AVG_PTS", "VS_OPP_GAMES"):
            assert stale[col].iloc[0] == pytest.approx(served[col].iloc[0]), col

    def test_stale_mode_moves_the_rolling_features(self, replay):
        _, _, _, frame, history, served = replay
        stale = bt.serve_features(
            frame.iloc[:-1], bt.game_context(frame), TEAM_STATS, history
        )
        moved = [
            c for c in ev.MLPredictor.FEATURE_COLS
            if c in served.columns
            and not np.isclose(float(served[c].iloc[0]), float(stale[c].iloc[0]),
                               equal_nan=True)
        ]
        assert len(moved) >= 40, f"only {len(moved)} features differ"
