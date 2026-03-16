-- Add CLV (Closing Line Value) tracking columns to picks table.
-- opening_line: the line at time of pick creation (backfilled from existing `line` column)
-- closing_line: the line at game start (populated by future closing-line fetch job)

ALTER TABLE picks ADD COLUMN IF NOT EXISTS opening_line REAL;
ALTER TABLE picks ADD COLUMN IF NOT EXISTS closing_line REAL;

-- Backfill: set opening_line = line for all existing picks that don't have it
UPDATE picks SET opening_line = line WHERE opening_line IS NULL;
