# Terminal upload (Mac)

Run the checks first. This copies your updated project into a fresh checkout of
the existing GitHub history, then commits and pushes without rewriting history.

```sh
(
set -e
project_dir="$HOME/Documents/GITHUB/OXHACK/cancer-clock"
test -f "$project_dir/config.py"
push_dir=$(mktemp -d "$HOME/Documents/GITHUB/OXHACK/cancer-clock-push.XXXXXX")
git clone https://github.com/sanjayashokbuilds/cancer-clock.git "$push_dir"
rsync -a --exclude='.git/' --exclude='.venv/' --exclude='venv/' \
  --exclude='data/raw/' --exclude='node_modules/' --exclude='__pycache__/' \
  --exclude='.pytest_cache/' --exclude='__MACOSX/' --exclude='._*' \
  --exclude='.DS_Store' --exclude='*.pyc' --exclude='*.zip' \
  --include='.env.example' --exclude='.env*' "$project_dir/" "$push_dir/"
cd "$push_dir"
git rm -r -f --ignore-unmatch -- __pycache__ .pytest_cache \
  ':(glob)**/__pycache__/**' ':(glob)**/.pytest_cache/**' \
  analysis/.gitkeep sim/.gitkeep
git add -A
git diff --cached --stat
git commit -m "Show capacity trade-offs with uncertainty in a working dashboard" \
  -m "The simulator now varies fitted capacities as well as daily arrivals, so the ranges show more of the uncertainty. Added a dose-response view to compare diagnosis and treatment capacity, with prior conflicts and assumptions visible. The API serves precomputed results so switching hospitals and plans is immediate. The allocator and voice feature have been left out."
git push origin HEAD
)
```

If authentication or author identity is not configured, complete that setup
before retrying the commit/push. The original working folder remains intact.
