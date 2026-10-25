"""The map must preserve dates, missing values and the model's exact anchors."""
from datetime import date, timedelta
from copy import copy
import json

from fastapi.testclient import TestClient
import pytest

from api.data import Snapshot, digest, forecast_direction, planning_consistency
from api.main import create_app
from pipeline.universe import load_core_trusts


@pytest.fixture(scope='module')
def snapshot():
    return Snapshot()


def test_map_dates_keep_the_publication_gap_visible(snapshot):
    data = snapshot.map
    assert data['history_start'] == '2023-04-09'
    assert data['latest_observed_week'] == '2026-08-30'
    assert data['forecast_start'] == data['issue_date'] == '2026-10-18'
    assert data['forecast_end'] == '2027-01-10'
    assert data['publication_gap']['days'] == 49
    weeks = [date.fromisoformat(week) for week in data['weeks']]
    assert all(b - a == timedelta(weeks=1) for a, b in zip(weeks, weeks[1:]))
    for trust in data['trusts']:
        assert all(row['week_ending'] <= data['latest_observed_week'] for row in trust['history'])
        assert all(row['published_on'] is None or row['published_on'] <= data['issue_date']
                   for row in trust['history'])
        assert all(point['target_date'] > data['issue_date'] for point in trust['forecasts'])


def test_map_keeps_missing_values_and_true_zeros_distinct(snapshot):
    trusts = {trust['org_code']: trust for trust in snapshot.map['trusts']}
    assert set(trusts) == set(load_core_trusts().org_code)
    assert not {'RAP', 'RVJ', 'RY2', 'RVY'}.intersection(trusts)
    assert any(row['backlog'] is None for row in trusts['RTH']['history'])
    assert trusts['RP6']['history'][-1]['backlog'] == 0
    assert trusts['RWF']['history'][-1]['backlog'] == 79
    assert trusts['RWF']['forecasts'] == []
    assert trusts['RWF']['direction'] == 'unclear'
    # Reject JavaScript's non-standard NaN/Infinity JSON extensions.
    json.dumps(snapshot.map, allow_nan=False)


def test_map_uses_exact_model_anchors_and_observed_england_total(snapshot):
    for trust in snapshot.map['trusts']:
        originals = snapshot.indexes['forecasts_latest'][trust['org_code']]['forecasts']
        assert len(trust['forecasts']) == len(originals)
        for shown, original in zip(trust['forecasts'], originals):
            assert shown == {key: original[key] for key in shown}
            assert shown['horizon_weeks'] in (4, 8, 12)
    nation = snapshot.map['national']
    assert nation['latest']['total'] == 17841
    assert nation['latest']['week_ending'] == '2026-08-30'
    assert nation['observed_only'] is True
    assert nation['model_forecasts']['enabled'] is False


@pytest.mark.parametrize('latest,point,expected', [
    (100, 89, 'improving'), (100, 111, 'worsening'),
    (100, 100, 'unclear'), (100, 110, 'unclear'),
    (100, 90, 'unclear'), (None, 70, 'unclear'),
    (100, None, 'unclear'), (0, 0, 'unclear'),
    (1000, 950, 'unclear'), (1000, 899, 'improving'),
    (0, 11, 'worsening'),
])
def test_map_direction_uses_an_explicit_material_change_threshold(latest, point, expected):
    assert forecast_direction([dict(horizon_weeks=12, point_forecast=point)], latest) == expected
    assert forecast_direction([], latest) == 'unclear'


def test_map_route_is_cached_snapshot_data(snapshot, tmp_path):
    with TestClient(create_app(snapshot, tmp_path)) as client:
        response = client.get('/api/map')
    assert response.status_code == 200
    assert response.headers['X-Snapshot-Issue'] == snapshot.issue_date
    assert response.json() == snapshot.map


def write_grid_fixture(snapshot, directory):
    sources = {name + '.json': digest(snapshot.paths[name])
               for name in ['simulation_calibration', 'bottlenecks', 'decision_support', 'forecasts_latest']}
    files = {}
    for code in snapshot.codes:
        path = directory / f'{code}.json'
        path.write_text(json.dumps(dict(schema_version=2, org_code=code,
            issue_date=snapshot.issue_date, input_sha256=sources,
            status='unavailable', reason='Isolated grid validation fixture')))
        files[code] = digest(path)
    manifest = dict(schema_version=2, horizon_days=84, partial=False, issue_date=snapshot.issue_date,
                    input_sha256=sources, files=files, capacity_percent=[0, 1, 2, 3, 4, 5, 10, 15, 20])
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    return manifest


def test_planning_grid_is_attached_only_after_source_and_file_validation(snapshot, tmp_path):
    write_grid_fixture(snapshot, tmp_path)
    candidate = copy(snapshot)
    candidate.validate_planning_grid(tmp_path)
    decision = candidate.decision('RTH')
    assert decision['planning_grid']['status'] == 'unavailable'
    assert decision['planning_grid']['reason'] == 'Isolated grid validation fixture'
    assert decision['status'] == 'unavailable'
    assert decision['absolute_simulator_evidence']['dose_response'] == snapshot.indexes['decision_support']['RTH']['dose_response']
    assert 'dose_response' not in decision
    (tmp_path / 'RTH.json').write_text('{}')
    with pytest.raises(ValueError, match='file changed or missing: RTH'):
        candidate.validate_planning_grid(tmp_path)


