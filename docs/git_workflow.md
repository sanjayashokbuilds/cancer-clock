# Terminal update and push (Mac)

Download `cancer-clock-stage-4.zip` into Downloads. This merges the delivered
files into your existing folder and preserves `.git` and `.venv`:

```sh
(
set -e
unzip -o "$HOME/Downloads/cancer-clock-stage-4.zip" -d "$HOME/Documents/GITHUB/OXHACK"
cd "$HOME/Documents/GITHUB/OXHACK/cancer-clock"
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.check
.venv/bin/python -m analysis.bottleneck --check
)
```

Expect 52 tests and all three checks to pass. Dependencies are unchanged from
Stage 3. The review and bottlenecks are already bundled; no retraining needed.

Push **after those checks succeed**, from the same repository:

```sh
(
set -e
cd "$HOME/Documents/GITHUB/OXHACK/cancer-clock"
git rm -r --cached --ignore-unmatch -- \
  ':(glob)**/__pycache__/**' \
  ':(glob)**/.pytest_cache/**'
git add README.md config.py analysis models pipeline tests docs outputs scripts \
  data/processed/dm01_bottleneck_reference.parquet
git diff --cached --stat
if ! git diff --cached --quiet; then
  git commit \
    -m "Add bottleneck checks and temper the longer-range backlog forecasts" \
    -m "The longer forecasts tended to come in low, so they now split the difference with the last known backlog. This reduced errors for trusts and for their combined totals. The report keeps the original model results, including the large swings where it helped most. Added diagnosis and treatment signals with the underlying volumes, and ten hospitals for Rounak to check."
fi
git pull --rebase origin main
git push -u origin main
git status
)
```

This assumes the existing `origin` points to your `sanjayashokbuilds/cancer-clock`
repository. Success ends with an up-to-date branch and clean working tree.
If a command fails or a rebase reports conflicts, the block stops: keep that
output and resolve it before retrying. Do not force-push.

No source files need deletion. Cache removal only untracks generated files;
Python can keep using the local caches. For web uploads, use `web_upload.md`.
