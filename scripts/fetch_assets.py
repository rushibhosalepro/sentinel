"""Fetch third-party MuJoCo assets into sim/assets/ (git-ignored).

P0-03: downloads only `franka_emika_panda` from google-deepmind/mujoco_menagerie
via a sparse git checkout. The day-1 mug/knife/table are procedural primitives
defined in sim/scenes/day1.xml, so no other downloads are needed.

Usage:
    uv run python scripts/fetch_assets.py [--force]
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

MENAGERIE_URL = "https://github.com/google-deepmind/mujoco_menagerie.git"
MODEL_DIR = "franka_emika_panda"
PANDA_XML = "panda.xml"

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "sim" / "assets"
DEST_DIR = ASSETS_DIR / "mujoco_menagerie"


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def fetch(force: bool = False) -> Path:
    panda_xml = DEST_DIR / MODEL_DIR / PANDA_XML
    if panda_xml.exists() and not force:
        print(f"Already present: {panda_xml} (use --force to re-fetch)")
        return panda_xml
    if DEST_DIR.exists():
        print(f"Removing existing {DEST_DIR}")
        # Windows: git pack files may be briefly locked (indexer/AV); retry
        # a few times, clearing read-only bits on failure.
        def _onerror(func, path, _exc):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        for attempt in range(5):
            try:
                shutil.rmtree(DEST_DIR, onerror=_onerror)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(2)
    try:
        run(["git", "--version"], capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.exit("error: git is required to fetch assets (Git Bash ships it).")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    # On Windows, force the OpenSSL backend: schannel can fail without a
    # user credential store (e.g. service/sandbox accounts), OpenSSL works
    # everywhere. Ignored on platforms with a single TLS backend.
    backend = ["-c", "http.sslBackend=openssl"] if os.name == "nt" else []
    run([
        "git", *backend, "clone", "--depth", "1", "--filter=blob:none",
        "--sparse", MENAGERIE_URL, str(DEST_DIR),
    ])
    run(["git", "-C", str(DEST_DIR), *backend, "sparse-checkout", "set",
         "--skip-checks", MODEL_DIR, "LICENSE"])
    if not panda_xml.exists():
        sys.exit(f"error: expected {panda_xml} after checkout, not found.")
    n_meshes = sum(1 for p in (DEST_DIR / MODEL_DIR).rglob("*") if p.is_file())
    print(f"Fetched {MODEL_DIR} ({n_meshes} files) -> {DEST_DIR / MODEL_DIR}")
    return panda_xml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="delete and re-fetch even if present")
    args = parser.parse_args()
    fetch(force=args.force)


if __name__ == "__main__":
    main()
