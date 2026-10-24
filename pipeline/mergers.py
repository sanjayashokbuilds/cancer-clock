"""Evidence-gated merger detection and current-footprint count harmonisation."""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from config import OUTPUTS_DIR, PROCESSED_DIR, STATIC_DIR
from pipeline.common import DataError, assert_unique

MERGERS_PATH = STATIC_DIR / 'trust_mergers.csv'
SCOPE_PATH = STATIC_DIR / 'provider_scope.csv'
GEOGRAPHY = 'Retrospectively harmonised current organisation footprint; merger mapping uses later information'


def mergers() -> pd.DataFrame:
    """Only the reviewed, sourced registry can change a provider's identity."""
    frame = pd.read_csv(MERGERS_PATH, parse_dates=['effective_week', 'effective_month', 'legal_date'])
    assert_unique(frame, ['predecessor'], 'Merger registry')
    if set(frame.predecessor) & set(frame.successor):
        raise DataError('Chained mergers require an explicitly reviewed transitive mapping')
    if frame.evidence.isna().any():
        raise DataError('Every applied merger needs evidence')
    return frame


def mask_retired_backlogs(backlog: pd.DataFrame, registry: pd.DataFrame | None = None) -> pd.DataFrame:
    """Retired-provider zeros are missing, never evidence that a queue was cleared."""
    result = backlog.copy()
    for row in (mergers() if registry is None else registry).itertuples():
        retired = result.org_code.eq(row.predecessor) & result.week_ending.ge(row.effective_week)
        result.loc[retired, 'backlog'] = np.nan
    return result


def harmonize(frame: pd.DataFrame, dataset: str, registry: pd.DataFrame | None = None) -> pd.DataFrame:
    """Sum pre-merger counts once; retain successor-only observations after the boundary.

    Entire missing provider-months/weeks remain unknown. A CWT cancer/modality
    not reported within an otherwise observed provider metric contributes zero;
    an explicit suppressed numerator under an observed total remains unknown.
    """
    registry = mergers() if registry is None else registry
    if dataset in {'backlog_national', 'cwt_national'}:
        return frame.copy()
    result = mask_retired_backlogs(frame, registry) if dataset == 'backlog_trust' else frame.copy()
    time = 'week_ending' if dataset == 'backlog_trust' else 'period'
    dims = ['cancer_type'] if dataset == 'cwt_trust_month' else ['test'] if dataset.startswith('dm01') else []
    keys = [time, *dims]
    if dataset == 'backlog_trust':
        count_cols = ['backlog']
    elif dataset == 'cwt_first_seen':
        count_cols = ['usc_first_seen']
    elif dataset == 'cwt_trust_month':
        count_cols = [c for c in frame.select_dtypes(include='number') if '_performance' not in c]
    elif dataset.startswith('dm01'):
        count_cols = [c for c in ['total_waiting_list', 'waiting_6plus', 'activity', 'waiting_list_activity', 'planned_activity', 'unscheduled_activity'] if c in frame]
    else:
        raise DataError(f'Unsupported harmonisation dataset: {dataset}')
    for merger in registry.itertuples():
        cutoff = merger.effective_week if time == 'week_ending' else merger.effective_month
        old = result.loc[result.org_code.eq(merger.predecessor) & result[time].lt(cutoff)]
        successor = result.loc[result.org_code.eq(merger.successor) & result[time].lt(cutoff)]
        if old.empty and successor.empty:
            continue
        # Monthly RVY data begins after that merger; no pre-boundary rows to stitch.
        if old.empty and (time != 'week_ending' and frame[time].min() >= cutoff):
            continue
        a = successor.set_index(keys).sort_index()
        b = old.set_index(keys).sort_index()
        index = a.index.union(b.index).sort_values()
        a = a.reindex(index); b = b.reindex(index)
        joined = a.combine_first(b)
        for col in count_cols:
            left, right = a[col].copy(), b[col].copy()
            if dataset == 'cwt_trust_month':
                roots = sorted([c[:-6] for c in count_cols if c.endswith('_total')], key=len, reverse=True)
                root = next((r for r in roots if col.startswith(r + '_')), None)
                if root:
                    total_col = root + '_total'
                    for part, original, values in [(a, successor, left), (b, old, right)]:
                        available = original.loc[original.cancer_type.eq('ALL CANCERS')].set_index('period')[total_col].notna()
                        present = pd.Series(index.get_level_values('period').map(available).fillna(False), index=index)
                        values.loc[part[total_col].isna() & present] = 0.
            elif dataset.startswith('dm01'):
                for part, original, values in [(a, successor, left), (b, old, right)]:
                    present = index.get_level_values('period').isin(original.period.unique())
                    # An absent test in a reported organisation-month is structural absence;
                    # an existing test with a suppressed cell is not.
                    absent_row = part.org_code.isna()
                    values.loc[absent_row & present] = 0.
            joined[col] = left + right  # strict NaN propagation, including missing whole providers
        joined['org_code'] = merger.successor
        current_name = frame.loc[frame.org_code.eq(merger.successor), 'org_name'].iloc[-1]
        joined['org_name'] = current_name
        joined['component_codes'] = merger.successor + '+' + merger.predecessor
        joined['published_on'] = pd.concat([a.published_on, b.published_on], axis=1).max(axis=1)
        for col in ['source_url', 'source_sha256']:
            if col in joined:
                joined[col] = [ '|'.join(sorted(set(str(v) for v in values if pd.notna(v))))
                                for values in zip(a[col], b[col]) ]
        if dataset == 'cwt_trust_month':
            for col in [c for c in joined if c.endswith('_performance')]:
                prefix = col[:-12]
                joined[col] = joined[prefix + '_within'] / joined[prefix + '_total'].where(joined[prefix + '_total'].gt(0))
        if dataset.startswith('dm01'):
            joined['pct_waiting_6plus'] = 100 * joined.waiting_6plus / joined.total_waiting_list.where(joined.total_waiting_list.gt(0))
        keep = ~((result.org_code.eq(merger.successor) & result[time].lt(cutoff)) | result.org_code.eq(merger.predecessor))
        result = pd.concat([result.loc[keep], joined.reset_index()], ignore_index=True)
    result = result.loc[~result.org_code.isin(registry.predecessor)].copy()
    result['geography_label'] = GEOGRAPHY
    result['component_codes'] = result.get('component_codes', pd.Series(index=result.index, dtype=str)).fillna(result.org_code)
    assert_unique(result, ['org_code', *keys], 'Harmonised ' + dataset)
    return result.sort_values(['org_code', *keys]).reset_index(drop=True)


