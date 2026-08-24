"""Runtime configuration flags shared by the API and the offline scripts.

Deliberately framework-free: `scripts/daily_best_picks.py` imports from here and
must not pull FastAPI in to read a flag. Callers that need an HTTP response map
`PICKS_DISABLED_DETAIL` onto a 503 themselves.
"""
import os
from typing import Optional

# A flag is OFF unless the env var is exactly '1' or 'true' (case-insensitive,
# surrounding whitespace ignored). Mirrors `frontend/src/shared/lib/flags.ts`.
TRUTHY_FLAG_VALUES = frozenset({"1", "true"})

#: Gates every code path that generates or serves a pick recommendation.
PICKS_FLAG_ENV_VAR = "NBA_EVAL_ENABLE_PICKS"

#: Single source of truth for why pick generation is off. Keep in sync with
#: `MODEL_ACCURACY_NOTICE` in frontend/src/shared/components/ModelAccuracyBanner.tsx.
PICKS_DISABLED_DETAIL = (
    "Pick generation is disabled. The prop model went 40-66 (37.7%) on 106 graded "
    "picks against real lines, versus a 52.4% breakeven, and loses to a 10-game "
    "rolling average on every stat. Research endpoints (game logs, splits, "
    "matchup context) are unaffected. Set NBA_EVAL_ENABLE_PICKS=1 to re-enable. "
    "See docs/NEXT_STEPS_2026-08-23.md."
)

#: HTTP status returned when a recommendation endpoint is called with picks off.
PICKS_DISABLED_STATUS = 503


def parse_flag(raw: Optional[str]) -> bool:
    """Parse a raw env value into a boolean flag. Absent/empty/unknown -> False."""
    if raw is None:
        return False
    return raw.strip().lower() in TRUTHY_FLAG_VALUES


def picks_enabled(env: Optional[dict] = None) -> bool:
    """True when pick generation has been explicitly enabled.

    `env` is injectable so tests never have to mutate ``os.environ`` in place.
    """
    source = os.environ if env is None else env
    return parse_flag(source.get(PICKS_FLAG_ENV_VAR))
