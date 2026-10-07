# NBA Eval on your computer

The personal app runs at **http://127.0.0.1:8765**. Double-click **Start NBA Eval.cmd** in the repository to launch it. The browser opens after the server is ready; launching it again opens the existing app. Close the server terminal or press Ctrl+C to stop it.

This mode needs no BallDontLie subscription, Odds API key, Supabase account, login, Railway, or Vercel. The original Bettin' Jrys React interface is built locally once; Node is not required while using the app. It reads ESPN's public JSON endpoints. Those are still APIs, but require no paid key in the verified setup. Internet access is needed for fresh data. The service listens only on this computer and rejects remote clients and cross-site requests; it is not a public hosting configuration.

## Using it

1. Search for a player on Home, or choose a team and player under Forecasts. The first search loads current ESPN rosters. The first player visit checks up to 60 historical final box scores, so it can take 30–90 seconds. Cached visits are much faster.
2. Selecting a player automatically finds their next supported regular-season game, checks ESPN's injury listing and generates PTS, REB, AST and PRA forecasts with 80% outcome ranges. The result appears above the optional controls and saves on this computer. Research remains a logs-only view.
3. Check the displayed matchup and availability. ESPN listings of out or suspended block an active-player forecast. No injury listing means participation is unconfirmed, not guaranteed. Questionable players receive explicitly conditional predictions. Times display in your computer's timezone.
4. Inspect the recent-game table and excluded-game messages. Optionally choose another matchup or enter a sportsbook line, side and **current** American odds, then click **Compare Price**. Prices are entered manually; the app does not have a complete free player-prop odds feed.
5. Use **Refresh Forecast** to recheck the current context and save a fresh snapshot. Revisit close to tipoff rather than relying on an early season preview.

The rebuilt research model is used throughout this personal app. The old hosted game-winner, social, daily best-bet and automatic betting paths are not included. No wagers are placed. Positive estimated returns are **not** established profitable edges: no priced historical betting validation has been completed. Preseason, playoffs, play-in and neutral-site upcoming games are unsupported. Rookies and players with fewer than ten usable prior NBA appearances receive no forecast.

The Home, Games, Research, Forecasts, Picks and Leaders navigation uses the original shared app shell, logo, typography, colors and mobile navigation. Games lists ESPN schedules; Research shows verified logs; Picks holds saved research snapshots; Leaders ranks the latest saved player projections, not betting profits. The profile menu opens personal settings, including the original light/dark theme toggle. Existing local history is retained.

## What happens to discrepancies

- ESPN IDs are explicitly namespaced as `espn:`. NBA and BDL IDs are never substituted or guessed from player names.
- Historical team membership comes from that game's box score, including traded players. Team abbreviations are normalized to the model's conventions.
- Only completed regular-season history before today in Eastern Time is used. ESPN sometimes groups play-in games and All-Star exhibitions under “Regular Season.” The adapter checks both the final summary's season type and the competing NBA franchise IDs; exhibition teams are excluded even when ESPN labels them type 2. Duplicate player/date checks remain active for genuinely ambiguous regular-season data.
- Counts must be finite, nonnegative integers. Points must agree with made field goals, three-pointers and free throws; rebounds must equal offensive plus defensive rebounds; player points must add to both final team scores. PRA is always recomputed.
- A valid final box score takes precedence over a conflicting game log. The original and corrected observations are retained in an append-only correction log. Saved forecasts never change retroactively.
- Internally inconsistent older games are **quarantined, not repaired with invented numbers**. At most three of the 60 candidate games may be excluded this way, matching the training pipeline's exclusion of inconsistent games. If the most recent candidate regular-season game is inconsistent, more than three are inconsistent, or fewer than ten usable appearances remain, forecasting stops. Exclusion is not proof that ESPN's remaining stats equal official NBA records.
- An explicit DNP is excluded. Missing minutes are unknown, not zero. Missing minutes for the selected player stop the forecast; rounded zero-minute appearances are excluded and counted in the quality report. Missing identities are never inferred from names.
- Provider errors and expired cache entries do not silently fall back to stale data. Rosters/game logs/recent three summaries refresh after 15 minutes, schedules after five minutes, older summaries and the team list after a day. Requests are serialized and capped at three per second. ESPN's undocumented feeds can change or be unavailable.

ESPN feed families verified against live responses on September 27, 2026:

- `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams`
- Same base: `teams/{team_id}/roster`, `teams/{team_id}/schedule?season=2027&seasontype=2`, `summary?event={event_id}`
- `https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{athlete_id}/gamelog?season={ending_year}`