@pytest.mark.parametrize('change, message', [
    ({'issue_date': '2026-10-11'}, 'different snapshot issue'),
    ({'partial': True}, 'incomplete'),
    ({'input_sha256': {}}, 'sources changed'),
    ({'files': {}}, 'cohort mismatch'),
])
def test_planning_grid_rejects_mixed_or_partial_batches(snapshot, tmp_path, change, message):
    manifest = write_grid_fixture(snapshot, tmp_path)
    (tmp_path / 'manifest.json').write_text(json.dumps({**manifest, **change}))
    candidate = copy(snapshot)
    with pytest.raises(ValueError, match=message):
        candidate.validate_planning_grid(tmp_path)


@pytest.mark.parametrize('code, status', [('RNS', 'conflict'), ('RAL', 'conflict'),
    ('RA7', 'conflict'), ('RTH', 'consistent'), ('RET', 'unavailable'), ('RWF', 'unavailable')])
def test_old_absolute_mismatch_is_diagnostic_only_at_the_same_date(snapshot, code, status):
    check = snapshot.decision(code)['planning_consistency']
    assert check['status'] == status
    assert check['comparison_date'] == '2027-01-10'
    assert check['requires_review'] is False
    assert 'does not gate forecast-anchored plans' in check['interpretation']
    if code == 'RNS':
        assert check['simulator_baseline']['median'] == pytest.approx(248.99958837853922)
        assert check['forecast']['median'] == pytest.approx(144.35784155412804)
        assert check['forecast']['upper_80'] == pytest.approx(217.71035388372027)


def test_planning_screen_never_compares_the_six_month_endpoint_with_twelve_weeks():
    forecast = {'forecasts': [dict(horizon_weeks=12, issue_date='2026-10-18',
        target_date='2027-01-10', point_forecast=100, lower_80=80, upper_80=120)]}
    baseline = dict(key='baseline', extra_capacity_pct=0,
        dates=['2026-10-18', '2027-01-10', '2027-04-18'], day_offsets=[0, 84, 182],
        backlog_62=dict(median=[100, 100, 360], lower_80=[90, 90, 340], upper_80=[110, 110, 380]))
    decision = {'scenario_comparison': [baseline]}
    assert planning_consistency(forecast, decision, '2026-10-18')['status'] == 'consistent'
    # Having a distant endpoint is not enough: do not interpolate a day-84 value.
    baseline['dates'][1] = '2027-01-03'
    baseline['day_offsets'][1] = 77
    assert planning_consistency(forecast, decision, '2026-10-18')['status'] == 'unavailable'


def test_planning_screen_rejects_invalid_ranges_and_wrong_date_offsets():
    forecast = {'forecasts': [dict(horizon_weeks=12, issue_date='2026-10-18',
        target_date='2027-01-10', point_forecast=100, lower_80=80, upper_80=120)]}
    baseline = dict(key='baseline', dates=['2026-10-18', '2027-01-10'], day_offsets=[0, 77],
        backlog_62=dict(median=[100, 100], lower_80=[90, 90], upper_80=[110, 110]))
    decision = {'scenario_comparison': [baseline]}
    assert planning_consistency(forecast, decision, '2026-10-18')['status'] == 'unavailable'
    baseline['day_offsets'][1] = 84
    baseline['backlog_62']['median'][1] = float('nan')
    assert planning_consistency(forecast, decision, '2026-10-18')['status'] == 'unavailable'
    baseline['dates'] = []
    assert planning_consistency(forecast, decision, '2026-10-18')['status'] == 'unavailable'


def test_ready_plans_preserve_forecast_anchors_and_only_gate_simulator_failures(snapshot):
    """A former baseline disagreement must not be a remaining reason for exclusion."""
    allowed_reasons = {'simulation_inputs_unavailable', 'history_fit_failure',
                       'optimizer_failure', 'weakly_identified', 'forecast_unavailable'}
    for code in snapshot.codes:
        decision = snapshot.decision(code)
        grid = decision['planning_grid']
        assert decision['planning_consistency']['requires_review'] is False
        assert decision['status'] == grid['status']
        if grid['status'] != 'ready':
            assert grid['eligibility']['reason_codes']
            assert set(grid['eligibility']['reason_codes']) <= allowed_reasons
            continue
        assert grid['horizon_days'] == 84
        assert grid['eligibility']['eligible'] is True
        scenario = next(s for s in grid['scenarios'] if s['key'] == 'none')
        baseline = scenario['plans']['diagnosis'][0]
        assert baseline['backlog_62']['median'] == grid['forecast_path']['backlog_62']['median']
        for point in snapshot.indexes['forecasts_latest'][code]['forecasts']:
            index = grid['day_offsets'].index(point['horizon_weeks'] * 7)
            assert baseline['backlog_62']['median'][index] == pytest.approx(point['point_forecast'], abs=.000501)
        assert grid['dates'][-1] == '2027-01-10'
