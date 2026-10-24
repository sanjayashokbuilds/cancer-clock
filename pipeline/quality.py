"""Report actual coverage, missing observations, and identifier changes."""
from __future__ import annotations

import pandas as pd


def coverage(frame: pd.DataFrame, time: str, code: str | None) -> dict:
    """Summarise a dataset without assuming missing observations are zero."""
    result = {'rows': len(frame), 'first_period': str(frame[time].min().date()),
              'last_period': str(frame[time].max().date()), 'periods': int(frame[time].nunique()),
              'missing_numeric_cells': {c: int(frame[c].isna().sum()) for c in frame.select_dtypes('number')}}
    if code:
        counts = frame.groupby(time)[code].nunique()
        result['providers'] = int(frame[code].nunique())
        result['providers_by_period'] = {str(k.date()): int(v) for k, v in counts.items()}
    return result


def identifier_changes(frame: pd.DataFrame, code: str, time: str) -> list[dict]:
    """List code appearance/disappearance; these are not proven mergers."""
    result = []
    previous = None
    for period, group in frame.groupby(time, sort=True):
        codes = set(group[code])
        if previous is not None and codes != previous:
            result.append({'period': str(period.date()), 'appeared': sorted(codes - previous),
                           'disappeared': sorted(previous - codes)})
        previous = codes
    return result


def build_report(data: dict[str, pd.DataFrame], manifest: pd.DataFrame) -> dict:
    """Produce JSON-safe audit information and clearly stated unresolved limits."""
    cwt, dm, backlog = data['cwt'], data['dm01'], data['backlog_trust']
    report = {'status': 'completed', 'sources': len(manifest), 'datasets': {},
              'availability': 'approximate dates and latest revised values; not verified historical vintages'}
    for name, frame in data.items():
        time = 'week_ending' if name.startswith('backlog') else 'period'
        code = 'org_code' if 'org_code' in frame else 'Org_Code' if 'Org_Code' in frame and name != 'cwt_national' else None
        report['datasets'][name] = coverage(frame, time, code)
    report['missing_months'] = {}
    for name, frame in [('cwt', cwt), ('dm01', dm)]:
        expected = pd.date_range(frame.period.min(), frame.period.max(), freq='MS')
        report['missing_months'][name] = [str(d.date()) for d in expected.difference(frame.period.unique())]
    missing = []
    for code, group in backlog.groupby('org_code'):
        valid = group.loc[group.backlog.notna(), 'week_ending']
        expected = pd.date_range(group.week_ending.min(), group.week_ending.max(), freq='7D')
        absent = expected.difference(valid)
        if len(absent):
            missing.append({'org_code': code, 'missing_weeks': [str(d.date()) for d in absent]})
    report['backlog_missing_weeks'] = missing
    report['code_changes'] = {'cwt': identifier_changes(cwt, 'Org_Code', 'period'),
                              'dm01': identifier_changes(dm, 'org_code', 'period')}
    c, d, b = set(cwt.Org_Code), set(dm.org_code), set(backlog.org_code)
    report['provider_overlap'] = {'in_all_three': len(c & d & b), 'cwt_without_backlog': sorted(c - b),
                                   'backlog_without_cwt': sorted(b - c), 'cwt_without_dm01': sorted(c - d)}
    provider_sums = backlog.groupby('week_ending').backlog.sum(min_count=1)
    national = data['backlog_national'].set_index('week_ending').total
    difference = provider_sums - national
    report['backlog_provider_sum_minus_national'] = {
        'max_absolute_difference': float(difference.abs().max()),
        'latest_difference': float(difference.dropna().iloc[-1]),
        'note': 'Provider/national scope may differ; no forced reconciliation.'}
    report['warnings'] = [
        'Release days are assumed, and downloaded historical observations may be revised.',
        'Latest backlog workbook has no archived trust-level diagnosis/treatment split.',
        'USC first-seen activity is a completed-attendance measure, not referrals received.',
        'DM01 includes non-cancer diagnostic demand.',
        'Source cancer labels differ between suspected and confirmed cancers; no invented mapping.',
        'CWT provider lists include independent providers; NHS trusts are not identified solely by code length.',
        'Locations use headquarters or representative hospital postcodes; use core_trusts.csv for maps and modelling.',
        'Appearing/disappearing codes are not automatically treated as mergers.',
    ]
    return report
