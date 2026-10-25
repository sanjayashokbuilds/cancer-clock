# Map-first demo interface

Designed for 1440×900 at 100% zoom: a dark UK basemap, one selected hospital
card, search, three map controls and four forecast stops. Oxford opens by default.
The design reference's 210→248 values are not used. All displayed numbers come
from the existing snapshot; the issue and observation dates stay explicit.

The overview is the minimum zoom and stays fixed; higher zoom permits bounded
panning. Only UK/Ireland geographic context is rendered. Reported mode uses
neutral dots; future stops show direction arrows. The card names the actual
forecast date and explains the count change in plain English.

The full animated onboarding for the voiceover recording is **still to build**.
About this demo currently opens a short explanation, not that guided tour.

## Recording route

1. Start on Oxford. Move between +4, +8 and +12 weeks, or press the outlook preview button.
2. Point out the actual backlog outlook and radiotherapy pressure. Search for
   another English hospital or select a marker; clusters reveal nearby trusts.
3. Select Test a recovery plan. With the five-day strike selected, choose
   Treatment and move capacity from 0 to 5, 10 and 20%.
4. Switch to Diagnosis to compare the limited response. Open How this works
   to show the assumptions; Evidence contains the model checks.

The direction key now follows displayed whole-person counts: estimated rise,
unchanged, estimated fall, or no forecast. A one-person rise is coral, not a
severity warning. At 4/8/12 weeks there are 3/17/32 rising rounded estimates;
all usable 80% ranges include the latest count. Model outputs are unchanged.
Cluster rims expose the mix of directions without enlarging the markers.

A larger dated forecast count, smaller reported reference, animated clock detail
and highlighted pathway make the hospital story easier to read. The map headline
is “Every week matters.” Reduced-motion preferences are respected.

Review-blocked hospitals show View planning options. That page explains the
same-date mismatch and offers Open Oxford example, explicitly switching hospital
data. The guard has not been removed and no model has been recalibrated.

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

TypeScript and the production build pass. Browser checks at 1440×900 cover the
map and recovery screen without page scrolling, exact horizon values, zoom/reset,
search by keyboard, cluster selection, missing forecasts, the RNS review guard,
capacity comparisons, combined pressures and the assumptions/Evidence views.
All 130 trusts remain reachable through 62 compact markers/clusters at the default view.
The existing data, model, simulation and API files remain unchanged.
No model was refitted and no new illustrative patient counts were introduced.
