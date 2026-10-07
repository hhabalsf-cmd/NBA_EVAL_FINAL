"""Adapter for observed ESPN public JSON feeds, verified September 2026.

No credentials or HTML scraping. These feeds are undocumented and may change.
Final summaries take precedence over game-log counts; malformed games fail closed.
"""
from datetime import datetime, timezone
import math
import threading
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests

SITE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'
WEB = 'https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/'
ET = ZoneInfo('America/New_York')
ALIASES = {'GS': 'GSW', 'NY': 'NYK', 'NO': 'NOP', 'SA': 'SAS', 'UTAH': 'UTA',
           'WSH': 'WAS', 'PHO': 'PHX', 'BRK': 'BKN'}
# ESPN identities of the 30 supported NBA franchises. Exhibition teams have
# separate IDs, even when ESPN assigns their games season type 2.
NBA_TEAM_IDS = frozenset(str(i) for i in range(1, 31))


class DataUnavailable(ValueError):
    pass


class BoxScoreMismatch(DataUnavailable):
    """A completed game's counts disagree internally; it must be quarantined."""


def canonical_team(value):
    return ALIASES.get(value, value)


def is_regular_nba_game(season_type, competition):
    competitors = competition['competitors']
    if len(competitors) != 2 or len({str(c['id']) for c in competitors}) != 2:
        raise DataUnavailable('Incomplete or duplicate game competitors.')
    if any('id' in c.get('team', {}) and str(c['id']) != str(c['team']['id']) for c in competitors):
        raise DataUnavailable('Game competitor team identity mismatch.')
    if {c['homeAway'] for c in competitors} != {'home', 'away'}:
        raise DataUnavailable('Game must identify one home and one away team.')
    return int(season_type) == 2 and all(str(c['id']) in NBA_TEAM_IDS for c in competitors)


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise DataUnavailable('ESPN returned a game time without a timezone.')
    return result


def count(value):
    result = float(value)
    if not math.isfinite(result) or result < 0 or not result.is_integer():
        raise DataUnavailable('ESPN returned an invalid counting statistic.')
    return int(result)


def shooting(value):
    made, attempted = map(count, value.split('-'))
    if made > attempted:
        raise DataUnavailable('Made shots exceed attempts.')
    return made, attempted


def parse_stats(values):
    """Use field labels, not positional assumptions or zero-filled missing values."""
    pts, reb, ast = (count(values[k]) for k in ('PTS', 'REB', 'AST'))
    raw_minutes = str(values['MIN'])
    if raw_minutes in ('--', ''):
        mins = None  # Unknown participation, not a DNP or zero-minute appearance.
    elif ':' in raw_minutes:
        minute, second = raw_minutes.split(':')
        minute, second = count(minute), count(second)
        if second >= 60:
            raise DataUnavailable('Invalid seconds in minutes played.')
        mins = minute + second / 60
    else:
        mins = float(raw_minutes)
    if mins is not None and (not math.isfinite(mins) or not 0 <= mins <= 80):
        raise DataUnavailable('Invalid minutes played.')
    fg, fga = shooting(values['FG'])
    three, three_a = shooting(values['3PT'])
    ft, _ = shooting(values['FT'])
    if three > fg or three_a > fga or pts != 2 * fg + three + ft:
        raise BoxScoreMismatch('Points disagree with made field goals and free throws.')
    if 'OREB' in values and 'DREB' in values and reb != count(values['OREB']) + count(values['DREB']):
        raise BoxScoreMismatch('Rebounds disagree with offensive and defensive rebounds.')
    return dict(MIN=mins, PTS=pts, REB=reb, AST=ast, PRA=pts + reb + ast)


