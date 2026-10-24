# Stage 0 handoff

Delivered: complete repository skeleton only. No later stage is implemented.

## Files changed

All files are new. Added:

- `README.md`, `LICENSE`, `.gitignore`, `.env.example`, `requirements.txt`
- `config.py`, `pytest.ini`, `tests/test_smoke.py`
- `docs/methodology.md`, `docs/assumptions.md`, `docs/stage_0.md`
- `.gitkeep` in `data/processed/`, `data/static/`, `pipeline/`, `models/`,
  `analysis/`, `sim/`, `api/`, `web/`, `integrations/` and `outputs/`

Modified: none. Files to DELETE on GitHub: none.

Commit message: `chore: initialise Stage 0 Cancer Clock repository`

## Run and done check

Use the Windows or macOS/Linux commands in the root README. `config.py` must
print `Stage 0 skeleton ready`, and `python -m pytest -q` must report `1 passed`.
Running config creates excluded local working directories without fetching data.

Stage 0 success criteria: required structure, README, ignore rules, empty key
template, staged requirements, typed configuration, MIT license and a passing
smoke test. There are 21 source files. The ZIP excludes raw data, environments,
secrets, caches and build outputs. It is below the 100-file upload ceiling and
every included file is below 25 MB.

## Risks to resolve later

1. Estimated publication dates and latest revised values do not establish a
   fully vintage-safe historical evaluation.
2. The brief reverses the sign of publication lag when describing forecast
   lead time; see `methodology.md` for the correct time-axis calculation.
3. Total backlog alone cannot identify both stage capacities or initial queue
   ages; scenario outputs require assumptions and sensitivity checks.
4. The full 12-stage build is substantial. Real data, honest baseline evaluation
   and one explainable decision should precede optional integrations.

No clarification is required to finish Stage 0. Later methodological decisions
remain explicit rather than being silently built into a model.
