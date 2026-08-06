"""Tests for season_utils ET date helpers at frozen instants.

The core invariant: an evening in the US (7 PM ET onward) is already
"tomorrow" in UTC. Every game-date read/write must resolve to the ET date,
and the grading crons (05:3x UTC) must land past ET midnight year-round.
"""
from datetime import date, datetime, timezone

import pytest

import season_utils
from season_utils import ET, get_current_season, today_et, today_et_str


class _FrozenDatetime:
    """Stand-in for season_utils.datetime with a fixed 'now'."""

    def __init__(self, utc_now: datetime):
        self._utc_now = utc_now

    def now(self, tz=None):
        return self._utc_now.astimezone(tz) if tz else self._utc_now.replace(tzinfo=None)


def _freeze(monkeypatch, utc_now: datetime):
    monkeypatch.setattr(season_utils, "datetime", _FrozenDatetime(utc_now))


@pytest.mark.unit
class TestTodayEt:
    def test_winter_evening_is_still_yesterday_et(self, monkeypatch):
        # Jan 16 04:30 UTC == Jan 15 11:30 PM EST — the old UTC code said Jan 16
        _freeze(monkeypatch, datetime(2027, 1, 16, 4, 30, tzinfo=timezone.utc))
        assert today_et() == date(2027, 1, 15)

    def test_winter_past_et_midnight(self, monkeypatch):
        # Jan 16 05:01 UTC == Jan 16 12:01 AM EST — new day in ET
        _freeze(monkeypatch, datetime(2027, 1, 16, 5, 1, tzinfo=timezone.utc))
        assert today_et() == date(2027, 1, 16)

    def test_summer_evening_is_still_yesterday_et(self, monkeypatch):
        # Jul 7 03:59 UTC == Jul 6 11:59 PM EDT
        _freeze(monkeypatch, datetime(2026, 7, 7, 3, 59, tzinfo=timezone.utc))
        assert today_et() == date(2026, 7, 6)

    def test_summer_past_et_midnight(self, monkeypatch):
        # Jul 7 04:01 UTC == Jul 7 12:01 AM EDT
        _freeze(monkeypatch, datetime(2026, 7, 7, 4, 1, tzinfo=timezone.utc))
        assert today_et() == date(2026, 7, 7)

    def test_str_matches_date(self, monkeypatch):
        _freeze(monkeypatch, datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc))
        assert today_et_str() == today_et().isoformat()


@pytest.mark.unit
class TestGradingCronInstant:
    """The 05:30 UTC grading run must see the finished slate as 'yesterday'."""

    def test_grading_gate_passes_after_shifted_cron(self, monkeypatch):
        # Cron fires 05:30 UTC on Jan 16; the slate played on Jan 15 ET.
        _freeze(monkeypatch, datetime(2027, 1, 16, 5, 30, tzinfo=timezone.utc))
        game_day = date(2027, 1, 15)
        assert game_day < today_et()  # pick is gradable

    def test_old_cron_instant_would_have_skipped(self, monkeypatch):
        # The old 04:30 UTC winter instant is 11:30 PM ET — same ET day, skip.
        _freeze(monkeypatch, datetime(2027, 1, 16, 4, 30, tzinfo=timezone.utc))
        game_day = date(2027, 1, 15)
        assert not (game_day < today_et())


@pytest.mark.unit
class TestSeasonUsesEt:
    def test_rollover_follows_et_not_utc(self, monkeypatch):
        # Oct 1 03:00 UTC is still Sep 30 in ET — season must NOT roll yet
        _freeze(monkeypatch, datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc))
        assert get_current_season() == '2025-26'

    def test_rollover_after_et_midnight(self, monkeypatch):
        _freeze(monkeypatch, datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc))
        assert get_current_season() == '2026-27'

    def test_et_zone_constant(self):
        assert str(ET) == "America/New_York"
