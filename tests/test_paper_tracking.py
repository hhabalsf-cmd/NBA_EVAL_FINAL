"""Tests for the forward-measurement modules.

Covers the pure logic across tracking_schema (normalizers), line_snapshots
(closing-line planning) and paper_tracking (paper-pick validation). No database:
the thin DB wrappers are exercised by scripts/ against the live database.
"""
from datetime import date, datetime, timezone

import pytest

import line_snapshots as ls
import paper_tracking as pt
import tracking_schema as ts


def _pick(**over):
    base = {
        "id": 1,
        "player": "LeBron James",
        "stat": "PTS",
        "game_date": "2026-08-24",
        "direction": "OVER",
        "line": 25.5,
        "opening_line": 25.5,
        "timestamp": "2026-08-24T12:00:00",
        "closing_line": None,
    }
    return {**base, **over}


def _snap(**over):
    base = {
        "game_date": "2026-08-24",
        "player": "LeBron James",
        "stat": "PTS",
        "line": 26.5,
        "captured_at": datetime(2026, 8, 24, 23, 0, 0),
    }
    return {**base, **over}


@pytest.mark.unit
class TestNormalizeHelpers:
    def test_game_date_accepts_date_object(self):
        assert ts.norm_date(date(2026, 8, 24)) == "2026-08-24"

    def test_game_date_accepts_string_with_time(self):
        assert ts.norm_date("2026-08-24T00:00:00") == "2026-08-24"

    def test_game_date_none(self):
        assert ts.norm_date(None) is None

    def test_player_key_is_case_and_space_insensitive(self):
        assert ts.norm_player("  LeBron   James ") == ts.norm_player("lebron james")

    def test_utc_naive_strips_tzinfo(self):
        aware = datetime(2026, 8, 24, 23, 0, tzinfo=timezone.utc)
        assert ts.to_utc_naive(aware) == datetime(2026, 8, 24, 23, 0)

    def test_utc_naive_parses_iso_string(self):
        assert ts.to_utc_naive("2026-08-24T12:00:00") == datetime(2026, 8, 24, 12, 0)

    def test_utc_naive_rejects_garbage(self):
        with pytest.raises(ValueError):
            ts.to_utc_naive("not-a-time")


