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
| P0-06 | done | P0-06 commit | perception/sam.py streaming SAM-3.1, 1 box + 1 mask, confidence 0.84 → GO; overlay + cache verified |
| P0-07 | done | P0-07 commit | pytest 9.1.1 (--dev); 5 tests pass in ~9 s (world, ik, sam replay) |
| S-01 | done | S-01 commit | kitchen.xml: Panda + counter + 10 free props + sticky + mocap hand (user's palm/fingers/sleeve) + front/top cams; wine at edge, exposure tamed; stable, both views verified |
| S-02 | done | S-02 commit | props.yaml (11 objects + owner/visitor); 2-way existence test vs free bodies; 7 passed |
| S-03 | done | S-03 commit | primitives.py (6 actions, kinematic rollout, honest failures); ik.py gains solve_pose; 7 passed |
| S-04 | done | S-04 commit | motion.py plan→Motion on sim copy (AABB end_state); knife_handover demo + strip; 11 passed |
| S-05 | done | S-05 commit | human.py reach/retreat mocap scripts (eased, no teleports); reach strip verified; 14 passed |
| G-01 | done | G-01 commit | schema.py + scene_graph.py GT builder (MultiDiGraph, AABB relations, ts everywhere); geometry.py shared w/ motion; 19 passed |
| G-02 | done | G-02 commit | sweep.py 12-label SAM sweep + sheet; 5 clean hits, 2 wording fixes (knife, white plate), 4 hard misses; 19 calls cached |

## Log

- Oct 27, 2026: started Phase 0. Workspace quirk: agent shell runs as a
  different Windows user than the repo owner, so every `git` call needs
  `-c safe.directory=<path>` and uv needs `UV_CACHE_DIR` /
  `UV_PYTHON_INSTALL_DIR` redirected to a writable dir (see `bugs.md`).
