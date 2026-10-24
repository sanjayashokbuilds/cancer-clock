"""Aggregate provider × commissioner × test records without mixing test totals."""
from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path
import re
from zipfile import ZipFile

import pandas as pd

from config import ROOT_DIR
from pipeline.common import DataError, assert_unique, metadata, normal, numeric, period_from_text, read_csv, require_columns

LOG = logging.getLogger(__name__)
TESTS = {'MRI': 'MRI', 'CT': 'CT', 'NON_OBSTETRIC_ULTRASOUND': 'Non-obstetric ultrasound',
         'COLONOSCOPY': 'Colonoscopy', 'FLEXI_SIGMOIDOSCOPY': 'Flexi sigmoidoscopy',
         'GASTROSCOPY': 'Gastroscopy', 'CYSTOSCOPY': 'Cystoscopy'}


def parse_zip(path: Path, item: dict[str, str], providers: set[str]) -> pd.DataFrame:
    """Retain only CWT-listed providers and the seven specified tests."""
    with ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.csv') and not n.startswith('__MACOSX/')]
        if len(names) != 1:
            raise DataError(f'Expected one DM01 CSV, found {names}')
        frame = read_csv(BytesIO(archive.read(names[0])))
    LOG.info('DM01 %s columns: %s', item['period'], ', '.join(frame.columns))
    require_columns(frame, ['Period', 'Provider Org Code', 'Provider Org Name', 'Commissioner Org Code',
                            'Diagnostic Tests', 'Total WL', 'Total Activity', 'Waiting List Activity',
                            'Planned Activity', 'Unscheduled Activity'], 'DM01')
    periods = {period_from_text(value) for value in frame.Period.unique()}
    if periods != {pd.Timestamp(item['period'])}:
        raise DataError(f'DM01 period mismatch: link {item["period"]}, CSV {periods}')
    for col in ['Provider Org Code', 'Provider Org Name', 'Commissioner Org Code', 'Diagnostic Tests']:
        frame[col] = frame[col].map(normal)
    canonical = frame['Diagnostic Tests'].str.upper().str.replace(r'[\s-]+', '_', regex=True)
    unknown = set(TESTS) - set(canonical)
    if unknown:
        raise DataError(f'DM01 expected tests missing: {unknown}; found {sorted(set(canonical))}')
    frame['test'] = canonical.map(TESTS)
    frame = frame.loc[frame['Provider Org Code'].isin(providers) & frame.test.notna()].copy()
    if frame.empty:
        raise DataError('No DM01 providers match CWT; check for a CDC-only extract or changed identifiers')
    if frame['Commissioner Org Code'].str.upper().isin(['TOTAL', 'ALL', 'ENGLAND']).any():
        raise DataError('DM01 commissioner aggregate rows need explicit handling to avoid double counting')
    assert_unique(frame, ['Provider Org Code', 'Commissioner Org Code', 'test'], 'DM01 source')
    bins = [c for c in frame if re.fullmatch(r'\d{2}\s*<\s*\d{2}\s+Weeks?', c)]
    long_bins = [c for c in bins if int(c[:2]) >= 6] + ['13+ Weeks']
    if len(bins) != 13 or len(long_bins) != 8:
        raise DataError(f'DM01 age-bin schema changed: {bins}, {long_bins}')
    require_columns(frame, ['13+ Weeks'], 'DM01')
    count_cols = bins + ['13+ Weeks', 'Total WL', 'Waiting List Activity', 'Planned Activity', 'Unscheduled Activity', 'Total Activity']
    for col in count_cols:
        frame[col] = numeric(frame[col], col)
    ages = frame[bins + ['13+ Weeks']].sum(axis=1, min_count=14)
    complete = ages.notna() & frame['Total WL'].notna()
    if (ages[complete] - frame.loc[complete, 'Total WL']).abs().gt(1e-6).any():
        raise DataError('DM01 age bins do not reconcile to Total WL')
    frame['waiting_6plus'] = frame[long_bins].sum(axis=1, min_count=8)
    rename = {'Total WL': 'total_waiting_list', 'Waiting List Activity': 'waiting_list_activity',
              'Planned Activity': 'planned_activity', 'Unscheduled Activity': 'unscheduled_activity', 'Total Activity': 'activity'}
    frame.rename(columns=rename, inplace=True)
    measures = list(rename.values()) + ['waiting_6plus']
    grouped = frame.groupby(['Provider Org Code', 'test'], sort=True)
    # A suppressed commissioner value makes the aggregate missing, not understated.
    totals = grouped[measures].sum(min_count=1)
    totals = totals.mask(grouped[measures].count().lt(grouped.size(), axis=0)).reset_index()
    names = frame[['Provider Org Code', 'Provider Org Name']].drop_duplicates()
    assert_unique(names, ['Provider Org Code'], 'DM01 provider names')
    totals = totals.merge(names, on='Provider Org Code', validate='many_to_one')
    totals['pct_waiting_6plus'] = 100 * totals.waiting_6plus.div(totals.total_waiting_list.where(totals.total_waiting_list.gt(0)))
    totals = metadata(totals, item)
    return totals.rename(columns={'Provider Org Code': 'org_code', 'Provider Org Name': 'org_name'})


def parse_all(manifest: pd.DataFrame, providers: set[str]) -> dict[str, pd.DataFrame]:
    """Build the combined monthly diagnostic series."""
    parts = [parse_zip(ROOT_DIR / item['local_path'], item, providers)
             for item in manifest.loc[manifest.dataset.eq('dm01')].to_dict('records')]
    frame = pd.concat(parts, ignore_index=True)
    assert_unique(frame, ['org_code', 'period', 'test'], 'DM01 output')
    return {'dm01': frame}