def load_harmonized(name: str) -> pd.DataFrame:
    """Read immutable source counts and apply the reviewed mapping in memory."""
    raw = pd.read_parquet(PROCESSED_DIR / f'{name}.parquet')
    return harmonize(raw, name) if name not in {'backlog_national', 'cwt_national'} else raw


def detect_candidates(backlog: pd.DataFrame, cwt: pd.DataFrame) -> list[dict]:
    """Flag an ending positive series and simultaneous compatible level jumps.

    Suggestions are not mergers. Monthly activity continuing after the candidate
    boundary and tiny predecessor counts explicitly weaken the evidence.
    """
    wide = backlog.pivot(index='week_ending', columns='org_code', values='backlog').sort_index()
    locations = pd.read_csv(STATIC_DIR / 'trust_locations.csv').set_index('org_code')
    results = []
    for code in wide:
        positive = wide[code].loc[wide[code].gt(0)]
        if positive.empty:
            continue
        last = positive.index.max(); after = wide.loc[wide.index > last, code]
        if len(after) < 4 or after.gt(0).any():
            continue
        week = after.index[0]
        prev = float(positive.iloc[-1])
        last_month = cwt.loc[cwt.org_code.eq(code) & cwt.d31_all_total.gt(0), 'period'].max()
        continuing = pd.notna(last_month) and last_month >= week.to_period('M').to_timestamp()
        candidates = []
        for other in wide.columns.difference([code]):
            before, following = wide.at[last, other], wide.at[week, other]
            if not np.isfinite(before) or not np.isfinite(following):
                continue
            jump = following - before
            ratio = jump / prev
            if jump > 0 and .25 <= ratio <= 2.0:
                distance = None
                if code in locations.index and other in locations.index:
                    xy = locations.loc[[code, other], ['lat', 'lon']].to_numpy(dtype=float)
                    if np.isfinite(xy).all():
                        distance = float(np.hypot(111 * (xy[0,0]-xy[1,0]), 111 * np.cos(np.deg2rad(xy[:,0].mean())) * (xy[0,1]-xy[1,1])))
                candidates.append(dict(successor=other, jump=float(jump), predecessor_last=prev,
                    jump_to_predecessor_ratio=float(ratio), distance_km=distance,
                    discrepancy=float(abs(np.log(ratio))) + (distance / 100 if distance is not None else 0.)))
        candidates = sorted(candidates, key=lambda r: r['discrepancy'])[:5]
        results.append(dict(predecessor=code, candidate_week=str(week.date()),
            last_positive_week=str(last.date()), monthly_activity_continues=bool(continuing),
            signal='needs_review' if prev >= 5 and not continuing else 'weak_or_contradicted',
            candidates=candidates, automatic_application=False))
    return results


