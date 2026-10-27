# Third-party / environment issues encountered during the build

For Meta/third-party bugs: what broke, workaround used, and (if applicable)
a minimal repro to file upstream.

## ENV-01 (2026-10-27): uv cache dir not writable in this shell

- Symptom: any `uv` command fails with
  `Could not acquire lock ... C:\Users\rushi\AppData\Local\uv\cache\.lock:
  Access is denied. (os error 5)`.
- Cause: shell runs as user `muse-sbx-r1`, but `LOCALAPPDATA` points at the
  repo owner's profile.
- Workaround: set `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` to a writable
  dir for every uv invocation. Not a uv bug — sandbox artifact.
- Impact on repo: none; `.venv/` stays project-local per uv convention.

## ENV-02 (2026-10-27): git "dubious ownership" in this shell

- Symptom: `git -C sentinel status` → `fatal: detected dubious ownership`.
- Cause: same user mismatch as ENV-01.
- Workaround: prefix git calls with
  `git -c safe.directory=D:/projects/hackathons/meta/sentinel`.
- Impact on repo: none.

## ENV-03 (2026-10-27): `uv python install` warnings + interpreter location

- Symptom: `uv python install 3.14` prints warnings
  "Failed to create Python executable link" and "Failed to create registry
  entry" (both Access denied), and a 3.15.1 install under the sandbox temp
  dir failed to launch (`0xc06d007e`, DLL load failure).
- Cause: sandbox user has no registry/symlink rights; temp-dir DLL loading
  appears restricted.
- Workaround: install with `UV_PYTHON_INSTALL_DIR=sentinel/.uv-python`
  (workspace, git-ignored). Interpreter runs fine there (3.14.9 verified).
- Impact on repo: `.uv-python/` is git-ignored. The human owner should run
  `uv sync` with their own Python 3.14 — the committed `.venv/`-less tree
  plus `pyproject.toml`/`uv.lock` recreates cleanly. Not a uv bug.

## ENV-04 (2026-10-27): `warning: Failed to set cwd to temp dir`

- Symptom: venv python prints `warning: Failed to set cwd to temp dir`
  on startup.
- Cause: `TEMP` points at the repo owner's (unreadable) profile dir.
- Impact: cosmetic so far; `tempfile` users may need `TMPDIR` redirected.
  Sandbox artifact, not a repo issue.
