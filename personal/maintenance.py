"""Local readiness checks, consistent backups, and forward forecast scoring.

python -m personal.maintenance check --online --players 4433134,3945274,3975
python -m personal.maintenance score
python -m personal.maintenance backup
Nothing here places bets, changes model coefficients, or rewrites predictions.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from forecasting.features import STATS, normalize_logs
from forecasting.service import load_model, forecast_player
from personal.espn import ESPN, SITE, DataUnavailable, final_rows, instant, ET
from personal.store import Store

ROOT = Path(__file__).resolve().parents[1]


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def check(store, provider=None, players=(), now=None):
    now = now or datetime.now(timezone.utc)
    report = dict(checked_at=now.isoformat(), checks={}, errors=[], warnings=[], samples=[])
    model = None
    try:
        model = load_model()
        report['checks']['model'] = {k: model.metadata[k] for k in (
            'version', 'trained_through', 'calibrated_through', 'artifact_sha256', 'betting_validated')}
        if instant(model.metadata['calibrated_through'] + 'T00:00:00Z').date() >= now.astimezone(ET).date():
            raise ValueError('Model calibration is not strictly before today.')
        # Calendar-season check: a healthy off-season artifact can be months old.
        previous_end_year = now.year if now.month >= 7 else now.year - 1
        if model.metadata['calibrated_through'] < f'{previous_end_year}-04-01':
            report['warnings'].append('The model predates the last completed regular season; evaluate a refreshed artifact before relying on it.')
        report['warnings'].append('Priced betting profitability is unvalidated. Predictions remain research output.')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        report['errors'].append(f'Model: {exc}')
    with store.connect() as db:
        integrity = db.execute('PRAGMA quick_check').fetchone()[0]
        report['checks']['database'] = integrity
        report['checks']['saved_forecasts'] = db.execute('SELECT COUNT(*) FROM forecasts').fetchone()[0]
    if integrity != 'ok':
        report['errors'].append('Local database integrity check failed.')
    built = ROOT / 'frontend' / 'dist-personal' / 'personal.html'
    report['checks']['frontend_built'] = built.exists()
    if not built.exists():
        report['errors'].append('Run npm run build:personal in frontend/.')
    if provider is not None:
        try:
            teams = provider.teams()['teams']
            ids = [t['id'] for t in teams]
            if len(ids) != 30 or len(set(ids)) != 30:
                raise DataUnavailable('Expected 30 distinct NBA franchise rosters.')
            report['checks']['teams'] = len(teams)
        except (DataUnavailable, KeyError, TypeError, ValueError) as exc:
            report['errors'].append(f'Team feed: {exc}')
            teams = []
        locations, schedules, event_context = {}, {}, {}
        for team in teams:
            try:
                roster = provider.roster(team['id'])['players']
                for player in roster:
                    if player['id'] in locations:
                        report['errors'].append(f"Player {player['id']} appears on more than one current roster.")
                    locations[player['id']] = (team, player)
                events = provider.schedule(team['id'], now=now)['events']
                schedules[team['id']] = events
                for event in events:
                    home, away = (event['team'], event['opponent']) if event['home'] else (event['opponent'], event['team'])
                    context = (instant(event['starts_at']), home, away)
                    if event['id'] in event_context and event_context[event['id']] != context:
                        report['errors'].append(f"Conflicting team schedules for event {event['id']}.")
                    event_context[event['id']] = context
                if not events:
                    report['warnings'].append(f"No supported upcoming game for {team['abbreviation']}.")
            except (DataUnavailable, KeyError, TypeError, ValueError) as exc:
                report['errors'].append(f"{team['name']}: {exc}")
        report['checks'].update(roster_players=len(locations), schedules_checked=len(schedules),
                                upcoming_events=len(event_context),
                                first_tipoff=min((c[0].isoformat() for c in event_context.values()), default=None))
        for pid in players:
            sample = {'player_id': pid}
            try:
                team, player = locations[pid]
                sample['player_name'] = player['name']
                history, quality = provider.history(pid, now=now)
                normalize_logs(history)
                sample.update(quality=quality, rows=len(history))
                statuses = {str(i.get('status', '')).strip().lower() for i in player['injuries']}
                events = schedules.get(team['id'], [])
                if statuses & {'out', 'suspended', 'suspension'}:
                    sample['status'] = 'out; forecast correctly withheld'
                elif events and model is not None:
                    event = events[0]
                    result = forecast_player(history, model=model, player_id=f'espn:{pid}',
                        event_id=f"espn:{event['id']}", starts_at=instant(event['starts_at']),
                        team=event['team'], home=event['home'], as_of=now,
                        availability='questionable' if statuses else 'unknown')
                    sample.update(status='passed', event=event, predictions=result['predictions'])
                else:
                    sample['status'] = 'history passed; no upcoming game/model available'
            except (DataUnavailable, KeyError, TypeError, ValueError) as exc:
                sample['error'] = str(exc)
                report['errors'].append(f'Sample {pid}: {exc}')
            report['samples'].append(sample)
    report['ready_for_research'] = not report['errors']
    report['ready_for_betting'] = False
    return report


def score(store, provider, now=None):
    """Score the latest pre-tipoff snapshot per player/event; keep prior revisions."""
    now = now or datetime.now(timezone.utc)
    with store.connect() as db:
        records = db.execute('SELECT id,body FROM forecasts ORDER BY id').fetchall()
        db.execute('''CREATE TABLE IF NOT EXISTS forecast_evaluations (
            id INTEGER PRIMARY KEY, forecast_id INTEGER, observed TEXT, actual_sha256 TEXT, body TEXT,
            UNIQUE(forecast_id, actual_sha256))''')
    latest, invalid = {}, []
    for ident, body in records:
        try:
            f = json.loads(body)
            # Compare both stored event times; do not grade mismatched identities.
            start = instant(f['event']['starts_at'])
            if f['event_id'] != f"espn:{f['event']['id']}" or not f['player_id'].startswith('espn:'):
                raise ValueError('Invalid ESPN identity')
            if instant(f['as_of']) >= start:
                raise ValueError('Snapshot is not pregame')
            key = (f['event_id'], f['player_id'])
            if key not in latest or instant(f['as_of']) > instant(latest[key][1]['as_of']):
                latest[key] = (ident, f)
        except (KeyError, TypeError, ValueError) as exc:
            invalid.append({'forecast_id': ident, 'reason': str(exc)})
    report = dict(checked_at=now.isoformat(), pending=0, dnp=0, scored=0, errors=invalid, models={})
    groups = defaultdict(lambda: defaultdict(list))
    for ident, f in latest.values():
        if instant(f['event']['starts_at']) >= now:
            report['pending'] += 1
            continue
        try:
            payload, _ = provider.get(SITE, f"summary?event={f['event']['id']}", 900)
            competition = payload['header']['competitions'][0]
            if str(payload['header']['id']) != str(f['event']['id']):
                raise DataUnavailable('Final event identity mismatch')
            if not competition['status']['type'].get('completed'):
                report['pending'] += 1
                continue
            if instant(f['as_of']) >= instant(competition['date']):
                raise DataUnavailable('Snapshot was not before actual tipoff')
            rows = final_rows(payload, f['event']['id'])
            pid = f['player_id'].split(':', 1)[1]
            row = rows.get(pid)
            if row is None:
                dnp = any(str(p['athlete'].get('id')) == pid and p.get('didNotPlay') is True
                    for b in payload['boxscore']['players'] for s in b['statistics'] for p in s['athletes'])
                if not dnp:
                    raise DataUnavailable('Player identity missing from final box score')
                report['dnp'] += 1
                continue
            if row['MIN'] is None:
                raise DataUnavailable('Participation minutes unavailable')
            if row['MIN'] == 0:
                report['dnp'] += 1
                continue
            values = {}
            model = f['model'].get('artifact_sha256', 'unversioned')
            for stat in STATS:
                prediction = f['predictions'][stat]
                delta = float(prediction['prediction']) - row[stat]
                if not np.isfinite(delta):
                    raise ValueError('Non-finite saved prediction')
                values[stat] = dict(actual=row[stat], error=delta,
                    covered=prediction['range_low'] <= row[stat] <= prediction['range_high'])
                baseline = f.get('baselines', {}).get(stat, {}).get('last_20')
                if baseline is not None:
                    if not np.isfinite(baseline):
                        raise ValueError('Non-finite saved baseline')
                    values[stat]['baseline_error'] = float(baseline) - row[stat]
            digest = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
            with store.connect() as db:
                db.execute('INSERT OR IGNORE INTO forecast_evaluations(forecast_id,observed,actual_sha256,body) VALUES (?,?,?,?)',
                    (ident, now.isoformat(), digest, json.dumps({'actual': row, 'metrics': values, 'model': model})))
            for stat, value in values.items():
                groups[model][stat].append(value)
            report['scored'] += 1
        except (DataUnavailable, KeyError, TypeError, ValueError) as exc:
            report['errors'].append({'forecast_id': ident, 'reason': str(exc)})
    for model, stats in groups.items():
        report['models'][model] = {s: dict(n=len(v), mae=float(np.mean([abs(x['error']) for x in v])),
            bias=float(np.mean([x['error'] for x in v])), coverage_80=float(np.mean([x['covered'] for x in v]))) for s, v in stats.items()}
        for stat, values in stats.items():
            paired = [v for v in values if 'baseline_error' in v]
            report['models'][model][stat].update(baseline_n=len(paired),
                baseline_l20_mae=float(np.mean([abs(v['baseline_error']) for v in paired])) if paired else None,
                mae_minus_l20=float(np.mean([abs(v['error']) - abs(v['baseline_error']) for v in paired])) if paired else None)
    report['note'] = 'Forward point-forecast evaluation only. DNPs are excluded; no betting ROI or profitability claim.'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'score', 'backup'])
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--players', default='', help='Comma-separated ESPN player IDs for extra history/inference checks')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    store = Store(ROOT / 'cache' / 'personal' / 'nba.sqlite3')
    if args.action == 'backup':
        path = args.output or ROOT / 'cache' / 'personal' / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
        print(store.backup(path))
        return
    report = check(store, ESPN(store) if args.online else None, [p.strip() for p in args.players.split(',') if p.strip()]) if args.action == 'check' else score(store, ESPN(store))
    path = args.output or ROOT / 'cache' / 'personal' / f'{args.action}-report.json'
    write_report(path, report)
    print(json.dumps(report, indent=2, allow_nan=False), flush=True)
    print(f'Report saved: {path}')
    if report.get('errors'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
