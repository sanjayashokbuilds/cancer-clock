"""Availability filters that refuse to imply reconstructed historical vintages."""
from __future__ import annotations

import pandas as pd

from config import PROCESSED_DIR
from pipeline.common import DataError


def available_at(dataset: str | pd.DataFrame, as_of_date: str | pd.Timestamp,
                 *, allow_approximate: bool = False) -> pd.DataFrame:
    """Filter release dates; approximate current revised values require explicit opt-in.

    This Stage 1 dataset is not verified historical-vintage data. Later back-tests
    must disclose that limitation or obtain archived releases. No values are filled.
    """
    allowed = {'cwt', 'cwt_national', 'cwt_trust_month', 'cwt_first_seen',
               'backlog_trust', 'backlog_national', 'dm01'}
    if isinstance(dataset, str):
        if dataset not in allowed:
            raise ValueError(f'Unknown dataset: {dataset}')
        frame = pd.read_parquet(PROCESSED_DIR / f'{dataset}.parquet')
    else:
        frame = dataset.copy()
    if 'published_on' not in frame:
        raise DataError('Missing publication dates')
    dates = pd.to_datetime(frame.published_on, errors='coerce')
    result = frame.loc[dates.notna() & dates.le(pd.Timestamp(as_of_date))].copy()
    verified = result.get('historical_vintage_verified', pd.Series(False, index=result.index))
    if not allow_approximate and not verified.fillna(False).all():
        raise DataError('Historical vintages are unverified. Pass allow_approximate=True only for an explicitly labelled approximate evaluation.')
    result.attrs['availability_mode'] = 'approximate_latest_revised_values' if allow_approximate else 'verified_vintages'
    return result
