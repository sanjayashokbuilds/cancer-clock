"""Discover official NHS downloads, cache bytes, and record their provenance."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import RAW_DIR, ROOT_DIR, START_PERIOD
from pipeline.common import DataError, period_from_text

LOG = logging.getLogger(__name__)
BASE = 'https://www.england.nhs.uk/statistics/statistical-work-areas/'
PAGES = {
    'cwt': BASE + 'cancer-waiting-times/monthly-data-and-summaries/',
    'backlog': BASE + 'cancer-waiting-times/management-information-on-cancer/',
    'dm01': BASE + 'diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/',
}


class Downloader:
    """Sequential, rate-limited requests with atomic cache writes and retries."""

    def __init__(self, raw_dir: Path = RAW_DIR, refresh: bool = False) -> None:
        self.raw_dir = raw_dir
        self.refresh = refresh
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'CancerClock/0.1 (public NHS statistics research)'
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retry))
        self.last_request = 0.0

    def get(self, url: str, folder: str) -> Path:
        """Cache by URL hash, preventing collisions between repeated filenames."""
        if urlparse(url).hostname not in {'www.england.nhs.uk', 'england.nhs.uk'}:
            raise DataError(f'Unexpected download host: {url}')
        suffix = Path(urlparse(url).path).suffix or '.html'
        target = self.raw_dir / folder / (hashlib.sha256(url.encode()).hexdigest()[:20] + suffix)
        if target.exists() and target.stat().st_size and not self.refresh:
            LOG.info('Cached %s', url.rsplit('/', 1)[-1] or url)
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        time.sleep(max(0, 0.35 - (time.monotonic() - self.last_request)))
        LOG.info('Downloading %s', url)
        self.last_request = time.monotonic()
        response = self.session.get(url, timeout=(15, 90))
        response.raise_for_status()
        payload = response.content
        if not payload:
            raise DataError(f'Empty response: {url}')
        if b"verify that you're not a robot" in payload[:20000] or b'Just a moment...' in payload[:20000]:
            raise DataError(f'NHS site returned a browser challenge for {url}. Try again later; no bypass attempted.')
        if suffix in {'.zip', '.xlsx'} and not payload.startswith(b'PK'):
            raise DataError(f'Expected ZIP/XLSX bytes, received another format: {url}')
        if suffix == '.csv' and payload.lstrip().lower().startswith((b'<!doctype html', b'<html')):
            raise DataError(f'Expected CSV, received HTML: {url}')
        temp = target.with_suffix(target.suffix + '.part')
        temp.write_bytes(payload)
        temp.replace(target)
        return target

    def links(self, url: str) -> list[tuple[str, str]]:
        """Return unique text/URL pairs from a cached official page."""
        page = self.get(url, 'pages')
        soup = BeautifulSoup(page.read_bytes(), 'html.parser')
        return list(dict.fromkeys((a.get_text(' ', strip=True), urljoin(url, a['href']))
                                 for a in soup.select('a[href]')))


def publication_date(url: str, period: pd.Timestamp | None) -> tuple[str, str]:
    """Use the upload month plus assumed day 14; never call this an exact date."""
    found = re.search(r'/uploads/(?:sites/\d+/)?(20\d{2})/(\d{2})/', url)
    if found:
        return f'{found[1]}-{found[2]}-14', 'assumed_day_14_of_url_upload_month'
    if period is None:
        raise DataError(f'No publication month identifiable: {url}')
    return (period + pd.DateOffset(months=2, days=13)).date().isoformat(), 'assumed_observation_month_plus_2_day_14'


def candidate(dataset: str, title: str, url: str, source_page: str,
              period: pd.Timestamp | None = None) -> dict[str, str]:
    """Describe one source, including its format and revision status."""
    if dataset != 'backlog' and period is None:
        if dataset == 'dm01':
            period = period_from_text(Path(urlparse(url).path).name)
            if period_from_text(title) != period:
                LOG.warning('Source page month disagrees with DM01 filename: %s. Using %s, checked against CSV Period during parsing.', title, period.date())
        else:
            period = period_from_text(title + ' ' + Path(urlparse(url).path).name)
    published, basis = publication_date(url, period)
    version = 'final' if re.search(r'\bfinal\b', title, re.I) else 'provisional' if 'provisional' in title.lower() else 'unspecified'
    return {'dataset': dataset, 'period': period.date().isoformat() if period is not None else '',
            'url': url, 'title': title, 'source_page': source_page, 'version': version,
            'format': Path(urlparse(url).path).suffix.lstrip('.'), 'published_on': published,
            'publication_date_basis': basis, 'new_icb_structure': str('new icb structure' in title.lower()).lower()}


def select_sources(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Prefer original ICB structure, then Final, with deterministic revision order."""
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for item in items:
        grouped.setdefault((item['dataset'], item['period']), []).append(item)
    chosen = []
    for key, values in sorted(grouped.items()):
        original = [v for v in values if v['new_icb_structure'] == 'false']
        pool = original or values
        chosen.append(max(pool, key=lambda v: (v['version'] == 'final', v['published_on'], v['url'])))
    return chosen


