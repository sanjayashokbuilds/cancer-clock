# GitHub web upload

1. Run the README checks in your local project. No git CLI is needed.
2. Extract a **fresh copy of cancer-clock-stage-5.zip** into a separate upload
   folder. Python tests recreate caches; upload this fresh copy, not the tested
   working folder.
3. On [your repository](https://github.com/sanjayashokbuilds/cancer-clock), remove
   any old cache directories using the directory's top-right **… → Delete
   directory → Commit changes**. Check `__pycache__/`, `pipeline/__pycache__/`,
   `tests/__pycache__/`, `models/__pycache__/`, `analysis/__pycache__/`,
   `sim/__pycache__/` and `.pytest_cache/`; delete matching caches at any depth.
   If absent, skip them. Keep their parent source folders.
4. Delete only these obsolete placeholder files if present: `analysis/.gitkeep`
   and `sim/.gitkeep` (open each, **… → Delete file**). Web upload does not
   remove files missing from the new ZIP.
5. At the repository root choose **Add file → Upload files**. Drag the **contents**
   of the freshly extracted `cancer-clock` folder into the upload box. Do not
   upload the ZIP itself or nest another `cancer-clock/` folder.
6. Finder **Command + Shift + .** reveals hidden files; include `.gitignore` and
   `.env.example`. Check paths such as `sim/simulator.py` and `README.md`.
   Use the message below, then **Commit changes** (or propose a new branch/PR
   if your repository requires it).

Cleanup message: `Remove generated Python caches and unused placeholder files`.

Upload commit message:

```text
Join merged hospital histories and add daily recovery-plan simulations
```

Optional description:

```text
The Bristol and Royal Free mergers were making ordinary changes look like
backlog jumps. Their older counts now include the hospitals that joined them,
and the forecasts have been rerun. Diagnosis labels now follow the relevant
cancer pathways, with routine diagnostic waits kept as context. Added a daily
two-stage simulator to compare extra diagnosis and treatment capacity, with
fit errors and assumptions shown. The ten hospital examples still need
Rounak's clinical review.
```

The complete ZIP has 100 files, each below 25 MB. It excludes caches at every
depth, raw downloads, virtual environments and secrets. Web upload ignores
`.gitignore`, so use the supplied clean ZIP.

Official guidance: [upload files](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository),
[delete files/directories](https://docs.github.com/en/repositories/working-with-files/managing-files/deleting-files-in-a-repository).