These URLs are observed interfaces, not a published stability guarantee. The adapter does not scrape ESPN HTML or bypass challenges.

## Local files and setup

- `cache/personal/nba.sqlite3`: cached public responses, observed stats/corrections, saved forecasts. Back up this file while the server is stopped to preserve your history. It is ignored by Git.
- `models/forecast/league.pkl` and `league.json`: the local trained model and integrity manifest. Already prepared on this computer; intentionally not committed. Only use artifacts you trust.
- `personal/`: the isolated FastAPI app and ESPN adapter. It never imports the hosted API's authentication or paid-data startup paths.
- `frontend/src/personal/`: the local React screens. They reuse the original `AppShell`, `PlayerSearchBase`, `PredictionCard`, theme and global stylesheet. The personal bundle does not include Supabase authentication.
- `frontend/dist-personal/`: the built local website, including the original logo assets. Already built on this computer. Rebuild after frontend source changes.
- `start_personal.ps1`: Windows launcher. For a different port: `powershell -File .\start_personal.ps1 -Port 8766`.

On a fresh checkout, install Python 3.12 and run from the repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r personal/requirements.txt
cd frontend
npm ci
npm run build:personal
cd ..
```

Copy your trusted model and matching manifest into `models/forecast/`, or reproduce the free offline rebuild:

```powershell
.\.venv\Scripts\python.exe -m pip install pyarrow
.\.venv\Scripts\python.exe scripts/rebuild_forecast.py prepare --download
.\.venv\Scripts\python.exe scripts/rebuild_forecast.py select
.\.venv\Scripts\python.exe scripts/rebuild_forecast.py fit-current --calibration-start 2026-01-01 --through 2026-04-13
.\start_personal.ps1
```

The pinned research dataset and these dates reproduce the current artifact, whose calibration ends April 12, 2026. They do not automatically retrain it for later seasons. Fresh game logs update the rolling inputs; fitted coefficients and calibration remain versioned. See `PREDICTOR_REBUILD_2026-09-27.md` for the frozen evaluation and limitations. The personal app does not silently train new models on live requests.

For a terminal-only launch: `.\.venv\Scripts\python.exe -m personal --no-browser`. If port 8765 belongs to another service, use `--port 8766`.

Export downloads the most recent 30 forecasts and 100 correction records as JSON. The database preserves older records too. Home shows four recent forecasts; Picks shows the available recent archive and correction records.

## Verification on this computer

The October 1 follow-up audit and current operational instructions are in [SEASON_READINESS_2026-10-01.md](SEASON_READINESS_2026-10-01.md). New double-click launchers provide readiness checks, forward scoring and consistent backups. Fresh installs can use `personal/requirements.lock.txt` to reproduce the verified Windows/Python 3.12 runtime. The dated results below describe earlier milestones.

- Automatic player selection update: 85 personal-mode and forecasting tests passed. Regression checks cover unconfirmed/questionable availability and type-2 All-Star exhibitions. Scottie Barnes's live history now contains 56 verified franchise appearances with the three same-day All-Star games excluded; his next-game prediction generates automatically. The model's duplicate-date validation remains unchanged.
- Earlier milestone: 184 focused tests passed across the personal adapter/app, forecasting engine and prior readiness regressions, including 39 personal-mode cases. Its legacy hosted test failures were subsequently addressed in the October 1 audit (851 passed, 4 skipped); live hosted deployment remains outside this local setup.
- Live ESPN checks covered Luka Doncic (59 usable games, one inconsistent game quarantined), Stephen Curry (57 usable games, three play-in games excluded), and Walker Kessler (60 historical Utah games despite current Lakers roster membership).
- A real upcoming Lakers matchup produced and saved all four forecasts through the browser, with no mocked data transport. No sportsbook quote or wager was fabricated in the live app.
- Cached Luka history requests took about 0.77–0.84 seconds locally, including parsing and reconciliation. First-time downloads take longer and depend on ESPN.
- Original-interface restoration: 81 personal-mode and forecasting tests passed, including current-roster search and direct navigation to React pages. Both personal and hosted production builds and frontend lint passed.
- Browser checks verified the original logo, theme, navigation and forecast cards; ESPN player search; forecast generation and reopening the saved result; upcoming games; and the research page. The saved-forecast layout was also checked at a 375-pixel viewport without horizontal page overflow. Use `npm run build:personal` after changing frontend source.
