# Stage 1 handoff (historical)

Snapshot below describes the original Stage 1. Stage 2 corrects release timing,
extends backlog history and supplies the core universe; see stage_2.md.

The real-data pipeline is built and tested. No forecasting, simulator or web app
has been added. Stage 0 configuration and its smoke test still run.

## Measured done check

- 71 selected source downloads: 35 CWT releases, 35 DM01 extracts and one backlog
  workbook. Raw downloads are excluded from the deliverable and Git.
- CWT: 621,228 provider records across 35 months, October 2023–August 2026.
  There are 195 distinct provider codes across history, including independent
  providers, and 147 codes in the latest CWT month (excluding the national Total row).
- CWT national: 6,166 records, kept separately from providers.
- Tidy CWT: 116,111 provider/month/source-cancer-label rows.
- First-attendance volume proxy: 4,931 provider/month rows.
- Backlog: 20,502 provider/week rows covering 134 providers and 153 weekly dates
  from 1 October 2023 through 30 August 2026; 282 source cells are missing and
  remain null. One listed code (RVY) has no observed backlog values in this
  window, so 133 providers have at least one observed count. See the report for which codes and weeks are affected.
- National backlog: 153 weeks; provider sums match national totals for every
  included week. The national No-DTT + With-DTT split also reconciles.
- DM01: 36,477 provider/test/month rows across 35 months and seven selected tests.
- No entire observation month is missing in CWT or DM01.
- 133 provider codes occur in all three datasets over the included history.
- Real headquarters postcode coordinates resolved for 145 of 195 historical
  provider codes. The remaining rows have blank coordinates (including two
  latest-provider lookups that timed out); no locations were invented.
- 14 automated tests passed on Python 3.12.14. The bundled seven-file snapshot
  passed its saved-row-count, unique-key and provenance checks.
- The Oxford PNG was generated from observations and visually inspected.
- Every processed file is below 25 MB; the largest is about 9.14 MB.

These are data checks, not model validation scores. The timestamp filter requires
an explicit opt-in to approximate availability because exact historical vintages
have not been reconstructed. See README for one-command rebuilding and the quick
snapshot checks. Optional location lookups may leave unresolved rows blank.

## Important source adaptations

Older CWT releases are Excel provider workbooks, not Combined CSVs. Some have
incorrect sheet dimensions declared as A1; the parser resets those dimensions.
The March 2025 DM01 link incorrectly says March 2026 on the NHS page; file dates
are confirmed against the internal Period field. CDC-only extracts are excluded.
First outpatient attendances are not described as referrals received. These
changes are covered by tests and documented in data_dictionary.md.

## Files changed this stage

Added:

- `data/processed/backlog_national.parquet`
- `data/processed/backlog_trust.parquet`
- `data/processed/cwt.parquet`
- `data/processed/cwt_first_seen.parquet`
- `data/processed/cwt_national.parquet`
- `data/processed/cwt_trust_month.parquet`
- `data/processed/dm01.parquet`
- `data/static/trust_locations.csv`
- `docs/data_dictionary.md`
- `docs/fig_rth_backlog.png`
- `docs/git_workflow.md`
- `docs/source_manifest.csv`
- `outputs/data_quality.json`
- `pipeline/__init__.py`
- `pipeline/build.py`
- `pipeline/check.py`
- `pipeline/common.py`
- `pipeline/fetch.py`
- `pipeline/locations.py`
- `pipeline/parse_backlog.py`
- `pipeline/parse_cwt.py`
- `pipeline/parse_dm01.py`
- `pipeline/plot.py`
- `pipeline/quality.py`
- `pipeline/vintages.py`
- `scripts/package_repo.py`
- `tests/test_pipeline.py`
- `docs/stage_1.md`

Modified:

- `README.md`
- `config.py`
- `docs/assumptions.md`
- `docs/methodology.md`
- `requirements.txt`

Files to DELETE on GitHub: none. Existing `.gitkeep` files are harmless and retained.

## Commit and run

Commit subject:

`Add NHS waiting-time data so we can test backlog forecasts against real history`

Suggested body:

The pipeline now combines weekly cancer backlogs, monthly cancer-wait figures
and diagnostic waiting lists. It handles the older Excel releases as well as
the newer CSVs, keeps missing values visible and saves an Oxford chart for a
first sanity check. Publication dates are still approximate, and first
outpatient attendances are labelled separately from referrals received.

Commands to run from the repository folder on the Mac:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pipeline.check
open docs/fig_rth_backlog.png
```

Expected: `14 passed`, then `Stage 1 snapshot checks passed` and the Oxford chart.
To reproduce the full snapshot from source:

```sh
.venv/bin/python -m pipeline.build --end 2026-08
```

Windows: replace `.venv/bin/python` with `.venv\Scripts\python.exe`, and open the
PNG from File Explorer. Source network availability and location lookup failures
can vary by laptop. See git_workflow.md for initialisation, two checkpoints and
remote setup. No GitHub push has been performed from this environment.
