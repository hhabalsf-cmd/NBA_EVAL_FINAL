"""Tests for season_utils — date-derived NBA season strings.

The NBA season string rolls over on October 1: from July 2026 the current
season is still '2025-26'; from October 2026 it becomes '2026-27'.
"""
from datetime import date

import pytest

from season_utils import get_current_season, get_recent_seasons


@pytest.mark.unit
class TestGetCurrentSeason:
    def test_offseason_belongs_to_completed_season(self):
        assert get_current_season(date(2026, 7, 14)) == '2025-26'

    def test_october_starts_new_season(self):
        assert get_current_season(date(2026, 10, 1)) == '2026-27'

    def test_midseason_january(self):
        assert get_current_season(date(2027, 1, 15)) == '2026-27'

    def test_june_playoffs_still_same_season(self):
        assert get_current_season(date(2027, 6, 10)) == '2026-27'

    def test_september_still_previous_season(self):
        assert get_current_season(date(2026, 9, 30)) == '2025-26'

    def test_year_suffix_wraps_correctly_at_century_boundary(self):
        assert get_current_season(date(2099, 11, 1)) == '2099-00'

    def test_defaults_to_today(self):
        # Sanity: no-arg call returns a well-formed season string
        season = get_current_season()
        assert len(season) == 7
        first, second = season.split('-')
        assert (int(first) + 1) % 100 == int(second)


@pytest.mark.unit
class TestGetRecentSeasons:
    def test_current_plus_two_prior(self):
        assert get_recent_seasons(3, date(2026, 7, 14)) == [
            '2025-26', '2024-25', '2023-24'
        ]

    def test_after_rollover(self):
        assert get_recent_seasons(2, date(2026, 10, 20)) == [
            '2026-27', '2025-26'
        ]

    def test_single_season(self):
        assert get_recent_seasons(1, date(2026, 7, 14)) == ['2025-26']

    def test_rejects_non_positive_n(self):
        with pytest.raises(ValueError):
            get_recent_seasons(0, date(2026, 7, 14))
