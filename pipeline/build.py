"""Download, validate, prepare all Stage 1 datasets, and plot Oxford observations."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import logging
from pathlib import Path
import shutil
import tempfile

import pandas as pd

from config import DOCS_DIR, OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR, ROOT_DIR, START_PERIOD, BACKLOG_START, STATIC_DIR, check_python_version, ensure_directories
from pipeline import parse_backlog, parse_cwt, parse_dm01
from pipeline.common import DataError, first_release
from pipeline.universe import write_core_trusts
from pipeline.fetch import fetch_all
from pipeline.locations import resolve_locations
from pipeline.plot import plot_oxford
from pipeline.quality import build_report

LOG = logging.getLogger(__name__)


def read_manifest() -> pd.DataFrame:
    """Read a complete cached manifest and verify every downloaded file's checksum."""
    path = RAW_DIR / 'manifest.csv'
    if not path.exists():
        raise DataError('No complete manifest. Run once without --offline first.')
    manifest = pd.read_csv(path, dtype=str, keep_default_na=False)
    for item in manifest.to_dict('records'):
        source = ROOT_DIR / item['local_path']
        if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
            raise DataError(f'Missing or changed cached file: {source}. Fetch again with --refresh.')
    return manifest


def write_locations(cwt: pd.DataFrame) -> None:
    """Provide a named blank-coordinate fallback; preserve any existing coordinates."""
    path = STATIC_DIR / 'trust_locations.csv'
    names = cwt.sort_values('period').drop_duplicates('Org_Code', keep='last')[['Org_Code', 'Org_Name']]
    names = names.rename(columns={'Org_Code': 'org_code', 'Org_Name': 'name'})
    if path.exists():
        existing = pd.read_csv(path, dtype={'org_code': str})
        names = names.merge(existing.drop(columns='name', errors='ignore'), on='org_code', how='left', validate='one_to_one')
    for column in ['lat', 'lon', 'postcode', 'source_url']:
        if column not in names:
            names[column] = pd.NA
    if 'location_status' not in names:
        names['location_status'] = 'not_resolved'
    names['location_status'] = names.location_status.fillna('not_resolved')
    names.to_csv(path, index=False)


def run(start: str, end: str | None, offline: bool, refresh: bool, skip_locations: bool = False) -> dict:
    """Write outputs only after all source parsers and validation checks succeed."""
    check_python_version()
    ensure_directories()
    manifest = read_manifest() if offline else fetch_all(start, end, refresh=refresh)
    if offline:
        start_date = pd.Timestamp(start).to_period('M').to_timestamp()
        end_date = pd.Timestamp(end or date.today()).to_period('M').to_timestamp()
        manifest = manifest.loc[manifest.dataset.eq('backlog') | pd.to_datetime(manifest.period, errors='coerce').between(start_date, end_date)].copy()
        if not {'cwt', 'dm01', 'backlog'}.issubset(set(manifest.dataset)):
            raise DataError('Cached manifest does not cover all datasets for that date range')
    # Upgrade old cached manifests without changing file bytes or checksums.
    if 'source_published_on' not in manifest:
        manifest['source_published_on'] = manifest['published_on']
    monthly = manifest.dataset.ne('backlog')
    manifest.loc[monthly, 'published_on'] = first_release(pd.to_datetime(manifest.loc[monthly, 'period'])).dt.strftime('%Y-%m-%d')
    manifest.loc[monthly, 'publication_date_basis'] = 'assumed_observation_month_plus_2_day_14'
    data = parse_cwt.parse_all(manifest)
    data.update(parse_backlog.parse_all(manifest, str(BACKLOG_START), end))
    data.update(parse_dm01.parse_all(manifest, set(data['cwt'].Org_Code)))
    report = build_report(data, manifest)
    with tempfile.TemporaryDirectory(prefix='cancer-clock-build-') as staging:
        temp = Path(staging)
        for name, frame in data.items():
            frame.to_parquet(temp / f'{name}.parquet', index=False)
        plot_oxford(data, temp / 'fig_rth_backlog.png')
        for file in temp.glob('*.parquet'):
            shutil.copy2(file, PROCESSED_DIR / file.name)
        shutil.copy2(temp / 'fig_rth_backlog.png', DOCS_DIR / 'fig_rth_backlog.png')
    write_locations(data['cwt'])
    if not offline and not skip_locations:
        report['locations'] = resolve_locations()
    else:
        locations = pd.read_csv(STATIC_DIR / 'trust_locations.csv')
        report['locations'] = {
            'providers': len(locations),
            'resolved': int(locations[['lat', 'lon']].notna().all(axis=1).sum()),
            'note': 'Organisation headquarters postcode coordinates, not all hospital sites.',
        }
    from pipeline.mergers import harmonize, write_scope
    write_scope(data['backlog_trust'],data['cwt_trust_month'])
    core = write_core_trusts(harmonize(data['backlog_trust'],'backlog_trust'))
    report['core_trusts'] = len(core)
    report['locations']['note'] = 'Headquarters or verified representative hospital postcode; location_kind identifies each.'
    report['core_locations_resolved'] = int(core.map_eligible.sum())
    report['processed_file_bytes'] = {p.name: p.stat().st_size for p in PROCESSED_DIR.glob('*.parquet')}
    (OUTPUTS_DIR / 'data_quality.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    # Public provenance may be committed; local download paths and timestamps are omitted.
    manifest.drop(columns=['local_path', 'downloaded_on'], errors='ignore').to_csv(DOCS_DIR / 'source_manifest.csv', index=False)
    print('\nStage 1 data-quality report')
    print(f'{"Dataset":24} {"Rows":>10} {"Providers":>10}  Coverage')
    for name, summary in report['datasets'].items():
        print(f'{name:24} {summary["rows"]:>10,} {summary.get("providers", "national"):>10}  {summary["first_period"]} to {summary["last_period"]}')
    print(f'Providers in all three datasets: {report["provider_overlap"]["in_all_three"]}')
    print(f'Providers with missing backlog weeks: {len(report["backlog_missing_weeks"])}')
    print('Missing months:', report['missing_months'])
    for warning in report['warnings']:
        print('NOTE:', warning)
    print('Written: data/processed/*.parquet, outputs/data_quality.json, docs/fig_rth_backlog.png')
    return report


def main() -> None:
    """Command-line entry point, with cache-only runs for quick repeated checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default=str(START_PERIOD), help='First observation month (default October 2023)')
    parser.add_argument('--end', help='Last observation month; default latest discovered releases')
    parser.add_argument('--offline', action='store_true', help='Parse cached files; do not make network requests')
    parser.add_argument('--refresh', action='store_true', help='Re-download pages and source files')
    parser.add_argument('--skip-locations', action='store_true', help='Keep named blank-coordinate fallback; resolve later')
    args = parser.parse_args()
    if args.offline and args.refresh:
        parser.error('--offline and --refresh cannot be combined')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        run(args.start, args.end, args.offline, args.refresh, args.skip_locations)
    except Exception as exc:
        LOG.error('BUILD FAILED: %s', exc)
        LOG.error('No success is claimed. Check the last source/schema above; existing outputs may be from a previous run.')
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
