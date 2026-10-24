"""Paired Monte Carlo what-ifs with explicit assumptions and daily referral ages."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.stats import poisson

from config import OUTPUTS_DIR
from models.forecast import write_json
from sim.calibrate import assumption_object
from sim.simulator import State, simulate


@dataclass(frozen=True)
class Scenario:
    """Editable forcing after issue; capacity is changed separately in each stage."""
    name: str = 'baseline'
    strike_start_day: int = 28
    strike_days: int = 0
    strike_factor: float = .952
    winter_start_day: int = 28
    winter_days: int = 0
    winter_capacity_loss: float = .10
    surge_start_day: int = 28
    surge_days: int = 0
    referral_increase: float = .20
    intervention_start_day: int = 28
    extra_diagnosis_capacity: float = 0.
    extra_treatment_capacity: float = 0.

    def validate(self) -> None:
        for key, value in asdict(self).items():
            if key.endswith('_day') or key.endswith('_days'):
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f'{key} must be a nonnegative integer')
        for key in ['strike_factor','winter_capacity_loss','referral_increase','extra_diagnosis_capacity','extra_treatment_capacity']:
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f'{key} must be in [0,1]')

    def multipliers(self, days: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Scenario-only calendar vectors; never inject these assumptions into observed data."""
        self.validate()
        d = np.arange(days); arrivals = np.ones(days); diagnosis = np.ones(days); treatment = np.ones(days)
        strike = (d >= self.strike_start_day) & (d < self.strike_start_day + self.strike_days)
        winter = (d >= self.winter_start_day) & (d < self.winter_start_day + self.winter_days)
        surge = (d >= self.surge_start_day) & (d < self.surge_start_day + self.surge_days)
        diagnosis[strike] *= self.strike_factor; treatment[strike] *= self.strike_factor
        diagnosis[winter] *= 1 - self.winter_capacity_loss; treatment[winter] *= 1 - self.winter_capacity_loss
        arrivals[surge] *= 1 + self.referral_increase
        intervention = d >= self.intervention_start_day
        diagnosis[intervention] *= 1 + self.extra_diagnosis_capacity
        treatment[intervention] *= 1 + self.extra_treatment_capacity
        return arrivals, diagnosis, treatment


def summary(values: np.ndarray) -> dict:
    """Monte Carlo process range, not a validated 80% predictive interval."""
    low, median, high = np.quantile(values, [.1,.5,.9], axis=0)
    def convert(x: np.ndarray) -> object:
        return x.tolist() if np.ndim(x) else float(x)
    return dict(lower_80=convert(low), median=convert(median), upper_80=convert(high))


def recovery_days(backlog: np.ndarray, baseline: np.ndarray, shock_end: int,
                  sustained_days: int = 14) -> dict:
    """Return right-censored recovery, conditional on an assumed tolerance and duration."""
    tolerance = np.maximum(5., .05 * baseline)
    excess = backlog - baseline
    near = excess <= tolerance
    windows = np.lib.stride_tricks.sliding_window_view(near, sustained_days, axis=-1).all(axis=-1)
    # Referral surges can breach day 62 long after the surge ends. Do not count
    # the quiet period before that delayed excess peak as recovery.
    peak_days = shock_end + excess[:, shock_end:].argmax(axis=1)
    has_adverse_effect = (~near[:, shock_end:]).any(axis=1)
    search_start = np.where(has_adverse_effect, peak_days, shock_end)
    eligible = windows & (np.arange(windows.shape[-1])[None, :] >= search_start[:, None])
    recovered = eligible.any(axis=1)
    values = (np.argmax(eligible, axis=1)[recovered] - shock_end) / 7
    return dict(recovered_fraction=float(recovered.mean()),
        weeks_after_shock_end_among_recovered=summary(values) if len(values) else None,
        not_recovered_by_horizon=int((~recovered).sum()),
        definition='After shock end and the post-shock excess peak, excess over paired baseline <= max(5 patients, 5% baseline) for 14 consecutive days; measured from shock end. If never above tolerance, recovery is zero; non-recovery is censored.')


