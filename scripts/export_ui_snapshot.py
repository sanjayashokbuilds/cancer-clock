"""Export real GET responses for static, offline UI review; never fabricate data.

Usage: python -m scripts.export_ui_snapshot --output /absolute/preview/dist
Copy web/dist into that directory first. The extensionless files under api/
are the same JSON bodies the application serves; no Python preview server is
needed. Keep this review export outside the source checkout and release ZIP.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from api.data import Snapshot
from config import ROOT_DIR


def export_snapshot(output: Path, snapshot: Snapshot | None = None) -> dict:
    output = output.resolve()
    if output == ROOT_DIR or output.is_relative_to(ROOT_DIR):
        raise ValueError('Static review snapshots must be written outside the source checkout')
    store = snapshot or Snapshot()
    count = 0

    def write(route: str, body: dict) -> None:
        nonlocal count
        target = output / route.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(body, allow_nan=False, separators=(',', ':')))
        count += 1

    write('/health', dict(status='ok', issue_date=store.issue_date,
        core_trusts=len(store.codes), snapshot_sha256=store.hashes, precomputed=True))
    write('/api/trusts', store.trusts)
    write('/api/map', store.map)
    write('/api/national', store.national)
    write('/api/backtest', dict(**store.meta, model=store.reports['backtest_model'],
        classifier=store.reports['backtest_classifier']))
    for code in sorted(store.codes):
        write(f'/api/trust/{code}/forecast', {**store.meta,
            **store.indexes['forecasts_latest'][code], 'history': store.backlogs[code]})
        write(f'/api/trust/{code}/bottleneck', {**store.meta, **store.indexes['bottlenecks'][code]})
        write(f'/api/trust/{code}/history', store.histories[code])
        # Snapshot.decision may attach a separately precomputed presentation grid.
        decision = store.decision(code) if hasattr(store, 'decision') else {
            **store.meta, **store.indexes['decision_support'][code]}
        write(f'/api/trust/{code}/decision', decision)
    result = dict(output=str(output), files=count, issue_date=store.issue_date,
                  source_sha256=store.hashes, purpose='Static UI review from the real API snapshot')
    (output / 'snapshot-provenance.json').write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_snapshot(args.output), indent=2))


if __name__ == '__main__':
    main()
