# Sentinel build progress (Phase 0)

Tracks P0-01..P0-06 against `../PLAN.md` (single source of truth).
All paths below are relative to `sentinel/` unless stated.

## Status

| Task | State | Commit | Notes |
|------|-------|--------|-------|
| P0-01 | done | P0-01 commit | uv init (requires-python >=3.14), MIT LICENSE, 12 pkgs + data dirs, README stub, .venv @ 3.14.9 |
| P0-02 | done | P0-02 commit | mujoco 3.17.0, mink 1.3.0, numpy 2.5.4, openai 3.39.0, meta-sam-parser 0.1.0; all imports verified |
| P0-03 | done | P0-03 commit | sparse-fetch franka_emika_panda (80 files, Apache-2.0); mug/knife/table are procedural primitives; panda.xml loads (12 bodies, 9 joints) |
| P0-04 | done | P0-04 commit | day1.xml (Panda + table + mug + knife + front cam + backdrop wall), world.py renders RGB/depth/seg to out/; 0 bg px; verified visually + probe |
| P0-05 | done | P0-05 commit | sim/ik.py mink+daqp IK, virtual grasp point (no site in panda.xml); target = 10 cm above mug rim, 8 iters, err 7e-06 m; out/day1_ik.png verified |
| P0-06 | todo | | perception/sam.py, SAM go/no-go |

## Log

- Oct 27, 2026: started Phase 0. Workspace quirk: agent shell runs as a
  different Windows user than the repo owner, so every `git` call needs
  `-c safe.directory=<path>` and uv needs `UV_CACHE_DIR` /
  `UV_PYTHON_INSTALL_DIR` redirected to a writable dir (see `bugs.md`).
