"""Snapshot API contracts, publication bounds and exact precomputed experiments."""
import json
from datetime import date, timedelta

import numpy as np

from fastapi.testclient import TestClient
import pytest

from api.data import Snapshot, digest
from api.main import create_app
from api.schemas import CAPACITY_GRID
from config import OUTPUTS_DIR
from pipeline.universe import load_core_trusts


@pytest.fixture(scope='module')
def decision_file(tmp_path_factory):
    """Small decision fixture; all other routes use the real bundled evidence."""
    path = tmp_path_factory.mktemp('api') / 'decision_support.json'
    trusts = [dict(org_code=t.org_code, name=t.name, status='unavailable', reason='Fixture without fit')
              for t in load_core_trusts().itertuples()]
    record = next(t for t in trusts if t['org_code'] == 'RTH')
    points = [dict(extra_capacity_pct=p, lower_80=160-p*5, median=170-p*5, upper_80=180-p*5)
              for p in CAPACITY_GRID]
    quantiles = dict(lower_80=[150,160], median=[160,170], upper_80=[170,180])
    plans = [dict(key=key, name=key, stage=stage, extra_capacity_pct=dose,
                  dates=['2026-10-18','2027-04-18'], backlog_62=quantiles,
                  long_wait_104=quantiles, final_backlog=dict(lower_80=160,median=170,upper_80=180))
             for key, stage, dose in [('baseline','none',0),('strike','none',0),
                 ('strike_plus_diagnosis','diagnosis',10),('strike_plus_treatment','treatment',10),
                 ('winter_dip','none',0),('referral_surge','none',0)]]
    record.update(status='ready', prior_conflict=False, treatment_label='Radiotherapy capacity',
        assumptions={'scope':'Test fixture'}, scenario_comparison=plans,
        dose_response=dict(scenario='five_day_strike',horizon_days=182,
            capacity_percent=list(CAPACITY_GRID), diagnosis=points,treatment=points))
    report = dict(stage=8,issue_date='2026-10-18',trusts=trusts,
        calibration_sha256=digest(OUTPUTS_DIR/'simulation_calibration.json'),
        bottleneck_sha256=digest(OUTPUTS_DIR/'bottlenecks.json'))
    path.write_text(json.dumps(report))
    return path


@pytest.fixture(scope='module')
def planning_dir(decision_file, tmp_path_factory):
    """An independent 12-week grid; old absolute outputs remain an evidence fixture."""
    directory = tmp_path_factory.mktemp('plans')
    sources = {name + '.json': digest(decision_file if name == 'decision_support' else OUTPUTS_DIR / (name + '.json'))
               for name in ['simulation_calibration', 'bottlenecks', 'decision_support', 'forecasts_latest']}
    forecasts = json.loads((OUTPUTS_DIR / 'forecasts_latest.json').read_text())
    forecast = next(t for t in forecasts['trusts'] if t['org_code'] == 'RTH')
    points = forecast['forecasts']; offsets = list(range(0, 85, 7))
    anchors = [p['point_forecast'] for p in points]
    central = np.interp(offsets, [0, 28, 56, 84], [anchors[0], *anchors]).tolist()
    dates = [(date(2026, 10, 18) + timedelta(days=d)).isoformat() for d in offsets]
    files = {}
    for code in load_core_trusts().org_code:
        item = dict(schema_version=2, org_code=code, issue_date='2026-10-18', input_sha256=sources,
                    status='unavailable', reason='Fixture without fit',
                    eligibility=dict(eligible=False, reason_codes=['simulator_unavailable']))
        if code == 'RTH':
            scenarios = []
            for mask in range(8):
                flags = {key: bool(mask & (1 << i)) for i, key in enumerate(['strike', 'winter', 'surge'])}
                key = '_'.join(k for k, enabled in flags.items() if enabled) or 'none'
                plans = []
                for dose in CAPACITY_GRID:
                    values = [max(0, value + (5 * mask - dose * 2) * offset / 84) for value, offset in zip(central, offsets)]
                    q = dict(median=values, lower_80=values, upper_80=values)
                    plans.append(dict(extra_capacity_pct=dose, backlog_62=q,
                                      final_backlog={name: rows[-1] for name, rows in q.items()}))
                scenarios.append(dict(key=key, flags=flags, plans=dict(diagnosis=plans, treatment=plans)))
            item.update(status='ready', horizon_days=84, day_offsets=offsets, dates=dates,
                        capacity_percent=list(CAPACITY_GRID), scenarios=scenarios,
                        eligibility=dict(eligible=True, reason_codes=[]), assumptions={'scope':'Test fixture'},
                        forecast_path=dict(dates=dates, day_offsets=offsets,
                            backlog_62=dict(median=central, lower_80=central, upper_80=central)))
        path = directory / (code + '.json'); path.write_text(json.dumps(item)); files[code] = digest(path)
    (directory / 'manifest.json').write_text(json.dumps(dict(schema_version=2, partial=False,
        issue_date='2026-10-18', horizon_days=84, capacity_percent=list(CAPACITY_GRID), input_sha256=sources, files=files)))
    return directory


