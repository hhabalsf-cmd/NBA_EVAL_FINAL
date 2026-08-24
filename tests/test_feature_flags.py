"""Flag-gating tests for the pick-recommendation surfaces.

Covers both states of ``NBA_EVAL_ENABLE_PICKS``: OFF (the default, after the
2026-08 audit found the prop model went 40-66 against real lines) and ON.

The frontend twin, ``VITE_ENABLE_PREDICTIONS``, uses the same parsing
convention; it is defined in ``frontend/src/shared/lib/flags.ts`` and its
parsing rules are asserted against this module's table below so the two
implementations cannot drift silently.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from api.config import (
    PICKS_DISABLED_DETAIL,
    PICKS_DISABLED_STATUS,
    PICKS_FLAG_ENV_VAR,
    parse_flag,
    picks_enabled,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# (raw env value, expected flag state). Shared convention: only '1' and 'true'
# turn a flag on; everything else — absent, empty, 'false', '0', garbage — is off.
FLAG_CASES = [
    (None, False),
    ("", False),
    ("0", False),
    ("false", False),
    ("False", False),
    ("no", False),
    ("yes", False),
    ("2", False),
    ("truthy", False),
    ("1", True),
    ("true", True),
    ("TRUE", True),
    ("True", True),
    ("  1  ", True),
    ("  true  ", True),
]


@pytest.mark.unit
class TestParseFlag:
    @pytest.mark.parametrize("raw,expected", FLAG_CASES)
    def test_parsing_convention(self, raw, expected):
        assert parse_flag(raw) is expected

    def test_parse_flag_does_not_mutate_input(self):
        raw = "  TrUe "
        assert parse_flag(raw) is True
        assert raw == "  TrUe "


@pytest.mark.unit
class TestPicksEnabled:
    @pytest.mark.parametrize("raw,expected", FLAG_CASES)
    def test_reads_the_env_var(self, raw, expected):
        env = {} if raw is None else {PICKS_FLAG_ENV_VAR: raw}
        assert picks_enabled(env) is expected

    def test_defaults_off_when_var_absent(self):
        assert picks_enabled({}) is False

    def test_ignores_unrelated_vars(self):
        assert picks_enabled({"ENABLE_PICKS": "1", "NBA_EVAL_ENABLE": "1"}) is False

    def test_reads_os_environ_by_default(self, monkeypatch):
        monkeypatch.delenv(PICKS_FLAG_ENV_VAR, raising=False)
        assert picks_enabled() is False
        monkeypatch.setenv(PICKS_FLAG_ENV_VAR, "1")
        assert picks_enabled() is True

    def test_disabled_detail_explains_why_and_how_to_re_enable(self):
        assert PICKS_FLAG_ENV_VAR in PICKS_DISABLED_DETAIL
        assert "37.7%" in PICKS_DISABLED_DETAIL
        assert "52.4%" in PICKS_DISABLED_DETAIL
        assert PICKS_DISABLED_STATUS == 503


@pytest.mark.unit
class TestRecommendationServiceGate:
    """`PredictionService.evaluate_line` returns a recommendation, so it is gated.

    Gating at the service keeps the HTTP route (`POST /api/players/evaluate-line`)
    covered without the route having to know about the flag.
    """

    @staticmethod
    def _service():
        from api.services.prediction_service import PredictionService
        return PredictionService()

    def test_evaluate_line_raises_503_when_disabled(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.delenv(PICKS_FLAG_ENV_VAR, raising=False)
        with pytest.raises(HTTPException) as excinfo:
            self._service().evaluate_line(prediction=25.0, line=24.5, stat="PTS")

        assert excinfo.value.status_code == PICKS_DISABLED_STATUS
        assert excinfo.value.detail == PICKS_DISABLED_DETAIL

    def test_evaluate_line_reaches_the_evaluator_when_enabled(self, monkeypatch):
        monkeypatch.setenv(PICKS_FLAG_ENV_VAR, "1")
        service = self._service()

        calls = []

        class _StubEvaluator:
            def evaluate(self, prediction, line, stat, confidence_info=None, predictor=None):
                calls.append((prediction, line, stat))
                return {"recommendation": "TARGET OVER"}

        monkeypatch.setattr(type(service), "evaluator", property(lambda self: _StubEvaluator()))

        result = service.evaluate_line(prediction=25.0, line=24.5, stat="PTS")

        assert result == {"recommendation": "TARGET OVER"}
        assert calls == [(25.0, 24.5, "PTS")]

    def test_best_bets_raises_503_when_disabled(self, monkeypatch):
        import asyncio

        from fastapi import HTTPException

        from api.services.prediction_service import BestBetsService

        monkeypatch.delenv(PICKS_FLAG_ENV_VAR, raising=False)
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(BestBetsService().get_todays_best_bets())

        assert excinfo.value.status_code == PICKS_DISABLED_STATUS


@pytest.mark.integration
class TestDailyBestPicksScriptGate:
    """`scripts/daily_best_picks.py` must refuse to run without the flag."""

    @staticmethod
    def _run(env_value):
        import os

        env = dict(os.environ)
        env["NBA_EVAL_DISABLE_TF"] = "1"
        env.pop(PICKS_FLAG_ENV_VAR, None)
        if env_value is not None:
            env[PICKS_FLAG_ENV_VAR] = env_value

        return subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "daily_best_picks.py")],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def test_exits_non_zero_without_the_flag(self):
        completed = self._run(None)
        assert completed.returncode != 0
        combined = completed.stdout + completed.stderr
        assert PICKS_FLAG_ENV_VAR in combined
        assert "37.7%" in combined

    def test_run_returns_a_failure_summary_without_the_flag(self, monkeypatch):
        monkeypatch.delenv(PICKS_FLAG_ENV_VAR, raising=False)
        monkeypatch.setenv("NBA_EVAL_DISABLE_TF", "1")
        sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.daily_best_picks import run

        result = run()

        assert result["success"] is False
        assert result["picks_count"] == 0
        assert PICKS_FLAG_ENV_VAR in result["error"]


@pytest.mark.unit
class TestFrontendFlagParityWithBackend:
    """The Vite flag must use the same wording and default as the backend one.

    The frontend has no JS test runner in this repo, so parity is asserted by
    reading the source: the flag module must exist, must be the only place that
    reads `import.meta.env.VITE_ENABLE_PREDICTIONS`, and must accept exactly the
    same truthy values as `api/config.py`.
    """

    FLAGS_TS = PROJECT_ROOT / "frontend" / "src" / "shared" / "lib" / "flags.ts"

    def test_flag_module_exists(self):
        assert self.FLAGS_TS.is_file()

    def test_truthy_values_match_the_backend(self):
        source = self.FLAGS_TS.read_text()
        assert "['1', 'true']" in source
        assert "VITE_ENABLE_PREDICTIONS" in source

    def test_env_is_read_only_in_the_flag_module(self):
        """No component may reach for `import.meta.env` directly."""
        src_dir = PROJECT_ROOT / "frontend" / "src"
        env_read = "import.meta.env.VITE_ENABLE_PREDICTIONS"
        offenders = [
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in src_dir.rglob("*.ts*")
            if path != self.FLAGS_TS and env_read in path.read_text()
        ]
        assert offenders == [], f"read the flag via shared/lib/flags.ts instead: {offenders}"

    BANNER_TSX = PROJECT_ROOT / "frontend" / "src" / "shared" / "components" / "ModelAccuracyBanner.tsx"

    def test_prop_accuracy_banner_carries_the_measured_record(self):
        source = self.BANNER_TSX.read_text()
        for fragment in ("40-66", "37.7%", "106 graded picks", "52.4%", "Not a betting recommendation"):
            assert fragment in source, f"missing from the accuracy notice: {fragment}"

    def test_game_accuracy_banner_carries_the_measured_record(self):
        source = self.BANNER_TSX.read_text()
        for fragment in (
            "24 correct of 38",
            "63.2%",
            "55.3%",
            "p = 0.63",
            "0.2542",
            "Not a betting recommendation",
        ):
            assert fragment in source, f"missing from the game accuracy notice: {fragment}"


@pytest.mark.unit
class TestEveryModelSurfaceIsGated:
    """Each page that renders model output must reference the flag.

    A page appearing here without a `PREDICTIONS_ENABLED` reference means a
    model surface shipped ungated. `PicksPage` is deliberately absent: it is a
    record of picks the user already made, not advice.
    """

    GATED_PAGES = [
        "features/home/HomePage.tsx",
        "features/predictions/PlayerPage.tsx",
        "features/research/ResearchPage.tsx",
        "features/landing/LandingPage.tsx",
        "features/games/GamesPage.tsx",
    ]

    @pytest.mark.parametrize("relative_path", GATED_PAGES)
    def test_page_references_the_flag(self, relative_path):
        page = PROJECT_ROOT / "frontend" / "src" / relative_path
        source = page.read_text()
        assert "PREDICTIONS_ENABLED" in source, f"{relative_path} renders model output ungated"
        assert "shared/lib/flags" in source, f"{relative_path} must import the shared flag module"
