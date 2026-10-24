# Stage 1 data dictionary

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

For monthly data, `published_on` is day 14 of the selected file's URL upload
month. This can be much later than the first release of the observation because
Final data are revisions. It is not an exact release date and may not be
conservative within that month. For backlog weeks, the assumed date is day 14
of observation month + 2; `source_published_on` separately records the latest
workbook's assumed upload date.

`available_at(dataset, as_of_date)` rejects unverified vintages by default. An
explicit `allow_approximate=True` opts into a labelled filter using these
assumptions. It does not prove what values were known at a historical date.

## Geography and scope

`trust_locations.csv` uses ODS organisation headquarters postcodes and
postcodes.io coordinates where resolved. These are not all individual hospital
sites, and several providers can share a postcode. Failed or retired postcodes
remain blank. The file preserves source URLs and lookup status. CWT's Provider
basis includes independent-sector providers; do not call every entry an NHS
trust. No code crosswalk or merger adjustment is inferred from disappearing codes.
