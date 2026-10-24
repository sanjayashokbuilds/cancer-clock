# Data dictionary

All observation dates use midnight-naive timestamps. Performance columns in CWT
are proportions from 0 to 1. `pct_waiting_6plus` in DM01 is a percentage from 0 to
100. Missing values stay null and must not be treated as zero.

| File | One row represents | Main fields |
| --- | --- | --- |
| `cwt.parquet` | Provider × month × standard × source cancer label × route/stage × modality | Original named dimensions, Total, Within, After, Performance, published day bands |
| `cwt_national.parquet` | Published national total at the same dimensional granularity | Kept separate; never add to provider rows |
| `cwt_trust_month.parquet` | Provider × month × source cancer label | Wide selected FDS, 62D and 31D metrics; null for unpublished combinations |
| `cwt_first_seen.parquet` | Provider × month | USC completed first attendances; volume proxy, not referrals received |
| `backlog_trust.parquet` | Provider × week ending | `backlog`: patients still waiting beyond 62 days |
| `backlog_national.parquet` | Week ending | `total`, `no_dtt`, `with_dtt`; `week` aliases `week_ending` |
| `dm01.parquet` | Provider × diagnostic test × month | Waiting list, count and percent waiting 6+ weeks, activity split |

The tidy CWT prefixes mean:

- `fds`: ALL ROUTES, all modalities (the source FDS modality is blank).
- `d62_usc`: URGENT SUSPECTED CANCER route, ALL MODALITIES.
- `d62_all`: ALL ROUTES, ALL MODALITIES.
- `d31_all`, `d31_surgery`, `d31_radiotherapy`, `d31_drugs`: ALL STAGES,
  with the stated modality.
- `usc_first_seen_total`: completed first attendances for the source cancer label.

The original source labels for suspected and confirmed cancer are different.
They are preserved, not automatically mapped. Older workbooks do not contain
every later cross-tabulation. Missing combinations are left null. Treatment
counts may include halves because of shared care; they are not rounded to people.
`Parent_Org` is blank when not published in the older workbook.

Referral-labelled tables are titled as waits to the first outpatient attendance
in the older source workbooks. They are not measured arrival counts. The Oxford
plot deliberately labels this series as first attendances. A later simulator
must source true arrivals or state its proxy assumption explicitly.

DM01 dates are read from the file name and checked against the internal Period
field. This handles a March 2025 link whose page label incorrectly says March
2026. CDC-only extracts are excluded because they do not represent the full
provider series.

DM01 aggregates commissioners for only these test categories: CT, MRI,
non-obstetric ultrasound, colonoscopy, flexible sigmoidoscopy, gastroscopy and
cystoscopy. It excludes the overlapping TOTAL test. Six weeks or more includes
06–07 through 12–13 weeks and 13+. If any contributing cell is suppressed or
missing, the affected aggregate remains missing. Zero-size lists have a null
percentage. `activity` is Total Activity, with waiting-list, planned and
unscheduled components retained separately. It includes non-cancer patients.

## Provenance and availability

All outputs carry `source_url`, `source_sha256`, `published_on`,
`publication_date_basis` and `historical_vintage_verified=False`. Monthly files
also carry their selected release status. `docs/source_manifest.csv` records
public source links and file hashes; the raw manifest adds local cache paths.

For **every dataset**, `published_on` is the 14th of observation month + 2.
`source_published_on` preserves the selected file's assumed URL upload date
separately. Neither date reconstructs original published values. The label is
`approximate: latest revised values` and verification remains false.

`available_at(dataset, as_of_date)` rejects unverified vintages by default. An
explicit `allow_approximate=True` opts into a labelled filter using these
assumptions. It does not prove what values were known at a historical date.

## Geography and scope

`core_trusts.csv` is the shared modelling/simulation/UI universe: 133 NHS trusts
with observed backlog from October 2023 onwards. CWT's broader provider tables
remain available for source audit, including independent providers.
Use `pipeline.universe.load_core_trusts()` and `core_locations()` downstream.

Locations are postcode centroids: ODS headquarters or verified representative
hospital sites (`location_kind`). Five explicit overrides retain address and
geocoding URLs in `location_overrides.csv`. Bridgewater uses its listed trust
address, not a supposed main hospital. All 133 core trusts have coordinates.
RVY has 13 April–July 2023 values but none in the evaluation era: it remains in
source data and is excluded from core/map. No code-merger crosswalk is inferred.