def discover(client: Downloader, start: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, str]]:
    """Follow year pages and legacy CWT month pages; never hard-code file URLs."""
    found = []
    for dataset in ('cwt', 'dm01'):
        years: dict[int, str] = {}
        for title, url in client.links(PAGES[dataset]):
            match = re.search(r'(20\d{2})[-–](\d{2})', title)
            if not match or ('monthly' not in title.lower()):
                continue
            year = int(match[1])
            if year < start.year - 1 or year > end.year:
                continue
            if 'statistical-work-areas' in url:
                years[year] = url.rstrip('/') + '/'
        if not years:
            raise DataError(f'No {dataset} year pages discovered')
        for year, page in sorted(years.items()):
            if pd.Timestamp(year + 1, 3, 1) < start or pd.Timestamp(year, 4, 1) > end:
                continue
            links = client.links(page)
            for title, url in links:
                text = title.lower()
                if dataset == 'cwt' and 'combined' in text and 'csv' in text and urlparse(url).path.lower().endswith('.csv'):
                    found.append(candidate(dataset, title, url, page))
                elif dataset == 'dm01' and is_dm01_extract(title, url):
                    found.append(candidate(dataset, title, url, page))
            # Older releases have separate month pages and a provider workbook.
            if dataset == 'cwt':
                months: dict[pd.Timestamp, list[tuple[str, str]]] = {}
                for title, url in links:
                    if 'cancer waiting times for' not in title.lower():
                        continue
                    period = period_from_text(title)
                    if start <= period <= end:
                        months.setdefault(period, []).append((title, url))
                for period, choices in sorted(months.items()):
                    title, child = max(choices, key=lambda x: ('final' in x[0].lower(), x[1]))
                    for label, url in client.links(child):
                        low = (label + ' ' + url).lower()
                        if 'provider' in low and 'workbook' in low and urlparse(url).path.lower().endswith('.xlsx'):
                            found.append(candidate(dataset, label, url, child, period))
    backlog = [candidate('backlog', title, url, PAGES['backlog'])
               for title, url in client.links(PAGES['backlog'])
               if 'backlog' in (title + url).lower() and urlparse(url).path.lower().endswith('.xlsx')]
    if not backlog:
        raise DataError('No official backlog XLSX discovered')
    found.extend(backlog)
    return [x for x in found if x['dataset'] == 'backlog' or start <= pd.Timestamp(x['period']) <= end]


def is_dm01_extract(title: str, url: str) -> bool:
    """Exclude the overlapping CDC-only series; retain the full provider extract."""
    text = title.lower()
    return ('csv' in text and 'extract' in text and 'all provider' in text
            and not re.search(r'\bcdc\b|community diagnostic', title + ' ' + url, re.I)
            and urlparse(url).path.lower().endswith('.zip'))


def fetch_all(start: str = str(START_PERIOD), end: str | None = None,
              raw_dir: Path = RAW_DIR, refresh: bool = False) -> pd.DataFrame:
    """Download selected sources and save an audit manifest after each success."""
    start_date = pd.Timestamp(start).to_period('M').to_timestamp()
    end_date = pd.Timestamp(end or date.today()).to_period('M').to_timestamp()
    if start_date < pd.Timestamp(START_PERIOD) or end_date < start_date:
        raise DataError('Use a valid range starting October 2023 or later')
    client = Downloader(raw_dir, refresh)
    candidates = discover(client, start_date, end_date)
    raw_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(candidates).drop_duplicates('url').to_csv(raw_dir / 'discovered_sources.csv', index=False)
    selected = select_sources(candidates)
    if not any(x['dataset'] == 'cwt' for x in selected) or not any(x['dataset'] == 'dm01' for x in selected):
        raise DataError('The requested range does not contain both CWT and DM01 releases')
    records = []
    for index, item in enumerate(selected, 1):
        LOG.info('Source %d/%d: %s %s', index, len(selected), item['dataset'], item['period'])
        path = client.get(item['url'], item['dataset'])
        row = dict(item)
        try:
            row['local_path'] = path.relative_to(ROOT_DIR).as_posix()
        except ValueError:
            row['local_path'] = str(path.resolve())
        row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        row['downloaded_on'] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        records.append(row)
        pd.DataFrame(records).to_csv(raw_dir / 'manifest.incomplete.csv', index=False)
    manifest = pd.DataFrame(records)
    (raw_dir / 'manifest.incomplete.csv').replace(raw_dir / 'manifest.csv')
    (raw_dir / 'fetch_request.json').write_text(json.dumps({'start': str(start_date.date()), 'end': str(end_date.date())}, indent=2))
    return manifest


def main() -> None:
    """Allow download-only runs for debugging and reuse."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default=str(START_PERIOD))
    parser.add_argument('--end')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    fetch_all(args.start, args.end, refresh=args.refresh)


if __name__ == '__main__':
    main()