def compare(record: dict, scenarios: list[Scenario], *, runs: int = 256,
            horizon_days: int = 182, seed: int = 42) -> dict:
    """Bridge the publication gap, then compare plans using the same random draws."""
    if record['status'] != 'calibrated':
        raise ValueError('A calibrated trust is required')
    if not 200 <= runs <= 500 or horizon_days < 14 or horizon_days > 366:
        raise ValueError('Use 200–500 runs and a 14–366 day horizon')
    if not scenarios or scenarios[0] != Scenario():
        raise ValueError('First scenario must be the unmodified baseline')
    names = [s.name for s in scenarios]
    if len(set(names)) != len(names):
        raise ValueError('Scenario names must be unique')
    issue = pd.Timestamp(record['issue_date']); observed = pd.Timestamp(record['observation_end'])
    bridge_days = (issue - observed).days
    if bridge_days < 0:
        raise ValueError('Issue date precedes observed data')
    rate = record['arrivals_per_day']; conversion = record['conversion_proxy']
    dc, tc = record['diagnosis_capacity_per_day'], record['treatment_capacity_per_day']
    initial = State(np.array(record['fitted_end_diagnosis_age_days']), np.array(record['fitted_end_treatment_age_days']))
    rng = np.random.default_rng(seed)
    # Inverse-CDF coupling retains the same Poisson quantiles across different arrival rates.
    bridge_arrivals = rng.poisson(rate, (runs, bridge_days))
    bridge_noise = rng.lognormal(-.5*.05**2, .05, (2, runs, bridge_days))
    _, start = simulate(initial, bridge_arrivals, dc * bridge_noise[0], tc * bridge_noise[1], conversion)
    u = rng.uniform(1e-10, 1 - 1e-10, (runs, horizon_days))
    service_noise = rng.lognormal(-.5*.05**2, .05, (2, runs, horizon_days))
    raw = []; plans = []
    sample = np.unique(np.r_[np.arange(0, horizon_days + 1, 7), horizon_days])
    for scenario in scenarios:
        arrivals_factor, d_factor, t_factor = scenario.multipliers(horizon_days)
        arrivals = poisson.ppf(u, rate * arrivals_factor)
        trajectory, _ = simulate(start, arrivals, dc * service_noise[0] * d_factor,
            tc * service_noise[1] * t_factor, conversion, sample_every=1)
        raw.append(trajectory)
        assumptions = assumption_object(record)
        assumptions['experiment'] = dict(value=dict(**asdict(scenario), runs=runs, horizon_days=horizon_days, seed=seed),
            unit='scenario parameters', source='assumed', note='Editable forcing; simulated strike dates are hypothetical, not a prediction of industrial action.')
        assumptions['recovery_tolerance'] = dict(value='max(5 patients, 5% paired baseline), sustained 14 days after the post-shock excess peak',
            unit='patients and days', source='assumed', note='Recovery is censored at the simulation horizon.')
        plans.append(dict(name=scenario.name, scenario=asdict(scenario), assumptions=assumptions,
            dates=[str((issue + pd.Timedelta(days=int(day))).date()) for day in sample], day_offsets=sample.tolist(),
            backlog_62=summary(trajectory['backlog_62'][:,sample]),
            long_wait_104=summary(trajectory['long_wait_104'][:,sample]),
            peak_backlog=summary(trajectory['backlog_62'].max(axis=1)),
            peak_day=summary(trajectory['backlog_62'].argmax(axis=1)),
            final_long_wait_104=summary(trajectory['long_wait_104'][:,-1]),
            final_backlog_change_vs_baseline=summary(trajectory['backlog_62'][:,-1]-raw[0]['backlog_62'][:,-1]),
            final_long_wait_change_vs_baseline=summary(trajectory['long_wait_104'][:,-1]-raw[0]['long_wait_104'][:,-1]),
            backlog_patient_days_change_vs_baseline=summary((trajectory['backlog_62']-raw[0]['backlog_62']).sum(axis=1))))
        ends = [scenario.strike_start_day + scenario.strike_days if scenario.strike_days else 0,
                scenario.winter_start_day + scenario.winter_days if scenario.winter_days else 0,
                scenario.surge_start_day + scenario.surge_days if scenario.surge_days else 0]
        plans[-1]['recovery'] = recovery_days(trajectory['backlog_62'], raw[0]['backlog_62'], min(max(ends), horizon_days)) if max(ends) else dict(status='not_applicable_no_temporary_shock')
    return dict(org_code=record['org_code'], issue_date=record['issue_date'], last_observed_week=record['observation_end'],
        observed_last_backlog=record['observed_backlog'][-1], fitted_last_backlog=record['fitted_backlog'][-1],
        publication_bridge_days=bridge_days, issue_backlog_nowcast=summary(raw[0]['backlog_62'][:,0]),
        runs=runs, seed=seed, horizon_days=horizon_days, calibration_rmse=record['rmse'],
        acceptable_calibration_fit=record['acceptable_fit'],
        uncertainty='10–90% Monte Carlo process ranges conditional on assumed age mix, conversion and fitted capacities; not calibrated predictive intervals.',
        long_wait_status='>104-day counts and their changes are modelled from unobserved age/split assumptions, not measured trust outcomes.',
        plans=plans, recommendations='No causal or clinical recommendation is inferred from these scenarios.')


def default_scenarios() -> list[Scenario]:
    """A common stress case with diagnostic versus treatment capacity plans."""
    return [Scenario(), Scenario(name='five_day_strike', strike_days=5),
        Scenario(name='strike_plus_diagnosis_10pct', strike_days=5, extra_diagnosis_capacity=.10),
        Scenario(name='strike_plus_treatment_10pct', strike_days=5, extra_treatment_capacity=.10),
        Scenario(name='six_week_winter_dip', winter_days=42),
        Scenario(name='four_week_referral_surge', surge_days=28)]


