import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal.maintenance import score
from personal.store import Store


@pytest.fixture
def scoring(tmp_path):
    store = Store(tmp_path / 'local.sqlite3')
    box = json.loads((Path(__file__).parent / 'fixtures' / 'espn_final_401811041.json').read_text())
    start = datetime.fromisoformat(box['header']['competitions'][0]['date'].replace('Z', '+00:00'))
    snapshot = dict(event_id='espn:401811041', player_id='espn:4432573',
        event=dict(id='401811041', starts_at=start.isoformat()),
        as_of=(start - timedelta(hours=2)).isoformat(), model={'artifact_sha256': 'model-A'},
        predictions={s: dict(prediction=p, range_low=p-2, range_high=p+2) for s,p in [('PTS',20),('REB',10),('AST',10),('PRA',40)]})
    return store, box, snapshot, start + timedelta(days=1)


def test_scoring_uses_latest_pregame_snapshot_and_is_idempotent(scoring):
    store, box, snapshot, now = scoring
    store.save_forecast(snapshot)
    newer = copy.deepcopy(snapshot)
    newer['as_of'] = (datetime.fromisoformat(snapshot['as_of']) + timedelta(hours=1)).isoformat()
    newer['predictions']['PTS']['prediction'] = 23
    newer['baselines'] = {'PTS': {'last_20': 20}}
    latest_id = store.save_forecast(newer)
    provider = SimpleNamespace(get=lambda *a: (box, 0))
    for _ in range(2):
        report = score(store, provider, now)
        assert report['scored'] == 1 and not report['errors']
        assert report['models']['model-A']['PTS']['mae'] == 0
        assert report['models']['model-A']['PTS']['baseline_l20_mae'] == 3
        assert report['models']['model-A']['PTS']['mae_minus_l20'] == -3
    with store.connect() as db:
        assert db.execute('SELECT forecast_id FROM forecast_evaluations').fetchall() == [(latest_id,)]
        assert db.execute('SELECT COUNT(*) FROM forecasts').fetchone()[0] == 2


def test_scoring_does_not_fetch_future_or_accept_postgame_snapshot(scoring):
    store, box, snapshot, now = scoring
    store.save_forecast(snapshot)
    def no_network(*args):
        pytest.fail('Future events must not require a final-score download')
    assert score(store, SimpleNamespace(get=no_network), datetime.fromisoformat(snapshot['as_of']))['pending'] == 1
    late = copy.deepcopy(snapshot)
    late['as_of'] = now.isoformat()
    store.save_forecast(late)
    report = score(store, SimpleNamespace(get=lambda *a: (box, 0)), now)
    assert report['scored'] == 1
    assert 'not pregame' in report['errors'][0]['reason']


def test_scoring_dnp_is_not_a_zero_and_rejects_wrong_final_event(scoring):
    store, box, snapshot, now = scoring
    snapshot['player_id'] = 'espn:3150844'  # explicit DNP in the real fixture
    store.save_forecast(snapshot)
    report = score(store, SimpleNamespace(get=lambda *a: (box, 0)), now)
    assert report['dnp'] == 1 and report['scored'] == 0 and not report['models']
    box['header']['id'] = '999'
    assert score(store, SimpleNamespace(get=lambda *a: (box, 0)), now)['errors']


def test_backup_preserves_history_and_refuses_overwrite(tmp_path):
    store = Store(tmp_path / 'live.sqlite3')
    store.save_forecast({'retained': True})
    path = Path(store.backup(tmp_path / 'backup.sqlite3'))
    assert Store(path).forecasts()[0]['forecast'] == {'retained': True}
    with pytest.raises(ValueError): store.backup(path)
    with pytest.raises(ValueError): store.backup(store.path)


def test_future_dated_cache_is_not_trusted(tmp_path):
    store = Store(tmp_path / 'cache.sqlite3')
    store.cache('key', {'source': 'future'})
    with store.connect() as db:
        db.execute('UPDATE cache SET fetched=?', (datetime.now(timezone.utc).timestamp() + 3600,))
    assert store.cached('key', 86400) is None