def write_scope(backlog: pd.DataFrame, cwt: pd.DataFrame) -> pd.DataFrame:
    """Explicit reviewed service scope; retain acute specialist cancer providers."""
    registry = mergers().set_index('predecessor')
    latest = cwt.period.max()
    active = cwt.loc[cwt.period.ge(latest - pd.DateOffset(months=11)) & cwt.cancer_type.eq('ALL CANCERS')].groupby('org_code').d31_all_total.sum(min_count=1)
    rows = []
    for code, raw in backlog.groupby('org_code'):
        name = raw.org_name.iloc[-1]
        nonacute = code == 'RY2' or any(word in name.upper() for word in ['MENTAL HEALTH', 'COMMUNITY HEALTHCARE'])
        successor = registry.loc[code, 'successor'] if code in registry.index else ''
        in_window = raw.loc[raw.week_ending.ge('2023-10-01'), 'backlog'].notna().any()
        cancer_active = active.get(code, 0) > 0
        include = bool(not successor and not nonacute and in_window and cancer_active)
        reason = f'merged into {successor}' if successor else 'non-acute provider' if nonacute else 'no evaluation-era backlog' if not in_window else 'no recent reported cancer treatment' if not cancer_active else 'live acute/specialist trust with cancer treatment and backlog observations'
        evidence = 'Reviewed hospital service scope and positive 31D completed-treatment count in latest 12 published months'
        if code == 'RET':
            evidence += '; active neuro-oncology; no RET-to-RDE merger: https://www.thewaltoncentre.nhs.uk/neurooncology-department'
        if code == 'RP6':
            evidence += '; active ocular oncology; zero backlog is retained: https://www.moorfields.nhs.uk/for-health-professionals/ocular-oncology'
        rows.append(dict(org_code=code, name=name, service_scope='community' if nonacute else 'acute_or_specialist',
            included=include, successor=successor, note=reason, evidence=evidence))
    result = pd.DataFrame(rows)
    result.to_csv(SCOPE_PATH, index=False)
    return result


def run() -> None:
    """Audit candidates, publish the core scope and rebuild its map eligibility."""
    from pipeline.universe import write_core_trusts
    raw = pd.read_parquet(PROCESSED_DIR / 'backlog_trust.parquet')
    cwt = pd.read_parquet(PROCESSED_DIR / 'cwt_trust_month.parquet')
    scope = write_scope(raw, cwt)
    harmonised = harmonize(raw, 'backlog_trust')
    core = write_core_trusts(harmonised)
    report = dict(geography_label=GEOGRAPHY,
        limitation='Count availability is issue-filtered, but the fixed present-day cohort and merger mapping are retrospective, not an as-was organisational backtest.',
        detector=detect_candidates(raw, cwt), applied=mergers().astype(str).to_dict('records'),
        excluded=scope.loc[~scope.included].to_dict('records'), core_trusts=len(core),
        retired_post_boundary_zeros_masked=int((raw.backlog.eq(0) & mask_retired_backlogs(raw).backlog.isna()).sum()))
    (OUTPUTS_DIR / 'merger_audit.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    quality_path = OUTPUTS_DIR / 'data_quality.json'
    if quality_path.exists():
        quality = json.loads(quality_path.read_text())
        quality.update(core_trusts=len(core),core_locations_resolved=int(core.map_eligible.sum()),
            modelling_geography=GEOGRAPHY,source_tables='Original provider codes preserved; downstream counts harmonised in memory via trust_mergers.csv')
        quality_path.write_text(json.dumps(quality,indent=2,allow_nan=False)+'\n')
    print(f'Merger audit complete: {len(core)} live acute/specialist core trusts; {len(mergers())} verified mappings.')


if __name__ == '__main__':
    run()
