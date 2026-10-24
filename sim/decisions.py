"""Precompute paired capacity dose responses with calibration-parameter uncertainty."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.stats import poisson

from config import OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from models.features import load_sources
from models.forecast import write_json
from sim.calibrate import assumption_object, prepare
from sim.scenarios import Scenario, recovery_days, summary
from sim.simulator import AGE_MAX, DIAGNOSIS_MIN_DAYS, State, initial_state

DOSES = [0, 1, 2, 3, 4, 5, 10, 15, 20]
HORIZON = 182
RUNS = 256
SEED = 42
TARGET = OUTPUTS_DIR / 'decision_support.json'


def validate_calibration_inputs(calibration: dict) -> None:
    """Refuse to combine a stale fitted calibration with changed raw inputs."""
    for name, expected in calibration['input_sha256'].items():
        path = (STATIC_DIR if name.endswith('.csv') else PROCESSED_DIR) / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Calibration input changed; refit before decisions: ' + name)


def simulate_fast(initial: State, arrivals: np.ndarray, diagnosis_capacity: np.ndarray | float,
                  treatment_capacity: np.ndarray | float, conversion: float) -> tuple[dict, State]:
    """Same daily cohort equations as simulator.simulate, with fewer temporary arrays."""
    arrivals = np.asarray(arrivals, dtype=float)
    if arrivals.ndim != 2:
        raise ValueError('Expected draws × days')
    runs, days = arrivals.shape
    d = np.broadcast_to(initial.diagnosis, (runs, AGE_MAX + 1)).copy()
    t = np.broadcast_to(initial.treatment, (runs, AGE_MAX + 1)).copy()
    dc = np.broadcast_to(diagnosis_capacity, arrivals.shape)
    tc = np.broadcast_to(treatment_capacity, arrivals.shape)
    if np.any(arrivals < 0) or np.any(dc < 0) or np.any(tc < 0) or not 0 <= conversion <= 1:
        raise ValueError('Nonnegative flows and capacities, conversion in [0,1] required')
    backlog = np.zeros((runs, days + 1)); long_wait = np.zeros_like(backlog)
    def record(day: int) -> None:
        backlog[:, day] = d[:, 63:].sum(axis=1) + t[:, 63:].sum(axis=1)
        long_wait[:, day] = d[:, 105:].sum(axis=1) + t[:, 105:].sum(axis=1)
    record(0)
    for day in range(days):
        dtail = d[:, -1].copy(); ttail = t[:, -1].copy()
        d = np.roll(d, 1, axis=1); t = np.roll(t, 1, axis=1)
        d[:, -1] += dtail; t[:, -1] += ttail
        d[:, 0] = arrivals[:, day]; t[:, 0] = 0.
        total_d = d[:, DIAGNOSIS_MIN_DAYS:].sum(axis=1); total_t = t.sum(axis=1)
        ds = np.minimum(1., np.divide(dc[:, day], total_d, out=np.zeros(runs), where=total_d > 0))
        ts = np.minimum(1., np.divide(tc[:, day], total_t, out=np.zeros(runs), where=total_t > 0))
        t *= (1 - ts[:, None])
        diagnosed = d[:, DIAGNOSIS_MIN_DAYS:] * ds[:, None]
        t[:, DIAGNOSIS_MIN_DAYS:] += conversion * diagnosed
        d[:, DIAGNOSIS_MIN_DAYS:] -= diagnosed
        record(day + 1)
    return dict(backlog_62=backlog, long_wait_104=long_wait, days=np.arange(days + 1)), State(d, t)


def treatment_label(bottleneck: dict) -> tuple[str, str]:
    driver = bottleneck.get('treatment_driver')
    if driver and bottleneck.get('evidence_status') == 'screened':
        modality = {'d31_radiotherapy': 'Radiotherapy', 'd31_surgery': 'Surgery',
                    'd31_drugs': 'Anti-cancer drug treatment'}.get(driver['key'])
        if modality:
            return f'{modality} capacity (stage proxy)', (
                f'{modality} is the adverse 31-day driver. The simulation changes the entire treatment-stage '
                'service budget; it does not estimate a modality-specific staffing effect.')
    return 'Treatment capacity', 'Whole treatment-stage service budget; no supported modality-specific driver assigned.'


def experiment_plans() -> list[tuple[str, str, str, int, Scenario]]:
    plans = [('baseline', 'Baseline', 'none', 0, Scenario()),
             ('strike', 'Five-day strike', 'none', 0, Scenario(name='strike', strike_days=5))]
    for stage in ['diagnosis', 'treatment']:
        for pct in DOSES[1:]:
            kwargs = {f'extra_{stage}_capacity': pct / 100}
            key = f'strike_plus_{stage}' if pct == 10 else f'strike_{stage}_{pct}'
            plans.append((key, f'Strike + {pct}% {stage} capacity', stage, pct,
                          Scenario(name=key, strike_days=5, **kwargs)))
    plans += [('winter_dip', 'Six-week winter dip', 'none', 0, Scenario(name='winter_dip', winter_days=42)),
              ('referral_surge', 'Four-week referral surge', 'none', 0, Scenario(name='referral_surge', surge_days=28))]
    return plans


def width(q: dict) -> float:
    return float(q['upper_80'] - q['lower_80'])


def build_trust(payload: tuple[dict, dict, dict]) -> dict:
    """Construct one complete ready/unavailable decision record; no disk mutation."""
    from sim.uncertainty import capacity_draws
    record, prepared, bottleneck = payload
    label, caveat = treatment_label(bottleneck)
    common = dict(org_code=record['org_code'], name=record['name'],
                  issue_date=str(record.get('issue_date', prepared.get('issue_date', '')))[:10],
                  prior_conflict=record.get('prior_direction_conflict', False),
                  acceptable_fit=record.get('acceptable_fit', False),
                  treatment_label=label, treatment_label_caveat=caveat,
                  bottleneck_label=bottleneck['label'])
    if record['status'] != 'calibrated' or prepared['status'] != 'ready':
        return dict(**common, status='unavailable', reason=record.get('reason', prepared.get('reason', 'Missing calibration')))
    ratios, uncertainty = capacity_draws(record, prepared, runs=RUNS, seed=SEED + 113)
    rate = record['arrivals_per_day']; conversion = record['conversion_proxy']
    dc = rate * ratios[:, 0, None]; tc = rate * conversion * ratios[:, 1, None]
    fixed_dc = record['diagnosis_capacity_per_day']; fixed_tc = record['treatment_capacity_per_day']
    initial = initial_state(rate, conversion, float(prepared['observed'][0]), record['prior']['diagnosis_share'])
    history = np.broadcast_to(prepared['arrivals'], (RUNS, len(prepared['arrivals'])))
    _, fitted_end = simulate_fast(initial, history, dc, tc, conversion)
    fixed_end = State(np.array(record['fitted_end_diagnosis_age_days']), np.array(record['fitted_end_treatment_age_days']))
    bridge_days = (pd.Timestamp(record['issue_date']) - pd.Timestamp(record['observation_end'])).days
    rng = np.random.default_rng(SEED)
    bridge_arrivals = rng.poisson(rate, (RUNS, bridge_days))
    bridge_noise = rng.lognormal(-.5 * .05 ** 2, .05, (2, RUNS, bridge_days))
    _, start = simulate_fast(fitted_end, bridge_arrivals, dc * bridge_noise[0], tc * bridge_noise[1], conversion)
    _, fixed_start = simulate_fast(fixed_end, bridge_arrivals, fixed_dc * bridge_noise[0], fixed_tc * bridge_noise[1], conversion)
    u = rng.uniform(1e-10, 1 - 1e-10, (RUNS, HORIZON))
    service_noise = rng.lognormal(-.5 * .05 ** 2, .05, (2, RUNS, HORIZON))
    base_arrivals = poisson.ppf(u, rate)
    surge_factor = Scenario(surge_days=28).multipliers(HORIZON)[0]
    surge_arrivals = poisson.ppf(u, rate * surge_factor)
    kept = {'baseline', 'strike', 'strike_plus_diagnosis', 'strike_plus_treatment', 'winter_dip', 'referral_surge'}
    raw = {}; exported = []; dose = {'diagnosis': [], 'treatment': []}; dose_raw = {}
    samples = np.unique(np.r_[np.arange(0, HORIZON + 1, 7), HORIZON])
    dates = [str((pd.Timestamp(record['issue_date']) + pd.Timedelta(days=int(day))).date()) for day in samples]
    assumptions = assumption_object(record)
    assumptions['parameter_uncertainty'] = dict(value=uncertainty, unit='daily capacity ratios',
        source='estimated from data + explicit weak-identification assumptions',
        note='Residual-block bootstrap with local joint sensitivity and nonlinear-fit filtering; not full structural uncertainty.')
    assumptions['interpretation']['note'] = 'Process plus capacity-parameter sensitivity ranges; age mix, conversion and service-order uncertainty remain unquantified.'
    assumptions['scenario_grid'] = dict(value=dict(strike_days=5, strike_start_day=28, strike_factor=.952,
        intervention_start_day=28, extra_capacity_percent=DOSES, horizon_days=HORIZON, runs=RUNS, seed=SEED),
        unit='editable planning experiment', source='assumed', note='Dose curves include the five-day strike. Capacity stays added from day28 onwards.')
    comparisons = []; fixed_dose = {'diagnosis': [], 'treatment': []}
    for key, name, stage, pct, scenario in experiment_plans():
        _, df, tf = scenario.multipliers(HORIZON)
        arrivals = surge_arrivals if key == 'referral_surge' else base_arrivals
        trajectory, _ = simulate_fast(start, arrivals, dc * service_noise[0] * df, tc * service_noise[1] * tf, conversion)
        final = trajectory['backlog_62'][:, -1]
        if key in kept or record['org_code'] == 'RTH':
            fixed, _ = simulate_fast(fixed_start, arrivals, fixed_dc * service_noise[0] * df,
                                     fixed_tc * service_noise[1] * tf, conversion)
            fixed_q = summary(fixed['backlog_62'][:, -1])
            if record['org_code'] == 'RTH':
                if key == 'strike':
                    for side in fixed_dose: fixed_dose[side].append(dict(extra_capacity_pct=0, **fixed_q))
                elif stage in fixed_dose:
                    fixed_dose[stage].append(dict(extra_capacity_pct=pct, **fixed_q))
        if key in kept:
            raw[key] = trajectory
            q = summary(final)
            pw = width(fixed_q); cw = width(q)
            comparisons.append(dict(key=key, process_only_width=pw, combined_width=cw,
                width_change=cw - pw, ratio=cw / pw if pw > 1e-12 else None,
                ratio_reason=None if pw > 1e-12 else 'Process-only interval width is zero or numerically negligible',
                process_only_final_backlog=fixed_q, combined_final_backlog=q))
            shock_end = max(scenario.strike_start_day + scenario.strike_days if scenario.strike_days else 0,
                            scenario.winter_start_day + scenario.winter_days if scenario.winter_days else 0,
                            scenario.surge_start_day + scenario.surge_days if scenario.surge_days else 0)
            plan_assumptions = dict(assumptions, experiment=dict(value=asdict(scenario), unit='scenario parameters',
                source='assumed', note='The same parameter draw and random numbers are paired across plans.'))
            exported.append(dict(key=key, name=name, stage=stage, extra_capacity_pct=pct,
                dates=dates, day_offsets=samples.tolist(),
                backlog_62=summary(trajectory['backlog_62'][:, samples]),
                long_wait_104=summary(trajectory['long_wait_104'][:, samples]), final_backlog=q,
                final_long_wait_104=summary(trajectory['long_wait_104'][:, -1]),
                final_backlog_change_vs_baseline=summary(final - raw['baseline']['backlog_62'][:, -1]),
                final_long_wait_change_vs_baseline=summary(trajectory['long_wait_104'][:, -1] - raw['baseline']['long_wait_104'][:, -1]),
                peak_backlog=summary(trajectory['backlog_62'].max(axis=1)),
                recovery=recovery_days(trajectory['backlog_62'], raw['baseline']['backlog_62'], shock_end) if shock_end else {'status': 'not_applicable_no_temporary_shock'},
                assumptions=plan_assumptions))
        if key == 'strike':
            for side in dose:
                dose[side].append(dict(extra_capacity_pct=0, **summary(final)))
                dose_raw[side, 0] = final
        elif stage in dose:
            dose[stage].append(dict(extra_capacity_pct=pct, **summary(final)))
            dose_raw[stage, pct] = final
    marginal = {side: summary((dose_raw[side, 0] - dose_raw[side, 5]) / 5) for side in dose}
    marginal['unit'] = 'fewer patients per +1 percentage point capacity, 0–5%'
    anchor = next(c for c in comparisons if c['key'] == 'strike_plus_treatment')
    return dict(**common, status='ready', runs=RUNS, horizon_days=HORIZON,
        calibration_rmse=record['rmse'], parameter_uncertainty=uncertainty,
        publication_bridge_days=bridge_days, assumptions=assumptions,
        dose_response=dict(scenario='five_day_strike', horizon_days=HORIZON, capacity_percent=DOSES,
            diagnosis=dose['diagnosis'], treatment=dose['treatment'], marginal_benefit=marginal,
            interpretation='Paired conditional sensitivity, not a causal capacity recommendation.'),
        scenario_comparison=exported, band_widening=dict(**anchor, comparisons=comparisons),
        process_only_dose_reference=fixed_dose if record['org_code'] == 'RTH' else None,
        uncertainty='10–90% process + calibrated capacity-parameter sensitivity ranges; not validated predictive intervals or full structural uncertainty.',
        long_wait_status='>104-day counts depend on unobserved age and stage-split assumptions.')


def check(report: dict | None = None) -> dict:
    from pipeline.universe import load_core_trusts
    report = report or json.loads(TARGET.read_text())
    validate_calibration_inputs(json.loads((OUTPUTS_DIR/'simulation_calibration.json').read_text()))
    for name, expected in report['input_sha256'].items():
        if hashlib.sha256((OUTPUTS_DIR / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Decision inputs changed: ' + name)
    if {t['org_code'] for t in report['trusts']} != set(load_core_trusts().org_code):
        raise ValueError('Decision coverage differs from live core trusts')
    for t in report['trusts']:
        if t['status'] == 'unavailable':
            if not t.get('reason'): raise ValueError('Unavailable trust missing reason')
            continue
        for side in ['diagnosis', 'treatment']:
            curve = t['dose_response'][side]
            if [p['extra_capacity_pct'] for p in curve] != DOSES:
                raise ValueError('Incomplete dose grid')
            for p in curve:
                if not 0 <= p['lower_80'] <= p['median'] <= p['upper_80']:
                    raise ValueError('Invalid dose ranges')
        if t['dose_response']['diagnosis'][0] != t['dose_response']['treatment'][0]:
            raise ValueError('Dose baselines not paired')
        for plan in t['scenario_comparison']:
            if not plan['assumptions']: raise ValueError('Missing scenario assumptions')
            for key in ['backlog_62', 'long_wait_104']:
                q=plan[key]
                if not (np.array(q['lower_80']) >= 0).all() or not (np.array(q['lower_80']) <= q['median']).all() or not (np.array(q['median']) <= q['upper_80']).all():
                    raise ValueError('Invalid trajectory ranges')
    print('Decision snapshot passed:', report['summary'])
    return report


def run(codes: list[str] | None = None, workers: int = 4) -> dict:
    started = time.monotonic()
    calibration = json.loads((OUTPUTS_DIR / 'simulation_calibration.json').read_text())
    validate_calibration_inputs(calibration)
    bottlenecks = {t['org_code']: t for t in json.loads((OUTPUTS_DIR / 'bottlenecks.json').read_text())['trusts']}
    sources = load_sources()
    records = [r for r in calibration['trusts'] if not codes or r['org_code'] in codes]
    payloads = []
    for r in records:
        prepared = prepare(sources, r['org_code'], pd.Timestamp(calibration['issue_date']))
        prepared.setdefault('issue_date', calibration['issue_date'])
        payloads.append((r, prepared, bottlenecks[r['org_code']]))
    output = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for record in pool.map(build_trust, payloads):
            output.append(record)
            print(f'Decisions {len(output)}/{len(records)} {record["org_code"]} {record["status"]} ({time.monotonic()-started:.0f}s)', flush=True)
    ready = [r for r in output if r['status'] == 'ready']
    ratios = [r['band_widening']['ratio'] for r in ready if r['band_widening']['ratio'] is not None]
    report = dict(stage=8, issue_date=calibration['issue_date'], availability_label=calibration['availability_label'],
        historical_vintage_verified=False, calibration_sha256=hashlib.sha256((OUTPUTS_DIR/'simulation_calibration.json').read_bytes()).hexdigest(),
        bottleneck_sha256=hashlib.sha256((OUTPUTS_DIR/'bottlenecks.json').read_bytes()).hexdigest(),
        input_sha256={n:hashlib.sha256((OUTPUTS_DIR/n).read_bytes()).hexdigest() for n in ['simulation_calibration.json','bottlenecks.json']},
        method='Paired residual-block bootstrap capacity uncertainty plus Poisson arrivals and service variation; daily age-cohort simulation.',
        summary=dict(core_trusts=len(output),ready_trusts=len(ready),unavailable_trusts=len(output)-len(ready),
            prior_conflicts=sum(r['prior_conflict'] for r in ready), runs=RUNS,
            median_band_width_ratio=float(np.median(ratios)) if ratios else None,
            valid_band_width_ratios=len(ratios),
            band_width_comparison='Day182 strike +10% treatment, combined vs process-only, paired noise'),
        trusts=output)
    target = TARGET if not codes else OUTPUTS_DIR / 'decision_support_sample.json'
    write_json(target, report)
    print('Written',target,'elapsed',round(time.monotonic()-started),flush=True)
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true');parser.add_argument('--trust',action='append')
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    check() if args.check else run(args.trust,args.workers)
