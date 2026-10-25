"""Reproduce availability transitions and the Oxford 12-week planning check."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import hashlib
import json

from config import OUTPUTS_DIR


def review() -> dict:
    def read(name: str) -> dict:
        return json.loads((OUTPUTS_DIR / name).read_text())

    legacy = read('decision_support.json')
    forecasts = read('forecasts_latest.json')
    manifest = read('planning_grid/manifest.json')
    expected = (date.fromisoformat(forecasts['issue_date']) + timedelta(weeks=12)).isoformat()
    forecast_by_code = {r['org_code']: r for r in forecasts['trusts']}
    old = {}; rows = []; matched = 0; comparable = 0
    for record in legacy['trusts']:
        code = record['org_code']
        point = next((p for p in forecast_by_code[code]['forecasts']
                      if p['horizon_weeks'] == 12 and p['target_date'] == expected), None)
        absolute = next((p for p in record.get('scenario_comparison', []) if p['key'] == 'baseline'), None)
        if record['status'] != 'ready':
            old[code] = 'simulator_unavailable'
        elif point is None or absolute is None or expected not in absolute['dates']:
            old[code] = 'forecast_check_unavailable'
        else:
            value = absolute['backlog_62']['median'][absolute['dates'].index(expected)]
            inside = point['lower_80'] <= value <= point['upper_80']
            comparable += 1; matched += inside
            old[code] = 'available' if inside else 'absolute_level_mismatch'
        grid = read(f'planning_grid/{code}.json')
        if grid['schema_version'] != 2 or grid['input_sha256'] != manifest['input_sha256']:
            raise ValueError(f'Mixed recovery grid: {code}')
        eligibility = grid.get('eligibility', {})
        rows.append(dict(org_code=code, name=record['name'], before=old[code],
            after='available' if grid['status'] == 'ready' else 'held_back',
            reason_codes=eligibility.get('reason_codes', []),
            reasons=eligibility.get('reasons', [grid.get('reason')])))
    before = dict(Counter(old.values()))
    after = dict(Counter(row['after'] for row in rows))
    excluded = [r for r in rows if r['after'] == 'held_back']
    oxford = read('planning_grid/RTH.json')
    strike = next(s for s in oxford['scenarios'] if s['key'] == 'strike')
    base = next(p for p in strike['plans']['treatment'] if p['extra_capacity_pct'] == 0)
    plan = next(p for p in strike['plans']['treatment'] if p['extra_capacity_pct'] == 10)
    output = dict(issue_date=forecasts['issue_date'], horizon_days=84, comparison_date=expected,
        before=before, after=after,
        released=[r['org_code'] for r in rows if r['before'] != 'available' and r['after'] == 'available'],
        newly_held=[r['org_code'] for r in rows if r['before'] == 'available' and r['after'] == 'held_back'],
        held_back=excluded,
        original_absolute_model_within_forecast_80=dict(inside=matched, comparable=comparable,
            interpretation='Unchanged original models; this diagnostic no longer gates plans.'),
        optional_forecast_weighted_recalibration_performed=False,
        oxford_strike_treatment_10=dict(org_code='RTH', date=expected,
            forecast_level=oxford['forecast_path']['backlog_62']['median'][-1],
            no_extra_capacity=base['final_backlog'], plan=plan['final_backlog'],
            paired_capacity_change=plan['final_capacity_delta'],
            paired_total_change=plan['final_total_delta'],
            marginal_benefit_0_to_5_percent=strike['marginal_benefit']['treatment']),
        uncertainty='Plan ranges vary paired simulation changes around fixed central forecasts; forecast-level uncertainty is excluded.',
        source_sha256={name: hashlib.sha256((OUTPUTS_DIR / name).read_bytes()).hexdigest()
                       for name in ['forecasts_latest.json', 'decision_support.json', 'planning_grid/manifest.json']})
    (OUTPUTS_DIR / 'recovery_plan_review.json').write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps(output, indent=2))
    return output


if __name__ == '__main__':
    review()
