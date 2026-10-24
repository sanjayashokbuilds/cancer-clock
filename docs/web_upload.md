# Uploading Stage 8

The project now has more than 100 files. Use the [terminal workflow](git_workflow.md)
to upload the complete project in one commit.

For browser uploads, extract a fresh Stage 8 ZIP, show hidden files in Finder
(Command + Shift + .), and upload its contents at the repository root in batches
of at most 100 files. Include `web/dist`, which contains the ready-to-run app.
Do not upload Python caches, local environments or `web/node_modules`.

Delete any previously committed `__pycache__` and `.pytest_cache` directories
at every depth, plus `analysis/.gitkeep` and `sim/.gitkeep` if present. Use the
file/directory's … menu. Uploads do not delete older files automatically.

Commit message: `Show capacity trade-offs with uncertainty in a working dashboard`.

Description: `The simulator now varies fitted capacities as well as daily arrivals,
so the ranges show more of the uncertainty. Added a dose-response view to compare
diagnosis and treatment capacity, with prior conflicts and assumptions visible.
The API serves precomputed results so switching hospitals and plans is immediate.`
