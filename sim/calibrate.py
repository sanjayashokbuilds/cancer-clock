"""Fit two effective daily service budgets to recent published merged backlog counts."""
from __future__ import annotations

import argparse
import hashlib
import json
import time

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from analysis.bottleneck import build as build_bottlenecks, load_inputs
from config import OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from models.features import load_sources
from models.forecast import write_json
from pipeline.mergers import GEOGRAPHY
from pipeline.universe import load_core_trusts
from pipeline.vintages import available_at
from sim.simulator import initial_state, simulate

WINDOW_WEEKS = 13
MIN_OBSERVATIONS = 10
PRIOR_STRENGTH = .15
CAPACITY_RATIO_BOUNDS = (.4, 1.8)
FIT_THRESHOLD = .30


def prior_from_bottleneck(bottleneck: dict) -> dict:
    """Weak directional prior; never interpret aggregate labels as measured capacities."""
    label = bottleneck['label']
    corroborated = bottleneck.get('corroborated_cancer_types', [])
    share = {'diagnosis-limited': .70, 'treatment-limited': .30, 'mixed': .50, 'no clear bottleneck': .50}[label]
    if corroborated and label in {'diagnosis-limited', 'mixed'}:
        share += .05
    ratios = {'diagnosis-limited': [.98, 1.02], 'treatment-limited': [1.02, .98],
              'mixed': [1., 1.], 'no clear bottleneck': [1., 1.]}[label]
    if bottleneck.get('evidence_status') != 'screened':
        share, ratios = .5, [1., 1.]
    return dict(label=label, diagnosis_share=share, capacity_ratio_centres=ratios,
        penalty_strength=PRIOR_STRENGTH, corroborated_cancer_types=corroborated,
        source='assumed weak prior informed by cancer-specific FDS / 31D label and corroborated cancer types',
        caveat='Neither the split nor either capacity is identified by total backlog alone.')


def prepare(sources: dict[str, pd.DataFrame], code: str, issue: pd.Timestamp) -> dict:
    """Read only published values; require current history and usable flow proxies."""
    backlog = available_at(sources['backlog_trust'], issue, allow_approximate=True)
    end = backlog.week_ending.max()
    raw = backlog.loc[backlog.org_code.eq(code)].set_index('week_ending')
    weeks = pd.date_range(end - pd.Timedelta(weeks=WINDOW_WEEKS - 1), end, freq='7D')
    history = raw.reindex(weeks)
    observed = history.backlog.to_numpy(dtype=float)
    if len(raw) == 0 or not np.isfinite(observed[[0, -1]]).all() or np.isfinite(observed).sum() < MIN_OBSERVATIONS:
        return dict(status='unavailable', reason='Insufficient current published backlog history')
    first = available_at(sources['cwt_first_seen'], issue, allow_approximate=True)
    first = first.loc[first.org_code.eq(code)].set_index('period').sort_index()
    cwt = available_at(sources['cwt_trust_month'], issue, allow_approximate=True)
    cwt = cwt.loc[cwt.org_code.eq(code) & cwt.cancer_type.eq('ALL CANCERS')].set_index('period')
    last_month = min(first.index.max(), cwt.index.max()) if len(first) and len(cwt) else pd.NaT
    if pd.isna(last_month):
        return dict(status='unavailable', reason='Missing first-attendance or cancer treatment flow proxy')
    months = pd.date_range(last_month - pd.DateOffset(months=2), last_month, freq='MS')
    flow = first.reindex(months).usc_first_seen
    treated = cwt.reindex(months).d62_usc_total
    valid = flow.gt(0) & treated.notna()
    if valid.sum() < 2:
        return dict(status='unavailable', reason='Fewer than two comparable months for the conversion proxy')
    conversion = float(treated[valid].sum() / flow[valid].sum())
    rate = float(flow[valid].sum() / np.sum(months[valid].days_in_month))
    if not 0 <= conversion <= 1 or rate <= 0:
        return dict(status='unavailable', reason='Completed-pathway conversion proxy outside [0,1] or nonpositive arrival proxy')
    days = pd.date_range(weeks[0] + pd.Timedelta(days=1), weeks[-1], freq='D')
    calendar_months = days.to_period('M').to_timestamp()
    rates = first.usc_first_seen / first.index.days_in_month
    arrivals = np.array(calendar_months.map(rates), dtype=float)
    if not np.isfinite(arrivals).all():
        return dict(status='unavailable', reason='Missing monthly arrival proxy during calibration window')
    return dict(status='ready', org_code=code, issue_date=issue, observation_end=weeks[-1],
        weeks=weeks, observed=observed, arrivals=arrivals, arrivals_per_day=rate,
        conversion_proxy=conversion, flow_months=months[valid],
        maximum_input_published_on=max(history.published_on.max(), first.loc[first.index.isin(calendar_months.union(months)), 'published_on'].max(), cwt.loc[cwt.index.isin(months), 'published_on'].max()))


