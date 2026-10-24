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
    scope_path = STATIC_DIR / 'provider_scope.csv'
    if scope_path.exists():
        scope = pd.read_csv(scope_path, keep_default_na=False)
        core = core.loc[core.org_code.isin(scope.loc[scope.included, 'org_code'])].copy()
    # Fail on an unfamiliar provider class rather than silently admit independents.
    if not core.name.str.contains(r'\bNHS\b.*\bTRUST\b', regex=True).all():
        raise DataError('Backlog universe contains a non-NHS-trust name; review membership')
    locations = pd.read_csv(STATIC_DIR / 'trust_locations.csv')
    locations['map_eligible'] = locations.org_code.isin(core.org_code) & locations[['lat', 'lon']].notna().all(axis=1)
    if scope_path.exists():
        locations['scope_note'] = locations.org_code.map(scope.set_index('org_code').note).fillna('Outside acute cancer backlog cohort')
    locations.to_csv(STATIC_DIR / 'trust_locations.csv', index=False)
    fields = ['org_code', 'lat', 'lon', 'postcode', 'location_kind', 'map_eligible']
    core = core.merge(locations[fields], on='org_code', how='left', validate='one_to_one')
    core['map_eligible'] = core.map_eligible.fillna(False).astype(bool)
    core['membership_basis'] = 'Live acute/specialist NHS cancer provider; reviewed current footprint; see provider_scope.csv'
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
