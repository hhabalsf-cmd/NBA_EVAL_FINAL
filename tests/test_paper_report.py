"""Tests for paper_report — the text rendering of the forward-sample standing.

The whole point of this report is to not fool ourselves again, so the n=0 and
small-n behaviour is pinned explicitly.
"""
import pytest

import clv
import paper_report


def _report(wins=0, losses=0, pending=0, clv_values=None, missing_close=0):
    values = clv_values or []
    return {
        "ready": True,
        "record": clv.summarize_record(wins, losses),
        "pending": pending,
        "total_recorded": wins + losses + pending,
        "clv": {**clv.summarize_clv(values),
                "picks_without_closing_line": missing_close},
    }


@pytest.mark.unit
class TestSchemaNotReady:
    def test_reports_missing_objects(self):
        out = paper_report.render({
            "ready": False,
            "missing_schema": ["picks.is_paper column", "line_snapshots table"],
            "migration_file": "supabase/001_paper_picks_and_line_snapshots.sql",
        })
        assert "picks.is_paper column" in out
        assert "line_snapshots table" in out
        assert "supabase/001_paper_picks_and_line_snapshots.sql" in out

    def test_does_not_claim_a_rate(self):
        out = paper_report.render({
            "ready": False, "missing_schema": ["line_snapshots table"],
            "migration_file": "x.sql",
        })
        assert "%" not in out


@pytest.mark.unit
class TestEmptySample:
    def test_reports_zero_without_crashing(self):
        out = paper_report.render(_report())
        assert "0" in out

    def test_refuses_to_conclude(self):
        out = paper_report.render(_report())
        assert "NO CONCLUSION" in out.upper()

    def test_states_no_win_rate_rather_than_zero_percent(self):
        out = paper_report.render(_report())
        # A 0-0 record must not be rendered as "0.0%" -- that reads as a result.
        assert "0.0%" not in out
        assert "n/a" in out.lower()

    def test_shows_full_distance_to_min_n(self):
        out = paper_report.render(_report())
        assert "500" in out


@pytest.mark.unit
class TestSmallSample:
    def test_shows_rate_and_interval(self):
        out = paper_report.render(_report(wins=12, losses=8))
        assert "60.0%" in out
        assert "20" in out

    def test_still_refuses_to_conclude_below_min_n(self):
        out = paper_report.render(_report(wins=12, losses=8))
        assert "NO CONCLUSION" in out.upper()

    def test_reports_remaining_picks_needed(self):
        out = paper_report.render(_report(wins=12, losses=8))
        assert "480" in out


@pytest.mark.unit
class TestConclusiveSample:
    def test_clears_breakeven(self):
        out = paper_report.render(_report(wins=320, losses=180))
        assert "CLEARS" in out.upper()
        assert "NO CONCLUSION" not in out.upper()

    def test_below_breakeven(self):
        out = paper_report.render(_report(wins=200, losses=300))
        assert "BELOW" in out.upper()

    def test_inconclusive_when_interval_straddles(self):
        out = paper_report.render(_report(wins=265, losses=235))
        assert "INCONCLUSIVE" in out.upper()


@pytest.mark.unit
class TestClvSection:
    def test_no_clv_data_is_stated_plainly(self):
        out = paper_report.render(_report(wins=5, losses=5, missing_close=10))
        assert "no closing lines" in out.lower()

    def test_renders_clv_average(self):
        out = paper_report.render(_report(wins=2, losses=2,
                                          clv_values=[1.0, -0.5, 0.5, 0.0]))
        assert "+0.25" in out

    def test_negative_average_keeps_sign(self):
        out = paper_report.render(_report(wins=2, losses=2,
                                          clv_values=[-1.0, -1.0]))
        assert "-1.00" in out

    def test_flags_picks_missing_a_closing_line(self):
        out = paper_report.render(_report(wins=5, losses=5,
                                          clv_values=[0.5], missing_close=9))
        assert "9" in out


@pytest.mark.unit
class TestPendingAndTotals:
    def test_pending_reported_separately_from_graded(self):
        out = paper_report.render(_report(wins=3, losses=2, pending=7))
        assert "7" in out

    def test_render_returns_a_string(self):
        assert isinstance(paper_report.render(_report()), str)

    def test_render_does_not_mutate_input(self):
        report = _report(wins=1, losses=1)
        snapshot = repr(report)
        paper_report.render(report)
        assert repr(report) == snapshot
