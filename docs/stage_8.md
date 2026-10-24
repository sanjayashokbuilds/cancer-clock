# Stage 7–8 handoff

This records the original Stage 8 release. For the redesigned interface and
recording status, see [the guided demo handoff](ui_redesign.md).

Built the FastAPI API and React/TypeScript decision dashboard. Stage 6 allocator
and Stage 11 voice are skipped. The project runs locally from one Python server;
compiled frontend assets and all precomputed outputs are bundled.

## Start

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000; interactive API docs are at /docs. No Node install is
needed unless editing the frontend. Development rebuild: `cd web`, `npm ci`,
`npm run build`. Existing model results are preserved.

## Decision contract

Final snapshot: 130 trusts, 124 ready and six unavailable; 29 prior conflicts.
For strike +10% treatment at day 182, range widths change as follows:

| Trust | Process-only width | Combined width | Ratio |
| --- | ---: | ---: | ---: |
| RTH | 20.01 | 45.78 | 2.29× |
| RAL | 16.34 | 38.52 | 2.36× |
| RA7 | 263.92 | 447.08 | 1.69× |

Median ratio is 2.91× across 120 nonzero denominators; four are undefined and
one range narrows slightly. RTH's paired near-zero treatment benefit is 8.67
fewer overdue patients per +1 percentage point; diagnosis has negligible effect.

All current core trusts have explicit ready/unavailable status. Curves compare
0, 1, 2, 3, 4, 5, 10, 15 and 20% extra capacity in either stage at day 182,
with 256 paired draws. The default is a five-day strike starting day 28, with
permanent extra capacity from the same day. Near-zero benefit is the paired
0-to-5% reduction divided by five, with its own 10–90% sensitivity range.

Joint capacity draws use a local residual-block bootstrap and nonlinear fit
screening; weak directions vary within explicit original bounds. Each draw
replays calibration. Parameter and process draws are shared across plans.
The resulting range is conditional on age mix, conversion, queue split and
service order; it is not complete structural uncertainty or a validated forecast.
See [method and widening results](uncertainty.md).

RTH uses a radiotherapy stage-proxy label because of its adverse 31D driver.
This does not turn whole-stage capacity into measured radiotherapy staffing.
RAL's prior conflict and all poor-fit flags are visible. Clinical review remains
pending. No personal waiting-time probabilities or national model forecasts.

## API and instant responses

GET `/api/trusts`, `/api/trust/{code}/forecast`, `/bottleneck`, `/history`,
`/decision`, `/api/backtest`, `/api/national`; `/health` reports snapshot hashes.
POST `/api/simulate` accepts a current trust, preset scenario, stage and cached
capacity percentage. Baseline, strike, winter and referral-surge trajectories are
precomputed, as are the strike with +10% in each stage. Other grid doses return
their six-month endpoint explicitly; trajectories are not invented. Unsupported
combinations return 422, retired codes 404, unavailable simulations 409.

The API checks cohort, issue dates and source hashes at startup, then reads
immutable cached results. All assumptions accompany scenario results. Historical
completed-wait distributions are labelled separately from the unobserved queue age mix.

## Reproduce and package

Validation: 90 Python tests pass with warnings as errors; TypeScript and the
production frontend build pass. All 130 real decision endpoints were checked.
Sampled local API responses took about 3–9 ms after a 4.3-second startup;
these measurements exclude network latency. Interactive browser QA could not
run because the managed preview service lacks the Python API dependencies.

```sh
.venv/bin/python -m sim.decisions --workers 4
.venv/bin/python -m sim.decisions --check
.venv/bin/python scripts/package_repo.py
```

The ZIP contains source plus `web/dist`, excludes caches at every depth, and
omits `analysis/.gitkeep` and `sim/.gitkeep`. There are now more than 100 files:
use the terminal Git workflow or split browser uploads into batches. Source
data and the original Stage 5 process-only experiments remain available.