def check(calibration: dict, examples: dict) -> None:
    """Validate the shipped calibration/experiment contracts without refitting."""
    from pipeline.universe import load_core_trusts
    from config import STATIC_DIR, PROCESSED_DIR
    for name,expected in calibration['input_sha256'].items():
        path=(STATIC_DIR if name.endswith('.csv') else PROCESSED_DIR)/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Simulation calibration input changed: '+name)
    if examples['calibration_sha256']!=hashlib.sha256((OUTPUTS_DIR/'simulation_calibration.json').read_bytes()).hexdigest():
        raise ValueError('Scenario examples use a different calibration')
    if {t['org_code'] for t in calibration['trusts']} != set(load_core_trusts().org_code):
        raise ValueError('Simulation coverage differs from the core cohort')
    for r in calibration['trusts']:
        if r['status'] == 'calibrated':
            y=np.array(r['observed_backlog'],float);pred=np.array(r['fitted_backlog']);valid=np.isfinite(y)
            if not np.isclose(np.sqrt(np.mean((pred[valid]-y[valid])**2)),r['rmse']):
                raise ValueError('Calibration errors do not match the fitted curve')
            if r['maximum_input_published_on'] > r['issue_date']:
                raise ValueError('Unpublished calibration input')
    for trust in examples['trusts']:
        if not 200 <= trust['runs'] <= 500:
            raise ValueError('Unsupported Monte Carlo draw count')
        for plan in trust['plans']:
            if not plan['assumptions']:
                raise ValueError('Missing scenario assumptions')
            for key in ['backlog_62','long_wait_104']:
                q=plan[key]
                if not (np.array(q['lower_80'])>=0).all() or not (np.array(q['lower_80'])<=q['median']).all() or not (np.array(q['median'])<=q['upper_80']).all():
                    raise ValueError('Invalid Monte Carlo ranges')
    print(f'Stage 5 snapshot checks passed: {calibration["calibrated_trusts"]} calibrated trusts, {len(examples["trusts"])} scenario examples.')


def main() -> None:
    """Build bundled examples or run editable parameters for one calibrated trust."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trust', help='One current core code; default RTH, RA7 and RAL')
    parser.add_argument('--runs',type=int,default=256);parser.add_argument('--days',type=int,default=182)
    parser.add_argument('--start-week',type=int,default=4)
    parser.add_argument('--winter-weeks',type=int,default=6);parser.add_argument('--surge-weeks',type=int,default=4)
    parser.add_argument('--strike-days',type=int,default=5);parser.add_argument('--winter-loss',type=float,default=.10)
    parser.add_argument('--referral-increase',type=float,default=.20);parser.add_argument('--extra-capacity',type=float,default=.10)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    calibration=json.loads((OUTPUTS_DIR/'simulation_calibration.json').read_text())
    if args.check:
        check(calibration,json.loads((OUTPUTS_DIR/'simulation_examples.json').read_text()));return
    lookup={r['org_code']:r for r in calibration['trusts']}
    codes=[args.trust] if args.trust else ['RTH','RA7','RAL']
    starts=dict(strike_start_day=args.start_week*7,winter_start_day=args.start_week*7,
                surge_start_day=args.start_week*7,intervention_start_day=args.start_week*7)
    scenarios=[Scenario(),Scenario(name='strike',strike_days=args.strike_days,**starts),
        Scenario(name='strike_plus_diagnosis',strike_days=args.strike_days,extra_diagnosis_capacity=args.extra_capacity,**starts),
        Scenario(name='strike_plus_treatment',strike_days=args.strike_days,extra_treatment_capacity=args.extra_capacity,**starts),
        Scenario(name='winter_dip',winter_days=args.winter_weeks*7,winter_capacity_loss=args.winter_loss,**starts),
        Scenario(name='referral_surge',surge_days=args.surge_weeks*7,referral_increase=args.referral_increase,**starts)]
    results=[]
    for code in codes:
        if code not in lookup:
            raise ValueError('Unknown or retired/non-acute trust code: '+code)
        results.append(compare(lookup[code],scenarios,runs=args.runs,horizon_days=args.days))
        print('Completed 256-run scenario comparison for' if args.runs==256 else f'Completed {args.runs}-run scenario comparison for',code,flush=True)
    report=dict(stage=5,issue_date=calibration['issue_date'],availability_label='approximate: latest revised values',
        historical_vintage_verified=False,calibration_sha256=hashlib.sha256((OUTPUTS_DIR/'simulation_calibration.json').read_bytes()).hexdigest(),trusts=results)
    target='simulation_examples.json' if not args.trust else f'simulation_{args.trust}.json'
    write_json(OUTPUTS_DIR/target,report)
    print('Written',target)


if __name__=='__main__':
    main()
