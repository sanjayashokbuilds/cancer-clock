"""Precompute forecast-anchored 12-week paired queue-model intervention effects."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.stats import poisson

from config import OUTPUTS_DIR
from models.features import load_sources
from sim.calibrate import prepare
from sim.decisions import DOSES, HORIZON as LEGACY_RANDOM_HORIZON, RUNS, SEED, simulate_fast, validate_calibration_inputs
from sim.forecast_plan import HORIZON_DAYS, eligibility, forecast_path, paired_plan
from sim.scenarios import Scenario, summary
from sim.simulator import initial_state
from sim.uncertainty import capacity_draws

TARGET_DIR = OUTPUTS_DIR / 'planning_grid'
SCHEMA_VERSION = 2
HORIZON = HORIZON_DAYS
PARAMETER_KEYS = ['strike', 'winter', 'surge']
SOURCE_FILES = ['simulation_calibration.json', 'bottlenecks.json', 'decision_support.json', 'forecasts_latest.json']


def source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((OUTPUTS_DIR / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def combinations() -> list[tuple[str, dict[str, bool]]]:
    result = []
    for mask in range(8):
        flags = {key: bool(mask & (1 << i)) for i, key in enumerate(PARAMETER_KEYS)}
        result.append(('_'.join(key for key in PARAMETER_KEYS if flags[key]) or 'none', flags))
    return result


def scenario_for(flags: dict[str, bool], stage: str = 'diagnosis', dose: int = 0) -> Scenario:
    if stage not in {'diagnosis', 'treatment'} or dose not in DOSES:
        raise ValueError('Only exact precomputed stage/dose combinations are supported')
    return Scenario(strike_days=5 if flags['strike'] else 0,
                    winter_days=42 if flags['winter'] else 0,
                    surge_days=28 if flags['surge'] else 0,
                    **{f'extra_{stage}_capacity': dose / 100})


def build_trust(payload: tuple) -> dict:
    record, prepared, hashes = payload[:3]
    forecast = payload[3] if len(payload) > 3 else {}
    previous_uncertainty = payload[4] if len(payload) > 4 else None
    common = dict(schema_version=SCHEMA_VERSION, org_code=record['org_code'],
                  issue_date=str(record.get('issue_date', prepared.get('issue_date', '')))[:10], input_sha256=hashes)
    # Simulation-input failures are meaningful without requiring a forecast.
    gate = eligibility(record, prepared, previous_uncertainty)
    if not gate['eligible']:
        return dict(**common, status='unavailable', reason='; '.join(gate['reasons']), eligibility=gate)
    try:
        reference = forecast_path(forecast, common['issue_date'])
    except ValueError as exc:
        gate = eligibility(record, prepared, previous_uncertainty, str(exc))
        return dict(**common, status='unavailable', reason='; '.join(gate['reasons']), eligibility=gate)

    ratios, uncertainty = capacity_draws(record, prepared, runs=RUNS, seed=SEED + 113)
    gate = eligibility(record, prepared, uncertainty)
    if not gate['eligible']:
        return dict(**common, status='unavailable', reason='; '.join(gate['reasons']),
                    eligibility=gate, parameter_uncertainty=uncertainty)
    rate = record['arrivals_per_day']; conversion = record['conversion_proxy']
    dc = rate * ratios[:, 0, None]; tc = rate * conversion * ratios[:, 1, None]
    initial = initial_state(rate, conversion, float(prepared['observed'][0]), record['prior']['diagnosis_share'])
    history = np.broadcast_to(prepared['arrivals'], (RUNS, len(prepared['arrivals'])))
    _, fitted_end = simulate_fast(initial, history, dc, tc, conversion)
    bridge_days = (pd.Timestamp(record['issue_date']) - pd.Timestamp(record['observation_end'])).days
    rng = np.random.default_rng(SEED)
    bridge_arrivals = rng.poisson(rate, (RUNS, bridge_days))
    bridge_noise = rng.lognormal(-.5 * .05 ** 2, .05, (2, RUNS, bridge_days))
    _, start = simulate_fast(fitted_end, bridge_arrivals, dc * bridge_noise[0], tc * bridge_noise[1], conversion)
    # Retain the previous stream layout, so the 12-week absolute paths can be
    # checked against the archived six-month simulation without changing noise.
    u = rng.uniform(1e-10, 1 - 1e-10, (RUNS, LEGACY_RANDOM_HORIZON))[:, :HORIZON]
    noise = rng.lognormal(-.5 * .05 ** 2, .05, (2, RUNS, LEGACY_RANDOM_HORIZON))[:, :, :HORIZON]
    base_arrivals = poisson.ppf(u, rate)
    surge_arrivals = poisson.ppf(u, rate * Scenario(surge_days=28).multipliers(HORIZON)[0])

    split = Scenario().intervention_start_day
    prefix, prefix_end = simulate_fast(start, base_arrivals[:, :split],
        dc * noise[0, :, :split], tc * noise[1, :, :split], conversion)
    sample = np.arange(0, HORIZON + 1, 7)
    dates = reference['dates']
    central = np.asarray(reference['backlog_62']['median'])
    scenarios = []; no_change = None
    for key, flags in combinations():
        arrivals = surge_arrivals if flags['surge'] else base_arrivals
        plans = {'diagnosis': [], 'treatment': []}
        marginal = {}; zero_draws = None; zero_display = None; zero_plan = None
        for stage in plans:
            for dose in DOSES:
                if dose == 0 and zero_plan is not None:
                    plans[stage].append(zero_plan)
                    continue
                scenario = scenario_for(flags, stage, dose)
                _, df, tf = scenario.multipliers(HORIZON)
                tail, _ = simulate_fast(prefix_end, arrivals[:, split:],
                    dc * noise[0, :, split:] * df[split:],
                    tc * noise[1, :, split:] * tf[split:], conversion)
                backlog = np.concatenate((prefix['backlog_62'][:, :split], tail['backlog_62']), axis=1)[:, sample]
                if dose == 0:
                    zero_draws = backlog
                    if key == 'none':
                        no_change = backlog
                translated, displayed = paired_plan(central, backlog, zero_draws, no_change)
                plan = dict(extra_capacity_pct=dose, **translated)
                plans[stage].append(plan)
                if dose == 0:
                    zero_display = displayed
                    zero_plan = plan
                if dose == 5:
                    # This is the paired effect on the displayed 12-week count,
                    # including the same non-negativity floor as the decision UI.
                    marginal[stage] = summary((zero_display[:, -1] - displayed[:, -1]) / 5)
        marginal['unit'] = 'fewer people at 12 weeks per extra percentage point of capacity, averaged from 0 to 5%'
        pressure = zero_draws - no_change
        scenarios.append(dict(key=key, flags=flags, plans=plans, marginal_benefit=marginal,
            pressure_delta=summary(pressure), final_pressure_delta=summary(pressure[:, -1])))
    return dict(**common, status='ready', eligibility=gate, runs=RUNS, horizon_days=HORIZON,
        capacity_percent=DOSES, dates=dates, day_offsets=sample.tolist(), forecast_path=reference,
        scenarios=scenarios, prior_conflict=record.get('prior_direction_conflict', False),
        acceptable_fit=record.get('acceptable_fit', False), parameter_uncertainty=uncertainty,
        interpretation='The forecast supplies the waiting-list level; paired queue-model differences supply the effect of a change. Conditional planning sensitivity, not a validated causal effect.',
        assumptions=dict(intervention_start_day=28, extra_capacity_duration='continues to day84',
            strike_days=5, strike_factor=.952, winter_days=42, winter_capacity_loss=.10,
            surge_days=28, referral_increase=.20,
            combined_shocks='Strike and winter capacity multipliers multiply; referral surge affects arrivals. All begin on day28.',
            comparison='No extra capacity uses the same selected pressures. With no pressure or capacity change, the displayed path equals the statistical forecast.',
            formula='displayed = max(0, forecast_point + simulator(plan, pressures) - simulator(no capacity, no pressures)); capacity delta = simulator(plan, pressures) - simulator(no capacity, same pressures)',
            pairing='Capacity parameters, arrival uniforms and service-noise draws are identical across each comparison. Differences are formed per draw before any quantile.',
            ranges='10th–90th percentiles of the paired change, translated around a fixed central forecast and floored at zero. These conditional sensitivity ranges exclude forecast-level uncertainty and are not combined predictive intervals.',
            forecast_ranges='Original forecast 80% ranges are retained separately in forecast_path for evidence; no independence or correlation assumption combines them with intervention effects.',
            absolute_outputs='The original six-month absolute simulation is retained in decision_support.json for Evidence only.',
            serialization='Full-precision JSON numbers preserve equality with source forecast anchors; paired differences, floor and quantiles are computed before serialization.'))


def rounded(value):
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError('Non-finite grid output')
        return value
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rounded(item) for item in value]
    return value


def write_record(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(rounded(value), separators=(',', ':'), allow_nan=False) + '\n')
    temporary.replace(path)


def validate_record(record: dict, hashes: dict[str, str] | None = None) -> None:
    if record['schema_version'] != SCHEMA_VERSION:
        raise ValueError('Planning grid schema differs')
    if hashes is not None and record['input_sha256'] != hashes:
        raise ValueError('Planning grid sources differ; rebuild it')
    if record['status'] == 'unavailable':
        if not record.get('reason') or record.get('eligibility', {}).get('eligible', True):
            raise ValueError('Unavailable planning grid needs a reason')
        return
    if not record.get('eligibility', {}).get('eligible'):
        raise ValueError('Ready planning grid fails eligibility')
    if record['runs'] != RUNS or record['horizon_days'] != HORIZON or record['capacity_percent'] != DOSES:
        raise ValueError('Planning grid parameters differ')
    if len(record['dates']) != len(record['day_offsets']) or record['day_offsets'] != list(range(0, HORIZON + 1, 7)):
        raise ValueError('Planning grid calendar differs')
    if [(s['key'], s['flags']) for s in record['scenarios']] != combinations():
        raise ValueError('Planning grid shock combinations differ')
    if record['forecast_path']['dates'] != record['dates']:
        raise ValueError('Forecast and planning calendars differ')
    reference = np.asarray(record['forecast_path']['backlog_62']['median'])
    unshocked = record['scenarios'][0]['plans']['diagnosis'][0]
    if not np.array_equal(unshocked['backlog_62']['median'], reference):
        raise ValueError('No-change planning path differs from forecast')
    for scenario in record['scenarios']:
        for stage in ['diagnosis', 'treatment']:
            plans = scenario['plans'][stage]
            if [plan['extra_capacity_pct'] for plan in plans] != DOSES:
                raise ValueError('Planning grid dose combinations differ')
            for plan in plans:
                q = plan['backlog_62']
                if any(len(q[name]) != len(record['dates']) for name in ['median', 'lower_80', 'upper_80']):
                    raise ValueError('Planning grid trajectory length differs')
                low = np.asarray(q['lower_80']); med = np.asarray(q['median']); high = np.asarray(q['upper_80'])
                if not (np.isfinite(low).all() and np.isfinite(med).all() and np.isfinite(high).all()
                        and (0 <= low).all() and (low <= med).all() and (med <= high).all()):
                    raise ValueError('Invalid planning grid range')
                for quantile in q:
                    if q[quantile][-1] != plan['final_backlog'][quantile]:
                        raise ValueError('Planning grid endpoint differs from trajectory')
                for effect_name in ['capacity_delta', 'total_delta']:
                    effect = plan[effect_name]
                    if any(len(effect[name]) != len(record['dates']) for name in ['median', 'lower_80', 'upper_80']):
                        raise ValueError('Paired effect trajectory length differs')
                    lo, mid, hi = [np.asarray(effect[name]) for name in ['lower_80', 'median', 'upper_80']]
                    if not (np.isfinite(lo).all() and np.isfinite(mid).all() and np.isfinite(hi).all()
                            and (lo <= mid).all() and (mid <= hi).all()):
                        raise ValueError('Invalid paired change range')
                    if any(effect[name][-1] != plan['final_' + effect_name][name] for name in effect):
                        raise ValueError('Paired effect endpoint differs')
                if plan['extra_capacity_pct'] == 0 and any(any(v != 0 for v in values) for values in plan['capacity_delta'].values()):
                    raise ValueError('Zero extra capacity has a nonzero capacity effect')
        if scenario['plans']['diagnosis'][0] != scenario['plans']['treatment'][0]:
            raise ValueError('Zero-capacity baselines are not paired')


def check() -> dict:
    manifest = json.loads((TARGET_DIR / 'manifest.json').read_text())
    hashes = source_hashes()
    if manifest['input_sha256'] != hashes:
        raise ValueError('Planning manifest sources differ')
    from pipeline.universe import load_core_trusts
    if set(manifest['files']) != set(load_core_trusts().org_code):
        raise ValueError('Planning grid cohort differs')
    ready = 0
    for code, expected in manifest['files'].items():
        path = TARGET_DIR / f'{code}.json'
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Planning grid file hash differs: ' + code)
        record = json.loads(path.read_text())
        validate_record(record, hashes)
        if record['org_code'] != code or record['issue_date'] != manifest['issue_date']:
            raise ValueError('Planning grid identity or issue differs: ' + code)
        ready += record['status'] == 'ready'
    if ready != manifest['ready_trusts']:
        raise ValueError('Planning grid availability differs')
    print(f'Planning grid passed: {ready} ready trusts, {len(manifest["files"])} total', flush=True)
    return manifest


def run(codes: list[str] | None = None, workers: int = 4, resume: bool = True) -> dict:
    started = time.monotonic()
    TARGET_DIR.mkdir(exist_ok=True)
    calibration = json.loads((OUTPUTS_DIR / 'simulation_calibration.json').read_text())
    validate_calibration_inputs(calibration)
    hashes = source_hashes()
    selected = [r for r in calibration['trusts'] if not codes or r['org_code'] in codes]
    if codes and set(codes) - {r['org_code'] for r in selected}:
        raise ValueError('Unknown trust code')
    forecasts = {r['org_code']: r for r in json.loads((OUTPUTS_DIR / 'forecasts_latest.json').read_text())['trusts']}
    decisions = {r['org_code']: r for r in json.loads((OUTPUTS_DIR / 'decision_support.json').read_text())['trusts']}
    sources = load_sources(); payloads = []; completed = 0
    for record in selected:
        path = TARGET_DIR / f'{record["org_code"]}.json'
        if resume and path.is_file():
            try:
                cached = json.loads(path.read_text())
                validate_record(cached, hashes)
                if cached['org_code'] != record['org_code'] or cached['issue_date'] != calibration['issue_date']:
                    raise ValueError('Cached planning grid identity or issue differs')
                completed += 1
                continue
            except (ValueError, KeyError, json.JSONDecodeError):
                pass
        prepared = prepare(sources, record['org_code'], pd.Timestamp(calibration['issue_date']))
        prepared.setdefault('issue_date', calibration['issue_date'])
        payloads.append((record, prepared, hashes, forecasts.get(record['org_code'], {}),
                         decisions.get(record['org_code'], {}).get('parameter_uncertainty')))
    errors = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(build_trust, p): p[0]['org_code'] for p in payloads}
        for future in as_completed(pending):
            try:
                result = future.result()
                validate_record(result, hashes)
            except Exception as exc:
                errors.append((pending[future], str(exc)))
                print(f'Planning grid failed {pending[future]}: {exc}', flush=True)
                continue
            write_record(TARGET_DIR / f'{result["org_code"]}.json', result)
            completed += 1
            print(f'Planning grid {completed}/{len(selected)} {result["org_code"]} {result["status"]} ({time.monotonic()-started:.0f}s)', flush=True)
    if errors:
        raise ValueError('Planning grid failures: ' + repr(errors))
    manifest = dict(schema_version=SCHEMA_VERSION, issue_date=calibration['issue_date'],
        input_sha256=hashes, runs=RUNS, horizon_days=HORIZON, capacity_percent=DOSES,
        shock_combinations=8, unique_plans_per_ready_trust=8 * (2 * len(DOSES) - 1),
        partial=bool(codes), files={}, ready_trusts=0, unavailable_trusts=0)
    for record in selected:
        code = record['org_code']; path = TARGET_DIR / f'{code}.json'
        item = json.loads(path.read_text())
        manifest['files'][code] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest['ready_trusts' if item['status'] == 'ready' else 'unavailable_trusts'] += 1
    if not codes:
        write_record(TARGET_DIR / 'manifest.json', manifest)
    print(f'Planning grid complete: {completed} trusts in {time.monotonic()-started:.1f}s', flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trust', action='append')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--no-resume', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    check() if args.check else run(args.trust, args.workers, not args.no_resume)
