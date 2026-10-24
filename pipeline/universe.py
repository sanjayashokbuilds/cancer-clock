"""One explicit NHS trust universe for modelling, simulation and UI consumers."""
from __future__ import annotations

import pandas as pd

from config import EVALUATION_START, STATIC_DIR
from pipeline.common import DataError, assert_unique


def write_core_trusts(backlog: pd.DataFrame) -> pd.DataFrame:
    """Include trusts with observed backlog in the evaluation era, retaining history."""
    observed = backlog.loc[backlog.backlog.notna() & backlog.week_ending.ge(pd.Timestamp(EVALUATION_START))]
    core = observed.sort_values('week_ending').groupby('org_code').agg(
        name=('org_name', 'last'), first_observed_week=('week_ending', 'min'),
        last_observed_week=('week_ending', 'max'), observed_weeks=('backlog', 'size')).reset_index()
    # Fail on an unfamiliar provider class rather than silently admit independents.
    if not core.name.str.contains(r'\bNHS\b.*\bTRUST\b', regex=True).all():
        raise DataError('Backlog universe contains a non-NHS-trust name; review membership')
    locations = pd.read_csv(STATIC_DIR / 'trust_locations.csv')
    locations['map_eligible'] = locations.org_code.isin(core.org_code) & locations[['lat', 'lon']].notna().all(axis=1)
    locations.to_csv(STATIC_DIR / 'trust_locations.csv', index=False)
    fields = ['org_code', 'lat', 'lon', 'postcode', 'location_kind', 'map_eligible']
    core = core.merge(locations[fields], on='org_code', how='left', validate='one_to_one')
    core['map_eligible'] = core.map_eligible.fillna(False).astype(bool)
    core['membership_basis'] = 'NHS backlog provider with observed value on/after 2023-10-01'
    core.to_csv(STATIC_DIR / 'core_trusts.csv', index=False)
    return core


def load_core_trusts() -> pd.DataFrame:
    """Load the shared universe; downstream modules must use this entry point."""
    core = pd.read_csv(STATIC_DIR / 'core_trusts.csv', dtype={'org_code': str})
    assert_unique(core, ['org_code'], 'Core trusts')
    if core.empty or not core.name.str.contains(r'\bNHS\b.*\bTRUST\b').all():
        raise DataError('Invalid core NHS trust universe')
    return core


def core_locations() -> pd.DataFrame:
    """Map markers only for observed core trusts with real coordinates."""
    core = load_core_trusts()
    return core.loc[core.map_eligible & core[['lat', 'lon']].notna().all(axis=1)].copy()
