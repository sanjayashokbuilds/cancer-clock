# Cancer Clock

Hospital-level forecasts of NHS patients still waiting beyond 62 days, cancer
pathway bottleneck screening, and daily queue simulations for comparing plans.
Stage 5 is complete; API, website and national allocation are later stages.
Planning information, not personal waiting-time predictions.

## Run locally

Python 3.11+; Mac LightGBM needs OpenMP (`brew install libomp`, once only).
From the existing project folder:

```sh
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.check
.venv/bin/python -m analysis.bottleneck --check
.venv/bin/python -m sim.scenarios --check
```

Expected: **68 tests pass** and all snapshot checks pass. Bundled outputs need no
keys or downloads. First setup only: `python3.12 -m venv .venv`, then
`.venv/bin/python -m pip install -r requirements.txt`. Windows uses
`.venv\Scripts\python.exe`. No dependencies were added after Stage 4.

Run an editable six-plan comparison for Oxford:

```sh
.venv/bin/python -m sim.scenarios --trust RTH --strike-days 5 --extra-capacity 0.10 --start-week 4
```

Full reproduction and upload instructions: [Stage 5 handoff](docs/stage_5.md).

## Current cohort and availability

**Approximate: latest revised values.** Releases use observation month +2, day14;
historical vintages are unverified. Backlog history starts April 2023 for lags;
scored outcomes start October 2023. Features and fitted outcomes must be published
by issue, but the current organisation footprint uses retrospective merger knowledge.
This is not an as-was historical deployment test.

The core has **130 live NHS acute/specialist trusts treating cancer**. Independent
and community-only providers receive no model, label or map marker. RET (Walton)
and RP6 (Moorfields) remain active cancer providers; genuine zero queues remain zero.
Before each merger, counts are summed into the current successor and rates rebuilt:
RVJ→RA7, RAP→RAL, RY2→RWW and RVY→RBN. Retired predecessor zeros are masked, not
learned as sudden recovery. Evidence and dates: `data/static/trust_mergers.csv`;
inclusion/exclusion notes: `provider_scope.csv`. Raw source tables remain intact.

## Forecast evidence: issue anchor, identical current cases

MAE is patients per forecast. Paired cases at issue +4/+8/+12 weeks are
**4,371 / 4,113 / 3,855**. All results remain exploratory.

| Model | +4 weeks | +8 weeks | +12 weeks |
| --- | ---: | ---: | ---: |
| Last value | 30.25 | 32.32 | 34.30 |
| Recent trend | 53.07 | 61.62 | 73.17 |
| Partial mean reversion | 29.62 | 31.93 | 33.55 |
| Reversion + season + national trend | 29.10 | 32.23 | 35.03 |
| Raw LightGBM | 28.37 | 31.35 | 32.88 |
| Published-history bias correction | 32.77 | 36.15 | 35.38 |
| **50:50 LightGBM / last-value blend** | **28.33** | **30.63** | **32.14** |

The **50:50 blend was selected post-hoc on the back-test**; its fixed weight does
not make selection independent. The bias correction was rejected. Blend signed
errors are **+2.62 / +0.05 / −2.64**, versus raw **−1.30 / −6.16 / −10.10**.
Blend nominal 80% coverage is **84.8% / 84.1% / 83.5%**.

Raw LightGBM gains are **6.2% / 3.0% / 4.2%**, with paired trust-cluster bootstrap
95% intervals **3.8–8.5% / −0.4–6.3% / 0.1–8.0%**. The 8-week interval includes
zero. Bootstrap: 10,000 whole-trust draws, seed 42; shared national shocks and
model-selection uncertainty are not captured.

**Large swings**, defined after observing `abs(actual-last) > 0.30*last`, give
raw gains **13.3% / 11.8% / 14.5%**, versus blend **6.7% / 6.1% / 7.5%**, on
**1,259 / 1,287 / 1,323** cases. This is our strongest slice-specific evidence,
but these cases cannot be selected at forecast time.

| Before → after merger correction | +4 weeks | +8 weeks | +12 weeks |
| --- | ---: | ---: | ---: |
| Raw trust MAE | 28.08 → 28.37 | 31.15 → 31.35 | 32.22 → 32.88 |
| Blend trust MAE | 28.09 → 28.33 | 30.44 → 30.63 | 31.73 → 32.14 |
| Blend paired-sum MAE | 1,678.35 → 1,668.00 | 1,913.96 → 1,889.73 | 1,895.38 → 1,906.07 |
| Raw large-swing gain | 13.6% → 13.3% | 11.4% → 11.8% | 15.3% → 14.5% |

These overall comparisons change trust units/cohorts; they are not an isolated
effect estimate. On unchanged trusts and exact common cases, blend MAE changes
**27.81→27.85 / 30.17→30.13 / 31.45→31.58**. Full comparison is in the report.

Current paired-sum naive MAE is **1,953.74 / 2,031.88 / 2,026.13**; the blend
improves it **14.6% / 7.0% / 5.9%**. Raw LightGBM remains worse at 8/12 weeks.
These varying-coverage sums are not England totals; **national model forecasts
remain withheld**. Growth display is only **likely up / likely down / unclear
at 4 weeks**, without probabilities. Research Brier scores/curves remain available.

## Bottlenecks and simulation

June–August 2026: **77 diagnosis-limited, 3 treatment-limited, 17 mixed, 33 no
clear bottleneck**. Both sides are screened for 124 trusts; five have partial
and one insufficient evidence. Diagnosis drivers are cancer-specific FDS gaps;
treatment drivers are 31D modality gaps. DM01 is context only, corroborated only
by an adverse matching cancer pathway. Mixed labels expose both main drivers.
[Ten live acute examples](docs/bottleneck_examples.md) await Rounak's review.

The simulator keeps referral age in **days across both stages**. It fits 124/130
trusts; 122 meet the declared in-sample threshold. Median RMSE is **6.73 patients**
(10th–90th percentile **3.18–16.05**). Each of six plans has **256 Monte Carlo
runs**, trajectories, peaks, recovery, >104-day changes and an assumptions object.
The 29 conflicts between fitted capacity ordering and the weak bottleneck prior
are flagged. Age mix and two capacities are not jointly identified; >104-day
counts are assumption-led. Monte Carlo process ranges are not validated forecast
intervals. See [simulator method](docs/simulator_method.md).

Snapshot issue: **18 October 2026**, not a live feed; 129/130 current trust
forecasts are available. Outputs include model review/paired prediction parquets,
`forecasts_latest.json`, `bottlenecks.json`, `simulation_calibration.json` and
`simulation_examples.json`. [Forecast method](docs/methodology.md),
[bottleneck method](docs/bottleneck_method.md), [assumptions](docs/assumptions.md).

Code: MIT. NHS data: OGL v3.0; URLs/hashes in `docs/source_manifest.csv` and merger
registry. Locations: NHS sources/postcodes.io. HRT remains primary; Gemini,
Tiger Data and Vultr integrations are planned. ElevenLabs/Delta remain optional.
