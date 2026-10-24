"""Resolve provider headquarters through NHS ODS and postcodes.io; keep gaps blank."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from urllib.parse import quote

import pandas as pd
import requests

from config import RAW_DIR, STATIC_DIR

LOG = logging.getLogger(__name__)
ODS = 'https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations/'
POSTCODES = 'https://api.postcodes.io/postcodes/'


def cached_json(url: str, cache: Path) -> dict:
    """Cache public location responses; never disable TLS validation."""
    if cache.exists():
        return json.loads(cache.read_text())
    time.sleep(0.6)  # At most two workers, under the ODS five-request/second guidance.
    response = requests.get(url, timeout=(8, 15), headers={'Accept': 'application/json'})
    response.raise_for_status()
    result = response.json()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result))
    return result


def locate(row: dict) -> dict:
    """Use organisation headquarters, not an invented individual hospital location."""
    code = row['org_code']
    result = dict(row)
    if pd.notna(row.get('lat')) and pd.notna(row.get('lon')):
        return result
    result['source_url'] = ODS + code
    result['location_kind'] = 'organisation_headquarters_postcode'
    try:
        source = cached_json(ODS + quote(code), RAW_DIR / 'locations' / f'{code}.json')['Organisation']
        postcode = source.get('GeoLoc', {}).get('Location', {}).get('PostCode')
        result['postcode'] = postcode
        result['ods_status'] = source.get('Status', '')
        if not postcode:
            result['location_status'] = 'missing_postcode'
            return result
        geocode = cached_json(POSTCODES + quote(postcode), RAW_DIR / 'locations' / ('postcode_' + postcode.replace(' ', '') + '.json'))
        if not geocode.get('result'):
            result['location_status'] = 'postcode_not_found'
            return result
        result['lat'] = geocode['result']['latitude']
        result['lon'] = geocode['result']['longitude']
        result['geocode_source_url'] = POSTCODES + quote(postcode)
        result['location_status'] = 'resolved'
        result['retrieved_on'] = datetime.now(timezone.utc).date().isoformat()
    except (requests.RequestException, ValueError, KeyError) as exc:
        LOG.warning('Location unresolved for %s: %s', code, type(exc).__name__)
        result['location_status'] = 'lookup_failed'
    return result


def resolve_locations() -> dict:
    """Populate the named fallback file, leaving failures usable as explicit gaps."""
    path = STATIC_DIR / 'trust_locations.csv'
    frame = pd.read_csv(path, dtype={'org_code': str})
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = pd.DataFrame(pool.map(locate, frame.to_dict('records')))
    result.to_csv(path, index=False)
    report = {'providers': len(result), 'resolved': int(result[['lat', 'lon']].notna().all(axis=1).sum()),
              'note': 'Organisation headquarters postcode coordinates, not all hospital sites.'}
    print('Location lookup:', report)
    return report


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    resolve_locations()
