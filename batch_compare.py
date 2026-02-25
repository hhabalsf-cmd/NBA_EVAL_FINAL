import sys
sys.path.insert(0, '/Users/hhabal/Downloads/Projects/NBA/EVAL')

import warnings
warnings.filterwarnings('ignore')
import pandas as pd
from datetime import datetime

PICKS = [
    {"id": 141, "player": "Tyrese Maxey",       "stat": "AST", "line": 6.5,  "old_pred": 12.1, "direction": "OVER",  "old_edge": 86.15},
    {"id": 142, "player": "Jarrett Allen",       "stat": "REB", "line": 8.5,  "old_pred": 12.6, "direction": "OVER",  "old_edge": 48.24},
    {"id": 143, "player": "James Harden",        "stat": "AST", "line": 7.5,  "old_pred": 12.2, "direction": "OVER",  "old_edge": 62.67},
    {"id": 144, "player": "Desmond Bane",        "stat": "PTS", "line": 19.5, "old_pred": 11.7, "direction": "UNDER", "old_edge": -40.0},
    {"id": 145, "player": "Karl-Anthony Towns",  "stat": "AST", "line": 2.5,  "old_pred": 3.7,  "direction": "OVER",  "old_edge": 48.0},
    {"id": 146, "player": "Chet Holmgren",       "stat": "PTS", "line": 17.5, "old_pred": 22.0, "direction": "OVER",  "old_edge": 25.71},
    {"id": 147, "player": "Tristan Vukcevic",    "stat": "PTS", "line": 12.5, "old_pred": 6.8,  "direction": "UNDER", "old_edge": -45.6},
    {"id": 148, "player": "Bilal Coulibaly",     "stat": "PTS", "line": 10.5, "old_pred": 15.9, "direction": "OVER",  "old_edge": 51.43},
    {"id": 149, "player": "Bilal Coulibaly",     "stat": "PRA", "line": 15.5, "old_pred": 25.6, "direction": "OVER",  "old_edge": 65.16},
    {"id": 150, "player": "Isaiah Joe",          "stat": "AST", "line": 2.5,  "old_pred": 1.3,  "direction": "UNDER", "old_edge": -48.0},
    {"id": 151, "player": "Jared McCain",        "stat": "PTS", "line": 10.5, "old_pred": 13.5, "direction": "OVER",  "old_edge": 28.57},
    {"id": 152, "player": "Scottie Barnes",      "stat": "AST", "line": 4.5,  "old_pred": 6.0,  "direction": "OVER",  "old_edge": 33.33},
    {"id": 153, "player": "Luguentz Dort",       "stat": "REB", "line": 3.5,  "old_pred": 5.0,  "direction": "OVER",  "old_edge": 42.86},
    {"id": 154, "player": "Jamal Shead",         "stat": "REB", "line": 1.5,  "old_pred": 2.9,  "direction": "OVER",  "old_edge": 93.33},
    {"id": 155, "player": "Isaiah Hartenstein",  "stat": "AST", "line": 4.5,  "old_pred": 1.1,  "direction": "UNDER", "old_edge": -75.56},
    {"id": 156, "player": "Nolan Traore",        "stat": "REB", "line": 2.5,  "old_pred": 1.1,  "direction": "UNDER", "old_edge": -56.0},
    {"id": 157, "player": "Max Christie",        "stat": "PTS", "line": 14.5, "old_pred": 9.0,  "direction": "UNDER", "old_edge": -37.93},
    {"id": 158, "player": "OG Anunoby",          "stat": "PTS", "line": 16.6, "old_pred": 21.7, "direction": "OVER",  "old_edge": 30.72},
    {"id": 159, "player": "Gui Santos",          "stat": "AST", "line": 3.5,  "old_pred": 0.5,  "direction": "UNDER", "old_edge": -85.71},
    {"id": 160, "player": "Anthony Edwards",     "stat": "AST", "line": 3.5,  "old_pred": 5.3,  "direction": "OVER",  "old_edge": 51.43},
    {"id": 161, "player": "Julius Randle",       "stat": "REB", "line": 7.5,  "old_pred": 9.0,  "direction": "OVER",  "old_edge": 20.0},
    {"id": 162, "player": "LeBron James",        "stat": "PTS", "line": 17.5, "old_pred": 22.6, "direction": "OVER",  "old_edge": 29.14},
    {"id": 163, "player": "Tyler Herro",         "stat": "PTS", "line": 17.5, "old_pred": 29.6, "direction": "OVER",  "old_edge": 69.14},
]

