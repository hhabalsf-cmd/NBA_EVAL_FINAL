-- Enable extensions (run once)
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Nightly picks grading (11:30 PM ET = 4:30 AM UTC)
SELECT cron.schedule(
  'nightly-auto-grade-picks',
  '30 4 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/picks/auto-grade',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>')
  );
  $$
);

-- Nightly game grading (11:35 PM ET = 4:35 AM UTC)
SELECT cron.schedule(
  'nightly-auto-grade-games',
  '35 4 * * *',
  $$
  SELECT net.http_post(
    url := '<your-fastapi-url>/api/games/auto-grade',
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>')
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
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>')
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
    headers := jsonb_build_object('X-Service-Key', '<FASTAPI_SERVICE_KEY>')
  );
  $$
);

-- Verify
SELECT jobname, schedule, active FROM cron.job;