@pytest.fixture(scope='module')
def snapshot(decision_file, planning_dir):
    return Snapshot(decision_file, planning_dir)


@pytest.fixture(scope='module')
def client(snapshot, tmp_path_factory):
    static = tmp_path_factory.mktemp('web')
    (static/'index.html').write_text('<title>Cancer Clock</title>')
    with TestClient(create_app(snapshot, static)) as client:
        yield client


def test_health_and_trust_list_share_current_core(client):
    assert client.get('/health').json()['core_trusts'] == 130
    health = client.get('/health').json()
    assert len(health['snapshot_sha256']) == 6 and health['precomputed'] is True
    response = client.get('/api/trusts')
    assert response.status_code == 200
    assert response.headers['X-Snapshot-Issue'] == '2026-10-18'
    trusts = response.json()['trusts']
    assert {t['org_code'] for t in trusts} == set(load_core_trusts().org_code)
    assert not {'RVJ','RAP','RY2','RVY'}.intersection(t['org_code'] for t in trusts)
    assert all(t['lat'] is not None and t['lon'] is not None for t in trusts)
    rth = next(t for t in trusts if t['org_code']=='RTH')
    assert rth['latest_backlog'] == 179 and rth['bottleneck_label']=='treatment-limited'
    assert rth['decision_status']=='ready'
    rwf = next(t for t in trusts if t['org_code']=='RWF')
    assert rwf['latest_backlog'] is not None
    forecast=client.get('/api/trust/RWF/forecast').json()
    assert forecast['status']!='forecast_available' and forecast['forecasts']==[]
    assert any(r['backlog'] is not None for r in forecast['history'])


def test_forecast_bottleneck_history_and_national_are_labelled(client):
    forecast = client.get('/api/trust/RTH/forecast').json()
    assert [f['horizon_weeks'] for f in forecast['forecasts']] == [4,8,12]
    assert 'growth_signal' not in forecast['forecasts'][1]
    assert all('probability' not in key for f in forecast['forecasts'] for key in f)
    bottleneck = client.get('/api/trust/RTH/bottleneck').json()
    assert bottleneck['treatment_driver']['key']=='d31_radiotherapy'
    history = client.get('/api/trust/RTH/history').json()
    assert 'Historical completed' in history['label']
    latest = history['latest']
    assert latest['period']=='2026-08-01' and latest['published_on'] <= history['issue_date']
    assert latest['bands_available'] and sum(b['count'] for b in latest['bands'])==latest['total']
    nation = client.get('/api/national').json()
    assert nation['observed_only'] and nation['model_forecasts']['enabled'] is False
    assert nation['latest']['total']==17841
    assert nation['latest']['no_dtt']+nation['latest']['with_dtt']==nation['latest']['total']
    assert client.get('/api/backtest').json()['model']['evaluation_anchor']=='issue'


