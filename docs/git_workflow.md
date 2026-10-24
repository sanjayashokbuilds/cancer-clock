# GitHub checkpoints

Commit after a stage runs and its checks pass. Push that checkpoint so both team
members can recover it. Do not commit every failed install or terminal attempt.
Use the Git commands below instead of dragging environments into the web uploader.

## First checkpoint: working Stage 0

Run these in the existing, working Stage 0 folder BEFORE overlaying Stage 1:

```sh
cd ~/Downloads/cancer-clock
git --version
git init
git add .
git status --short
git commit -m "Set up the project so we can build and test it locally" -m "Added the folder structure, shared settings and a basic test. Raw downloads and local environments are excluded from Git so we can add the NHS data without uploading temporary files."
```

If `git --version` prompts for Apple's command-line tools, complete that installer
and run it again. If Git requests your identity, set your real name and the email
associated with your GitHub account using `git config user.name` and
`git config user.email`; no `--global` is needed on a shared laptop. A GitHub
privacy/no-reply address is also suitable. Do not paste credentials into chat.

Before committing, `git status --short` must not list `.venv/`, `.env` or
`data/raw/`. The project's ignore rules handle these for normal Git commands.
If an existing repository already tracks those files, stop and review it; ignore
rules do not remove files that were previously tracked.

## Link an empty GitHub repository

On GitHub, create `cancer-clock`. Leave the options for a README, license and
.gitignore unticked because those files already exist locally. Use whichever
visibility the team and event require. Copy the repository's HTTPS URL.

```sh
git branch -M main
git remote add origin YOUR_REPOSITORY_HTTPS_URL
git push -u origin main
```

Replace `YOUR_REPOSITORY_HTTPS_URL` with the actual URL before running it. Do not
run `remote add` again if `origin` already exists; inspect `git remote -v` first.
Use your configured GitHub authentication; a normal GitHub account password is
not accepted for HTTPS Git. If authentication fails, stop and share the error
without credentials. Never force-push to resolve an unexpected remote history.

If you already uploaded files through the GitHub website, the remote is not
empty. Clone that repository to a separate folder first, then overlay the new
source files there. Do not create an unrelated local history and force it over
your existing remote.

## Second checkpoint: Stage 1

Keep the working folder and overlay the ZIP contents into it. This preserves
`.git/` and `.venv/` because neither is included in the ZIP.

```sh
cd ~/Downloads
unzip -o cancer-clock-stage-1.zip -d .
cd cancer-clock
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pipeline.check
```

The processed NHS snapshot is already included. To reproduce it from the public
sources, run `.venv/bin/python -m pipeline.build --end 2026-08`. This downloads
raw files into the excluded cache and takes longer than the snapshot check.

When tests and snapshot checks pass:

```sh
git add .
git status --short
git diff --cached --stat
git commit -m "Add NHS waiting-time data so we can test backlog forecasts against real history" -m "The pipeline now combines weekly cancer backlogs, monthly cancer-wait figures and diagnostic waiting lists. It handles the older Excel releases as well as the newer CSVs, keeps missing values visible and saves an Oxford chart for a first sanity check. Publication dates are still approximate, and first outpatient attendances are labelled separately from referrals received."
git push
```

If Stage 0 was never committed, do not pretend there was an earlier checkpoint.
Initialise the repository at Stage 1 and use this Stage 1 message for the first
commit. No files need to be manually deleted for this update.

## Later checkpoints

Each next stage will come with its own tested changes and a specific message.
A good message says what now works and why it was needed. Do not claim model
accuracy, deployment or a live integration until it has actually been verified.
