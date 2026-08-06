"""Tests for the pretrain_all_players skip/refresh logic (pure parts only)."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from pretrain_all_players import DEFAULT_MAX_AGE_DAYS, parse_args, should_skip

TODAY = date(2026, 10, 20)


@pytest.mark.unit
class TestShouldSkip:
    def test_fresh_model_skipped(self):
        assert should_skip('2026-10-18', 7, force=False, today=TODAY) is True

    def test_boundary_exactly_max_age_still_fresh(self):
        assert should_skip('2026-10-13', 7, force=False, today=TODAY) is True

    def test_one_past_boundary_retrains(self):
        assert should_skip('2026-10-12', 7, force=False, today=TODAY) is False

    def test_stale_march_model_retrains(self):
        assert should_skip('2026-03-01', 7, force=False, today=TODAY) is False

    def test_force_overrides_freshness(self):
        assert should_skip('2026-10-20', 7, force=True, today=TODAY) is False

    def test_missing_trained_at_retrains(self):
        assert should_skip(None, 7, force=False, today=TODAY) is False

    def test_unparsable_trained_at_retrains(self):
        assert should_skip('not-a-date', 7, force=False, today=TODAY) is False

    def test_datetime_style_string_accepted(self):
        assert should_skip('2026-10-19 04:12:00', 7, force=False, today=TODAY) is True

    def test_custom_max_age(self):
        assert should_skip('2026-09-25', 30, force=False, today=TODAY) is True


@pytest.mark.unit
class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.force is False
        assert args.max_age_days == DEFAULT_MAX_AGE_DAYS

    def test_force_flag(self):
        assert parse_args(['--force']).force is True

    def test_max_age_override(self):
        assert parse_args(['--max-age-days', '30']).max_age_days == 30