def fit(prepared: dict, bottleneck: dict) -> dict:
    """Bounded least squares with a weak prior; fit error is in-sample, not validation."""
    if prepared['status'] != 'ready':
        return prepared
    prior = prior_from_bottleneck(bottleneck)
    y = prepared['observed']; valid = np.isfinite(y)
    rate, conversion = prepared['arrivals_per_day'], prepared['conversion_proxy']
    initial = initial_state(rate, conversion, float(y[0]), prior['diagnosis_share'])
    scale = max(float(y[valid].mean()), 10.)
    def evaluate(ratios: np.ndarray) -> tuple[dict, object]:
        return simulate(initial, prepared['arrivals'], rate * ratios[0], rate * conversion * ratios[1], conversion)
    def residual(ratios: np.ndarray) -> np.ndarray:
        trajectory, _ = evaluate(ratios)
        return np.r_[(trajectory['backlog_62'][valid] - y[valid]) / scale,
                     PRIOR_STRENGTH * (ratios - np.array(prior['capacity_ratio_centres']))]
    optim = least_squares(residual, prior['capacity_ratio_centres'], bounds=CAPACITY_RATIO_BOUNDS,
                          max_nfev=35, diff_step=1e-3, ftol=1e-5, xtol=1e-5, gtol=1e-5)
    trajectory, state = evaluate(optim.x)
    errors = trajectory['backlog_62'][valid] - y[valid]
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    nrmse = rmse / scale
    return dict(status='calibrated', org_code=prepared['org_code'], issue_date=prepared['issue_date'],
        observation_end=prepared['observation_end'], maximum_input_published_on=prepared['maximum_input_published_on'],
        calibration_weeks=list(prepared['weeks']), observed_backlog=y.tolist(),
        fitted_backlog=trajectory['backlog_62'].tolist(), observations=int(valid.sum()),
        arrivals_per_day=rate, conversion_proxy=conversion, flow_months=list(prepared['flow_months']),
        diagnosis_capacity_per_day=float(rate * optim.x[0]),
        treatment_capacity_per_day=float(rate * conversion * optim.x[1]),
        capacity_ratios=optim.x.tolist(), prior=prior, rmse=rmse, mae=float(abs(errors).mean()),
        normalised_rmse=nrmse, acceptable_fit=nrmse <= FIT_THRESHOLD,
        fit_threshold='In-sample RMSE / max(mean observed backlog, 10) <= 0.30; heuristic, not a clinical standard',
        optimizer_success=bool(optim.success), optimizer_evaluations=int(optim.nfev),
        at_capacity_bound=bool(np.any(np.isclose(optim.x, CAPACITY_RATIO_BOUNDS[0], atol=.002)) or np.any(np.isclose(optim.x, CAPACITY_RATIO_BOUNDS[1], atol=.002))),
        prior_direction_conflict=bool((prior['label']=='diagnosis-limited' and optim.x[0]>optim.x[1]) or (prior['label']=='treatment-limited' and optim.x[1]>optim.x[0])),
        fitted_end_diagnosis_age_days=state.diagnosis.tolist(), fitted_end_treatment_age_days=state.treatment.tolist(),
        interpretation='Effective service budgets fitted to total backlog; two capacities and age mix are not uniquely identified.')


