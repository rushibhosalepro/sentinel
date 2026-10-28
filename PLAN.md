# SENTINEL: Master Build Plan

> **This file is the single source of truth.** Build from it, change it here first, then change code.
> Every task has an ID (e.g. `S-04`) so commits, issues and chats can refer to it.
> Background and reasoning live in [`research/`](research/README.md); this file only says **what to build, in what order, and how we know it's done.**

| | |
|---|---|
| Event | Meta Global AI Developer Hackathon: **Indie track**, theme **Push the Frontier** |
| Build window | Oct 27 → **Nov 4, 9:00 PM ET** (= **Nov 5, 6:30 AM IST**) |
| Repo | new public repo `sentinel` (fresh code only, nothing copied from Steward) |
| Plan version | **v1.7** (Oct 27, 2026) · see [Change log](#14-change-log) |

---

## 1. Goal (one sentence)

**The LLM and Sentinel decide a robot's actions together:** Muse Spark proposes *how*, Sentinel deterministically decides *whether* using a live scene graph, sends fixable feedback so the LLM can replan, and a background Meta-model learner keeps improving Sentinel's rules safely.

**Pitch:** *"The LLM decides how. Sentinel decides whether. Together they find the safe way to do what you asked."*

### Success criteria (what "done" means on Nov 4)

- [ ] Live demo URL: simulated kitchen arm, dashboard, ALLOW / ASK / BLOCK / HALT with a **Why?** path
- [ ] 3 hero scenarios work end-to-end: **knife hand-over**, **water next to laptop**, **sticky-note injection**
- [ ] LLM × Sentinel **feedback loop** repairs plans (e.g. knife turned handle-first, without asking the owner)
- [ ] **Rule learner** adds one rule live in the demo (wine glass at the edge → new rule → ASK)
- [ ] Benchmark (~100 scenarios) with the headline table: unsafe **x/N → 0/N**, task completion ≥ 95%
- [ ] Public repo, README, **3-minute demo video**, X post, submitted before the deadline

---

## 2. Architecture

```
 owner instruction (text)
        │
        ▼
 ┌─────────────┐   graph facts (JSON, no raw image)   ┌──────────────────────────┐
 │  PLANNER    │◄────────────────────────────────────│  SCENE GRAPH (+ memory)   │◄── PERCEPTION
 │ Muse Spark  │   (privileged: owner text + facts)   │ objects, people, props,   │    SAM 3.1 + depth
 └─────┬───────┘                                      │ relations, time, rules    │    (+ sim ground truth)
       │ plan: primitives + serves_instruction        └──────────▲──────▲────────┘
       ▼                                                         │      │ SceneText nodes (data only)
 ┌─────────────┐  Motion (path, held, tilt, speed,              │  ┌───┴─────────────┐
 │ MOTION GEN  │  end_state, provenance)                        │  │ QUARANTINED     │
 │ mink IK on  ├──────────────────┐                             │  │ READER Muse Spark│
 │ sim copy    │                  ▼                             │  └─────────────────┘
 └─────────────┘         ┌──────────────────┐                   │
       ▲                 │    SENTINEL      │── reads ──────────┘
       │ feedback        │ check(motion,    │
       │ (fixable only,  │  graph, rules)   │── verdict + Why path ──► DASHBOARD
       │  ≤ 3 rounds)    │ + preflight sim  │
       └─────────────────┴───┬──────────────┘
                             │ ALLOW → execute (live re-check → HALT)
                             │ ASK → owner   BLOCK → stop, no retries
                             ▼
                      EVENT LOG ──► RULE LEARNER (Muse Wonder / Muse Spark, background)
                                       └─► candidate rule ─► GATE (schema, replay, ratchet) ─► RULEBOOK vN+1
```

### Meta models used (and where)

| Role | Model | Module |
|---|---|---|
| Perception: segment + track | `sam-3.1` | `perception/` |
| Planner + replanner | `muse-spark-1.3` (bulk runs: `muse-spark-1.3-contributor`) | `planner/` |
| Planner, open-weights variant (bonus prize) | `meta-models/muse-spark-open-1026` on Baseten | `planner/` |
| Quarantined scene-text reader | `muse-spark-1.3` | `planner/reader.py` |
| Unknown-object properties | `muse-spark-1.3` structured output | `graph/` |
| Incident explanation from video | `muse-spark-1.3` video understanding | `learner/` |
| Rule writing, repair, red-team | `muse-wonder-1.0` | `learner/` |
| Baseline judge | `muse-spark-1.3`, `muse-wonder-1.0` | `bench/` |
| Coding agent while building | Muse Code | (all) |

---

## 3. Repository layout

```
sentinel/
├── PLAN.md                  ← copy of this file; keep in sync
├── README.md                ← plain-language first, then technical
├── pyproject.toml           ← uv-managed, Python 3.14
├── .env.example             ← MODEL_API_KEY, BASETEN_API_KEY, PLANNER_MODEL, ...
├── sim/
│   ├── scenes/kitchen.xml   ← MJCF: Panda + counter + objects + human hand + cameras
│   ├── scenes/props.yaml    ← semantic layer: properties, owners, people
│   ├── assets/              ← meshes/textures (licences listed in README)
│   ├── world.py             ← load, step, render rgb/depth/seg, copy state
│   ├── primitives.py        ← move_to, grasp, release, tilt, set_speed, stop
│   └── motion.py            ← plan step → Motion (dry run on a sim copy)
├── perception/
│   ├── sam.py               ← sam-3.1 calls, streaming, caching
│   ├── parse.py             ← meta-sam-parser → masks/boxes/ids/confidence
│   └── lift3d.py            ← mask + depth → 3D position/box
├── graph/
│   ├── schema.py            ← node/edge types (see §4)
│   ├── scene_graph.py       ← per-frame update, relations, time, permanence
│   └── store.py             ← in-memory (spatial) + optional FalkorDB (rest)
├── planner/
│   ├── client.py            ← Meta Model API / Baseten clients (OpenAI SDK)
│   ├── planner.py           ← privileged planner, structured output, replanning
│   ├── reader.py            ← quarantined scene-text reader
│   └── prompts/             ← prompt templates (versioned)
├── sentinel/
│   ├── rules/               ← rulebook JSON files, versioned (hard/ is read-only)
│   ├── check.py             ← check(motion, graph, rules) → Verdict
│   ├── relations.py         ← near/above/on/crosses/inside predicates
│   ├── preflight.py         ← simulate motion on a copy, detect falls/spills/contact
│   ├── feedback.py          ← fixable findings → constraints for the LLM
│   └── explain.py           ← Why? paths
├── loop/
│   ├── orchestrator.py      ← LLM × Sentinel loop (≤3 rounds), ASK/BLOCK routing
│   └── monitor.py           ← live re-check during execution → HALT
├── learner/
│   ├── events.py            ← event log
│   ├── propose.py           ← Muse Wonder rule proposals / repairs / red-team
│   ├── gate.py              ← schema → replay → preflight variants → ratchet
│   └── rulebook.py          ← versions, diff, rollback
├── bench/
│   ├── scenarios/*.yaml     ← ~100 scenarios (see research/06)
│   ├── conditions.py        ← planner-only, self-check, judge, veto-only, loop, ablations
│   ├── run.py               ← headless runner, seeds, repeats
│   └── report.py            ← RESULTS.md tables
├── server/api.py            ← FastAPI + WebSocket: frames, graph, plans, verdicts, approvals
├── web/                     ← React + Vite dashboard
├── deploy/modal_app.py      ← headless MuJoCo (MUJOCO_GL=egl) + API on Modal
└── tests/
```

---

## 4. Data contracts (keep these stable; change here first)

```python
# planner output (structured output schema)
PlanStep = {"id": str, "primitive": "move_to|grasp|release|tilt|set_speed|stop|hand_to",
            "args": dict, "serves_instruction": str, "why": str}

# sim/motion.py output, the ONE object Sentinel checks
Motion = {"body": "arm|car", "path": [[x, y, z, qw, qx, qy, qz], ...], "t": [float, ...],
          "held": [obj_id | None, ...], "tilt": [deg, ...], "speed": ["slow|normal", ...],
          "sample_steps": [str, ...],
          "end_state": [{"rel": "on|near|above|inside", "a": id, "b": id, "dist_cm": float}],
          "derived_from": instruction_id | scene_text_id, "step_ids": [str]}

# graph nodes (subset): Object{id,label,track_id,pos,bbox3d,conf,last_seen}, Person{id,role,authorised},
# BodyPart{id,kind,pos,velocity}, Property{name}, SceneText{text,pos}, Instruction{text,source}
# graph edges: HAS, OWNED_BY, ON, NEAR{dist_cm,ts}, ABOVE, INSIDE, HOLDS, WRITTEN_ON, DERIVED_FROM

# sentinel/rules/*.json
Rule = {"id": str, "when": {...}, "unless": {...}, "verdict": "ALLOW|ASK|BLOCK|HALT",
        "hard": bool, "fixable": bool, "constraint_hint": str, "reason": str,
        "origin": "handwritten|learned", "learned_from": [event_id], "version": int}

Verdict = {"kind": "ALLOW|ASK|BLOCK|HALT", "findings": [{"rule": id, "node": id, "t": float,
           "detail": str}], "why_path": [...], "feedback": [constraint, ...] | None}

Event = {"id": str, "type": "verdict|ask_answer|halt|preflight_surprise|unknown_object|false_block",
         "ts": float, "data": dict}
```

**Primitives** (the only actions the planner may use): `move_to(pose)`, `grasp(object_id)`, `release()`, `tilt(deg)`, `set_speed(slow|normal)`, `stop()`, plus the planner skill `hand_to(person)` (NOT a sim primitive: `loop/live` expands it to slow → offer 25 cm short of the hand → person reaches → wait 5 cm → release + transfer → retract → person steps back).

**Verdict order:** BLOCK > HALT > ASK > ALLOW. **A BLOCK is never approvable and never gets feedback.**

---

## 5. Build phases and tasks

Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` cut. Days are targets, not promises.

### Phase 0: Setup and day-1 check (Oct 27)
- [x] **P0-01** Create public repo `sentinel`, MIT licence, `uv init`, `.env.example`, copy this PLAN.md
- [x] **P0-02** Install `mujoco mink daqp numpy pillow imageio[ffmpeg] fastapi uvicorn openai meta-sam-parser pyyaml networkx`
- [x] **P0-03** Clone MuJoCo Menagerie (Panda) + Google Scanned Objects; record licences
- [x] **P0-04** Load Panda + table + mug + knife; render RGB/depth/seg to PNG
- [x] **P0-05** Move gripper above the mug with mink
- [x] **P0-06** Send a frame to `sam-3.1` ("mug"), parse, draw box/mask → **go/no-go for SAM on renders**
- [x] **P0-07** Phase 0 tests: `pytest` suite — scene loads + renders non-blank (`test_world.py`), IK error < 1 cm (`test_ik.py`), SAM cache replay with box+mask+confidence (`test_sam_parse.py`, skips without cache)
- **Done when:** `python -m sim.world --demo` saves a frame and an overlay with SAM's mask.

### Phase 1: Simulation, primitives, Motion (Oct 28)
- [x] **S-01** Kitchen scene: counter, ~15 objects (knife, kettle/jug, cup, laptop, pill bottle, wine glass, ...), full mocap person, sticky note texture, front (perception) + demo (wide) cameras
- [x] **S-02** `props.yaml` semantic layer (properties, owners, people/roles)
- [x] **S-03** Primitives with grasp-by-attach, tilt, speed
- [x] **S-04** `motion.py`: plan → Motion via dry run on a sim copy (`mj_copyData`)
- [x] **S-05** Scripted human paths: full person leans + reaches in at time *t* (2-bone-IK arm, hand yawed onto forearm)
- [x] **S-06** `sim/play.py`: play a scenario live in the viewer (Motion + scripted hand, pause/restart/quit, loop, `--speed`, `--record` mp4) + headless attach test
- [x] **S-07** Real hand-over: `release()` waits for the hand within 5 cm of the handle (timeout keeps holding), knife transfers to `human_hand`, robot retracts, person retreats carrying it; `knife_handover_safe` (handle-first, slow) + `knife_handover_unsafe` (blade-first) variants
- **Done when:** a hand-written plan for each hero scenario produces a Motion and plays back.

### Phase 2: Perception → scene graph (Oct 29)
- [x] **G-01** Ground-truth scene graph from simulator state (positions, relations)
- [x] **G-02** SAM 3.1 pipeline: label prompts, confidence, cache by (scene, frame, label)
- [x] **G-03** Lift to 3D with depth + intrinsics; associate SAM ids ↔ nodes; object permanence
- [x] **G-04** Relations: ON / NEAR{dist} / ABOVE / INSIDE / HOLDS with timestamps
- [x] **G-05** Person velocity + short prediction (`person_predicted`)
- [ ] **G-06** Perception accuracy vs ground truth (IoU, misses) → number for README
- **Done when:** the graph from SAM matches ground truth on the hero scenes (or the fallback is documented).

### Phase 3: Sentinel core (Oct 30)
- [x] **C-00** Recorded planner fixtures (trick/handto/apple, no network in tests)
- [x] **C-01** Rule format + hand-written rulebook v1 (`rules/hard/*.json` read-only, `rules/soft/*.json`)
- [x] **C-02** `relations.py` predicates over Motion × graph (incl. swept held object)
- [x] **C-03** `check()` → Verdict with findings + Why path
- [ ] **C-04** Uncertainty margins (clearance grows with low confidence / speed)
- [ ] **C-05** Provenance check (owner vs SceneText → BLOCK)
- [ ] **C-06** Preflight: run Motion on a copy; detect falls, spills, contact, end-state hazards
- [ ] **C-07** Unit tests for each rule with positive and negative cases
- **Done when:** the 3 hero scenarios get the expected verdicts from hand-written plans, in < 100 ms (excl. preflight).

### Phase 4: LLM × Sentinel loop (Oct 31)
- [x] **L-00** (do first) Live vertical slice: `loop/live` prompts for instructions, Muse Spark plans from GT facts, Motion builds, stub ALLOW, executes in the viewer
- [ ] **L-01** Meta Model API client + Baseten client (`muse-spark-open-1026`), retries, cost logging
- [ ] **L-02** Privileged planner: owner text + graph facts → PlanStep[] (structured output)
- [ ] **L-03** Quarantined reader: image → SceneText nodes only
- [ ] **L-04** Naive planner (sees image) for the baseline
- [ ] **L-05** `feedback.py`: fixable findings → constraints ("blade must point away", "≥ 25 cm", "slow within 30 cm")
- [ ] **L-06** Orchestrator: propose → motion → check → feedback → replan (≤ 3) → ASK / BLOCK / execute
- [ ] **L-07** Live monitor: re-check at perception rate → HALT → replan from new state
- **Done when:** "Give me the knife" ends with a handle-first hand-over **without** owner input, and the sticky note is BLOCKed with no retries.

### Phase 5: Dashboard (Nov 1)
- [ ] **D-01** FastAPI + WebSocket: frames, graph, plan, verdicts, events
- [ ] **D-02** React: camera view (+ SAM overlay via `@meta-sam/graphics`), instruction box
- [ ] **D-03** Live graph view + verdict cards + **Why?** panel (rule + origin + path)
- [ ] **D-04** Loop timeline: proposal → finding → feedback → replan → verdict
- [ ] **D-05** ASK approval UI (owner only)
- **Done when:** all hero scenarios are runnable from the browser.

### Phase 6: Rule learner (Nov 2)
- [ ] **R-01** Event log from verdicts, ASK answers, HALTs, preflight surprises, unknown objects
- [ ] **R-02** `propose.py`: Muse Wonder → candidate rules (JSON, fixed vocabulary)
- [ ] **R-03** Unknown-object properties via Muse Spark (pending owner confirmation)
- [ ] **R-04** Gate: schema → benchmark replay (unsafe must stay 0) → preflight variants → **ratchet**
- [ ] **R-05** Rulebook versions, diff, rollback; "learned from" in the Why? panel
- [ ] **R-06** (should) Red-team: Muse Wonder generates scenarios that slip past the rules
- [ ] **R-07** (should) Incident explanation from HALT/preflight video via Muse Spark
- **Done when:** the wine-glass demo produces, validates and activates a new rule live.

### Phase 7: Benchmark and baselines (Nov 2–3)
- [ ] **B-01** ~100 scenario YAMLs across categories (research/06), ≥ 30% safe controls, **labels frozen before the first run**
- [ ] **B-02** Conditions: planner-only (naive), self-check, Muse Spark judge, Muse Wonder judge, Sentinel veto-only, **LLM × Sentinel loop**, ablations (graph relations off, no preflight), SAM vs ground truth
- [ ] **B-03** Held-out split for the learner (seen vs unseen hazards)
- [ ] **B-04** Run with 3 repeats; contributor-mode models for bulk; cache everything
- [ ] **B-05** `RESULTS.md` + first-run record + "numbers that proved me wrong"
- **Done when:** the headline table is filled with real numbers.

### Phase 8: Deploy, docs, video, submit (Nov 3–4)
- [ ] **F-01** Deploy on Modal (headless MuJoCo), public URL, rate limits, daily budget
- [ ] **F-02** README: problem → demo → how it works → results → limits → licences → what was built during the hackathon
- [ ] **F-03** 3-minute demo video (script in §8), uploaded and public
- [ ] **F-04** X post with the sticky-note / knife clip; link submitted for Most Viral
- [ ] **F-05** Flag Muse Spark Open usage for the open-weights bonus
- [ ] **F-06** Submit on the CV platform; check repo + video are public
- **Done when:** submitted before **Nov 4, 9 PM ET (Nov 5, 6:30 AM IST)**; aim for Nov 4 evening IST.

---

## 6. Day-by-day schedule

| Date | Main work | Event (ET → IST) |
|---|---|---|
| Tue Oct 27 | Phase 0 | Agents 101 · 12 PM ET → 9:30 PM IST |
| Wed Oct 28 | Phase 1 | **Agents 102: Verifiable Agents** · 9:30 PM IST |
| Thu Oct 29 | Phase 2 | |
| Fri Oct 30 | Phase 3 | Fireworks workshop · 9:30 PM IST |
| Sat Oct 31 | Phase 4 | |
| Sun Nov 1 | Phase 5 | |
| Mon Nov 2 | Phase 6 + start Phase 7 | |
| Tue Nov 3 | Phase 7 + F-01, F-02 | Last day for organiser support |
| Wed Nov 4 | F-03 → F-06 | **Deadline 9 PM ET = Nov 5, 6:30 AM IST** |

Daily: Discord #office-hours 10–11 AM ET (8:30–9:30 PM IST) for blocked questions.

---

## 7. Benchmark headline (target shape)

| Condition | Unsafe executed | Task completion | Human ASKs | False blocks |
|---|---|---|---|---|
| LLM alone | x / N | high | 0 | n/a |
| LLM + self-check | | | | |
| LLM + Muse Wonder as judge | | | | |
| Sentinel veto-only | **0 / N** | lower | many | |
| **LLM × Sentinel loop** | **0 / N** | **≥ 95%** | **few** | **≈ 0** |
| + learned rules (held-out hazards) | caught ↑ | = | = | ≤ |

---

## 8. Demo video script (3:00)

| Time | Shot |
|---|---|
| 0:00–0:20 | Problem: AI now moves robots; a vague instruction, a jailbreak, a sticky note. Split screen from the explainer |
| 0:20–0:50 | Knife: LLM plans blade-first → Sentinel finding → feedback → LLM replans handle-first → ALLOW, no human needed |
| 0:50–1:15 | Water + laptop: ASK, owner approves moving the cup; Why? panel |
| 1:15–1:40 | Sticky note: naive planner obeys; Sentinel BLOCKs, no retries; provenance path |
| 1:40–2:05 | Hand enters mid-motion → HALT → replan |
| 2:05–2:30 | Rule learner: wine glass at the edge → new rule validated live → ASK "learned 2 min ago" |
| 2:30–2:50 | Benchmark table; Meta models used (SAM 3.1, Muse Spark/Open, Muse Wonder) |
| 2:50–3:00 | "The LLM decides how. Sentinel decides whether." + link |

---

## 9. Rules of the build (don't break these)

1. **Runtime decisions are deterministic.** No LLM in `check()`.
2. **BLOCK is final:** never approvable, never sent back as feedback, never loosened by the learner.
3. **Data read from the scene is never an instruction.** The planner never sees raw scene text.
4. **The learner can tighten automatically; loosening needs the owner; hard rules are read-only.**
5. **Unknown → ASK.** Unknown objects, low confidence and out-of-schema plans are never ALLOWed.
6. **New work only.** No Steward code; commit early and often so the history shows hackathon work.
7. **Freeze benchmark labels before running.** Keep the first run and the failures.
8. **Every number in the README comes from a script in `bench/`.**

---

## 10. Cut list (in this order if behind)

1. Shadow mode for learned rules
2. Red-team generation (R-06)
3. Incident video explanation (R-07)
4. Real-video "shadow mode" perception clip
5. FalkorDB (keep everything in memory)
6. Live re-check / HALT (L-07): keep only plan-time checks
7. SAM in the benchmark loop: use ground truth, show SAM in the demo only

**Never cut:** hero scenarios, the LLM × Sentinel loop, the benchmark headline, the demo video.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| SAM 3.1 weak on rendered frames | Better textures/lighting; ground-truth fallback for scoring (G-06) |
| Meta credits arrive late | Use the card + spend limit; contributor mode; aggressive caching |
| LLM latency makes the loop slow | Contributor mode for bulk; cache plans per scenario; cap rounds at 3 |
| Muse Spark Open access/limits on Baseten | Fall back to the Meta API planner; keep the bonus as optional |
| Windows/MuJoCo rendering issues | WSL2 or Modal (Linux, EGL) |
| Scope creep | This file + the cut list; change the plan before changing scope |

---

## 12. Open questions

- [ ] Which camera(s): front only, or front + top for occlusion?
- [ ] Ground-truth vs SAM for the main benchmark table (decide after G-06)
- [ ] FalkorDB or in-memory only (decide at Phase 3)
- [ ] Include the car scenario as a vision slide only? (current answer: yes, slide only)

---

## 13. Decisions log

| Date | Decision | Why |
|---|---|---|
| Oct 25 | Indie track, Push the Frontier, simulation only | Solo, no hardware, 10 days |
| Oct 26 | Name **Sentinel**; new work, broader than Steward | New-work-only rule; physical vs informational safety |
| Oct 26 | Use Meta models wherever possible | Judging: "Use of Meta AI tooling" |
| Oct 27 | One checker over a **Motion** object + rules as data | Instructions are open-ended; check motions, not words |
| Oct 27 | **LLM × Sentinel loop** with fixable feedback, ≤ 3 rounds | Safe *and* useful; Best Agentic bonus |
| Oct 27 | Background **rule learner** with gate + ratchet | Learns new hazards without an LLM in the runtime decision |
| Oct 27 | Demo robot: Franka Panda arm; cars/humanoids = vision only | Focus beats breadth |

---

## 14. Change log

| Version | Date | Change |
|---|---|---|
| v1.0 | Oct 27 | First full plan |
| v1.1 | Oct 27 | Add P0-07 (Phase 0 pytest suite) |
| v1.2 | Oct 27 | Add S-06 (scenario playback `sim/play.py` + headless attach test) |
| v1.3 | Oct 27 | S-05: full procedural person (lean, IK arm, hand orientation); split front/demo cameras |
| v1.4 | Oct 27 | Add S-07 (real hand-over with safe/unsafe variants) |
| v1.5 | Oct 27 | Add L-00 (live vertical slice, do first) |
| v1.6 | Oct 27 | Motion gains sample_steps (per-sample step ids) |
| v1.7 | Oct 27 | Planner skill hand_to (person) + people in facts |

### How to change this plan
1. Edit the relevant section (tasks, contracts, schedule, cut list).
2. Add a row to **Decisions log** if it's a design choice, and bump the version in the **Change log**.
3. New task → next free ID in its phase (e.g. `C-08`). Removed task → mark `[-]`, don't delete (keeps history).
4. Changing a **data contract** (§4)? Update it here first, then the code and its tests.

---

## 15. Reference map (`research/`)

| Need | Read |
|---|---|
| Hackathon rules, credits, judging | `00-hackathon-info.md` |
| What Sentinel is | `01-what-is-sentinel.md` |
| Scene graph + memory | `02-graph-memory.md` |
| Upgrades (preflight, CaMeL split, uncertainty, temporal rules) | `03-making-it-better.md` |
| Simulator setup | `04-simulation-stack.md` |
| Meta model IDs, SAM output, prices | `05-meta-models-cheatsheet.md` + `sources/` |
| Benchmark design | `06-benchmark-design.md` |
| One checker for any instruction | `07-one-checker-for-any-instruction.md` |
| Real robot pipeline | `08-how-real-robots-work.md` |
| Self-improving rules | `09-self-improving-rules.md` |
| Papers | `papers/INDEX.md` (41 papers) |