print("Loading NBA evaluator modules...")
from nba_evaluator import NBADataScraper, FeatureEngineer, MLPredictor

print("Initializing scraper and loading team stats...")
scraper    = NBADataScraper()
team_stats = scraper.get_team_defensive_stats()
injuries   = scraper.get_injury_report()
print("Setup done.\n")

results = []

# Cache per-player data so Bilal Coulibaly isn't fetched twice
player_cache = {}

for i, pick in enumerate(PICKS):
    player = pick["player"]
    stat   = pick["stat"]
    line   = pick["line"]
    print(f"[{i+1}/{len(PICKS)}] {player} {stat} {line} ...", flush=True)

    try:
        if player not in player_cache:
            player_info = scraper.get_player_info(player)
            if not player_info:
                print(f"  SKIP: player not found")
                results.append({**pick, "new_pred": None, "error": "player not found"})
                player_cache[player] = None
                continue

            game_log = scraper.get_player_game_log(player_info['player_id'])
            if game_log is None or game_log.empty:
                print(f"  SKIP: no game logs")
                results.append({**pick, "new_pred": None, "error": "no game logs"})
                player_cache[player] = None
                continue

            df = FeatureEngineer.create_features(game_log, team_stats=team_stats)
            if df is None or df.empty:
                print(f"  SKIP: feature engineering failed")
                results.append({**pick, "new_pred": None, "error": "feature engineering failed"})
                player_cache[player] = None
                continue

            game_info = scraper.get_player_next_game(player_info)
            is_home  = game_info.get('is_home', 0) if game_info else 0
            opponent = game_info.get('opponent', '') if game_info else ''

            vs_stats = None
            if game_info:
                try:
                    vs_stats = scraper.get_vs_team_stats(player_info['player_id'], opponent)
                except Exception:
                    pass

            opp_def_rating  = team_stats.get(opponent, {}).get('def_rating', 110)
            opp_pace        = team_stats.get(opponent, {}).get('pace', 100)
            opp_ast_allowed = team_stats.get(opponent, {}).get('opp_ast', 25)
            team_abbrev     = player_info.get('team_abbrev', '')
            injuries_team   = injuries.get(team_abbrev, {}).get('out', 0)
            injuries_opp    = injuries.get(opponent, {}).get('out', 0)

            features_df = FeatureEngineer.get_prediction_features(
                df, is_home, opponent,
                injuries_team=injuries_team,
                injuries_opp=injuries_opp,
                opp_def_rating=opp_def_rating,
                opp_pace=opp_pace,
                opp_ast_allowed=opp_ast_allowed,
                vs_stats=vs_stats
            )

            days_rest_val = 2
            if 'GAME_DATE' in df.columns and len(df) > 1:
                last_game = pd.to_datetime(df['GAME_DATE'].iloc[-1])
                days_rest_val = min((datetime.now() - last_game).days, 7)
            estimated_minutes = FeatureEngineer.estimate_minutes(
                df, is_home, days_rest_val, injuries_team
            )

            # Train model (gradient_boost to match stored picks)
            predictor = MLPredictor(model_type='gradient_boost', use_ensemble=False)
            if predictor.load(player):
                predictor.update(df)
            else:
                print(f"  Training new model for {player}...")
                if not predictor.train(df):
                    print(f"  SKIP: training failed")
                    results.append({**pick, "new_pred": None, "error": "training failed"})
                    player_cache[player] = None
                    continue

            predictor._update_recent_averages(df)
            preds = predictor.predict(features_df, estimated_minutes=estimated_minutes)
            preds = predictor.apply_injury_boost(preds, injuries_team, injuries_opp)

            player_cache[player] = preds
        else:
            preds = player_cache[player]

        if preds is None:
            results.append({**pick, "new_pred": None, "error": "cached failure"})
            continue

        if stat not in preds:
            print(f"  SKIP: stat {stat} not in predictions (have: {list(preds.keys())})")
            results.append({**pick, "new_pred": None, "error": f"stat {stat} not predicted"})
            continue

        new_pred = preds[stat]
        print(f"  OLD: {pick['old_pred']}  ->  NEW: {new_pred:.1f}  (delta {new_pred - pick['old_pred']:+.1f})", flush=True)
        results.append({**pick, "new_pred": new_pred, "error": None})

    except Exception as e:
        import traceback
        tb = traceback.format_exc().strip().splitlines()[-1]
        print(f"  ERROR: {tb}", flush=True)
        results.append({**pick, "new_pred": None, "error": tb[:100]})

