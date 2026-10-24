"""Build Stage 4's English DM01 reference from the existing full source extracts."""
from __future__ import annotations

import pandas as pd

from config import PROCESSED_DIR, ROOT_DIR
from pipeline.build import read_manifest
from pipeline.common import assert_unique
from pipeline.parse_cwt import PROVENANCE
from pipeline.parse_dm01 import parse_zip
from pipeline.mergers import mergers
from pipeline.universe import load_core_trusts

REFERENCE_PATH = PROCESSED_DIR / 'dm01_bottleneck_reference.parquet'
SCOPE = 'English commissioners, all reporting providers; NONC excluded; seven tests separately'


def run() -> pd.DataFrame:
    """Bundle core trusts and a full England reference; do not alter Stage 3 inputs."""
    manifest = read_manifest()
    # Keep raw predecessor counts for later harmonisation into current successors.
    core = set(load_core_trusts().org_code) | set(mergers().predecessor)
    parts = []
    measures = ['total_waiting_list', 'waiting_6plus']
    for item in manifest.loc[manifest.dataset.eq('dm01')].sort_values('period').to_dict('records'):
        frame = parse_zip(ROOT_DIR / item['local_path'], item, None, exclude_non_english=True)
        grouped = frame.groupby('test', sort=True)
        national = grouped[measures].sum(min_count=1)
        # Never treat an incomplete/suppressed component as a zero contribution.
        national = national.mask(grouped[measures].count().lt(grouped.size(), axis=0)).reset_index()
        national['org_code'] = 'ENGLAND'
        national['org_name'] = 'England: all reporting providers, English commissioners'
        national['provider_count'] = national.test.map(grouped.org_code.nunique())
        national['period'] = frame.period.iloc[0]
        for col in PROVENANCE:
            national[col] = frame[col].iloc[0]
        trusts = frame.loc[frame.org_code.isin(core)].copy()
        trusts['provider_count'] = 1
        columns = ['org_code', 'org_name', 'period', 'test', *measures, 'provider_count', *PROVENANCE]
        combined = pd.concat([trusts[columns], national[columns]], ignore_index=True)
        combined['reference_scope'] = SCOPE
        parts.append(combined)
        print('English DM01 reference:', item['period'], flush=True)
    result = pd.concat(parts, ignore_index=True)
    assert_unique(result, ['org_code', 'period', 'test'], 'Stage 4 DM01 reference')
    result.to_parquet(REFERENCE_PATH, index=False)
    print(f'Written {len(result):,} rows to {REFERENCE_PATH.name}')
    return result


if __name__ == '__main__':
    run()