def final_rows(payload, event_id):
    header = payload['header']
    comp = header['competitions'][0]
    status = comp['status']['type']
    if str(header['id']) != str(event_id) or not status.get('completed') or status.get('state') != 'post':
        raise DataUnavailable('A selected game does not have a final box score yet.')
    if not is_regular_nba_game(header['season']['type'], comp):
        raise DataUnavailable('Only regular-season games are supported by this model.')
    competitors = {str(c['id']): c for c in comp['competitors']}
    boxes = payload['boxscore']['players']
    if len(competitors) != 2 or {str(b['team']['id']) for b in boxes} != set(competitors):
        raise DataUnavailable('Incomplete team box scores.')
    date = instant(comp['date']).astimezone(ET).date().isoformat()
    rows, seen = {}, set()
    for box in boxes:
        team_id = str(box['team']['id'])
        competitor = competitors[team_id]
        blocks = box['statistics']
        if len(blocks) != 1:
            raise DataUnavailable('Unexpected ESPN box-score format.')
        block = blocks[0]
        points = 0
        for item in block['athletes']:
            raw_id = item['athlete'].get('id')
            pid = str(raw_id) if raw_id is not None else None
            if pid is not None and pid in seen:
                raise DataUnavailable('Duplicate athlete in a final box score.')
            if pid is not None:
                seen.add(pid)
            if item.get('didNotPlay') is True:
                continue
            if len(block['names']) != len(item['stats']):
                raise DataUnavailable('Incomplete player box score.')
            stats = parse_stats(dict(zip(block['names'], item['stats'])))
            points += stats['PTS']
            if pid is None:
                # Count toward team reconciliation, but never guess an identity from a name.
                continue
            rows[pid] = dict(PLAYER_ID=f'espn:{pid}', GAME_ID=f'espn:{event_id}',
                             GAME_DATE=date, TEAM=canonical_team(box['team']['abbreviation']),
                             HOME=int(competitor['homeAway'] == 'home'), **stats)
        if points != count(competitor['score']):
            raise BoxScoreMismatch('Player points do not add up to the final team score.')
    return rows


def regular_events(payload):
    """ESPN groups playoff and regular-season rows in the same game-log response."""
    output = {}
    for season in payload.get('seasonTypes', []):
        if not season['displayName'].endswith(' Regular Season'):
            continue
        for category in season.get('categories', []):
            if category.get('type') != 'event':
                continue
            for row in category.get('events', []):
                eid = str(row['eventId'])
                event = payload['events'][eid]
                if eid in output:
                    raise DataUnavailable('Duplicate regular-season game-log entry.')
                if len(payload['labels']) != len(row['stats']) or len(set(payload['labels'])) != len(payload['labels']):
                    raise DataUnavailable('Incomplete or duplicate ESPN game-log stat labels.')
                values = dict(zip(payload['labels'], row['stats']))
                output[eid] = (event, values)
    return output


