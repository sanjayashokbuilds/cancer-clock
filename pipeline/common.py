"""Shared parsing and validation helpers."""
from __future__ import annotations

from calendar import month_name
from io import BytesIO
from pathlib import Path
import re

import pandas as pd

MONTHS = {name.lower(): i for i, name in enumerate(month_name) if name}
MISSING = {'', '-', '--', '*', '**', ':', '..', '...', 'n/a', 'na', 'nan', 'null', 'not available'}


class DataError(ValueError):
    """A source format or value needs review; never silently replace it."""


def normal(value: object) -> str:
    """Normalise whitespace without altering category meaning."""
    return re.sub(r'\s+', ' ', str(value).replace('\xa0', ' ')).strip()


def period_from_text(text: str) -> pd.Timestamp:
    """Read a named month/year, including NHS fiscal-year page titles."""
    clean = re.sub(r'[-–_/]', ' ', text.lower())
    match = re.search(r'\b(' + '|'.join(MONTHS) + r')\s+(20\d{2})(?:\s+(\d{2}))?\b', clean)
    if not match:
        raise DataError(f'Cannot identify a month in: {text}')
    month, year = MONTHS[match[1]], int(match[2])
    # A page named January 2023-24 refers to January 2024.
    if match[3] and int(match[3]) == (year + 1) % 100 and month <= 3:
        year += 1
    return pd.Timestamp(year, month, 1)


def numeric(series: pd.Series, label: str) -> pd.Series:
    """Parse counts, preserving suppressed or blank values as missing."""
    text = series.astype('string').str.strip().str.replace(',', '', regex=False)
    text = text.mask(text.str.lower().isin(MISSING))
    result = pd.to_numeric(text, errors='coerce')
    bad = text.notna() & result.isna()
    if bad.any():
        raise DataError(f'{label}: unexpected numeric values {text[bad].unique()[:8].tolist()}')
    if result.lt(0).any():
        raise DataError(f'{label}: negative counts need review')
    return result.astype('float64')


def read_csv(path: Path | BytesIO) -> pd.DataFrame:
    """Read UTF-8 NHS CSVs with a Windows-1252 fallback for older releases."""
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            if hasattr(path, 'seek'):
                path.seek(0)
            frame = pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
            frame.columns = [normal(c) for c in frame.columns]
            return frame
        except UnicodeDecodeError:
            continue
    raise DataError(f'Cannot decode {path}')


def require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    """Fail with the observed schema when a required field changes."""
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise DataError(f'{label}: missing {missing}; found {frame.columns.tolist()}')


def assert_unique(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    """Prevent accidental aggregation of overlapping published totals."""
    duplicates = frame.duplicated(keys, keep=False)
    if duplicates.any():
        raise DataError(f'{label}: duplicate keys: {frame.loc[duplicates, keys].head().to_dict("records")}')


def metadata(frame: pd.DataFrame, item: dict[str, str]) -> pd.DataFrame:
    """Attach source provenance and explicitly approximate availability."""
    result = frame.copy()
    result['period'] = pd.Timestamp(item['period'])
    result['published_on'] = first_release(result['period'])
    result['source_published_on'] = pd.Timestamp(item.get('source_published_on', item['published_on']))
    result['publication_date_basis'] = 'assumed_observation_month_plus_2_day_14'
    result['availability_label'] = 'approximate: latest revised values'
    result['source_url'] = item['url']
    result['source_sha256'] = item['sha256']
    result['source_version'] = item['version']
    result['historical_vintage_verified'] = False
    return result


def first_release(observations: pd.Series) -> pd.Series:
    """Assume first release on the 14th of M+2; do not infer original values."""
    return pd.to_datetime(observations).dt.to_period('M').dt.to_timestamp() + pd.DateOffset(months=2, days=13)
