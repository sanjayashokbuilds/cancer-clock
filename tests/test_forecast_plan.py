"""Calendar, quality gating and nonnegative display contract for recovery plans."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from sim.forecast_plan import eligibility, forecast_path, paired_plan


def sample_forecast() -> dict:
    issue = date(2026, 10, 18)
    return {'forecasts': [dict(horizon_weeks=w, issue_date=issue.isoformat(),
        target_date=(issue + timedelta(weeks=w)).isoformat(), latest_observation='2026-08-30',
        last_value=100., point_forecast=p, lower_80=p - 20, upper_80=p + 30, model='lightgbm_blend')
        for w, p in [(4, 122.), (8, 110.), (12, 90.)]]}


def test_interpolates_from_observation_on_issue_calendar_and_keeps_anchors() -> None:
    result = forecast_path(sample_forecast(), '2026-10-18')
    assert result['day_offsets'] == list(range(0, 85, 7))
    assert result['dates'][0] == '2026-10-18'
    assert result['dates'][-1] == '2027-01-10'
    assert result['backlog_62']['median'][0] == pytest.approx(100 + 22 * 49 / 77)
    assert [result['backlog_62']['median'][i] for i in [4, 8, 12]] == [122., 110., 90.]
    assert result['interpolation_dates'][0] == '2026-08-30'
    assert result['interpolation_median'][0] == 100.


@pytest.mark.parametrize('mutation', ['issue', 'missing', 'wrong_target', 'negative', 'bad_range', 'latest'])
def test_incomplete_or_mismatched_forecast_cannot_supply_fake_anchor(mutation: str) -> None:
    data = sample_forecast()
    if mutation == 'issue': data['forecasts'][0]['issue_date'] = '2026-10-11'
    if mutation == 'missing': data['forecasts'].pop()
    if mutation == 'wrong_target': data['forecasts'][1]['target_date'] = '2026-12-06'
    if mutation == 'negative': data['forecasts'][0]['lower_80'] = -1
    if mutation == 'bad_range': data['forecasts'][0]['upper_80'] = 1
    if mutation == 'latest': data['forecasts'][1]['last_value'] = 99
    with pytest.raises(ValueError): forecast_path(data, '2026-10-18')


def test_quality_gate_uses_simulator_fit_and_identification_not_level_disagreement() -> None:
    record = dict(status='calibrated', acceptable_fit=True, optimizer_success=True)
    prepared = dict(status='ready')
    assert eligibility(record, prepared, {'weakly_identified': False})['eligible']
    poor = eligibility({**record, 'acceptable_fit': False}, prepared, {'weakly_identified': True})
    assert poor['reason_codes'] == ['history_fit_failure', 'weakly_identified']
    assert not poor['eligible']
    missing = eligibility(record, prepared, {'weakly_identified': False}, 'No blend forecast')
    assert missing['reason_codes'] == ['forecast_unavailable']


def test_floor_is_applied_per_draw_before_quantiles_and_retains_raw_effect() -> None:
    forecast = np.array([2., 2.])
    baseline = np.array([[100., 100.], [101., 101.], [102., 102.], [103., 103.]])
    plan = baseline + np.array([[-8., -8.], [-6., -6.], [-4., -4.], [-1., -1.]])
    result, displayed = paired_plan(forecast, plan, baseline, baseline)
    np.testing.assert_array_equal(displayed, [[0., 0.], [0., 0.], [0., 0.], [1., 1.]])
    assert result['final_backlog']['lower_80'] == 0.
    assert result['final_backlog']['median'] == 0.
    assert result['final_total_delta']['median'] == -5.
    assert result['final_capacity_delta'] == result['final_total_delta']


def test_zero_change_cancels_parameter_and_process_noise_exactly() -> None:
    rng = np.random.default_rng(11)
    raw = rng.uniform(0, 10000, (256, 13))
    forecast = np.linspace(20, 80, 13)
    result, displayed = paired_plan(forecast, raw, raw, raw)
    np.testing.assert_array_equal(displayed, np.broadcast_to(forecast, raw.shape))
    for q in ('lower_80', 'median', 'upper_80'):
        assert result['total_delta'][q] == [0.] * 13
        assert result['backlog_62'][q] == forecast.tolist()
