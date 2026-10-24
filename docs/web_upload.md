# GitHub web upload

1. Test the updated project locally (README commands).
2. For uploading, extract a **fresh copy of the delivered ZIP** into a separate
   folder. Do not upload the working folder after running Python: tests recreate
   caches and web uploads do not obey `.gitignore`.
3. Open your repository on GitHub. Remove these directories using the directory's
   top-right `…` menu -> **Delete directory** -> review -> **Commit changes**:
   - `__pycache__/`
   - `pipeline/__pycache__/`
   - `tests/__pycache__/`
   - `.pytest_cache/`
   Remove any other `__pycache__` directory too, including one under `models/`.
   Delete only these generated caches, not `pipeline/`, `tests/` or `models/`.
   Suggested cleanup message: `Remove local Python and test caches from the repo`.
4. At the repository root choose **Add file -> Upload files**. Open the freshly
   extracted `cancer-clock` folder and drag its **contents** into the upload box.
   Do not upload the ZIP or add a second enclosing `cancer-clock/` folder.
5. In Finder, press **Command + Shift + .** to show hidden files. Include
   `.gitignore` and `.env.example`; the clean ZIP contains no `.env` or `.git`.
6. Check paths such as `models/forecast.py` and `README.md`, then commit the upload.
   If your branch is protected, use the offered new-branch/pull-request flow.

Upload summary:
`Test mean reversion and machine learning against the backlog baseline`

Optional description:
`Added an interpretable reversion model, LightGBM forecasts and a separate growth
classifier. They use published history and are compared on the same future
forecast cases as the baseline. The results include error scores, uncertainty
coverage and probability calibration, so we can see which approaches help.`

Web uploads overwrite files but do **not** delete old files or respect ignore
rules. The packaged ZIP excludes caches at every depth, raw downloads, virtual
environments, node_modules and secrets. No source-code files need deletion.

Official instructions:
- https://docs.github.com/en/repositories/working-with-files/managing-files/deleting-files-in-a-repository
- https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
