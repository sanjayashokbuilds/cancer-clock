"""Run paired rolling-origin baseline checks on the shared NHS trust universe."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import EVALUATION_START, FORECAST_HORIZONS_WEEKS, OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from models.baselines import calibration_errors, interval, mase_scale, predict
from pipeline.common import DataError, assert_unique
from pipeline.universe import load_core_trusts
from pipeline.vintages import available_at

LABEL = 'approximate: latest revised values'


def evaluate(backlog: pd.DataFrame, codes: set[str], origins: pd.DatetimeIndex,
             anchors: tuple[str, ...] = ('observation', 'issue'),
             horizons: tuple[int, ...] = FORECAST_HORIZONS_WEEKS) -> tuple[pd.DataFrame, dict]:
    """Separate feature/calibration availability from held-out outcome lookup.

    Missing observations are never filled. Both baselines use identical cases.
    Latest missing observations, insufficient history and unknown outcomes are
    counted as skips. Dates before October 2023 may train but are never scored.
    """
    assert_unique(backlog, ['org_code', 'week_ending'], 'Backtest backlog')
    if not set(anchors) <= {'observation', 'issue'} or any(h <= 0 for h in horizons):
        raise ValueError('Unknown anchor or non-positive horizon')
    if any(origin.dayofweek != 6 for origin in origins):
        raise ValueError('Issue dates must be Sundays to match weekly target dates')
    selected = backlog.loc[backlog.org_code.isin(codes)].copy()
    records, skipped = [], Counter()
    for code, raw in selected.groupby('org_code', sort=True):
        raw = raw.sort_values('week_ending')
        for issue in origins:
            if issue < pd.Timestamp(EVALUATION_START):
                continue
            known = available_at(raw, issue, allow_approximate=True)
            # Eligibility uses only information available at this origin.
            if known.empty:
                skipped['no_published_history'] += len(anchors)*len(horizons)
                continue
            latest = known.week_ending.max()
            history = known.set_index('week_ending').reindex(pd.date_range(raw.week_ending.min(), latest, freq='7D'))
            values = history.backlog.to_numpy(dtype=float)
            if len(values) < 26 or not np.isfinite(values[-9:]).all():
                skipped['insufficient_history_or_recent_gap'] += len(anchors)*len(horizons)
                continue
            scale = mase_scale(values)
            releases = pd.to_datetime(history.published_on).to_numpy()
            actuals = raw.set_index('week_ending').backlog
            for anchor in anchors:
                for horizon in horizons:
                    target = (latest if anchor == 'observation' else issue) + pd.Timedelta(weeks=horizon)
                    steps = int((target - latest).days // 7)
                    if target < pd.Timestamp(EVALUATION_START):
                        skipped['target_before_evaluation_start'] += 1
                        continue
                    errors = calibration_errors(values, releases, issue, steps)
                    if min(map(len, errors.values())) < 8:
                        skipped[f'{anchor}_{horizon}w_insufficient_calibration'] += 1
                        continue
                    points = predict(values, steps)
                    # Labels below are used for scoring only, never prediction or calibration.
                    actual = actuals.get(target, np.nan)
                    if not np.isfinite(actual):
                        skipped[f'{anchor}_{horizon}w_unknown_target'] += 1
                        continue
                    lead = (target-issue).days / 7
                    for model, point in points.items():
                        lower, upper = interval(point, errors[model])
                        records.append(dict(org_code=code, model=model, anchor=anchor,
                            horizon_weeks=horizon, as_of_date=issue, latest_observation=latest,
                            target_date=target, observation_horizon_weeks=steps,
                            issue_lead_weeks=lead, publication_lag_weeks=(issue-latest).days/7,
                            target_is_future=lead > 0, last_value=float(values[-1]),
                            prediction=point, lower_80=lower, upper_80=upper,
                            calibration_n=len(errors[model]), training_n=int(np.isfinite(values).sum()),
                            training_scale=scale, actual=float(actual),
                            absolute_error=abs(float(actual)-point),
                            scaled_error=abs(float(actual)-point)/scale if scale is not None else None,
                            direction_correct=bool(np.sign(point-values[-1]) == np.sign(actual-values[-1])),
                            covered_80=bool(lower <= actual <= upper), availability_label=LABEL,
                            historical_vintage_verified=False))
    if not records:
        raise DataError('No evaluable forecasts; check history, dates and core trust coverage')
    return pd.DataFrame(records), dict(sorted(skipped.items()))


def score(rows: pd.DataFrame) -> dict:
    """Report pair-weighted metrics and sample counts, retaining zero-scale cases."""
    scaled = rows.scaled_error.dropna()
    direction = rows.loc[rows.actual.ne(rows.last_value)]
    return dict(n=len(rows), trusts=int(rows.org_code.nunique()), origins=int(rows.as_of_date.nunique()),
        mae=float(rows.absolute_error.mean()), mase=float(scaled.mean()) if len(scaled) else None,
        mase_n=len(scaled), undefined_scale_n=int(rows.training_scale.isna().sum()),
        direction_accuracy=float(rows.direction_correct.mean()),
        grow_shrink_accuracy=float(direction.direction_correct.mean()) if len(direction) else None,
        grow_shrink_n=len(direction), unchanged_actual_n=int(rows.actual.eq(rows.last_value).sum()),
        coverage_80=float(rows.covered_80.mean()), mean_interval_width=float((rows.upper_80-rows.lower_80).mean()),
        issue_lead_weeks_min=float(rows.issue_lead_weeks.min()),
        issue_lead_weeks_max=float(rows.issue_lead_weeks.max()),
        retrospective_or_nowcast_n=int((~rows.target_is_future).sum()))


def summarize(rows: pd.DataFrame) -> list[dict]:
    """Show both horizon conventions and distinguish future-only scores."""
    result = []
    for (anchor, horizon, model), group in rows.groupby(['anchor', 'horizon_weeks', 'model'], sort=True):
        for scope in ('all_targets', 'future_only'):
            subset = group if scope == 'all_targets' else group.loc[group.target_is_future]
            if len(subset):
                result.append(dict(anchor=anchor, horizon_weeks=int(horizon), model=model, scope=scope, **score(subset)))
    return result


def run(start: str = '2024-01-07', end: str | None = None,
        output_dir: Path = OUTPUTS_DIR) -> dict:
    """Reproduce results from bundled data offline and save row-level audit evidence."""
    from pipeline.mergers import load_harmonized, GEOGRAPHY
    backlog = load_harmonized('backlog_trust')
    core = load_core_trusts()
    start_date, end_date = pd.Timestamp(start), pd.Timestamp(end or backlog.week_ending.max())
    if start_date.dayofweek != 6 or start_date < pd.Timestamp(EVALUATION_START) or end_date < start_date:
        raise DataError('Choose a Sunday start on/after 2023-10-01 and an end on/after start')
    origins = pd.date_range(start_date, end_date, freq='28D')
    rows, skipped = evaluate(backlog, set(core.org_code), origins)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = output_dir / 'backtest_baseline_predictions.parquet'
    rows.to_parquet(audit, index=False)
    report = dict(stage=2, availability_label=LABEL, historical_vintage_verified=False,
        core_trusts=len(core), evaluated_trusts=int(rows.org_code.nunique()),
        origins_requested=len(origins), first_issue=str(origins.min().date()), last_issue=str(origins.max().date()),
        evaluation_start=str(EVALUATION_START), first_history=str(backlog.week_ending.min().date()),
        last_observation=str(backlog.week_ending.max().date()), rows=len(rows), skipped=skipped,
        definitions={
            'release_rule': 'Observation month M -> 14th of M+2 for every dataset; latest revisions remain unverified.',
            'observation_anchor': 'target=latest published observation + h weeks; lead=target-issue (can be negative).',
            'issue_anchor': 'target=issue+h weeks; extrapolation spans publication lag plus h.',
            'drift': 'last + h*(last-value eight weeks earlier)/8, clipped at zero; h measured from last observation.',
            'mase': 'MAE scaled per case by mean absolute consecutive weekly change in available training history; zero scales excluded from MASE only.',
            'direction': 'Three-way sign: shrink/unchanged/grow. Persistence predicts unchanged. grow_shrink_accuracy excludes unchanged actual outcomes; persistence abstentions count as incorrect.',
            'interval': '80% symmetric empirical absolute-error band, last 52 eligible within-trust residuals, minimum 8; calibration targets must be published by issue. Coverage is measured, not guaranteed.',
            'cohort': GEOGRAPHY,
            'aggregation': 'Paired forecast-case mean; both baselines evaluated on identical trust/origin/target cases.',
        }, limitations=['Approximate release dates and latest revised values are not a strict historical-vintage backtest.',
            'Overlapping horizons and residuals are dependent; no significance or causal claim.',
            'Confirmed mergers use retrospective current footprints; retired codes are excluded. Missing component counts remain unknown.',
            'Only overdue >62-day backlogs are forecast, not the entire waiting list or personal waits.'],
        metrics=summarize(rows), input_sha256={
            'backlog_trust.parquet': hashlib.sha256((PROCESSED_DIR/'backlog_trust.parquet').read_bytes()).hexdigest(),
            'core_trusts.csv': hashlib.sha256((STATIC_DIR/'core_trusts.csv').read_bytes()).hexdigest(),
            'trust_mergers.csv': hashlib.sha256((STATIC_DIR/'trust_mergers.csv').read_bytes()).hexdigest(),
            'provider_scope.csv': hashlib.sha256((STATIC_DIR/'provider_scope.csv').read_bytes()).hexdigest()})
    (output_dir/'backtest_baselines.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print('Stage 2 baseline backtest | '+LABEL)
    print('Anchor       Horizon Model       N     MAE    MASE  Direction  Coverage80  Issue lead')
    for metric in report['metrics']:
        if metric['scope'] != 'all_targets':
            continue
        m=metric
        scaled=f'{m["mase"]:.3f}' if m['mase'] is not None else 'n/a'
        print(f'{m["anchor"]:12} {m["horizon_weeks"]:>3}w   {m["model"]:6} {m["n"]:6} {m["mae"]:7.2f} {scaled:>7} {m["direction_accuracy"]:9.1%} {m["coverage_80"]:11.1%} {m["issue_lead_weeks_min"]:4.0f}..{m["issue_lead_weeks_max"]:.0f}w')
    print(f'{len(core)} core trusts; {rows.org_code.nunique()} evaluated; {len(origins)} requested origins.')
    print('Stage 2 backtest complete. No ML model has been trained.')
    return report


def main() -> None:
    """CLI: python -m models.backtest (no keys or network needed)."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2024-01-07')
    parser.add_argument('--end')
    args=parser.parse_args()
    run(args.start,args.end)


if __name__ == '__main__':
    main()
