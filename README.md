# Cancer Clock

Hospital-level forecasts of NHS patients still waiting beyond 62 days.
Stage 4 adds descriptive bottleneck screening and strengthens the Stage 3 review.
No personal waiting-time predictions, simulator or web app yet.

## Run locally

Python 3.11+; Mac LightGBM needs OpenMP (`brew install libomp`, once only).
From the existing `cancer-clock` folder:

```sh
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.check
.venv/bin/python -m analysis.bottleneck --check
```

Expected: **52 tests pass**, followed by successful pipeline, model/review and
bottleneck checks. Everything needed is bundled; no keys or downloads required.
First setup only: `python3.12 -m venv .venv`, then
`.venv/bin/python -m pip install -r requirements.txt`.
Windows uses `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

Rebuild the review and bottlenecks without repeating historical training:

```sh
.venv/bin/python -m models.review
.venv/bin/python -m analysis.bottleneck
```

Full model reproduction: `python -m models.forecast` (also runs the review).
Earlier stages: `python -m models.backtest`; optional source rebuild:
`python -m pipeline.build --end 2026-08`, then `python -m analysis.build_diagnostics`.
The latter rebuilds the English DM01 reference from cached full extracts.

## Forecast evidence: issue-anchored, identical cases

MAE is patients per forecast; paired cases at +4/+8/+12 weeks are
**4,446 / 4,182 / 3,919**. All results remain exploratory.

| Model | +4 weeks | +8 weeks | +12 weeks |
| --- | ---: | ---: | ---: |
| Last value | 29.98 | 32.00 | 33.91 |
| Recent trend | 52.65 | 61.12 | 72.37 |
| Partial mean reversion | 29.37 | 31.63 | 33.18 |
| Reversion + season + national trend | 28.97 | 32.07 | 34.83 |
| Original LightGBM | 28.08 | 31.15 | 32.22 |
| Published-history mean bias correction | 32.52 | 35.96 | 34.79 |
| **Fixed 50:50 LightGBM / last-value blend** | **28.09** | **30.44** | **31.73** |

Original LightGBM MAE gains are **6.3% / 2.7% / 5.0%**. Paired trust-cluster
bootstrap 95% intervals: **3.8–8.8% / −0.7–5.8% / 0.8–8.8%**.
The **8-week interval includes zero**. We resample whole trusts, retaining all
their cases, with 10,000 draws and seed 42. This handles within-trust dependence,
but not shared national shocks or retrospective model selection.

**Large swings:** where `abs(actual − last) > 30% of last`, original LightGBM
reduces MAE by **13.6% / 11.4% / 15.3%** on **1,280 / 1,313 / 1,350** paired cases.
This is our strongest slice-specific evidence. It is defined using the eventual
outcome, so we cannot identify these cases at forecast time. The selected blend's
gains on the same slice are **6.8% / 5.9% / 8.0%**; do not attribute the original
model's larger gains to the blend.

## Bias and aggregate safeguards

Mean signed error (`prediction − actual`) changes from original LightGBM's
**−0.99 / −5.72 / −9.60** to the blend's **+2.68 / +0.13 / −2.55** patients.
The expanding published-history bias correction worsened MAE and was rejected.
The blend weight is fixed, not fitted. It beats both baselines on trust MAE/MASE
at 8/12 weeks; nominal 80% interval coverage is **84.5% / 83.9% / 83.5%**.

| MAE of summed predictions over the same scored trusts | +4 weeks | +8 weeks | +12 weeks |
| --- | ---: | ---: | ---: |
| Last value | 1,964.18 | 2,026.12 | 2,018.40 |
| Original LightGBM | 1,760.94 | 2,206.16 | 2,141.94 |
| Fixed blend | 1,678.35 | 1,913.96 | 1,895.38 |

Original LightGBM is worse at 8/12 weeks; the blend improves paired-sum MAE by
**14.6% / 5.5% / 6.1%**. These sums have varying trust coverage and are not the
official England series. **National model forecasts remain withheld.**

Growth display is limited to **likely up / likely down / unclear at 4 weeks**.
No numerical growth probabilities are exported, and no growth signal is shown
at 8/12 weeks. Brier scores and reliability curves remain in the research outputs;
the categories are experimental, not calibrated confidence claims.

## Bottleneck screening

All **133 core trusts** have labels for the latest three published months,
**June–August 2026**: **54 diagnosis-limited, 4 treatment-limited, 16 mixed,
59 no clear bottleneck**. Evidence is available on both sides for 128 trusts;
two have partial evidence and three insufficient data. Missing evidence is
explicitly flagged and is not interpreted as good performance.

Inputs: FDS, seven separate DM01 test waits and 31-day performance by modality,
compared with matching England references. Scores, volumes, source periods,
strength and main drivers are exposed. DM01 includes non-cancer demand; FDS
disagreement is flagged. National No-DTT/With-DTT counts are context only.
Rules are screening assumptions, not identified causes or capacity estimates.
See [method](docs/bottleneck_method.md) and [ten examples for Rounak](docs/bottleneck_examples.md).

## Data, outputs and upload

**Approximate: latest revised values.** Release dates use the 14th of observation
month + 2. Every feature and fitted outcome must be published by issue; original
historical vintages remain unverified. April 2023 backlog history supports lags;
evaluation outcomes start October 2023. All downstream work uses the 133-trust
core list, excluding RVY and independent providers from labels and forecasts.
England diagnostic reference totals include NHS-funded independent-sector care.

Latest forecast issue: **18 October 2026**; 129 trusts have sufficient history,
four have explicit unavailable statuses. This is a bundled snapshot, not a live feed.
Results: `outputs/backtest_model.json` (including `review`), original and adjusted
prediction parquets, `forecasts_latest.json`, and `bottlenecks.json`.
Full changes and commands: [Stage 4 handoff](docs/stage_4.md).
[Terminal upload](docs/git_workflow.md) or [web upload](docs/web_upload.md).

Code: MIT. NHS data: OGL v3.0; source URLs/hashes in `docs/source_manifest.csv`.
Locations: NHS sources and postcodes.io. HRT remains primary; Gemini, Tiger Data
and Vultr integrations are planned. ElevenLabs/Delta remain optional later scope.
