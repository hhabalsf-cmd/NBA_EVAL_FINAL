"""No network: observed ESPN schema, corrections, and isolated local-app boundaries."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from forecasting.model import CountDistribution
from personal.espn import ESPN, SITE, DataUnavailable, final_rows, parse_stats, regular_events, canonical_team
from personal.store import Store


@pytest.fixture
def box():
    return json.loads((Path(__file__).parent / 'fixtures' / 'espn_final_401811041.json').read_text())


def test_real_final_box_score(box):
    rows = final_rows(box, '401811041')
    paolo = rows['4432573']
    assert paolo == dict(PLAYER_ID='espn:4432573', GAME_ID='espn:401811041', GAME_DATE='2026-04-12',
                         TEAM='ORL', HOME=0, MIN=38, PTS=23, REB=10, AST=11, PRA=44)
    assert '3150844' not in rows  # explicit DNP


@pytest.mark.parametrize('field,value', [('PTS','24'), ('REB','11'), ('AST','-1'), ('AST','1.5'),
                                       ('MIN','NaN'), ('MIN','34:75'), ('FG','4-3'), ('3PT','8-30')])
def test_stat_corruption_rejected(box, field, value):
    block = box['boxscore']['players'][0]['statistics'][0]
    block['athletes'][0]['stats'][block['names'].index(field)] = value
    with pytest.raises((DataUnavailable, ValueError)):
        final_rows(box, '401811041')


def test_missing_minutes_are_unknown_and_unidentified_players_not_guessed(box):
    block = box['boxscore']['players'][0]['statistics'][0]
    item = block['athletes'][0]
    item['stats'][block['names'].index('MIN')] = '--'
    assert final_rows(box, '401811041')['4432573']['MIN'] is None
    item['athlete'] = {'shortName': 'Banchero'}
    assert '4432573' not in final_rows(box, '401811041')


@pytest.mark.parametrize('mutation', ['in_progress','wrong_event','postseason','team_points','missing_team','duplicate','missing_stat'])
def test_invalid_final_games_fail_closed(box, mutation):
    eid = '401811041'
    if mutation == 'in_progress': box['header']['competitions'][0]['status']['type']['completed'] = False
    if mutation == 'wrong_event': eid = '999'
    if mutation == 'postseason': box['header']['season']['type'] = 3
    if mutation == 'team_points': box['header']['competitions'][0]['competitors'][0]['score'] = '999'
    if mutation == 'missing_team': box['boxscore']['players'].pop()
    if mutation == 'duplicate': box['boxscore']['players'][0]['statistics'][0]['athletes'].append(copy.deepcopy(box['boxscore']['players'][0]['statistics'][0]['athletes'][0]))
    if mutation == 'missing_stat': box['boxscore']['players'][0]['statistics'][0]['athletes'][0]['stats'].pop()
    with pytest.raises(DataUnavailable): final_rows(box, eid)


def test_minutes_and_pra_are_normalized():
    values = dict(MIN='12:30', PTS='9', REB='4', AST='2', FG='3-7', **{'3PT':'1-3','FT':'2-2'})
    assert parse_stats(values) == dict(MIN=12.5, PTS=9, REB=4, AST=2, PRA=15)
    assert canonical_team('GS') == 'GSW'


def test_type_two_all_star_game_is_not_regular_nba_history(box):
    competitor = box['header']['competitions'][0]['competitors'][0]
    competitor['id'] = '132374'
    competitor['team'] = {'id': '132374', 'abbreviation': 'STARS'}
    assert box['header']['season']['type'] == 2
    with pytest.raises(DataUnavailable, match='Only regular-season games'):
        final_rows(box, '401811041')


def test_game_logs_exclude_playoffs_and_duplicates():
    regular = {'displayName':'2025-26 Regular Season', 'categories':[{'type':'event','events':[{'eventId':'1','stats':['9']}]}]}
    postseason = {'displayName':'2025-26 Postseason', 'categories':[{'type':'event','events':[{'eventId':'2','stats':['99']}]}]}
    data = {'seasonTypes':[postseason, regular], 'labels':['PTS'], 'events':{'1':{'gameDate':'2026-01-01T01:00Z'},'2':{}}}
    assert list(regular_events(data)) == ['1']
    data['seasonTypes'].append(regular)
    with pytest.raises(DataUnavailable): regular_events(data)


def test_corrections_do_not_mutate_old_forecasts(tmp_path):
    store = Store(tmp_path / 'test.sqlite3')
    before = dict(MIN=30.0, PTS=20, REB=5, AST=3, PRA=28)
    assert not store.reconcile('p:g', before, {**before, 'PTS':20.0})
    store.save_forecast({'observed':before})
    after = {**before, 'AST':4, 'PRA':29}
    assert store.reconcile('p:g', after)
    assert not store.reconcile('p:g', after)
    assert len(store.corrections()) == 1
    assert store.corrections()[0]['before']['AST'] == 3
    assert store.forecasts()[0]['forecast']['observed']['AST'] == 3


def test_cache_expiry_and_failure_never_silently_use_stale_data(tmp_path, monkeypatch):
    store = Store(tmp_path / 'test.sqlite3')
    provider = ESPN(store)
    store.cache(SITE + 'test', {'ok':True})
    assert provider.get(SITE, 'test')[0] == {'ok':True}
    with store.connect() as db: db.execute('UPDATE cache SET fetched=0')
    import requests
    def fail(*args, **kwargs): raise requests.ConnectionError('offline')
    monkeypatch.setattr(provider.session, 'get', fail)
    with pytest.raises(DataUnavailable): provider.get(SITE, 'test')


def test_schedule_excludes_postponed_preseason_neutral_and_wrong_team(tmp_path, monkeypatch):
    provider = ESPN(Store(tmp_path / 'test.sqlite3'))
    now = datetime(2026,9,27,tzinfo=timezone.utc)
    event = dict(id='11', name='GS at LAL', seasonType={'type':2}, competitions=[dict(
        date='2026-10-22T02:00Z', timeValid=True, status={'type':{'name':'STATUS_SCHEDULED'}},
        competitors=[{'id':'13','homeAway':'home','team':{'abbreviation':'LAL'}},
                     {'id':'9','homeAway':'away','team':{'abbreviation':'GS'}}])])
    variants = [copy.deepcopy(event) for _ in range(3)]
    variants[0]['seasonType']['type'] = 1
    variants[1]['competitions'][0]['status']['type']['name'] = 'STATUS_POSTPONED'
    variants[2]['competitions'][0]['neutralSite'] = True
    paths=[]
    def get(base,path,ttl): paths.append(path); return {'events':[event]+variants}, 1
    monkeypatch.setattr(provider,'get',get)
    result=provider.schedule('13',now)
    assert len(result['events']) == 1 and result['events'][0]['opponent'] == 'GSW'
    assert 'season=2027' in paths[0]
    with pytest.raises(DataUnavailable): provider.schedule('30',now)


@pytest.fixture
def local_app(tmp_path, monkeypatch):
    import personal.app as module
    store = Store(tmp_path / 'local.sqlite3')
    now = datetime.now(timezone.utc)
    dates = pd.date_range(end=(now - timedelta(days=2)).date(), periods=15, freq='2D')
    logs = pd.DataFrame([dict(PLAYER_ID='espn:1', GAME_DATE=d, TEAM='LAL', HOME=1, MIN=30, PTS=20, REB=5, AST=5) for d in dates])
    event = dict(id='9', name='GSW at LAL', starts_at=(now + timedelta(days=2)).isoformat(), team='LAL', opponent='GSW', home=True)
    player = dict(id='1', name='Test Player', injuries=[])
    provider = SimpleNamespace(roster=lambda team:dict(players=[player]),
         schedule=lambda team,now=None:dict(events=[event]),
         history=lambda pid,now=None:(logs,dict(verified_games=15)))
    distributions={s:CountDistribution(v,2,np.array([-1.,0.,1.])) for s,v in [('PTS',20),('REB',5),('AST',5),('PRA',30)]}
    model=SimpleNamespace(metadata={'calibrated_through':'2026-04-12'}, distributions=lambda f,d:distributions)
    monkeypatch.setattr(module,'load_model',lambda:model)
    frontend=tmp_path/'frontend'
    frontend.mkdir()
    (frontend/'personal.html').write_text('<html><body>Personal app shell</body></html>')
    app=module.create_app(store,provider,frontend_dir=frontend)
    client=TestClient(app,base_url='http://127.0.0.1:8765',client=('127.0.0.1',12345))
    return client,store,provider,player


def test_local_forecast_uses_verified_context_and_saves(local_app):
    client,store,provider,player=local_app
    response=client.post('/api/forecast',json=dict(team_id='13', player_id='1', event_id='9', availability='available',
        quote=dict(stat='PTS',side='OVER',line=20,american_odds=-110,book='Manual')))
    assert response.status_code == 200, response.text
    body=response.json()
    assert body['event_id'] == 'espn:9' and body['player_id'] == 'espn:1'
    assert body['offers'][0]['prob_push'] > 0 and body['offers'][0]['recommend'] is False
    assert len(store.forecasts()) == 1
    assert client.get('/').status_code == 200
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']


@pytest.mark.parametrize('changes', [dict(player_id='2'),dict(event_id='99'),dict(availability='out'),dict(starts_at='2026-01-01'),dict(team_id='../')])
def test_forged_or_unsupported_forecasts_not_saved(local_app,changes):
    client,store,_,_=local_app
    body=dict(team_id='13',player_id='1',event_id='9',**{})
    body.update(changes)
    assert client.post('/api/forecast',json=body).status_code == 422
    assert not store.forecasts()


def test_provider_out_cannot_be_overridden(local_app):
    client,store,_,player=local_app
    player['injuries']=[{'status':'Out'}]
    assert client.post('/api/forecast',json=dict(team_id='13',player_id='1',event_id='9',availability='available')).status_code == 422
    assert not store.forecasts()


@pytest.mark.parametrize('injuries,expected', [([], 'unknown'), ([{'status': 'Questionable'}], 'questionable')])
def test_automatic_forecast_preserves_unconfirmed_availability(local_app, injuries, expected):
    client, store, _, player = local_app
    player['injuries'] = injuries
    response = client.post('/api/forecast', json=dict(team_id='13', player_id='1', event_id='9', availability='unknown'))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['availability'] == expected
    assert body['injuries'] == injuries
    assert set(body['predictions']) == {'PTS', 'REB', 'AST', 'PRA'}
    assert any('Availability is unresolved' in note for note in body['notes'])
    assert len(store.forecasts()) == 1


def test_local_app_rejects_remote_origins_hosts_and_oversized_requests(local_app):
    client,_,_,_=local_app
    assert client.get('/api/status',headers={'Host':'attacker.example'}).status_code == 400
    assert client.post('/api/forecast',json={},headers={'Origin':'https://attacker.example'}).status_code == 403
    assert client.post('/api/forecast',content='x'*9000,headers={'Content-Type':'application/json'}).status_code == 413
    assert client.post('/api/forecast',data={'team_id':'13'}).status_code == 415
    remote=TestClient(client.app,base_url='http://127.0.0.1:8765',client=('192.168.1.10',12345))
    assert remote.get('/api/status').status_code == 403


def test_provider_schema_errors_are_actionable(local_app):
    client,store,provider,_=local_app
    def invalid(*args): raise KeyError('missing source field')
    provider.roster=invalid
    response=client.post('/api/forecast',json=dict(team_id='13',player_id='1',event_id='9'))
    assert response.status_code == 503 and 'format' in response.json()['detail']
    assert not store.forecasts()


def test_personal_navigation_deep_links_do_not_swallow_api_or_asset_errors(local_app):
    client,_,_,_=local_app
    for route in ('/app','/research','/forecasts?team=13&player=1','/games','/picks','/settings','/leaderboard'):
        response=client.get(route)
        assert response.status_code==200 and 'Personal app shell' in response.text
    assert client.get('/api/not-an-endpoint').status_code==404
    assert client.get('/assets/missing.js').status_code==404


def test_current_roster_search_uses_espn_ids_and_accent_insensitive_names(tmp_path,monkeypatch):
    provider=ESPN(Store(tmp_path/'search.sqlite3'))
    monkeypatch.setattr(provider,'teams',lambda:dict(teams=[dict(id='7',name='Denver Nuggets',abbreviation='DEN')]))
    monkeypatch.setattr(provider,'roster',lambda team:dict(players=[dict(id='3112335',name='Nikola Jokić',headshot='')]))
    result=provider.search('jokic')
    assert result[0]['player_name']=='Nikola Jokić'
    assert result[0]['player_id']==3112335 and result[0]['team_id']==7
    assert 'espncdn.com' in result[0]['headshot_url']
    assert provider.search('No match')==[]


def test_search_does_not_guess_between_conflicting_current_rosters(tmp_path, monkeypatch):
    provider = ESPN(Store(tmp_path/'search.sqlite3'))
    monkeypatch.setattr(provider, 'teams', lambda: dict(teams=[
        dict(id='7', name='Denver', abbreviation='DEN'), dict(id='13', name='Lakers', abbreviation='LAL')]))
    monkeypatch.setattr(provider, 'roster', lambda team: dict(players=[dict(id='3112335', name='Nikola Jokic')]))
    with pytest.raises(DataUnavailable, match='multiple rosters'):
        provider.search('Jokic')


def test_game_log_misaligned_stats_do_not_shift_field_values():
    data = dict(labels=['MIN','PTS'], events={'1': {'gameDate':'2026-01-01T00:00Z'}}, seasonTypes=[
        dict(displayName='2025-26 Regular Season', categories=[dict(type='event', events=[dict(eventId='1',stats=['20'])])])])
    with pytest.raises(DataUnavailable, match='stat labels'):
        regular_events(data)


def test_invalid_home_away_context_is_rejected(box):
    for competitor in box['header']['competitions'][0]['competitors']:
        competitor['homeAway'] = 'home'
    with pytest.raises(DataUnavailable, match='home and one away'):
        final_rows(box, '401811041')


@pytest.mark.parametrize('scenario', ['correction', 'old_mismatch', 'latest_mismatch', 'too_many_mismatches', 'play_in', 'same_day', 'bad_before_play_in', 'invalid_log_count', 'all_star', 'dnp'])
def test_history_reconciliation_and_quarantine(tmp_path, monkeypatch, box, scenario):
    store=Store(tmp_path/'history.sqlite3')
    provider=ESPN(store)
    now=datetime(2026,4,14,18,tzinfo=timezone.utc)
    events, entries, summaries = {}, [], {}
    for i in range(12):
        eid=str(100+i)
        date=(now-timedelta(days=13-i)).isoformat()
        if scenario == 'all_star' and i >= 10: date=(now-timedelta(days=2)).isoformat()
        if scenario == 'same_day' and i == 11: date=now.isoformat()
        events[eid]={'gameDate':date}
        entries.append({'eventId':eid, 'stats':['38','22' if scenario=='correction' else '23','10','11']})
        if scenario=='invalid_log_count': entries[-1]['stats'][1]='NaN'
        game=copy.deepcopy(box)
        game['header']['id']=eid
        game['header']['competitions'][0]['date']=date
        if (scenario=='old_mismatch' and i==0) or (scenario=='latest_mismatch' and i==11) or (scenario=='too_many_mismatches' and i<4):
            game['header']['competitions'][0]['competitors'][0]['score']='999'
        if scenario == 'dnp' and i == 0:
            athletes = game['boxscore']['players'][0]['statistics'][0]['athletes']
            target = next(p for p in athletes if p['athlete'].get('id') == '4432573')
            # Keep the complete team score while making the selected identity an explicit DNP.
            target['athlete']['id'] = 'another-player'
            athletes.append({'athlete': {'id': '4432573'}, 'didNotPlay': True})
        if scenario=='play_in' and i==11: game['header']['season']['type']=5
        if scenario == 'all_star' and i >= 10:
            competitor = game['header']['competitions'][0]['competitors'][0]
            competitor['id'] = '132374'
            competitor['team'] = {'id': '132374', 'abbreviation': 'STARS'}
        if scenario=='bad_before_play_in':
            if i==10: game['header']['competitions'][0]['competitors'][0]['score']='999'
            if i==11: game['header']['season']['type']=5
        summaries[eid]=game
    gamelog={'labels':['MIN','PTS','REB','AST'], 'events':events, 'seasonTypes':[
        {'displayName':'2025-26 Regular Season','categories':[{'type':'event','events':entries}]}]}
    def get(base,path,ttl):
        return (summaries[path.split('=')[-1]] if base == SITE else gamelog), 100
    monkeypatch.setattr(provider,'get',get)
    if scenario in ('latest_mismatch','too_many_mismatches','bad_before_play_in'):
        with pytest.raises(DataUnavailable): provider.history('4432573',now)
    else:
        logs,q=provider.history('4432573',now)
        assert len(logs)==(12 if scenario in ('correction','invalid_log_count') else 10 if scenario == 'all_star' else 11)
        assert (logs.PRA == 44).all()
        if scenario=='correction':
            assert q['corrections_this_refresh']==12
            assert len(store.corrections())==12
            assert provider.history('4432573',now)[1]['corrections_this_refresh']==0
        if scenario=='old_mismatch': assert len(q['quarantined_games'])==1
        if scenario=='play_in': assert q['excluded_non_regular_games']==['111']
        if scenario=='dnp': assert q['excluded_dnp_games']==['100']
        if scenario == 'all_star':
            assert q['excluded_non_regular_games'] == ['110', '111']
            assert not logs.duplicated(['PLAYER_ID', 'GAME_DATE']).any()
        if scenario=='same_day': assert logs.GAME_DATE.max()<'2026-04-14'
        if scenario=='invalid_log_count':
            assert q['corrections_this_refresh']==12
            assert store.corrections()[0]['before']['PTS']=='NaN'
            json.dumps(store.corrections(),allow_nan=False)