class ESPN:
    def __init__(self, store):
        self.store = store
        self.session = requests.Session()
        self.lock = threading.Lock()
        self.last_request = 0.0

    def get(self, base, path, ttl=900):
        url = base + path
        hit = self.store.cached(url, ttl)
        if hit:
            return hit
        # One connection at a time, at most three requests/second, no retry storm.
        with self.lock:
            hit = self.store.cached(url, ttl)
            if hit:
                return hit
            time.sleep(max(0, .34 - (time.monotonic() - self.last_request)))
            try:
                response = self.session.get(url, timeout=(5, 20))
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError('Expected an object')
            except (requests.RequestException, ValueError) as exc:
                raise DataUnavailable('ESPN is unavailable. Try again later; stale data will not be used for a new forecast.') from exc
            finally:
                self.last_request = time.monotonic()
            return payload, self.store.cache(url, payload)

    def teams(self):
        data, fetched = self.get(SITE, 'teams', 86400)
        teams = data['sports'][0]['leagues'][0]['teams']
        return dict(teams=[dict(id=str(t['team']['id']), name=t['team']['displayName'],
                               abbreviation=canonical_team(t['team']['abbreviation'])) for t in teams
                           if t['team'].get('isActive') and not t['team'].get('isAllStar')], fetched_at=fetched)

    def roster(self, team_id):
        data, fetched = self.get(SITE, f'teams/{team_id}/roster')
        if str(data['team']['id']) != str(team_id):
            raise DataUnavailable('Roster team identity mismatch.')
        ids = [str(p['id']) for p in data['athletes']]
        if len(ids) != len(set(ids)):
            raise DataUnavailable('Duplicate player identity on ESPN roster.')
        return dict(team=data['team'], players=[dict(id=str(p['id']), name=p['displayName'],
                    position=p.get('position', {}).get('abbreviation', ''),
                    headshot=p.get('headshot', {}).get('href', ''),
                    injuries=p.get('injuries', [])) for p in data['athletes']], fetched_at=fetched)

    def search(self, query):
        """Search current rosters, retaining the team and ESPN athlete identity."""
        import unicodedata
        def key(value):
            return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))
        needle = key(query.strip())
        matches = {}
        for team in self.teams()['teams']:
            for player in self.roster(team['id'])['players']:
                if needle in key(player['name']):
                    if player['id'] in matches and matches[player['id']]['team_id'] != int(team['id']):
                        raise DataUnavailable('ESPN lists a matching player on multiple rosters. Refresh their current team before forecasting.')
                    matches[player['id']] = dict(player_id=int(player['id']), player_name=player['name'],
                        team_id=int(team['id']), team_abbrev=team['abbreviation'], team_name=team['name'],
                        headshot_url=player.get('headshot') or f"https://a.espncdn.com/i/headshots/nba/players/full/{player['id']}.png")
        return sorted(matches.values(), key=lambda p: p['player_name'])[:20]

    def schedule(self, team_id, now=None):
        now = now or datetime.now(timezone.utc)
        # July switches to the next season, including upcoming fall schedules.
        year = now.year + int(now.month >= 7)
        data, fetched = self.get(SITE, f'teams/{team_id}/schedule?season={year}&seasontype=2', 300)
        events = []
        seen = {}
        for event in data.get('events', []):
            comp = event['competitions'][0]
            if not is_regular_nba_game(event.get('seasonType', {}).get('type', 0), comp):
                continue
            if comp.get('neutralSite') or not comp.get('timeValid', event.get('timeValid', False)):
                continue
            status = comp['status']['type']
            if status.get('name') != 'STATUS_SCHEDULED' or status.get('completed') or status.get('state', 'pre') != 'pre' or instant(comp['date']) <= now:
                continue
            members = comp['competitors']
            selected = [c for c in members if str(c['id']) == str(team_id)]
            if len(selected) != 1 or len(members) != 2:
                raise DataUnavailable('Schedule team identity mismatch.')
            other = next(c for c in members if str(c['id']) != str(team_id))
            result = dict(id=str(event['id']), name=event['name'], starts_at=comp['date'],
                               home=selected[0]['homeAway'] == 'home',
                               team=canonical_team(selected[0]['team']['abbreviation']),
                               opponent=canonical_team(other['team']['abbreviation']))
            if result['id'] in seen:
                if seen[result['id']] != result:
                    raise DataUnavailable('ESPN returned conflicting schedule entries for the same event.')
                continue
            seen[result['id']] = result
            events.append(result)
        return dict(events=sorted(events, key=lambda e: e['starts_at']), fetched_at=fetched)

    def history(self, player_id, now=None):
        now = now or datetime.now(timezone.utc)
        year = now.year + int(now.month >= 7)
        candidates, stamps = {}, []
        for season in range(year, year - 3, -1):
            data, stamp = self.get(WEB, f'athletes/{player_id}/gamelog?season={season}', 900)
            stamps.append(stamp)
            for eid, entry in regular_events(data).items():
                if eid in candidates and candidates[eid] != entry:
                    raise DataUnavailable('Conflicting game-log entries across ESPN seasons.')
                candidates[eid] = entry
            if len(candidates) >= 60:
                break
        today = now.astimezone(ET).date()
        ordered = sorted(candidates.items(), key=lambda item: instant(item[1][0]['gameDate']))
        ordered = [item for item in ordered if instant(item[1][0]['gameDate']).astimezone(ET).date() < today][-60:]
        if not ordered:
            raise DataUnavailable('No completed regular-season NBA history is available for this player.')
        rows, corrections, zero_minutes, quarantined, non_regular, dnps = [], 0, 0, [], [], []
        last_regular_id = None
        for index, (eid, (event, values)) in enumerate(ordered):
            # Recent games refresh every 15 minutes for corrections; older ones daily.
            payload, stamp = self.get(SITE, f'summary?event={eid}', 900 if index >= len(ordered) - 3 else 86400)
            stamps.append(stamp)
            if str(payload['header']['id']) != eid:
                raise DataUnavailable('Final box-score event identity mismatch.')
            if not is_regular_nba_game(payload['header']['season']['type'], payload['header']['competitions'][0]):
                # ESPN includes play-in and type-2 All-Star exhibitions in some
                # "Regular Season" logs. These are not NBA franchise games.
                non_regular.append(eid)
                continue
            previous_regular_id = last_regular_id
            last_regular_id = eid
            try:
                row = final_rows(payload, eid).get(str(player_id))
            except BoxScoreMismatch as exc:
                # Match offline training's exclusion of inconsistent games. Never invent
                # a repair or silently discard the most recent outcome before forecasting.
                quarantined.append(dict(event_id=eid, date=event['gameDate'], reason=str(exc)))
                if len(quarantined) > 3:
                    raise DataUnavailable(f'History cannot be verified: {exc} Game {eid}.') from exc
                continue
            if row is None:
                if any(str(item['athlete'].get('id')) == str(player_id) and item.get('didNotPlay') is True
                       for box in payload['boxscore']['players'] for block in box['statistics'] for item in block['athletes']):
                    dnps.append(eid)
                    last_regular_id = previous_regular_id
                    continue
                raise DataUnavailable(f'Player missing from final box score {eid}; history needs reconciliation.')
            if row['MIN'] is None:
                raise DataUnavailable(f'Player minutes are missing from final box score {eid}.')
            if row['GAME_DATE'] != instant(event['gameDate']).astimezone(ET).date().isoformat():
                raise DataUnavailable('Game-log date disagrees with the final box score.')
            reference = dict(row)
            for field in ('MIN', 'PTS', 'REB', 'AST'):
                reference[field] = values.get(field)  # Preserve even malformed source values.
                try:
                    numeric = float(reference[field])
                    if math.isfinite(numeric):
                        reference[field] = numeric
                except (ValueError, TypeError):
                    pass
            try:
                reference['PRA'] = sum(float(reference[k]) for k in ('PTS', 'REB', 'AST'))
                if not math.isfinite(reference['PRA']):
                    reference['PRA'] = None
            except (ValueError, TypeError):
                reference['PRA'] = None
            corrections += self.store.reconcile(row['GAME_ID'] + ':' + row['PLAYER_ID'], row, reference)
            # ESPN can round a sub-minute appearance to 0. Do not invent playing time.
            if row['MIN'] == 0:
                zero_minutes += 1
                continue
            rows.append(row)
        if any(q['event_id'] == last_regular_id for q in quarantined):
            raise DataUnavailable(f'The most recent regular-season box score is inconsistent: game {last_regular_id}.')
        if len(rows) < 10:
            raise DataUnavailable(f'Need 10 prior appearances with usable minutes; ESPN provided {len(rows)}.')
        if pd.DataFrame(rows).duplicated(['PLAYER_ID', 'GAME_DATE']).any():
            raise DataUnavailable('Conflicting regular-season games share a player/date. No history or forecast will be used until ESPN resolves them.')
        return pd.DataFrame(rows), dict(source='ESPN final box scores', player_id_namespace='espn',
                    checked_at=now.isoformat(), oldest_fetch=min(stamps), newest_fetch=max(stamps),
                    verified_games=len(rows), corrections_this_refresh=corrections,
                    excluded_zero_minute_rows=zero_minutes, quarantined_games=quarantined,
                    excluded_non_regular_games=non_regular, excluded_dnp_games=dnps)
