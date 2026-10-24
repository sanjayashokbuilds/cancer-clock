# Cancer Clock

An independent planning tool using public NHS data. Follow one story:
**England's waiting list → one hospital's pressure → a recovery plan.**
The interface is designed for a 1440×900 recording. Technical evidence and
assumptions sit behind Details and How this works; they travel with the results.
Stage 6 allocation and Stage 11 voice remain skipped.

## Run the app

From your existing project folder (Python 3.11+):

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. API documentation is at **/docs**. Stop with Ctrl+C.
First setup only: `python3.12 -m venv .venv`. Mac LightGBM needs
`brew install libomp`. Windows uses `.venv\Scripts\python.exe`.
The compiled frontend and precomputed results are bundled; Node and API keys
are not needed to run the app.

## What the screens mean

The map plays weekly observed counts from April 2023, then shows the published
4/8/12-week forecasts. The gap after the last observation is explicit. Dot colour
summarises the central 12-week change, with a threshold of the larger of 10 people
or 10%; it is not a probability of growth. England's headline is observed only.

A hospital opens with its forecast and diagnosis/treatment evidence. The recovery
screen compares doing nothing with the selected extra capacity under the same
chosen disruptions. Exact cached additions are 0, 1, 2, 3, 4, 5, 10, 15 and 20%.
The three disruption switches can be combined. Extra capacity starts in week four.
The whole treatment stage changes even where radiotherapy or surgery names the
observed pressure; this is not a measured modality-specific staffing effect.

The six-month ranges include arrival/service variation and fitted-capacity
uncertainty. They are sensitivity ranges, not validated prediction intervals.
Age mix, queue split, conversion and service order remain assumptions. A separate
quality screen flags disagreements between the simulator's unchanged-capacity
path and the statistical forecast at the same 12-week date. Flagged hospitals
need review before absolute recovery totals are presented as a decision headline.

See [recording guide and outstanding review](docs/ui_redesign.md),
[uncertainty method](docs/uncertainty.md) and [interface sources](docs/ui_sources.md).

## Forecast evidence

Issue +4/+8/+12 weeks, identical current cases: **4,371 / 4,113 / 3,855**.

| MAE, patients | +4 weeks | +8 weeks | +12 weeks |
| --- | ---: | ---: | ---: |
| Last value | 30.25 | 32.32 | 34.30 |
| Recent trend | 53.07 | 61.62 | 73.17 |
| Partial mean reversion | 29.62 | 31.93 | 33.55 |
| Reversion + context | 29.10 | 32.23 | 35.03 |
| Raw LightGBM | 28.37 | 31.35 | 32.88 |
| Selected 50:50 blend | 28.33 | 30.63 | 32.14 |

The blend was **selected post-hoc on the back-test**. Raw LightGBM trust-cluster
bootstrap 95% gain intervals: **3.8–8.5% / −0.4–6.3% / 0.1–8.0%**; eight weeks
includes zero. Bootstrap uses 10,000 whole-trust draws, seed 42, and does not
capture common shocks or model selection.

Large-swings raw gains are **13.3% / 11.8% / 14.5%**, versus blend
**6.7% / 6.1% / 7.5%**. Membership uses eventual outcomes and is unknown at issue.
Blend paired-sum MAE is **1,668 / 1,890 / 1,906**, improving on naive by
**14.6% / 7.0% / 5.9%**. These varying-coverage sums are not England totals.

## Scope and reproducibility

Snapshot issue **18 October 2026**; latest source months June–August. This is
not a live feed. **Approximate: latest revised values**; first release is assumed
month+2/day14 and historical vintages are unverified. Current organisation
boundaries use retrospective merger knowledge. Core: **130 live NHS acute/specialist
cancer providers**. RVJ→RA7, RAP→RAL, RY2→RWW and RVY→RBN are harmonised;
RET/RP6 remain active. Raw source tables are preserved.

Initial simulator fits: 124/130, with 122 meeting the declared in-sample threshold;
median RMSE 6.73 patients. These errors do not validate future predictions.
Clinical review of the [ten examples](docs/bottleneck_examples.md) remains pending.

[Stage 7–8 handoff](docs/stage_8.md) · [Forecast method](docs/methodology.md) ·
[Bottleneck method](docs/bottleneck_method.md) · [Assumptions](docs/assumptions.md).

For frontend changes only: `cd web`, `npm ci`, `npm run build`. The API serves
`web/dist`; source and built assets are both included in the ZIP. Packages exclude
caches at every depth, local environments, raw downloads and secrets. The project
now exceeds one browser upload batch; use your terminal Git workflow.

Code MIT; NHS data OGL v3.0. Source URLs/hashes are bundled. HRT remains the primary
track; Gemini, Tiger Data and Vultr are later integrations.
