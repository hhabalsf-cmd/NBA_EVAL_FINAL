-- 001_paper_picks_and_line_snapshots.sql
--
-- Track C of docs/NEXT_STEPS_2026-08-23.md: make reality measurable.
--
-- NOT YET APPLIED. Review before running. Two independent changes:
--
--   1. picks.is_paper       -- separates the forward paper sample from the
--                              114 real picks already on record.
--   2. line_snapshots       -- append-only log of observed lines, which is what
--                              closing-line value (CLV) actually needs.
--
-- Both are additive and backward compatible. Nothing existing is relabelled:
-- is_paper defaults to 0, so all 114 current picks remain real picks.
--
-- Safe to run more than once (IF NOT EXISTS throughout).


-- ── 1. Paper picks ──────────────────────────────────────────────────────────
--
-- Paper picks ride the existing nightly grading path unchanged: auto_grade_picks
-- selects on `won IS NULL`, which does not care about this flag. They carry
-- user_id IS NULL, so they are already excluded from every user-scoped query and
-- from leaderboard_view (which INNER JOINs picks to profiles on user_id).

ALTER TABLE picks
    ADD COLUMN IF NOT EXISTS is_paper INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'picks_is_paper_check'
    ) THEN
        ALTER TABLE picks
            ADD CONSTRAINT picks_is_paper_check CHECK (is_paper IN (0, 1));
    END IF;
END $$;

-- Reporting reads the paper sample only; keep that scan off the real picks.
CREATE INDEX IF NOT EXISTS idx_picks_paper
    ON picks (game_date DESC)
    WHERE is_paper = 1;

-- A paper pick is unique per player/stat/game_date. Partial unique index so it
-- constrains only paper rows and leaves real picks (which allow one row per
-- user) untouched.
CREATE UNIQUE INDEX IF NOT EXISTS idx_picks_paper_unique
    ON picks (player, stat, game_date)
    WHERE is_paper = 1 AND (voided IS NULL OR voided = 0);


-- ── 2. Line snapshots ───────────────────────────────────────────────────────
--
-- manual_lines holds exactly one mutable row per (game_date, player, stat), so
-- re-entering a line closer to tip-off overwrites the earlier observation and
-- the line's path is lost. CLV needs the path, so snapshots are append-only:
-- no unique constraint, no upsert, one row per observation.
--
-- captured_at is the ordering key. The closing line for a pick is the latest
-- snapshot captured strictly after that pick was created; a snapshot at or
-- before the pick is the same number the pick was taken at, and recording it
-- would manufacture a CLV of exactly 0.0.

CREATE TABLE IF NOT EXISTS line_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    game_date   DATE        NOT NULL,
    player      TEXT        NOT NULL,
    stat        TEXT        NOT NULL,
    line        NUMERIC     NOT NULL,
    source      TEXT        NOT NULL DEFAULT 'manual',
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT line_snapshots_stat_check
        CHECK (stat IN ('PTS', 'REB', 'AST', 'PRA')),
    CONSTRAINT line_snapshots_source_check
        CHECK (source IN ('manual', 'odds_api')),
    CONSTRAINT line_snapshots_line_check
        CHECK (line > 0)
);

-- The lookup the closing-line job performs: newest observation for a key.
CREATE INDEX IF NOT EXISTS idx_line_snapshots_lookup
    ON line_snapshots (game_date, player, stat, captured_at DESC);


-- Row-level security. Every other table in `public` has RLS enabled, and
-- PostgREST exposes anything in this schema to the anon key, so a new table
-- without it would be the only publicly readable table in the database.
--
-- This follows the `manual_lines` convention: RLS ON with zero policies, which
-- denies anon and authenticated outright. Only the service_role key bypasses
-- RLS, and the FastAPI backend is the sole writer and reader.

ALTER TABLE line_snapshots ENABLE ROW LEVEL SECURITY;


-- ── Verification ────────────────────────────────────────────────────────────
-- Expected after applying: is_paper present with 114 rows at 0, 0 snapshots.
--
--   SELECT count(*) AS total,
--          count(*) FILTER (WHERE is_paper = 1) AS paper,
--          count(*) FILTER (WHERE is_paper = 0) AS real_picks
--   FROM picks;
--
--   SELECT count(*) FROM line_snapshots;
--
--   SELECT relrowsecurity FROM pg_class WHERE relname = 'line_snapshots';
--   -- expected: true


-- ── NOT included on purpose ─────────────────────────────────────────────────
--
-- The `nightly-closing-lines` pg_cron job in supabase/pg_cron_setup.sql is NOT
-- scheduled here. It is currently inactive, and its endpoint
-- (/api/picks/update-closing-lines) was calling a permanently dead data source
-- until this change. Schedule it only once manual line entry near tip-off is
-- actually happening, otherwise it runs nightly and records nothing.
--
-- Do NOT re-run pg_cron_setup.sql wholesale: it would re-enable job 16
-- (daily-best-picks), which is deliberately disabled while the model is under
-- remediation.
