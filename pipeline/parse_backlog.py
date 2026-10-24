"""Parse weekly overdue cancer waiting lists and national DTT split."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import numpy as np
import pandas as pd

from config import ROOT_DIR, BACKLOG_START
from pipeline.common import DataError, assert_unique, normal, numeric, first_release


def week_date(value: object) -> pd.Timestamp | None:
    """Recognise date-valued cells or explicit w-e labels, never numeric notes."""
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).normalize()
    text = normal(value)
    if not re.match(r'w[\s-]*e\s+', text, re.I):
        return None
    date_text = re.sub(r'^w[\s-]*e\s+', '', text, flags=re.I)
    try:
        return pd.to_datetime(date_text, dayfirst=True, errors='raise').normalize()
    except ValueError as exc:
        raise DataError(f'Unrecognised backlog date: {value}') from exc


def provenance(frame: pd.DataFrame, item: dict[str, str]) -> pd.DataFrame:
    """Approximate original weekly availability; retain latest source release separately."""
    frame['published_on'] = first_release(frame.week_ending)
    frame['publication_date_basis'] = 'assumed_observation_month_plus_2_day_14'
    frame['source_published_on'] = pd.Timestamp(item.get('source_published_on', item['published_on']))
    frame['availability_label'] = 'approximate: latest revised values'
    frame['source_url'] = item['url']
    frame['source_sha256'] = item['sha256']
    frame['historical_vintage_verified'] = False
    return frame


def parse_workbook(path: Path, item: dict[str, str], start: str = str(BACKLOG_START), end: str | None = None) -> dict[str, pd.DataFrame]:
    """Detect header positions in both official backlog sheets."""
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    names = {name.strip().lower(): name for name in sheets}
    if not {'62 day ptl', '62 day ptl by provider'}.issubset(names):
        raise DataError(f'Unexpected backlog sheets: {list(sheets)}')
    national_raw = sheets[names['62 day ptl']]
    header = next((i for i, row in national_raw.iterrows() if 'No DTT' in row.values and 'With DTT' in row.values), None)
    if header is None:
        raise DataError('Cannot find national DTT headers')
    cols = {normal(v): i for i, v in national_raw.loc[header].items()}
    records = []
    for _, row in national_raw.iloc[header + 1:].iterrows():
        dates = [week_date(v) for v in row.iloc[:3]]
        week = next((v for v in dates if v is not None), None)
        if week is not None:
            records.append({'week_ending': week, 'total': row[cols['Total']], 'no_dtt': row[cols['No DTT']], 'with_dtt': row[cols['With DTT']]})
    national = pd.DataFrame(records)
    for col in ('total', 'no_dtt', 'with_dtt'):
        national[col] = numeric(national[col], col)
    complete = national[['total', 'no_dtt', 'with_dtt']].notna().all(axis=1)
    if not np.allclose(national.loc[complete, 'total'], national.loc[complete, 'no_dtt'] + national.loc[complete, 'with_dtt']):
        raise DataError('National backlog does not reconcile to No DTT + With DTT')
    raw = sheets[names['62 day ptl by provider']]
    header = next((i for i, row in raw.iterrows() if 'ORG CODE' in row.values), None)
    if header is None:
        raise DataError('Cannot find provider backlog headers')
    cols = {normal(v): i for i, v in raw.loc[header].items()}
    dates = {i: week_date(v) for i, v in raw.loc[header].items() if week_date(v) is not None}
    records = []
    for _, row in raw.iloc[header + 1:].iterrows():
        code = normal(row[cols['ORG CODE']])
        if not re.fullmatch(r'[A-Z0-9]{3,5}', code) or code in {'TOTAL'}:
            continue
        for col, week in dates.items():
            records.append({'org_code': code, 'org_name': normal(row[cols['ORG NAME']]), 'week_ending': week, 'backlog': row[col]})
    trust = pd.DataFrame(records)
    trust['backlog'] = numeric(trust.backlog, 'backlog')
    for frame in (national, trust):
        frame.drop(frame.index[frame.week_ending.lt(pd.Timestamp(start))], inplace=True)
        if end:
            cutoff = pd.Timestamp(end) + pd.offsets.MonthEnd(0)
            frame.drop(frame.index[frame.week_ending.gt(cutoff)], inplace=True)
        provenance(frame, item)
    national['week'] = national.week_ending  # compatibility alias requested in brief
    assert_unique(national, ['week_ending'], 'National backlog')
    assert_unique(trust, ['org_code', 'week_ending'], 'Provider backlog')
    if trust.empty or national.empty:
        raise DataError('No backlog observations in requested range')
    return {'backlog_national': national.reset_index(drop=True), 'backlog_trust': trust.reset_index(drop=True)}


def parse_all(manifest: pd.DataFrame, start: str, end: str | None) -> dict[str, pd.DataFrame]:
    """Read the single selected latest backlog source."""
    items = manifest.loc[manifest.dataset.eq('backlog')].to_dict('records')
    if len(items) != 1:
        raise DataError(f'Expected one backlog workbook, found {len(items)}')
    return parse_workbook(ROOT_DIR / items[0]['local_path'], items[0], start, end)
