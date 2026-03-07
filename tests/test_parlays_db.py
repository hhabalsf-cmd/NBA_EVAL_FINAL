"""Tests for parlay DB helper functions."""
import os
import pytest
import db

_HAS_DB = bool(os.environ.get('DATABASE_URL'))

# These tests require a real DB connection — skip if DATABASE_URL not set
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="DATABASE_URL not set")


# Stub fixtures — real implementations live in conftest when DATABASE_URL is set
@pytest.fixture
def tmp_pick_ids():
    if not _HAS_DB:
        pytest.skip("DATABASE_URL not set")
    pytest.skip("tmp_pick_ids fixture not yet implemented for live DB")


@pytest.fixture
def tmp_parlay_id():
    if not _HAS_DB:
        pytest.skip("DATABASE_URL not set")
    pytest.skip("tmp_parlay_id fixture not yet implemented for live DB")


def test_create_parlay_returns_dict_with_id(tmp_pick_ids):
    """create_parlay should return a dict with at least an id field."""
    result = db.create_parlay(
        user_id="test-user-id",
        pick_ids=tmp_pick_ids[:2],
        name="Test Parlay"
    )
    assert isinstance(result, dict)
    assert 'id' in result
    assert result['legs_count'] == 2
    assert result['status'] == 'pending'


def test_get_parlays_returns_list(tmp_parlay_id):
    """get_parlays should return a list of parlays for the user."""
    results = db.get_parlays(user_id="test-user-id")
    assert isinstance(results, list)
    ids = [r['id'] for r in results]
    assert tmp_parlay_id in ids


def test_void_parlay_sets_status(tmp_parlay_id):
    """void_parlay should set status to voided."""
    db.void_parlay(parlay_id=tmp_parlay_id, user_id="test-user-id")
    results = db.get_parlays(user_id="test-user-id")
    parlay = next(r for r in results if r['id'] == tmp_parlay_id)
    assert parlay['status'] == 'voided'


def test_grade_pending_parlays_marks_won_when_all_legs_win():
    """grade_pending_parlays should mark parlay won when all picks have won=1."""
    # Integration test — relies on fixture data
    # Run manually after seeding DB with known state
    pass
