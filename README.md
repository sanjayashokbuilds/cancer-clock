# Cancer Clock

Stage 0: repository skeleton. No data pipeline, forecast, simulator, API or
frontend has been implemented yet. There are no measured results to report.

The planned tool will forecast hospital-level cancer backlogs in England and
compare explicitly assumed recovery scenarios. Planning information, not
medical advice. No personal waiting-time predictions.

## Run Stage 0

Install Python 3.11 or newer. Extract the ZIP and open a terminal inside the
`cancer-clock` folder. No Git command-line tools or API keys are needed.

Windows (PowerShell or Command Prompt):

```text
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe config.py
.venv\Scripts\python.exe -m pytest -q
```

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python config.py
.venv/bin/python -m pytest -q
```

These commands use the virtual environment directly; activation is unnecessary.
On Windows, if `py` is unavailable, use `python` for the first command. Check
that it is version 3.11 or newer. If several Python versions are installed,
select a supported one explicitly (for example `py -3.11`).

Expected configuration output:

```text
Cancer Clock | Stage 0 skeleton ready
Python requirement: 3.11+ OK
Working directories ready; no data downloaded.
Planning information, not medical advice. Forecasts are hospital-level, not personal.
```

Expected test result: `1 passed` (elapsed time varies). The one smoke test only
checks configuration import and the supported runtime; it does not validate data
or forecasts. The only installed Stage 0 dependency is pytest. Later-stage
dependencies are listed as comments in `requirements.txt` and will be added and
tested when needed. This avoids installing ML/database packages before use.

## GitHub web upload

1. Extract the complete ZIP. At your repository root, choose **Add file → Upload
   files**. Upload the **contents** of `cancer-clock/` so `README.md` appears at
   the repository root; do not upload the ZIP itself or nest the folder twice.
2. Include `.gitignore` and `.env.example`. Enable hidden-file visibility in your
   file manager if necessary. GitHub cannot preserve empty folders, so `.gitkeep`
   files preserve the directories reserved for later stages.
3. The supplied ZIP excludes `data/raw/`, `.venv/`, `node_modules/`, `.env`,
   Python caches and build outputs. If you run the project before uploading,
   exclude these again manually. **GitHub's web uploader does not apply
   `.gitignore` to files you drag into it.** `config.py` recreates `data/raw/`
   locally; it should never be uploaded.
4. Keep uploads at no more than 100 files and every individual file below 25 MB.
   Future processed parquet files may be included only when smaller than that
   limit; otherwise the pipeline must regenerate them.
5. Commit with `chore: initialise Stage 0 Cancer Clock repository`.

Never upload credentials or patient-level data. Stage 0 has no credentials.
There are no files to delete for this initial stage. Future handoffs will list
removals explicitly because web uploads do not delete obsolete files.

## Structure

| Path | Purpose / stage |
| --- | --- |
| `config.py` | Project name, paths, constants and labelled proposed assumptions |
| `data/raw/` | Excluded downloads; created by `config.py` |
| `data/processed/` | Future parquet outputs |
| `data/static/` | Future verified strike dates, locations and test lists |
| `pipeline/` | Stage 1 data ingestion and availability filtering |
| `models/` | Stages 2–3 baselines, back-tests and forecasts |
| `analysis/` | Stage 4 bottleneck evidence |
| `sim/` | Stages 5–6 scenarios and optional allocation |
| `api/` | Stage 7 API |
| `web/` | Stage 8 React frontend |
| `integrations/` | Stages 9–11 optional services |
| `outputs/` | Future precomputed results; currently empty |
| `tests/` | Stage 0 smoke test |
| `docs/` | Methodology, assumptions and stage handoff |

## Roadmap and evidence gates

Build one stage at a time only when requested. Stage 1 must verify the real data
before any numerical results are shown. Stage 2 must establish baselines before
Stage 3 adds ML. Stage 3 must report the baseline comparison honestly and stop
for review if the required performance gate is missed. Stages 4–5 must separate
observed associations from assumed intervention effects. Stage 6 is stretch;
Stages 7–10 add API, frontend, Gemini, optional Tiger Data and deployment.
Stage 11 is optional voice/outlook; Stage 12 is submission polish.

## Methodology and results

See [methodology](docs/methodology.md) and [assumptions](docs/assumptions.md).
Data coverage, model scores, interval coverage, trust counts and simulator fit
are **not measured** in Stage 0. Screenshots and architecture details will be
added when the corresponding components exist.

## Proposed source pages

These URLs come from the supplied brief; they have not been fetched or verified
by this skeleton. Stage 1 will inspect the files and report schema differences.

- [NHS England Cancer Waiting Times](https://www.england.nhs.uk/statistics/statistical-work-areas/cancer-waiting-times/monthly-data-and-summaries/)
- [NHS England cancer management information](https://www.england.nhs.uk/statistics/statistical-work-areas/cancer-waiting-times/management-information-on-cancer/)
- [NHS England diagnostics waiting times](https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/)

Source licensing and attribution must be checked before redistributing data.
The MIT license covers repository code, not third-party datasets.

## Stage handoff

See [Stage 0 handoff](docs/stage_0.md) for the changed files, commit message,
verification scope and remaining risks. Team: Sanjay and Rounak, as provided in
the brief. Sponsor integrations and prize entries are planned, not completed.
