"""Tests for the second-observation capture path that makes CLV possible.

``manual_lines`` holds one mutable row per (game_date, player, stat), so without
a deliberate second observation ``line_snapshots`` collects exactly one row per
line and ``picks.closing_line`` stays NULL forever. These tests cover the pure
aggregation over snapshot rows and the admin endpoints that expose and append
observations.

No database: the DB wrappers are monkeypatched, and the live path is exercised
end to end by hand against the real database (see the Track C report).
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Required before importing the API layer (mirrors tests/test_auth.py).
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-supabase-jwt-secret-that-is-long-enough-32ch")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("FASTAPI_SERVICE_KEY", "test-fastapi-service-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from fastapi import FastAPI                          # noqa: E402
from fastapi.testclient import TestClient            # noqa: E402
from slowapi.errors import RateLimitExceeded         # noqa: E402

import line_snapshots as ls                          # noqa: E402
import tracking_schema as ts                         # noqa: E402
from api.limiter import limiter                      # noqa: E402
from api.routers import bets                         # noqa: E402
from api.routers.auth import require_admin           # noqa: E402

DATE = "2026-08-25"
T0 = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)


def _snap(**over):
    base = {
        "game_date": DATE,
        "player": "LeBron James",
        "stat": "PTS",
        "line": 25.5,
        "source": "manual",
        "captured_at": T0,
    }
    return {**base, **over}


def _summary(**over):
    base = {
        "game_date": DATE,
        "player": "LeBron James",
        "stat": "PTS",
        "observations": 1,
        "first_line": 25.5,
        "last_line": 25.5,
        "first_captured_at": T0,
        "last_captured_at": T0,
    }
    return {**base, **over}


# ── Pure aggregation ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSummarizeSnapshotRows:
    def test_empty_input_returns_empty_list(self):
        assert ls.summarize_snapshot_rows([]) == []

    def test_single_observation_reports_count_one(self):
        [row] = ls.summarize_snapshot_rows([_snap()])
        assert row["observations"] == 1
        assert row["first_line"] == 25.5
        assert row["last_line"] == 25.5
        assert row["first_captured_at"] == T0
        assert row["last_captured_at"] == T0

    def test_two_observations_order_by_captured_at_not_input_order(self):
        later = _snap(line=26.5, captured_at=T0 + timedelta(hours=5))
        [row] = ls.summarize_snapshot_rows([later, _snap()])
        assert row["observations"] == 2
        assert row["first_line"] == 25.5
        assert row["last_line"] == 26.5
        assert row["first_captured_at"] == T0
        assert row["last_captured_at"] == later["captured_at"]

    def test_an_unmoved_line_still_counts_as_two_observations(self):
        # Capturing the same number is a real observation: it records that the
        # line held. It must not be collapsed away.
        later = _snap(captured_at=T0 + timedelta(hours=5))
        [row] = ls.summarize_snapshot_rows([_snap(), later])
        assert row["observations"] == 2
        assert row["first_line"] == row["last_line"] == 25.5

    def test_distinct_keys_stay_separate_and_sort_by_player_then_stat(self):
        rows = ls.summarize_snapshot_rows([
            _snap(player="Stephen Curry", stat="PTS"),
            _snap(player="LeBron James", stat="REB"),
            _snap(player="LeBron James", stat="AST"),
        ])
        assert [(r["player"], r["stat"]) for r in rows] == [
            ("LeBron James", "AST"),
            ("LeBron James", "REB"),
            ("Stephen Curry", "PTS"),
        ]

    def test_player_spelling_variants_group_together(self):
        later = _snap(player="  lebron   james ", captured_at=T0 + timedelta(hours=1))
        rows = ls.summarize_snapshot_rows([_snap(), later])
        assert len(rows) == 1
        assert rows[0]["observations"] == 2

    def test_display_name_comes_from_the_newest_observation(self):
        later = _snap(player="LEBRON JAMES", captured_at=T0 + timedelta(hours=1))
        [row] = ls.summarize_snapshot_rows([_snap(), later])
        assert row["player"] == "LEBRON JAMES"

    def test_numeric_lines_are_coerced_to_float(self):
        [row] = ls.summarize_snapshot_rows([_snap(line=Decimal("25.5"))])
        assert isinstance(row["first_line"], float)
        assert row["first_line"] == 25.5

    def test_game_date_is_normalized_to_a_string(self):
        from datetime import date as date_cls
        [row] = ls.summarize_snapshot_rows([_snap(game_date=date_cls(2026, 8, 25))])
        assert row["game_date"] == DATE

    def test_timestamps_keep_their_timezone(self):
        # The frontend renders "entered 4h ago" from these; a naive UTC value
        # would be parsed as local time and report the wrong staleness.
        [row] = ls.summarize_snapshot_rows([_snap()])
        assert row["last_captured_at"].tzinfo is not None

    def test_input_rows_are_not_mutated(self):
        original = _snap()
        snapshot_of_input = dict(original)
        ls.summarize_snapshot_rows([original])
        assert original == snapshot_of_input

    def test_unparseable_timestamp_raises_rather_than_dropping_the_row(self):
        with pytest.raises(ValueError):
            ls.summarize_snapshot_rows([_snap(captured_at="not-a-time")])


@pytest.mark.unit
class TestKeysMissingNewObservation:
    def test_count_increase_means_nothing_is_missing(self):
        before = [_summary(observations=1)]
        after = [_summary(observations=2)]
        requested = [{"player": "LeBron James", "stat": "PTS"}]
        assert ls.keys_missing_new_observation(before, after, requested, DATE) == []

    def test_first_ever_observation_counts_as_recorded(self):
        after = [_summary(observations=1)]
        requested = [{"player": "LeBron James", "stat": "PTS"}]
        assert ls.keys_missing_new_observation([], after, requested, DATE) == []

    def test_unchanged_count_is_reported_missing(self):
        before = [_summary(observations=1)]
        requested = [{"player": "LeBron James", "stat": "PTS"}]
        missing = ls.keys_missing_new_observation(before, before, requested, DATE)
        assert missing == [{"player": "LeBron James", "stat": "PTS"}]

    def test_absent_from_both_is_reported_missing(self):
        requested = [{"player": "LeBron James", "stat": "PTS"}]
        assert ls.keys_missing_new_observation([], [], requested, DATE) == requested

    def test_matching_ignores_case_and_extra_whitespace(self):
        after = [_summary(observations=1)]
        requested = [{"player": "  lebron   JAMES ", "stat": "pts"}]
        assert ls.keys_missing_new_observation([], after, requested, DATE) == []

    def test_row_game_date_wins_over_the_default(self):
        after = [_summary(observations=1, game_date="2026-08-26")]
        requested = [{"player": "LeBron James", "stat": "PTS",
                      "game_date": "2026-08-26"}]
        assert ls.keys_missing_new_observation([], after, requested, DATE) == []

    def test_reports_only_the_rows_that_failed(self):
        after = [_summary(observations=1)]
        requested = [
            {"player": "LeBron James", "stat": "PTS"},
            {"player": "Stephen Curry", "stat": "AST"},
        ]
        missing = ls.keys_missing_new_observation([], after, requested, DATE)
        assert missing == [{"player": "Stephen Curry", "stat": "AST"}]

    def test_requested_rows_are_not_mutated(self):
        requested = [{"player": "LeBron James", "stat": "PTS"}]
        original = dict(requested[0])
        missing = ls.keys_missing_new_observation([], [], requested, DATE)
        assert requested[0] == original
        missing[0]["player"] = "changed"
        assert requested[0] == original


# ── Endpoints ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_rate_limit():
    """Deterministic tests: per-route limits are exercised elsewhere."""
    was_enabled = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = was_enabled


@pytest.fixture()
def client():
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, lambda r, e: None)
    app.include_router(bets.router)
    app.dependency_overrides[require_admin] = lambda: {"id": "admin-1", "role": "admin"}
    return TestClient(app)


@pytest.fixture()
def fake_db(monkeypatch):
    """A snapshot log and manual-line table that live in memory."""
    state = {"snapshots": [], "lines": [], "upsert_calls": []}

    def _upsert(rows, date_str=None):
        state["upsert_calls"].append((list(rows), date_str))
        for row in rows:
            state["snapshots"].append(_snap(
                game_date=date_str or DATE,
                player=row["player"],
                stat=row["stat"],
                line=row["line"],
                captured_at=T0 + timedelta(minutes=len(state["snapshots"])),
            ))
        return len(rows)

    monkeypatch.setattr(bets.db, "upsert_manual_lines", _upsert)
    monkeypatch.setattr(bets.line_snapshots, "require_snapshot_support", lambda: None)
    monkeypatch.setattr(
        bets.line_snapshots, "get_snapshot_summary",
        lambda date_str=None, **kw: ls.summarize_snapshot_rows(state["snapshots"]),
    )
    return state


@pytest.mark.unit
class TestSnapshotEndpointsAreAdminOnly:
    @pytest.mark.parametrize("path,method", [
        ("/api/bets/lines/snapshots", "GET"),
        ("/api/bets/lines/snapshots", "POST"),
    ])
    def test_route_depends_on_require_admin(self, path, method):
        matches = [r for r in bets.router.routes
                   if getattr(r, "path", None) == path and method in getattr(r, "methods", ())]
        assert matches, f"no {method} route registered at {path}"
        deps = {d.call for d in matches[0].dependant.dependencies}
        assert require_admin in deps


@pytest.mark.unit
class TestGetLineSnapshots:
    def test_empty_log_returns_an_empty_list(self, client, fake_db):
        body = client.get(f"/api/bets/lines/snapshots?date={DATE}").json()
        assert body == {"snapshots": [], "date": DATE}

    def test_returns_one_summary_per_line(self, client, fake_db):
        fake_db["snapshots"].extend([_snap(), _snap(stat="REB", line=7.5)])
        body = client.get(f"/api/bets/lines/snapshots?date={DATE}").json()
        assert [s["stat"] for s in body["snapshots"]] == ["PTS", "REB"]
        assert body["snapshots"][0]["observations"] == 1

    def test_missing_migration_returns_503(self, client, fake_db, monkeypatch):
        def _boom(*_a, **_kw):
            raise ts.MigrationRequiredError("line_snapshots table is missing.")
        monkeypatch.setattr(bets.line_snapshots, "get_snapshot_summary", _boom)
        response = client.get(f"/api/bets/lines/snapshots?date={DATE}")
        assert response.status_code == 503
        assert "line_snapshots" in response.json()["detail"]


@pytest.mark.unit
class TestCaptureLineSnapshots:
    def _post(self, client, line=25.5, player="LeBron James", stat="PTS"):
        return client.post("/api/bets/lines/snapshots", json={
            "game_date": DATE,
            "lines": [{"player": player, "stat": stat, "line": line}],
        })

    def test_capture_appends_a_second_observation(self, client, fake_db):
        fake_db["snapshots"].append(_snap())
        response = self._post(client, line=26.5)
        assert response.status_code == 200
        [summary] = response.json()["snapshots"]
        assert summary["observations"] == 2
        assert summary["first_line"] == 25.5
        assert summary["last_line"] == 26.5

    def test_capture_never_overwrites_the_first_observation(self, client, fake_db):
        fake_db["snapshots"].append(_snap())
        self._post(client, line=26.5)
        assert len(fake_db["snapshots"]) == 2
        assert fake_db["snapshots"][0]["line"] == 25.5

    def test_capturing_an_unmoved_line_is_allowed(self, client, fake_db):
        fake_db["snapshots"].append(_snap())
        response = self._post(client, line=25.5)
        assert response.status_code == 200
        assert response.json()["snapshots"][0]["observations"] == 2

    def test_capture_keeps_the_live_manual_line_current(self, client, fake_db):
        # manual_lines is the fallback line source; a capture that left it stale
        # would make Best Bets run off a number the book no longer offers.
        self._post(client, line=26.5)
        rows, date_str = fake_db["upsert_calls"][-1]
        assert date_str == DATE
        assert rows[0]["line"] == 26.5

    def test_a_snapshot_write_that_did_not_land_is_a_loud_500(self, client, fake_db, monkeypatch):
        # db.upsert_manual_lines appends snapshots best-effort and logs failures
        # without failing the request. Reporting success for a capture that was
        # never recorded is exactly the silence that hid the CLV bug.
        monkeypatch.setattr(bets.db, "upsert_manual_lines", lambda rows, date_str=None: len(rows))
        response = self._post(client)
        assert response.status_code == 500
        assert "LeBron James" in response.json()["detail"]

    def test_missing_migration_returns_503(self, client, fake_db, monkeypatch):
        def _boom():
            raise ts.MigrationRequiredError("line_snapshots table is missing.")
        monkeypatch.setattr(bets.line_snapshots, "require_snapshot_support", _boom)
        response = self._post(client)
        assert response.status_code == 503
        assert fake_db["upsert_calls"] == []

    def test_rejects_a_non_positive_line(self, client, fake_db):
        assert self._post(client, line=0).status_code == 422

    def test_rejects_an_unknown_stat(self, client, fake_db):
        assert self._post(client, stat="STL").status_code == 422

    def test_rejects_an_empty_batch(self, client, fake_db):
        response = client.post("/api/bets/lines/snapshots",
                               json={"game_date": DATE, "lines": []})
        assert response.status_code == 422
