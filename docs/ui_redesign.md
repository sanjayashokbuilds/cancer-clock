# Guided demo interface

The map, hospital panel and recovery plan are designed for 1440×900 at 100% zoom.
Use IBM Plex Sans locally, neutral panels and colour only for direction or stage.
The England boundary is real ONS geography. This is an independent tool, not an
NHS service. Sources and font licensing are in [ui_sources.md](ui_sources.md).

## Recording route

1. Open the map. Pause on the dated national count, then play the weekly history.
   The reporting gap remains visible; forecast dots are softer and outlined.
2. Find Oxford University Hospitals (RTH). Show the backlog history and forecast,
   then the treatment-stage pressure and radiotherapy evidence.
3. Select Test a recovery plan. Turn on the five-day strike, choose Treatment,
   and move extra capacity from 0 to 5, 10 and 20%. Compare the six-month totals.
4. Switch to Diagnosis: the limited response illustrates why the stage matters.
   Open How this works briefly to show the assumptions, then return to the result.

The exact grid covers all eight combinations of strike, winter pressure and
referral surge at nine capacity levels. Every displayed result comes from the
existing daily queue model with the same 256 parameter/process draws. Animation
changes presentation, not the underlying estimate. Original inputs, model code
and Stage 1–8 results are preserved.

## Outstanding section F

The request stopped after the RNS contradiction in F1. The rest of F1 and the
second requested data fix have not been supplied. Those data fixes are pending;
the recording must not be described as having completed section F.

RNS's same-date comparison confirms the issue: at 12 weeks the statistical
forecast is 144.4, while the unchanged-capacity simulator is 249.0. The latter
reaches 354.4 at six months, or 362.0 with the five-day strike. The simulator
extends fixed capacity/arrival assumptions; the forecast learns mean reversion.
A presentation-only quality guard flags a simulator median outside the forecast's
80% range at 12 weeks. It does not recalibrate either model or validate the
six-month horizon. RTH is not flagged by this check; RNS, RAL and RA7 are.

Clinical review remains pending. Neither screen predicts an individual's wait.

## Checks

122 Python tests pass with warnings treated as errors. TypeScript and the
production build pass. Browser review covered search, hospital navigation,
capacity changes, all-pressure comparisons, drawers and the RNS review state.
All three main screens fit a 1440×900 viewport without scrolling. The original
49 data/model/simulation/output files are byte-for-byte unchanged. All 130
trusts have a grid record: 124 ready and six unavailable.
