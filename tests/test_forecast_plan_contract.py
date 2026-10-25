"""Independent snapshot checks for forecast levels and paired scenario changes."""
from __future__ import annotations

from datetime import date, timedelta
import json

import numpy as np
import pytest

from config import OUTPUTS_DIR
from sim.forecast_plan import paired_plan


def _snapshots():
    forecasts = {r['org_code']: r for r in json.loads(
        (OUTPUTS_DIR / 'forecasts_latest.json').read_text())['trusts']}
    old = {r['org_code']: r for r in json.loads(
        (OUTPUTS_DIR / 'decision_support.json').read_text())['trusts']}
    manifest = json.loads((OUTPUTS_DIR / 'planning_grid' / 'manifest.json').read_text())
    grids = {code: json.loads((OUTPUTS_DIR / 'planning_grid' / f'{code}.json').read_text())
             for code in manifest['files']}
    return forecasts, old, grids


def test_paired_difference_is_not_difference_of_marginal_quantiles():
    # The same realization can be unusual in different ways across scenarios.
    # Marginal quantiles discard pairing and would falsely predict a 100-person gain.
    unchanged = np.array([[0.], [100.], [200.]])
    changed = np.array([[0.], [0.], [200.]])
    result, _ = paired_plan(np.array([150.]), changed, unchanged, unchanged)
    assert result['final_capacity_delta']['median'] == 0.
    assert result['final_backlog']['median'] == 150.
    assert np.median(changed) - np.median(unchanged) == -100.
    np.testing.assert_allclose(
        [result['final_capacity_delta'][q] for q in ['lower_80', 'median', 'upper_80']],
        np.quantile(changed[:, 0] - unchanged[:, 0], [.1, .5, .9]))


def test_every_available_no_change_path_matches_issue_anchored_forecast():
    forecasts, _, grids = _snapshots()
    for code, grid in grids.items():
        if grid['status'] != 'ready':
            continue
        issue = date.fromisoformat(grid['issue_date'])
        days = np.arange(0, 85, 7)
        assert grid['horizon_days'] == 84
        assert grid['day_offsets'] == days.tolist()
        assert grid['dates'] == [(issue + timedelta(days=int(d))).isoformat() for d in days]
        anchors = sorted(forecasts[code]['forecasts'], key=lambda r: r['horizon_weeks'])
        source_days = [(date.fromisoformat(anchors[0]['latest_observation']) - issue).days]
        source_values = [anchors[0]['last_value']]
        for point in anchors:
            delta = (date.fromisoformat(point['target_date']) - issue).days
            assert delta == point['horizon_weeks'] * 7
            source_days.append(delta)
            source_values.append(point['point_forecast'])
        reference = np.interp(days, source_days, source_values)
        no_change = next(s for s in grid['scenarios'] if s['key'] == 'none')
        for stage in ('diagnosis', 'treatment'):
            baseline = no_change['plans'][stage][0]
            for quantile in ('median', 'lower_80', 'upper_80'):
                np.testing.assert_allclose(baseline['backlog_62'][quantile], reference,
                                           atol=.000501, rtol=0, err_msg=code)
                np.testing.assert_array_equal(baseline['total_delta'][quantile], np.zeros(13))
        # The interpolated publication bridge is never labelled an observation.
        assert grid['forecast_path']['source_points'][0]['kind'] == 'observed'
        assert grid['forecast_path']['source_points'][0]['date'] == anchors[0]['latest_observation']


def test_pressure_zero_capacity_is_the_paired_pressure_change_only():
    _, _, grids = _snapshots()
    for code, grid in grids.items():
        if grid['status'] != 'ready':
            continue
        for scenario in grid['scenarios']:
            for stage in ('diagnosis', 'treatment'):
                baseline = scenario['plans'][stage][0]
                assert baseline['total_delta'] == scenario['pressure_delta'], code
                for quantile in ('median', 'lower_80', 'upper_80'):
                    np.testing.assert_array_equal(baseline['capacity_delta'][quantile], np.zeros(13))
                for plan in scenario['plans'][stage]:
                    # Day28 is the end of the common prefix. No selected control
                    # can alter an earlier displayed week.
                    for quantile in ('median', 'lower_80', 'upper_80'):
                        np.testing.assert_array_equal(plan['total_delta'][quantile][:5], np.zeros(5))
                        assert min(plan['backlog_62'][quantile]) >= 0, code


def test_original_absolute_simulation_is_preserved_only_as_separate_detail():
    _, legacy, grids = _snapshots()
    mappings = [('baseline', 'none', 'diagnosis', 0),
                ('strike', 'strike', 'diagnosis', 0),
                ('strike_plus_diagnosis', 'strike', 'diagnosis', 10),
                ('strike_plus_treatment', 'strike', 'treatment', 10),
                ('winter_dip', 'winter', 'diagnosis', 0),
                ('referral_surge', 'surge', 'diagnosis', 0)]
    for code, grid in grids.items():
        if grid['status'] != 'ready':
            continue
        scenarios = {s['key']: s for s in grid['scenarios']}
        old_plans = {p['key']: p for p in legacy[code]['scenario_comparison']}
        for old_key, key, stage, dose in mappings:
            plan = next(p for p in scenarios[key]['plans'][stage]
                        if p['extra_capacity_pct'] == dose)
            for quantile in ('median', 'lower_80', 'upper_80'):
                np.testing.assert_allclose(plan['absolute_simulator']['backlog_62'][quantile],
                    old_plans[old_key]['backlog_62'][quantile][:13], atol=.000501, rtol=0,
                    err_msg=f'{code} {key} {stage} {dose}')


def test_level_mismatch_does_not_hold_back_an_otherwise_usable_trust():
    forecasts, legacy, grids = _snapshots()
    code = 'RNS'
    assert grids[code]['status'] == 'ready'
    point = next(p for p in forecasts[code]['forecasts'] if p['horizon_weeks'] == 12)
    old = next(p for p in legacy[code]['scenario_comparison'] if p['key'] == 'baseline')
    old_median = old['backlog_62']['median'][old['dates'].index(point['target_date'])]
    assert old_median > point['upper_80']
    actual = grids[code]['scenarios'][0]['plans']['diagnosis'][0]['final_backlog']['median']
    assert actual == pytest.approx(point['point_forecast'], abs=.000501)
    allowed_reasons = {'simulation_inputs_unavailable', 'history_fit_failure',
                       'optimizer_failure', 'weakly_identified', 'forecast_unavailable'}
    for grid in grids.values():
        if grid['status'] == 'unavailable':
            assert grid['eligibility']['reason_codes']
            assert set(grid['eligibility']['reason_codes']) <= allowed_reasons
