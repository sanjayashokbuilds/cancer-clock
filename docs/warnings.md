# Warning review

The 44 warnings reported on the laptop were not reproduced in this environment;
their exact messages were not supplied, so they cannot be identified individually.

Before Stage 3: 29 tests passed under `python -m pytest -q -W error`.
After Stage 3: 38 tests passed under the same command, with zero warnings.
The complete model run also passed with `python -W error -m models.forecast`.
No warning filters or blanket suppression were added. Native LightGBM arrays
avoid feature-name wrapper warnings. Dependency versions are pinned.

If a warning remains on the laptop, `-W error` displays its traceback at the
cause. Keep that output for diagnosis; do not turn warnings off globally.
Mac LightGBM needs OpenMP (`brew install libomp`); failure to load it is an error,
not a model fallback. Linux was tested here; a Mac run is still needed locally.

Stage 5 compatibility fix: ZIP updates can leave `analysis/.gitkeep` and
`sim/.gitkeep` from older stages. Packaging now ignores those obsolete files,
Finder resource-fork files and `__MACOSX`, while retaining the 100-file limit.
The model checker allows floating-point roundoff (relative tolerance 1e-12,
absolute 1e-10), including bootstrap reductions that differ across numerical
libraries. Counts, decisions, report structure, release cutoffs and source
hashes remain strict. Errors identify the exact differing metric. Regression
checks cover an old-folder overlay, final-bit drift and substantive corruption;
no forecasts, model fitting or saved statistics were changed by this fix.
