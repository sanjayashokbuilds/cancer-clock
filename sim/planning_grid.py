"""Exact precomputed shock/capacity combinations for the presentation controls.

This is an export of the existing queue model, capacity ensemble and random
streams. It does not refit or adjust forecasts, calibration or decision outputs.
"""
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
from sim.decisions import DOSES, HORIZON, RUNS, SEED, simulate_fast, validate_calibration_inputs
from sim.scenarios import Scenario, summary
from sim.simulator import initial_state
from sim.uncertainty import capacity_draws

TARGET_DIR = OUTPUTS_DIR / 'planning_grid'
SCHEMA_VERSION = 1
PARAMETER_KEYS = ['strike', 'winter', 'surge']
SOURCE_FILES = ['simulation_calibration.json', 'bottlenecks.json', 'decision_support.json']


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


def build_trust(payload: tuple[dict, dict, dict[str, str]]) -> dict:
    record, prepared, hashes = payload
    common = dict(schema_version=SCHEMA_VERSION, org_code=record['org_code'],
                  issue_date=str(record.get('issue_date', prepared.get('issue_date', '')))[:10], input_sha256=hashes)
    if record['status'] != 'calibrated' or prepared['status'] != 'ready':
        return dict(**common, status='unavailable', reason=record.get('reason', prepared.get('reason', 'Missing calibration')))

    ratios, uncertainty = capacity_draws(record, prepared, runs=RUNS, seed=SEED + 113)
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
    u = rng.uniform(1e-10, 1 - 1e-10, (RUNS, HORIZON))
    noise = rng.lognormal(-.5 * .05 ** 2, .05, (2, RUNS, HORIZON))
    base_arrivals = poisson.ppf(u, rate)
    surge_arrivals = poisson.ppf(u, rate * Scenario(surge_days=28).multipliers(HORIZON)[0])

    # Every intervention starts at day28. Reuse the identical prefix exactly;
    # no interpolation or approximation is introduced by this split replay.
    split = Scenario().intervention_start_day
    prefix, prefix_end = simulate_fast(start, base_arrivals[:, :split],
        dc * noise[0, :, :split], tc * noise[1, :, :split], conversion)
    sample = np.unique(np.r_[np.arange(0, HORIZON + 1, 7), HORIZON])
    dates = [str((pd.Timestamp(record['issue_date']) + pd.Timedelta(days=int(day))).date()) for day in sample]
    scenarios = []
    for key, flags in combinations():
        arrivals = surge_arrivals if flags['surge'] else base_arrivals
        plans = {'diagnosis': [], 'treatment': []}
        marginal = {}; zero_final = None; zero_plan = None
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
                backlog = np.concatenate((prefix['backlog_62'][:, :split], tail['backlog_62']), axis=1)
                final = backlog[:, -1]
                plan = dict(extra_capacity_pct=dose, backlog_62=summary(backlog[:, sample]), final_backlog=summary(final))
                plans[stage].append(plan)
                if dose == 0:
                    zero_final = final
                    zero_plan = plan
                if dose == 5:
                    marginal[stage] = summary((zero_final - final) / 5)
        marginal['unit'] = 'fewer people per extra percentage point of capacity, averaged from 0 to 5%'
        scenarios.append(dict(key=key, flags=flags, plans=plans, marginal_benefit=marginal))
    return dict(**common, status='ready', runs=RUNS, horizon_days=HORIZON,
        capacity_percent=DOSES, dates=dates, day_offsets=sample.tolist(),
        scenarios=scenarios, prior_conflict=record.get('prior_direction_conflict', False),
        acceptable_fit=record.get('acceptable_fit', False),
        parameter_uncertainty=uncertainty,
        interpretation='Conditional comparisons from the existing daily queue model. Not validated forecasts or causal capacity effects.',
        assumptions=dict(intervention_start_day=28, extra_capacity_duration='continues to day182',
            strike_days=5, strike_factor=.952, winter_days=42, winter_capacity_loss=.10,
            surge_days=28, referral_increase=.20,
            combined_shocks='Strike and winter capacity multipliers multiply; referral surge affects arrivals. All begin on day28.',
            comparison='Do nothing uses the same selected shocks and random draws with no extra capacity.',
            ranges='10th–90th percentiles of process and calibrated capacity variation; structural assumptions remain fixed.',
            serialization='Counts rounded to 0.001 people only after full-precision simulation and quantiles.'))


def rounded(value):
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError('Non-finite grid output')
        return round(value, 3)
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
        if not record.get('reason'):
            raise ValueError('Unavailable planning grid needs a reason')
        return
    if record['runs'] != RUNS or record['horizon_days'] != HORIZON or record['capacity_percent'] != DOSES:
        raise ValueError('Planning grid parameters differ')
    if len(record['dates']) != len(record['day_offsets']) or record['day_offsets'] != list(range(0, 183, 7)):
        raise ValueError('Planning grid calendar differs')
    if [(s['key'], s['flags']) for s in record['scenarios']] != combinations():
        raise ValueError('Planning grid shock combinations differ')
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
        payloads.append((record, prepared, hashes))
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
