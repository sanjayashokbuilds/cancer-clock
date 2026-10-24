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