@pytest.mark.unit
class TestPlanClosingLineUpdates:
    def test_records_later_snapshot(self):
        updates, skipped = ls._plan_closing_line_updates([_pick()], [_snap()])
        assert skipped == []
        assert len(updates) == 1
        assert updates[0]["pick_id"] == 1
        assert updates[0]["closing_line"] == 26.5
        assert updates[0]["clv"] == pytest.approx(1.0)

    def test_never_overwrites_existing_closing_line(self):
        updates, skipped = ls._plan_closing_line_updates(
            [_pick(closing_line=27.0)], [_snap()]
        )
        assert updates == []
        assert skipped[0]["reason"] == ls.SKIP_ALREADY_RECORDED

    def test_ignores_snapshot_taken_before_the_pick(self):
        # A snapshot older than the pick is the same observation we bet into --
        # recording it would manufacture a fake CLV of 0.0.
        stale = _snap(captured_at=datetime(2026, 8, 24, 9, 0, 0))
        updates, skipped = ls._plan_closing_line_updates([_pick()], [stale])
        assert updates == []
        assert skipped[0]["reason"] == ls.SKIP_NO_LATER_SNAPSHOT

    def test_ignores_snapshot_equal_to_pick_time(self):
        same = _snap(captured_at=datetime(2026, 8, 24, 12, 0, 0))
        updates, skipped = ls._plan_closing_line_updates([_pick()], [same])
        assert updates == []
        assert skipped[0]["reason"] == ls.SKIP_NO_LATER_SNAPSHOT

    def test_picks_the_latest_of_several_snapshots(self):
        snaps = [
            _snap(line=26.0, captured_at=datetime(2026, 8, 24, 18, 0)),
            _snap(line=27.5, captured_at=datetime(2026, 8, 24, 22, 0)),
            _snap(line=26.5, captured_at=datetime(2026, 8, 24, 20, 0)),
        ]
        updates, _ = ls._plan_closing_line_updates([_pick()], snaps)
        assert updates[0]["closing_line"] == 27.5

    def test_no_snapshot_at_all(self):
        updates, skipped = ls._plan_closing_line_updates([_pick()], [])
        assert updates == []
        assert skipped[0]["reason"] == ls.SKIP_NO_SNAPSHOT

    def test_matches_player_case_insensitively(self):
        updates, _ = ls._plan_closing_line_updates(
            [_pick(player="lebron  james")], [_snap()]
        )
        assert len(updates) == 1

    def test_does_not_match_a_different_stat(self):
        updates, skipped = ls._plan_closing_line_updates(
            [_pick(stat="REB")], [_snap(stat="PTS")]
        )
        assert updates == []
        assert skipped[0]["reason"] == ls.SKIP_NO_SNAPSHOT

    def test_does_not_match_a_different_game_date(self):
        updates, skipped = ls._plan_closing_line_updates(
            [_pick()], [_snap(game_date="2026-08-25")]
        )
        assert skipped[0]["reason"] == ls.SKIP_NO_SNAPSHOT

    def test_under_direction_clv_sign(self):
        updates, _ = ls._plan_closing_line_updates(
            [_pick(direction="UNDER")], [_snap(line=24.5)]
        )
        assert updates[0]["clv"] == pytest.approx(1.0)

    def test_uses_opening_line_when_present(self):
        updates, _ = ls._plan_closing_line_updates(
            [_pick(line=99.0, opening_line=25.5)], [_snap()]
        )
        assert updates[0]["clv"] == pytest.approx(1.0)

    def test_falls_back_to_line_when_opening_missing(self):
        updates, _ = ls._plan_closing_line_updates(
            [_pick(opening_line=None, line=25.5)], [_snap()]
        )
        assert updates[0]["clv"] == pytest.approx(1.0)

    def test_skips_pick_with_no_usable_entry_line(self):
        updates, skipped = ls._plan_closing_line_updates(
            [_pick(opening_line=None, line=None)], [_snap()]
        )
        assert updates == []
        assert skipped[0]["reason"] == ls.SKIP_NO_ENTRY_LINE

    def test_result_does_not_mutate_inputs(self):
        pick = _pick()
        snapshot = _snap()
        ls._plan_closing_line_updates([pick], [snapshot])
        assert pick["closing_line"] is None
        assert snapshot["line"] == 26.5


@pytest.mark.unit
class TestValidatePaperPick:
    def _valid(self, **over):
        base = {
            "player": "LeBron James",
            "stat": "PTS",
            "line": 25.5,
            "prediction": 28.1,
            "direction": "OVER",
            "game_date": "2026-08-24",
        }
        return {**base, **over}

    def test_returns_new_dict_and_does_not_mutate(self):
        raw = self._valid()
        out = pt._validate_paper_pick(raw)
        assert out is not raw
        assert "is_paper" not in raw

    def test_flags_as_paper_and_clears_user(self):
        out = pt._validate_paper_pick(self._valid())
        assert out["is_paper"] == 1
        assert out["user_id"] is None

    def test_opening_line_defaults_to_line(self):
        out = pt._validate_paper_pick(self._valid())
        assert out["opening_line"] == 25.5

    def test_normalizes_stat_and_direction_case(self):
        out = pt._validate_paper_pick(self._valid(stat="pts", direction="over"))
        assert out["stat"] == "PTS"
        assert out["direction"] == "OVER"

    def test_rejects_missing_player(self):
        with pytest.raises(ValueError, match="player"):
            pt._validate_paper_pick(self._valid(player="  "))

    def test_rejects_bad_stat(self):
        with pytest.raises(ValueError, match="stat"):
            pt._validate_paper_pick(self._valid(stat="BLK"))

    def test_rejects_bad_direction(self):
        with pytest.raises(ValueError, match="direction"):
            pt._validate_paper_pick(self._valid(direction="SIDEWAYS"))

    def test_rejects_non_positive_line(self):
        with pytest.raises(ValueError, match="line"):
            pt._validate_paper_pick(self._valid(line=0))

    def test_rejects_bad_game_date(self):
        with pytest.raises(ValueError, match="game_date"):
            pt._validate_paper_pick(self._valid(game_date="24/08/2026"))

    def test_requires_game_date(self):
        with pytest.raises(ValueError, match="game_date"):
            pt._validate_paper_pick(self._valid(game_date=None))