def test_decision_unavailable_is_explicit_and_retired_codes_fail(client):
    assert client.get('/api/trust/RTH/decision').json()['treatment_label']=='Radiotherapy capacity'
    unavailable = client.get('/api/trust/RET/decision').json()
    assert unavailable['status']=='unavailable' and unavailable['reason']
    assert client.post('/api/simulate',json={'org_code':'RET'}).status_code==409
    for code in ['RVJ','RAP','RY2','RVY','XXX']:
        assert client.get(f'/api/trust/{code}/decision').status_code==404
        assert client.post('/api/simulate',json={'org_code':code}).status_code==404


def test_cached_plans_are_twelve_week_paired_effect_trajectories(client, snapshot):
    body = dict(org_code='RTH', scenario='strike', stage='treatment', extra_capacity_pct=10)
    response = client.post('/api/simulate', json=body)
    assert response.status_code == 200
    data = response.json()
    assert data['result_kind'] == 'trajectory' and data['horizon_days'] == 84
    assert data['result']['dates'][-1] == '2027-01-10'
    assert data['result']['day_offsets'] == list(range(0, 85, 7))
    before = snapshot.select_experiment.cache_info().hits
    assert client.post('/api/simulate', json=body).json() == data
    assert snapshot.select_experiment.cache_info().hits == before + 1
    smaller = client.post('/api/simulate', json={**body, 'extra_capacity_pct':5}).json()
    assert smaller['result_kind'] == 'trajectory' and smaller['assumptions']
    assert len(smaller['result']['dates']) == 13
    zero = client.post('/api/simulate', json={**body, 'extra_capacity_pct':0}).json()
    assert zero['stage'] == 'none' and zero['scenario_key'] == 'strike'
    assert data['result']['final_backlog']['median'] < zero['result']['final_backlog']['median']
    for scenario in ['baseline', 'winter_dip', 'referral_surge', 'strike_winter',
                     'strike_surge', 'winter_surge', 'strike_winter_surge']:
        assert client.post('/api/simulate', json={**body, 'scenario':scenario}).status_code == 200


def test_old_absolute_results_are_evidence_only_and_cannot_supply_a_missing_grid(decision_file):
    isolated = Snapshot(decision_file)
    record = isolated.decision('RTH')
    assert record['status'] == 'unavailable'
    assert record['eligibility']['reason_codes'] == ['planning_grid_missing']
    assert record['absolute_simulator_evidence']['status'] == 'ready'
    assert 'dose_response' not in record and 'scenario_comparison' not in record
    with pytest.raises(ValueError, match='has not been built'):
        isolated.select_experiment('RTH', 'strike', 'treatment', 10)


@pytest.mark.parametrize('change',[{'extra_capacity_pct':7},{'extra_capacity_pct':True},
    {'extra_capacity_pct':21},{'extra_capacity_pct':-1},{'extra_capacity_pct':'5'},
    {'stage':'none','extra_capacity_pct':5},{'stage':'radiotherapy'},
    {'horizon_days':365},
    {'scenario':'unknown'},{'org_code':'RTH/../../x'}])
def test_simulation_rejects_uncached_or_invalid_requests(client, change):
    body=dict(org_code='RTH',scenario='strike',stage='treatment',extra_capacity_pct=5)
    assert client.post('/api/simulate',json={**body,**change}).status_code==422


def test_startup_rejects_stale_hashes_and_missing_trusts(decision_file,tmp_path):
    report=json.loads(decision_file.read_text())
    path=tmp_path/'decision.json'
    report['calibration_sha256']='invalid'
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='different simulation_calibration'):
        Snapshot(path)
    report=json.loads(decision_file.read_text());report['trusts'].pop()
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='cohort mismatch'):
        Snapshot(path)


def test_frontend_is_served_without_exposing_repository_or_cors(client):
    assert '<title>Cancer Clock</title>' in client.get('/').text
    assert client.get('/api/not-real').status_code==404
    assert client.get('/data/static/trust_mergers.csv').status_code==404
    assert client.get('/api/trusts',headers={'Origin':'https://unrelated.example'}).headers.get('Access-Control-Allow-Origin') is None
