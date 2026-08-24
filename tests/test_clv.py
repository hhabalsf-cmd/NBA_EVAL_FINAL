"""Tests for clv — pure CLV math, Wilson intervals, and sample verdicts.

No database, no network. These are the numbers the forward paper sample will be
judged on, so they are pinned exactly.
"""
import math

import pytest

import clv


@pytest.mark.unit
class TestBreakeven:
    def test_breakeven_is_minus_110(self):
        # -110 juice both sides: risk 110 to win 100 => 110/210
        assert clv.BREAKEVEN_RATE == pytest.approx(110 / 210)
        assert clv.BREAKEVEN_RATE == pytest.approx(0.5238095, abs=1e-6)

    def test_min_conclusive_n_matches_plan(self):
        # Plan of record: n >= 500 for a +/-4% band.
        assert clv.MIN_CONCLUSIVE_N == 500


@pytest.mark.unit
class TestComputeClv:
    def test_over_gains_when_line_rises(self):
        # Bet OVER 25.5, closes 26.5 -> we hold the cheaper number.
        assert clv.compute_clv("OVER", 25.5, 26.5) == pytest.approx(1.0)

    def test_over_loses_when_line_falls(self):
        assert clv.compute_clv("OVER", 25.5, 24.5) == pytest.approx(-1.0)

    def test_under_gains_when_line_falls(self):
        # Bet UNDER 25.5, closes 24.5 -> we hold the richer number.
        assert clv.compute_clv("UNDER", 25.5, 24.5) == pytest.approx(1.0)

    def test_under_loses_when_line_rises(self):
        assert clv.compute_clv("UNDER", 25.5, 26.5) == pytest.approx(-1.0)

    def test_no_move_is_zero(self):
        assert clv.compute_clv("OVER", 25.5, 25.5) == 0.0

    def test_direction_is_case_insensitive(self):
        assert clv.compute_clv("over", 25.5, 26.5) == pytest.approx(1.0)

    def test_rejects_unknown_direction(self):
        with pytest.raises(ValueError, match="direction"):
            clv.compute_clv("SIDEWAYS", 25.5, 26.5)

    def test_rejects_none_lines(self):
        with pytest.raises(ValueError):
            clv.compute_clv("OVER", None, 26.5)
        with pytest.raises(ValueError):
            clv.compute_clv("OVER", 25.5, None)

    def test_rejects_non_numeric_lines(self):
        with pytest.raises(ValueError):
            clv.compute_clv("OVER", "twenty", 26.5)


@pytest.mark.unit
class TestWilsonInterval:
    def test_undefined_at_zero_n(self):
        assert clv.wilson_interval(0, 0) is None

    def test_rejects_wins_above_n(self):
        with pytest.raises(ValueError):
            clv.wilson_interval(5, 3)

    def test_rejects_negative(self):
        with pytest.raises(ValueError):
            clv.wilson_interval(-1, 3)

    def test_known_value_106_picks(self):
        # The real graded sample: 40-66. Hand-computed Wilson 95% interval.
        lo, hi = clv.wilson_interval(40, 106)
        assert lo == pytest.approx(0.29089, abs=1e-4)
        assert hi == pytest.approx(0.47240, abs=1e-4)

    def test_zero_wins_floors_at_zero(self):
        lo, hi = clv.wilson_interval(0, 10)
        assert lo == 0.0
        assert hi == pytest.approx(0.27753, abs=1e-4)

    def test_all_wins_ceils_at_one(self):
        lo, hi = clv.wilson_interval(10, 10)
        assert hi == 1.0
        assert lo == pytest.approx(0.72247, abs=1e-4)

    def test_interval_narrows_as_n_grows(self):
        narrow = clv.wilson_interval(500, 1000)
        wide = clv.wilson_interval(5, 10)
        assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])

    def test_interval_brackets_point_estimate(self):
        lo, hi = clv.wilson_interval(40, 106)
        assert lo < 40 / 106 < hi


@pytest.mark.unit
class TestSummarizeRecord:
    def test_empty_sample(self):
        s = clv.summarize_record(0, 0)
        assert s["n"] == 0
        assert s["win_rate"] is None
        assert s["wilson_low"] is None
        assert s["verdict"] == clv.VERDICT_INSUFFICIENT
        assert s["picks_to_min_n"] == clv.MIN_CONCLUSIVE_N

    def test_counts_and_rate(self):
        s = clv.summarize_record(40, 66)
        assert s["n"] == 106
        assert s["wins"] == 40
        assert s["losses"] == 66
        assert s["win_rate"] == pytest.approx(0.377358, abs=1e-6)
        assert s["picks_to_min_n"] == 394

    def test_refuses_conclusion_below_min_n(self):
        # 90% winners but only n=100: still not conclusive.
        s = clv.summarize_record(90, 10)
        assert s["verdict"] == clv.VERDICT_INSUFFICIENT

    def test_clears_breakeven_only_when_interval_excludes_it(self):
        s = clv.summarize_record(320, 180)  # 64% on n=500
        assert s["n"] == 500
        assert s["verdict"] == clv.VERDICT_CLEARS

    def test_below_breakeven_when_interval_entirely_under(self):
        s = clv.summarize_record(200, 300)  # 40% on n=500
        assert s["verdict"] == clv.VERDICT_BELOW

    def test_inconclusive_when_interval_straddles_breakeven(self):
        s = clv.summarize_record(265, 235)  # 53% on n=500, CI straddles 52.4%
        assert s["verdict"] == clv.VERDICT_INCONCLUSIVE

    def test_distance_to_breakeven_signed(self):
        s = clv.summarize_record(40, 66)
        assert s["distance_to_breakeven"] == pytest.approx(0.377358 - clv.BREAKEVEN_RATE, abs=1e-6)

    def test_rejects_negative_counts(self):
        with pytest.raises(ValueError):
            clv.summarize_record(-1, 5)


@pytest.mark.unit
class TestSummarizeClv:
    def test_empty(self):
        s = clv.summarize_clv([])
        assert s["n"] == 0
        assert s["avg_clv"] is None
        assert s["positive_clv_rate"] is None

    def test_averages_and_rate(self):
        s = clv.summarize_clv([1.0, -0.5, 0.5, 0.0])
        assert s["n"] == 4
        assert s["avg_clv"] == pytest.approx(0.25)
        # 0.0 is not positive
        assert s["positive_clv_rate"] == pytest.approx(0.5)

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError):
            clv.summarize_clv([1.0, "nope"])

    def test_rejects_nan(self):
        with pytest.raises(ValueError):
            clv.summarize_clv([float("nan")])
