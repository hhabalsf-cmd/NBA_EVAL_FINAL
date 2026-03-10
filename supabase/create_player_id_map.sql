-- Player ID mapping: BallDontLie IDs <-> nba.com IDs
-- Run in Supabase SQL Editor before deploying the migration

CREATE TABLE IF NOT EXISTS player_id_map (
    bdl_id      INTEGER PRIMARY KEY,
    nba_id      INTEGER,
    full_name   TEXT NOT NULL,
    team_abbrev TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_player_id_map_nba ON player_id_map(nba_id)
    WHERE nba_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_player_id_map_name ON player_id_map(lower(full_name));

-- RLS: service role writes, public reads
ALTER TABLE player_id_map ENABLE ROW LEVEL SECURITY;
CREATE POLICY "player_id_map_public_read" ON player_id_map FOR SELECT USING (true);
CREATE POLICY "player_id_map_service_write" ON player_id_map FOR ALL USING (auth.role() = 'service_role');
