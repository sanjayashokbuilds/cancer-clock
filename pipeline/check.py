"""Check the bundled processed snapshot without downloading NHS files again."""
from __future__ import annotations

import json

import pandas as pd

from config import DOCS_DIR, OUTPUTS_DIR, PROCESSED_DIR
from pipeline.common import DataError, assert_unique, first_release

KEYS = {
    'cwt': ['Org_Code', 'period', 'Standard_or_Item', 'Cancer_Type', 'Referral_Route_or_Stage', 'Treatment_Modality'],
    'cwt_national': ['Org_Code', 'period', 'Standard_or_Item', 'Cancer_Type', 'Referral_Route_or_Stage', 'Treatment_Modality'],
    'cwt_trust_month': ['org_code', 'period', 'cancer_type'],
    'cwt_first_seen': ['org_code', 'period'],
    'backlog_trust': ['org_code', 'week_ending'],
    'backlog_national': ['week_ending'],
    'dm01': ['org_code', 'period', 'test'],
}


def main() -> None:
    """Verify saved files, row counts, unique keys and availability metadata."""
    report = json.loads((OUTPUTS_DIR / 'data_quality.json').read_text())
    for name, keys in KEYS.items():
        path = PROCESSED_DIR / f'{name}.parquet'
        frame = pd.read_parquet(path)
        if frame.empty or len(frame) != report['datasets'][name]['rows']:
            raise DataError(f'{name}: saved row count does not match the build report')
        assert_unique(frame, keys, name)
        if frame.published_on.isna().any() or frame.source_url.isna().any():
            raise DataError(f'{name}: missing provenance')
        time = frame.week_ending if name.startswith('backlog') else frame.period
        if not frame.published_on.eq(first_release(time)).all():
            raise DataError(f'{name}: incorrect first-release rule')
        if not (frame.published_on-time).dt.days.between(44, 75).all():
            raise DataError(f'{name}: unexpected publication lag')
        if frame.historical_vintage_verified.any():
            raise DataError(f'{name}: revised snapshot must remain unverified')
        if path.stat().st_size >= 25_000_000:
            raise DataError(f'{path.name} exceeds the GitHub web upload limit')
        print(f'{name}: {len(frame):,} rows OK')
    from pipeline.universe import load_core_trusts, core_locations
    core = load_core_trusts()
    print(f'Core trusts: {len(core)}; map locations: {len(core_locations())}')
    chart = DOCS_DIR / 'fig_rth_backlog.png'
    if not chart.exists() or chart.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
        raise DataError('Oxford PNG is missing or invalid')
    print('Stage 1 snapshot checks passed. Publication dates remain approximate.')


if __name__ == '__main__':
    main()
