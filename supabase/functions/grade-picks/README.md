# grade-picks Edge Function

Triggered by a Supabase Database Webhook on `picks` INSERT events.
Also called by pg_cron nightly.

## Deployment

### 1. Install Supabase CLI (if not installed)
```bash
brew install supabase/tap/supabase
```

### 2. Set secrets
```bash
supabase secrets set FASTAPI_URL=https://<your-fastapi-host> --project-ref <project-ref>
supabase secrets set FASTAPI_SERVICE_KEY=<same-as-env-FASTAPI_SERVICE_KEY> --project-ref <project-ref>
```

### 3. Deploy
```bash
supabase functions deploy grade-picks --project-ref <your-project-ref>
```

### 4. Create Database Webhook (Supabase Dashboard)
- Table: `picks`, Event: `INSERT`
- URL: `https://<project-ref>.supabase.co/functions/v1/grade-picks`
- Header: `Authorization: Bearer <anon_key>`

### 5. Set up pg_cron (Supabase SQL Editor)
Run the SQL in `pg_cron_setup.sql`.
