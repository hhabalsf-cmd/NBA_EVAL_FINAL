-- Enable extensions (run once)
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- IMPORTANT: All net.http_post calls MUST include timeout_milliseconds := 60000.
-- The default pg_net timeout is 5 seconds, which is too short for Railway cold starts.

-- Keepalive ping every 10 minutes (prevents Railway from sleeping)
SELECT cron.schedule(
  'keepalive-ping',
  '*/10 * * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/health',
    headers := jsonb_build_object('Content-Type', 'application/json'),
    timeout_milliseconds := 5000
  );
  $$
);

-- Fetch closing lines for CLV tracking (5:00 AM UTC = 12:00/1:00 AM ET, always past ET midnight)
-- Runs 30 min before auto-grade to capture closing lines before picks are graded.
-- NOTE: grading uses ET dates (season_utils.today_et), so these jobs MUST run
-- after midnight ET year-round — 05:xx UTC covers both EST (UTC-5) and EDT (UTC-4).
SELECT cron.schedule(
  'nightly-closing-lines',
  '0 5 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/picks/update-closing-lines',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>'),
    timeout_milliseconds := 60000
  );
  $$
);

-- Nightly picks grading (5:30 AM UTC = 12:30/1:30 AM ET, always past ET midnight)
SELECT cron.schedule(
  'nightly-auto-grade-picks',
  '30 5 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/picks/auto-grade',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>'),
    timeout_milliseconds := 60000
  );
  $$
);

-- Nightly game grading (5:35 AM UTC = 12:35/1:35 AM ET, always past ET midnight)
SELECT cron.schedule(
  'nightly-auto-grade-games',
  '35 5 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/games/auto-grade',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>'),
    timeout_milliseconds := 60000
  );
  $$
);

-- Daily best picks generation (8:00 AM ET = 1:00 PM UTC)
SELECT cron.schedule(
  'daily-best-picks',
  '0 13 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/bets/generate',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>'),
    timeout_milliseconds := 60000
  );
  $$
);

-- Daily game predictions (8:00 AM ET = 1:00 PM UTC)
SELECT cron.schedule(
  'daily-game-predictions',
  '0 13 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/games/predict-cron',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>'),
    timeout_milliseconds := 60000
  );
  $$
);

-- Nightly sync game logs (1:00 AM ET = 6:00 AM UTC)
SELECT cron.schedule(
  'nightly-sync-game-logs',
  '0 6 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/sync/nightly',
    headers := jsonb_build_object('Content-Type', 'application/json', 'X-Service-Key', '<FASTAPI_SERVICE_KEY>'),
    body := '{}'::jsonb,
    timeout_milliseconds := 60000
  );
  $$
);

-- Verify
SELECT jobname, schedule, active FROM cron.job;
