"""Forecast levels plus paired queue-model changes, without mixing quantiles.

The statistical forecast supplies the level. The queue simulation supplies a
signed intervention difference, conditional on its assumed queue structure.
No joint predictive distribution for those two models is claimed.
"""
from __future__ import annotations

from datetime import date, timedelta
import math

import numpy as np

from sim.scenarios import summary

HORIZON_DAYS = 84
ELIGIBILITY_RULE = ('Require published simulation inputs, an optimizer-successful history fit with '
                    'normalised RMSE <= 0.30, both capacity directions identified, and all '
                    'three issue-anchored forecast points. Absolute simulator/forecast level '
                    'disagreement is not a hold-back rule.')


def forecast_path(forecast: dict, issue_date: str) -> dict:
    """Interpolate source values on dates; never reset the horizon at observation."""
    issue = date.fromisoformat(issue_date)
    points = []
    for horizon in (4, 8, 12):
        expected = (issue + timedelta(weeks=horizon)).isoformat()
        matches = [p for p in forecast.get('forecasts', [])
                   if p.get('horizon_weeks') == horizon and p.get('target_date') == expected
                   and p.get('issue_date') == issue_date]
        if len(matches) != 1:
            raise ValueError('A complete matching 4-, 8- and 12-week forecast is unavailable')
        point = matches[0]
        values = [point.get(k) for k in ('lower_80', 'point_forecast', 'upper_80')]
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in values):
            raise ValueError('Forecast values are missing or non-finite')
        if not 0 <= values[0] <= values[1] <= values[2]:
            raise ValueError('Forecast ranges are invalid')
        points.append(point)
    observed_date = points[0].get('latest_observation')
    if not observed_date or any(p.get('latest_observation') != observed_date for p in points):
        raise ValueError('Forecast observation anchors differ')
    observed = date.fromisoformat(observed_date)
    if observed > issue:
        raise ValueError('Latest observation is after forecast issue')
    latest = points[0].get('last_value')
    if not isinstance(latest, (int, float)) or not math.isfinite(latest) or latest < 0:
        raise ValueError('Latest observed backlog is unavailable')
    if any(p.get('last_value') != latest for p in points):
        raise ValueError('Forecast latest-observation values differ')
    source = [dict(date=observed_date, median=float(latest), lower_80=float(latest), upper_80=float(latest),
                   kind='observed')]
    source += [dict(date=p['target_date'], median=p['point_forecast'], lower_80=p['lower_80'],
                    upper_80=p['upper_80'], kind='forecast', horizon_weeks=p['horizon_weeks'],
                    model=p.get('model')) for p in points]
    offsets = list(range(0, HORIZON_DAYS + 1, 7))
    anchor_days = [(date.fromisoformat(p['date']) - issue).days for p in source]
    values = {q: np.interp(offsets, anchor_days, [p[q] for p in source]).tolist()
              for q in ('median', 'lower_80', 'upper_80')}
    bridge_offsets = list(range(anchor_days[0], HORIZON_DAYS + 1, 7))
    if bridge_offsets[-1] != HORIZON_DAYS:
        bridge_offsets.append(HORIZON_DAYS)
    return dict(issue_date=issue_date, dates=[(issue + timedelta(days=d)).isoformat() for d in offsets],
        day_offsets=offsets, backlog_62=values, source_points=source,
        interpolation_dates=[(issue + timedelta(days=d)).isoformat() for d in bridge_offsets],
        interpolation_median=np.interp(bridge_offsets, anchor_days, [p['median'] for p in source]).tolist(),
        method='Linear interpolation from the latest reported count through issue-anchored 4/8/12-week blend forecasts; intermediate weeks are not independently fitted forecasts.',
        uncertainty='Original forecast 80% ranges are interpolated only as separate reference evidence, not combined with the change-sensitivity range.')


def eligibility(record: dict, prepared: dict, uncertainty: dict | None = None,
                forecast_error: str | None = None) -> dict:
    """Declare independent failure reasons; do not screen by forecast disagreement."""
    codes = []; reasons = []
    if record.get('status') != 'calibrated' or prepared.get('status') != 'ready':
        codes.append('simulation_inputs_unavailable')
        reasons.append(record.get('reason') or prepared.get('reason') or 'Published inputs do not support a complete queue-model calibration')
    else:
        if not record.get('acceptable_fit', False):
            codes.append('history_fit_failure')
            reasons.append('Queue model history fit exceeds the declared normalised RMSE threshold of 0.30')
        if not record.get('optimizer_success', False):
            codes.append('optimizer_failure')
            reasons.append('Queue-model capacity calibration did not converge successfully')
        if uncertainty is not None and uncertainty.get('weakly_identified', True):
            codes.append('weakly_identified')
            reasons.append('Published history does not identify both diagnosis and treatment capacity effects closely enough')
    if forecast_error:
        codes.append('forecast_unavailable')
        reasons.append(forecast_error)
    return dict(eligible=not codes, reason_codes=codes, reasons=reasons, rule=ELIGIBILITY_RULE)


def paired_plan(forecast_median: np.ndarray, absolute_plan: np.ndarray,
                same_pressure_baseline: np.ndarray, no_change_baseline: np.ndarray) -> tuple[dict, np.ndarray]:
    """Translate paired draws, then summarize; a helpful capacity delta is negative."""
    if absolute_plan.shape != same_pressure_baseline.shape or absolute_plan.shape != no_change_baseline.shape:
        raise ValueError('Paired simulator draws must have identical dimensions')
    if absolute_plan.ndim != 2 or absolute_plan.shape[1] != len(forecast_median):
        raise ValueError('Forecast and weekly simulator paths must share a calendar')
    capacity_delta = absolute_plan - same_pressure_baseline
    total_delta = absolute_plan - no_change_baseline
    displayed = np.maximum(0., np.asarray(forecast_median)[None, :] + total_delta)
    result = dict(backlog_62=summary(displayed), final_backlog=summary(displayed[:, -1]),
        capacity_delta=summary(capacity_delta), final_capacity_delta=summary(capacity_delta[:, -1]),
        total_delta=summary(total_delta), final_total_delta=summary(total_delta[:, -1]),
        absolute_simulator=dict(backlog_62=summary(absolute_plan), final_backlog=summary(absolute_plan[:, -1])))
    return result, displayed
