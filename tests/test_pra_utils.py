"""Tests for pra_utils — single source of truth for PRA reconciliation.

Root cause (2026-07 audit): three code paths defined PRA three ways
(85/15 blend in predict(); pure component sum in the injury and blowout
adjustment paths), and PRA's serve-time std came from the independent
PRA model while the served value was the blend — overconfident probs.
"""
import math

import pytest

from pra_utils import reconcile_pra, pra_std_floor, rescale_pra_with_components


@pytest.mark.unit
class TestReconcilePra:
    def test_blends_components_with_independent_pra(self):
        preds = {'PTS': 25.0, 'REB': 8.0, 'AST': 7.0, 'PRA': 44.0}
        out = reconcile_pra(preds)
        # 0.85 * 40 + 0.15 * 44 = 40.6
        assert out['PRA'] == pytest.approx(40.6)

    def test_pure_sum_when_no_independent_pra(self):
        preds = {'PTS': 25.0, 'REB': 8.0, 'AST': 7.0}
        out = reconcile_pra(preds)
        assert out['PRA'] == pytest.approx(40.0)

    def test_returns_new_dict_without_mutating_input(self):
        preds = {'PTS': 25.0, 'REB': 8.0, 'AST': 7.0, 'PRA': 44.0}
        out = reconcile_pra(preds)
        assert preds['PRA'] == 44.0
        assert out is not preds

    def test_missing_component_leaves_pra_untouched(self):
        preds = {'PTS': 25.0, 'REB': 8.0, 'PRA': 44.0}
        out = reconcile_pra(preds)
        assert out['PRA'] == 44.0

    def test_other_stats_pass_through(self):
        preds = {'PTS': 25.0, 'REB': 8.0, 'AST': 7.0, 'PRA': 44.0, 'MIN': 34.0}
        out = reconcile_pra(preds)
        assert out['MIN'] == 34.0
        assert out['PTS'] == 25.0


@pytest.mark.unit
class TestRescalePraWithComponents:
    def test_independent_share_scales_with_component_adjustment(self):
        before = {'PTS': 20.0, 'REB': 10.0, 'AST': 10.0, 'PRA': 44.0}
        # Components uniformly discounted 10%
        after = {'PTS': 18.0, 'REB': 9.0, 'AST': 9.0, 'PRA': 44.0}
        out = rescale_pra_with_components(before, after)
        # ratio = 36/40 = 0.9 → independent 44*0.9 = 39.6
        # blend = 0.85*36 + 0.15*39.6 = 30.6 + 5.94 = 36.54
        assert out['PRA'] == pytest.approx(36.54)

    def test_no_adjustment_is_identity_blend(self):
        before = {'PTS': 20.0, 'REB': 10.0, 'AST': 10.0, 'PRA': 44.0}
        out = rescale_pra_with_components(before, dict(before))
        # blend of unchanged values: 0.85*40 + 0.15*44 = 40.6
        assert out['PRA'] == pytest.approx(40.6)

    def test_missing_pra_falls_back_to_component_sum(self):
        before = {'PTS': 20.0, 'REB': 10.0, 'AST': 10.0}
        after = {'PTS': 22.0, 'REB': 10.0, 'AST': 10.0}
        out = rescale_pra_with_components(before, after)
        assert out['PRA'] == pytest.approx(42.0)

    def test_zero_old_sum_does_not_divide_by_zero(self):
        before = {'PTS': 0.0, 'REB': 0.0, 'AST': 0.0, 'PRA': 5.0}
        after = {'PTS': 1.0, 'REB': 1.0, 'AST': 1.0, 'PRA': 5.0}
        out = rescale_pra_with_components(before, after)
        # Falls back to plain reconcile of `after`
        assert out['PRA'] == pytest.approx(0.85 * 3.0 + 0.15 * 5.0)

    def test_does_not_mutate_inputs(self):
        before = {'PTS': 20.0, 'REB': 10.0, 'AST': 10.0, 'PRA': 44.0}
        after = {'PTS': 18.0, 'REB': 9.0, 'AST': 9.0, 'PRA': 44.0}
        rescale_pra_with_components(before, after)
        assert after['PRA'] == 44.0 and before['PRA'] == 44.0


@pytest.mark.unit
class TestPraStdFloor:
    def test_floors_at_rss_of_components(self):
        # RSS of (6, 3, 2.5) = sqrt(36+9+6.25) = 7.16; PRA std of 5 is too low
        floored = pra_std_floor(5.0, [6.0, 3.0, 2.5])
        assert floored == pytest.approx(math.sqrt(36 + 9 + 6.25))

    def test_keeps_pra_std_when_already_wider(self):
        assert pra_std_floor(9.0, [6.0, 3.0, 2.5]) == 9.0

    def test_ignores_missing_component_stds(self):
        # Only PTS std known — floor is just that value
        assert pra_std_floor(4.0, [6.0, None, None]) == 6.0

    def test_no_components_returns_pra_std(self):
        assert pra_std_floor(4.0, [None, None, None]) == 4.0
        assert pra_std_floor(4.0, []) == 4.0