# ── Summary table ────────────────────────────────────────────────────────────
W = 112
print("\n" + "="*W)
print("COMPARISON SUMMARY")
print("="*W)
print(f"{'ID':<5} {'Player':<22} {'St':<4} {'Line':<6} {'Old':>7} {'New':>7} {'Delta':>7}  {'Old Dir':<8} {'New Dir':<8} {'Flag'}")
print("-"*W)

flips      = []
big_shifts = []

for r in results:
    if r['new_pred'] is None:
        err = r.get('error', '')[:60]
        print(f"{r['id']:<5} {r['player']:<22} {r['stat']:<4} {r['line']:<6} {r['old_pred']:>7.1f} {'ERROR':>7} {'':>7}  {r['direction']:<8} {'N/A':<8} [{err}]")
        continue

    delta   = r['new_pred'] - r['old_pred']
    new_dir = "OVER" if r['new_pred'] > r['line'] else "UNDER"
    flipped = (new_dir != r['direction'])
    flags   = []
    if flipped:
        flags.append("*** FLIP ***")
    if abs(delta) >= 3.0:
        flags.append(f"shift {delta:+.1f}")
    flag_str = "  ".join(flags)

    print(f"{r['id']:<5} {r['player']:<22} {r['stat']:<4} {r['line']:<6} {r['old_pred']:>7.1f} {r['new_pred']:>7.1f} {delta:>+7.1f}  {r['direction']:<8} {new_dir:<8} {flag_str}")

    if flipped:
        flips.append(r)
    if abs(delta) >= 3.0:
        big_shifts.append(r)

print("\n" + "="*W)
print(f"DIRECTION FLIPS ({len(flips)}):")
if flips:
    for r in flips:
        d       = r['new_pred'] - r['old_pred']
        new_dir = "OVER" if r['new_pred'] > r['line'] else "UNDER"
        new_edge = (r['new_pred'] - r['line']) / r['line'] * 100
        print(f"  *** {r['player']} {r['stat']} @ {r['line']}")
        print(f"      was {r['direction']} (pred {r['old_pred']}, edge {r['old_edge']:+.1f}%)")
        print(f"      now {new_dir} (pred {r['new_pred']:.1f}, edge {new_edge:+.1f}%,  delta {d:+.1f})")
else:
    print("  (none)")

print(f"\nBIG SHIFTS ≥3.0 ({len(big_shifts)}):")
if big_shifts:
    for r in big_shifts:
        d   = r['new_pred'] - r['old_pred']
        pct = d / r['old_pred'] * 100 if r['old_pred'] else 0
        print(f"  {r['player']} {r['stat']}:  {r['old_pred']} → {r['new_pred']:.1f}  ({d:+.1f}, {pct:+.0f}%)")
else:
    print("  (none)")

errors = [r for r in results if r['new_pred'] is None]
print(f"\nTotal: {len(PICKS)} picks  |  Errors: {len(errors)}  |  Flips: {len(flips)}  |  Big shifts: {len(big_shifts)}")
if errors:
    print("\nError details:")
    for r in errors:
        print(f"  {r['player']} {r['stat']}: {r.get('error','')}")