def assumption_object(record: dict) -> dict:
    """Every scenario receives values, units, source class and limitations."""
    def item(value: object, unit: str, source: str, note: str) -> dict:
        return dict(value=value, unit=unit, source=source, note=note)
    return dict(
        arrival_rate=item(record['arrivals_per_day'], 'patients/day', 'estimated from data', 'Completed first attendances proxy incoming referrals; these are not observed arrivals.'),
        conversion=item(record['conversion_proxy'], 'fraction', 'estimated from data', '62-day USC completed treatments / completed first attendances; unmatched cohorts, not a measured patient conversion probability.'),
        diagnosis_capacity=item(record['diagnosis_capacity_per_day'], 'patients/day', 'estimated from data', 'Regularised in-sample effective service budget, not measured staffing or spare capacity.'),
        treatment_capacity=item(record['treatment_capacity_per_day'], 'patients/day', 'estimated from data', 'Same identification limitation as diagnosis capacity.'),
        queue_split=item(record['prior']['diagnosis_share'], 'initial overdue diagnosis fraction', 'assumed', record['prior']['source']),
        corroborated_cancer_types=item(record['prior']['corroborated_cancer_types'], 'pathways', 'estimated from data', 'Used only to inform a weak split prior; not causal proof.'),
        initial_age_mix=item('Exponential age shapes matched to initial >62-day total and assumed split', 'daily bins', 'assumed', 'Current age distribution and >104-day count are not observed; final bucket is 365+ days.'),
        diagnosis_min_days=item(14, 'days', 'assumed', 'Processing eligibility delay; treatment starts no earlier than the day after diagnosis. Referral age is never reset.'),
        service_order=item('Proportional among eligible daily-age cohorts', 'fluid patient mass', 'assumed', 'Simplified heterogeneous completion order; fractional masses, not individual patient tracking.'),
        capacity_calendar=item('Uniform daily baseline, including weekends', 'calendar', 'assumed', 'Real rota and service-specific calendars are unavailable.'),
        capacity_variation=item(.05, 'daily lognormal sigma', 'assumed', 'Monte Carlo service variation; not fitted from staffing data.'),
        strike_factor=item(.952, 'capacity multiplier', 'assumed', 'Editable scenario assumption from the original brief; not a verified trust-level cancer effect.'),
        publication_bridge=item('Simulate from last observation to issue using the latest published flow proxy', 'days', 'assumed', 'The issue-date queue is an unobserved nowcast, not the latest observed backlog.'),
        interpretation=item('Planning sensitivity only', 'scope', 'assumed', 'Ranges reflect chosen process noise, not calibrated predictive intervals; no personal waits or lives-saved claims.'))


def run(issue: str | None = None) -> dict:
    """Calibrate all live core trusts and publish failures alongside fit distributions."""
    started = time.monotonic(); sources = load_sources(); core = load_core_trusts()
    release = sources['backlog_trust'].published_on.max()
    as_of = pd.Timestamp(issue) if issue else release + pd.Timedelta(days=(6 - release.dayofweek) % 7)
    bottlenecks = build_bottlenecks(load_inputs(), core, as_of)
    lookup = {r['org_code']: r for r in bottlenecks['trusts']}
    records = []
    for index, trust in enumerate(core.itertuples(), 1):
        record = fit(prepare(sources, trust.org_code, as_of), lookup[trust.org_code])
        record.update(org_code=trust.org_code, name=trust.name)
        records.append(record)
        if index % 10 == 0:
            print(f'Calibrated {index}/{len(core)} trusts ({time.monotonic() - started:.0f}s)', flush=True)
    fitted = [r for r in records if r['status'] == 'calibrated']
    stats = {}
    for metric in ['mae', 'rmse', 'normalised_rmse']:
        stats[metric] = dict(zip(['p10','median','p90','maximum'], np.quantile([r[metric] for r in fitted], [.1,.5,.9,1]).tolist()))
    inputs = [PROCESSED_DIR / f'{n}.parquet' for n in [*sources,'cwt_national','dm01_bottleneck_reference']] + [STATIC_DIR / f'{n}.csv' for n in ['core_trusts','trust_mergers','provider_scope']]
    report = dict(stage=5, issue_date=as_of, geography_label=GEOGRAPHY, availability_label='approximate: latest revised values',
        historical_vintage_verified=False, core_trusts=len(core), calibrated_trusts=len(fitted),
        unavailable_trusts=len(core)-len(fitted), acceptable_fit_trusts=sum(r['acceptable_fit'] for r in fitted),
        prior_direction_conflicts=sum(r['prior_direction_conflict'] for r in fitted),
        fit_statistics=stats, identifiability='Only total >62-day backlog is fitted. Age mix, split, conversion proxy and two capacities are not jointly identified.',
        validation='In-sample calibration only; Monte Carlo and >104-day outputs are assumption-led sensitivity results.',
        calibration_window_weeks=WINDOW_WEEKS, capacity_ratio_bounds=CAPACITY_RATIO_BOUNDS,
        input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}, trusts=records)
    write_json(OUTPUTS_DIR / 'simulation_calibration.json', report)
    print(f'Stage 5 calibration: {len(fitted)}/{len(core)} fitted; {report["acceptable_fit_trusts"]} meet the declared in-sample fit threshold.')
    print('Fit statistics:', stats)
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--as-of')
    run(parser.parse_args().as_of)
