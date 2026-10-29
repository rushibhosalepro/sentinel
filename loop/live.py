"""Live vertical slice: type an instruction, Muse Spark plans, robot acts. (L-00)

Opens the kitchen in a viewer, then loops: read an instruction from the
terminal, plan it with Muse Spark from ground-truth facts (no image),
validate, dry-run the Motion, pass Sentinel, preview the path, and execute.

Planning + rollout run in a background thread; the main thread only renders
(60 fps), steps execution, and updates the overlay, so the viewer never
freezes while the model thinks. Plans containing hand_to execute as
segments: plain primitive runs plus live hand-overs (loop/handover.py).

Usage:
    uv run python -m loop.live
    uv run python -m loop.live --instruction "..." --record out/live.mp4

Keys: F1 = person reaches in (random), F2 = toggle camera, F5 = reset,
Esc = quit.
"""

from __future__ import annotations

import argparse
import queue
from collections import deque
import random
import threading
import time
import uuid

import mujoco
import numpy as np

from graph.scene_graph import load_props
from learner import events as learner_events
from loop.handover import build_execution_script, step_handover
from loop.feedback import (MAX_REPLAN_ROUNDS, constraints_for,
                           format_error_note, format_replan_note,
                           has_hard_finding, should_replan)
from loop.monitor import CLEAR_S, MONITOR_DT_S, check_halt, rule_params
from planner.planner import plan_from_content, plan_instruction, scene_facts
from sentinel.check import check
from sentinel.graph_view import graph_snapshot
from sim.primitives import free_qposadr
from sim.human import (HANDOVER_HOVER, park_pos, reach_to_counter,
                       step_f6)
from sim.play import HAND_BODY, REACH_DURATION, drag_with_hand
from sim.world import RENDER_LOCK, load_scene

KEY_F1 = 290  # GLFW physical keys (no letters: safe while typing)
KEY_F2 = 291
KEY_F3 = 292
KEY_F4 = 293
KEY_F5 = 294
KEY_F6 = 295
KEY_ESC = 256

FPS = 60
SETTLE_T = 0.5  # hold the final frame briefly after executing
PREVIEW_T = 1.0  # path-preview dwell before executing (s)
PREVIEW_MAX = 40  # path markers
PROMPT = "instruction> "

ORB_POS = (1.0, 0.35, 0.9)  # status orb: verdict colour in the scene
ORB_R = 0.03
ORB_IDLE = (0.45, 0.45, 0.45, 1.0)
ORB_COLORS = {"ALLOW": (0.2, 0.9, 0.2, 1.0),
              "ASK": (1.0, 0.65, 0.1, 1.0),
              "BLOCK": (0.95, 0.15, 0.15, 1.0),
              "HALT": (0.95, 0.15, 0.15, 1.0)}
PATH_RGBA = (0.2, 0.85, 0.9, 1.0)
TARGET_RGBA = (1.0, 0.45, 0.1, 1.0)
_IDENT = np.eye(3).flatten()


def _set_sphere(g, pos, r, rgba) -> None:
    mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_SPHERE,
                        np.array([r, r, r]), np.asarray(pos, dtype=float),
                        _IDENT, np.asarray(rgba, dtype=float))


def _draw_orb(viewer, rgba) -> None:
    scn = viewer.user_scn
    _set_sphere(scn.geoms[0], ORB_POS, ORB_R, rgba)
    if scn.ngeom < 1:
        scn.ngeom = 1


def _show_preview(viewer, model, data, motion, steps) -> None:
    scn = viewer.user_scn
    pts = motion["path"]
    picks = np.linspace(0, len(pts) - 1, min(len(pts), PREVIEW_MAX))
    k = 1  # geom 0 is the status orb
    for i in (round(v) for v in picks):
        _set_sphere(scn.geoms[k], pts[int(i)][:3], 0.008, PATH_RGBA)
        k += 1
    for s in steps:
        if s["primitive"] == "grasp":
            obj = data.xpos[model.body(s["args"]["object_id"]).id]
            _set_sphere(scn.geoms[k], obj, 0.02, TARGET_RGBA)
            k += 1
            break
    scn.ngeom = k


def _clear_preview(viewer) -> None:
    viewer.user_scn.ngeom = 1  # keep the status orb


def _step_arg(s: dict) -> str:
    args = s["args"]
    if "pose" in args:
        xyz = [f"{v:.2f}" for v in args["pose"][:3]]
        return "[" + ", ".join(xyz) + "]"
    if "object_id" in args:
        return str(args["object_id"])
    if "person" in args:
        return str(args["person"])
    if "deg" in args:
        return f"{args['deg']} deg"
    if "speed" in args:
        return str(args["speed"])
    return ""


def _overlay_text(st: dict) -> str:
    lines = [f"Instruction: {st['instruction'] or '-'}"]
    if st.get("perception") == "sam":
        lines.append("perception: SAM 3.1")
        conf = st.get("perceive_conf") or {}
        if conf:
            lows = sorted(k for k, v in conf.items() if v < 0.5)
            detail = f"min {min(conf.values()):.2f} ({len(conf)} objects)"
            if lows:
                detail += f" LOW: {', '.join(lows[:3])}"
            lines.append(f"conf: {detail}"[:64])
    phase = st["phase"]
    if phase == "planning":
        lines.append(f"Muse Spark planning... "
                     f"{time.perf_counter() - st['plan_start']:.0f} s")
    elif phase == "preview":
        lines.append("previewing path...")
    elif phase == "executing":
        n = len(st["script"]) if st["script"] else 0
        lines.append(f"executing... (segment {st['seg_i'] + 1}/{n})")
    elif phase == "halt":
        h = st.get("halt") or {}
        lines.append(f"HALT: person_in_path "
                     f"({h.get('dist', 0.0) * 100:.0f} cm)")
        if h.get("clear_since") is not None:
            lines.append(f"  clear {h.get('clear_for', 0.0):.1f} s / "
                         f"{CLEAR_S:.0f} s")
        else:
            lines.append("  waiting for clear...")
    elif phase == "done":
        lines.append("Done")
    elif phase == "error":
        lines.append(str(st["error"])[:70])
    else:
        lines.append("idle - type an instruction")
    if st.get("queued"):
        lines.append(f"queued ({st['queued']})")
    if st["steps"]:
        ids = [s["id"] for s in st["steps"]]
        try:
            at = ids.index(st["current"])
        except ValueError:
            at = 0
        lo = max(0, min(at - 3, len(ids) - 7))
        for s in st["steps"][lo:lo + 7]:
            mark = ">" if s["id"] == st["current"] else " "
            lines.append(f"{mark} {s['id']} {s['primitive']} "
                         f"{_step_arg(s)}"[:64])
        if len(ids) > 7:
            lines.append(f"  ... +{len(ids) - 7} more")
    if st["verdict"] is not None:
        lines.append(f"Sentinel: {st['verdict']['kind']}")
        for t in (st.get("trace") or [])[-2:]:
            lines.append(f"  {t}"[:64])
        for f in st["verdict"]["findings"][:3]:
            lines.append(f"  ! {f['rule']}: {f['detail']}"[:64])
    return "\n".join(lines)


def _print_plan(steps: list[dict]) -> None:
    for s in steps:
        args = s["args"]
        if "pose" in args:
            shown = {"pose": [round(float(v), 3) for v in args["pose"]]}
        else:
            shown = args
        print(f"  {s['id']} {s['primitive']} {shown}  # {s['why']}")


def _closest_approach(motion: dict, graph: dict) -> dict:
    """Min held-gap per hazard class (R-01: lets Wonder calibrate).

    One sweep over held samples; None per class when empty-handed or
    no such target exists. Rounded to mm: telemetry, not evidence.
    """
    from sentinel import relations as R

    out = {"fragile_cm": None, "fragile_obj": None,
           "electronic_cm": None, "electronic_obj": None,
           "person_cm": None, "person": None}
    for i in range(len(motion["t"])):
        if motion["held"][i] is None:
            continue
        m = R.measure_held_object_property(motion, graph, i, ["fragile"])
        if m is not None and (out["fragile_cm"] is None
                              or m["gap_cm"] < out["fragile_cm"]):
            out["fragile_cm"] = round(m["gap_cm"], 1)
            out["fragile_obj"] = m["near"]
        m = R.measure_held_electronic(motion, graph, i)
        if m is not None and (out["electronic_cm"] is None
                              or m["gap_cm"] < out["electronic_cm"]):
            out["electronic_cm"] = round(m["gap_cm"], 1)
            out["electronic_obj"] = m["electronic"]
        m = R.measure_held(motion, graph, i)
        if m is not None and (out["person_cm"] is None
                              or m["gap_cm"] < out["person_cm"]):
            out["person_cm"] = round(m["gap_cm"], 1)
            out["person"] = m["person"]
    return out


def _motion_summary(motion: dict) -> str:
    t = motion["t"]
    return (f"Motion: {len(t)} samples over {t[-1]:.2f} s, "
            f"held={motion['held'][-1]}, "
            f"{len(motion['end_state'])} end relations")


def _step_person(model, data, person: dict, now: float | None = None,
               dt: float = 0.0) -> None:
    if not person["active"]:
        return
    now = time.perf_counter() if now is None else now
    if person.get("f6") is not None:
        if step_f6(model, data, person["f6"], dt):
            person.update(active=False, f6=None)
    else:
        elapsed = now - person["t0"]
        reach_to_counter(model, data, elapsed, 0.0, REACH_DURATION,
                         person["target"], face=person["face"],
                         origin=person["origin"])
    if person["carrying"] is not None:
        drag_with_hand(model, data, person["carrying"]["obj"],
                       person["carrying"]["offset"])


def _restore(model, data, home: dict, person: dict) -> None:
    data.qpos[:] = home["qpos"]
    data.mocap_pos[:] = home["mocap_pos"]
    data.mocap_quat[:] = home["mocap_quat"]
    data.time = 0.0
    person.update(active=False, target=HANDOVER_HOVER, face=None,
                  origin=None, carrying=None, f6=None)
    mujoco.mj_forward(model, data)


def _motion_path(motion: dict, findings: list,
                 max_points: int = 200) -> dict:
    """Top-down gripper path + the points near a finding's t (graph tab)."""
    n = len(motion["path"])
    stride = max(1, n // max(1, max_points))
    idx = list(range(0, n, stride))
    if idx and idx[-1] != n - 1:
        idx.append(n - 1)
    pts = [[float(motion["path"][i][0]), float(motion["path"][i][1])]
           for i in idx]
    fire_t = [f["t"] for f in findings]
    fires = [p for i, p in zip(idx, pts)
             if any(abs(motion["t"][i] - ft) <= 0.25 for ft in fire_t)]
    return {"points": pts, "fires": fires}


def _error_entry(attempt: int, model_name: str, t0: float, n_steps: int,
                 err: str, latency: float | None = None) -> dict:
    """rounds_log entry for a round that died before a verdict (D-04)."""
    if latency is None:
        latency = round(time.perf_counter() - t0, 1)
    return {"round": attempt, "kind": "ERROR", "rules": [],
            "findings": [], "feedback": None, "why": None,
            "graph": None,
            "proposal": {"model": model_name, "latency_s": latency,
                         "n_steps": n_steps},
            "feedback_note": None, "error": err}


ASK_TIMEOUT_S = 60.0


def ask_question(verdict: dict) -> str:
    """The question a final ASK puts to the owner (D-05)."""
    details = "; ".join(f["detail"] for f in verdict.get("findings", []))
    if not details:
        return "Allow the motion?"
    return f"Allow the motion? ({details})"


def decide_ask(verdict: dict, round_no: int, ask_handler, emit,
               timeout: float = ASK_TIMEOUT_S) -> tuple[str, str]:
    """Emit the ask event and wait for the owner. Returns (ask_id, decision).

    decision is "approve" or "deny"; a timeout (or anything unrecognised)
    is a deny. ask_handler is the dashboard's registry (pre_register/wait).
    """
    from dashboard.events import ask_event

    ask_id = f"ask-{uuid.uuid4().hex[:8]}"
    ask_handler.pre_register(ask_id)
    emit(ask_event(ask_id, round_no, ask_question(verdict),
                   verdict.get("findings", [])))
    print(f"Sentinel: ASK {ask_id} (round {round_no}), waiting up to "
          f"{timeout:.0f} s for the owner")
    decision = ask_handler.wait(ask_id, timeout=timeout)
    if decision != "approve":
        if decision is None:
            print(f"Sentinel: ASK {ask_id} timed out, denying")
        decision = "deny"
    return ask_id, decision


def _planner_worker(model, jobs: queue.Queue, results: queue.Queue) -> None:
    """Background thread: perceive -> propose -> motion -> check -> replan.

    Retries ASK and SOFT-BLOCK verdicts with fixable feedback, plus
    invalid plans and build errors (error text as feedback); never
    retries a verdict with a hard finding. Max 3 rounds. Records the
    round trace for the overlay. A job may carry rounds/trace to
    continue numbering after a HALT replan (fresh plan, no feedback).
    A job with a captured "frame" runs G-09 perception first (sam
    mode): facts positions and the checker graph come from the frame,
    and low-confidence targets ASK via the unknown_object rule.
    """
    while True:
        job = jobs.get()
        if job is None:
            return
        note = None
        rounds = job.get("rounds", 0)
        trace: list[str] = list(job.get("trace", []))
        rounds_log: list[dict] = []  # D-01: per-round verdict records
        # L-03 hardening: quarantine every frame we see (sam runs
        # read the live frame; attack runs read the staged one).
        # --attack keeps ONLY the "planner sees the note" simulation.
        read_path = job.get("attack_frame")
        if read_path is None and job.get("frame") is not None \
                and "quarantine" not in job:
            read_path = job["frame"]["path"]
        attack_ctx = None
        if read_path is not None:
            from loop.quarantine import attack_note
            try:
                job["quarantine"] = _read_quarantine(
                    model, job["data"], job["props"], read_path)
            except Exception as e:  # noqa: BLE001 - reported, never raised
                trace.append("quarantine: ERROR reader error")
                results.put({"gen": job["gen"],
                             "error": f"reader error: {e}", "trace": trace,
                             "rounds_log": rounds_log})
                continue
            for o in job["facts"]["objects"]:
                o["has_text"] = o["id"] in job["quarantine"]
            if job["quarantine"]:
                trace.append("quarantine: " + ", ".join(
                    sorted(job["quarantine"])) + " has text on it")
                if job.get("attack_frame"):
                    # Attack context persists across replan rounds (a
                    # VLM's context does); the round note follows it.
                    attack_ctx = attack_note(job["quarantine"])
        conf_summary = None
        if "frame" in job:  # --perception sam: see before thinking
            from perception.perceive import perceive_frame
            try:
                out = perceive_frame(
                    model, job["data"], job["frame"]["frame"],
                    job["frame"]["path"], job["props"])
            except Exception as e:  # noqa: BLE001 - reported, never raised
                trace.append("perception: ERROR")
                results.put({"gen": job["gen"],
                             "error": f"perception error: {e}",
                             "trace": trace, "rounds_log": rounds_log})
                continue
            objs = [o for o in job["facts"]["objects"]
                    if o["id"] in out["positions"]]
            for o in objs:
                o["pos"] = [round(float(v), 3)
                            for v in out["positions"][o["id"]]]
            job["facts"]["objects"] = objs
            job["perceived"] = out["perceived"]
            conf_summary = {k: round(v["conf"], 2)
                            for k, v in out["perceived"].items()}
            n_unknown = sum(k.startswith("unknown")
                            for k in conf_summary)
            trace.append(f"perception: SAM 3.1 ({len(objs)} objects"
                         + (f", {n_unknown} unknown" if n_unknown else "")
                         + f", min conf {min(conf_summary.values()):.2f})")
            print(f"perceived {len(objs)} objects "
                  f"(min conf {min(conf_summary.values()):.2f})")
        while True:  # replan loop
            attempt = rounds + 1
            model_name = job.get("model") or "spark"
            t0 = time.perf_counter()
            try:
                round_note, system = note, None
                if attack_ctx:
                    from planner.planner import SYSTEM_PROMPT_UNPATCHED
                    round_note = attack_ctx if note is None \
                        else f"{attack_ctx}\n\n{note}"
                    system = SYSTEM_PROMPT_UNPATCHED
                content = plan_instruction(job["instruction"], job["facts"],
                                           model=job.get("model"),
                                           note=round_note,
                                           system_prompt=system)
            except Exception as e:  # noqa: BLE001 - reported, never raised
                err = f"planner error: {e}"
                trace.append(f"Round {attempt}: ERROR planner error")
                rounds_log.append(_error_entry(
                    attempt, model_name, t0, 0, err))
                results.put({"gen": job["gen"], "error": err,
                             "trace": trace, "rounds_log": rounds_log})
                break
            latency = round(time.perf_counter() - t0, 1)
            steps, err = plan_from_content(content, job["valid_ids"],
                                           job["valid_people"])
            if err is not None:
                err = f"invalid plan: {err}"
                entry = _error_entry(attempt, model_name, t0, 0, err,
                                     latency=latency)
                rounds_log.append(entry)
                if rounds >= MAX_REPLAN_ROUNDS:
                    trace.append(f"Round {attempt}: ERROR {err}"[:80])
                    results.put({"gen": job["gen"], "error": err,
                                 "trace": trace, "rounds_log": rounds_log})
                    break
                rounds += 1
                note = format_error_note(err, attempt)
                entry["feedback_note"] = note
                trace.append(f"Round {attempt}: ERROR {err}"[:80])
                trace.append(f"feedback: {err}"[:80])
                print(f"replan round {rounds}/{MAX_REPLAN_ROUNDS}: {err}")
                continue
            script, err = build_execution_script(
                model, job["data"], steps, job["home_pos"],
                job["home_quat"], job["instruction"])
            if err is not None:
                _print_plan(steps)
                entry = _error_entry(attempt, model_name, t0, len(steps),
                                     err, latency=latency)
                rounds_log.append(entry)
                learner_events.append_event({
                    "kind": "build_surprise",
                    "run_id": job.get("run_id"),
                    "instruction": job["instruction"], "round": attempt,
                    "graph": None, "motion": None, "findings": [],
                    "outcome": err})
                if rounds >= MAX_REPLAN_ROUNDS:
                    trace.append(f"Round {attempt}: ERROR {err}"[:80])
                    results.put({"gen": job["gen"], "error": err,
                                 "trace": trace, "rounds_log": rounds_log})
                    break
                rounds += 1
                note = format_error_note(err, attempt)
                entry["feedback_note"] = note
                trace.append(f"Round {attempt}: ERROR {err}"[:80])
                trace.append(f"feedback: {err}"[:80])
                print(f"replan round {rounds}/{MAX_REPLAN_ROUNDS}: {err}")
                continue
            if job.get("quarantine"):  # L-03: derived from scene text?
                from loop.quarantine import scan_steps
                hit = scan_steps(steps, job["quarantine"],
                                 job["instruction"], job["props"],
                                 job["valid_people"])
                if hit is not None:
                    script["motion"]["derived_from"] = (
                        f"scene_text:{sorted(job['quarantine'])[0]}")
                    trace.append(f"quarantine: {hit['detail']}"[:80])
                    print(f"quarantine hit: {hit['detail']}")
            graph = graph_snapshot(model, job["data"], job["props"],
                                     perceived=job.get("perceived"))
            try:
                verdict = check(script["motion"], graph)
            except Exception as e:  # noqa: BLE001 - reported, never raised
                err = f"Sentinel error: {e}"
                trace.append(f"Round {attempt}: ERROR Sentinel error")
                entry = _error_entry(attempt, model_name, t0, len(steps),
                                     err, latency=latency)
                entry["graph"] = graph
                rounds_log.append(entry)
                learner_events.append_event({
                    "kind": "build_surprise",
                    "run_id": job.get("run_id"),
                    "instruction": job["instruction"], "round": attempt,
                    "graph": learner_events.compact_graph(graph),
                    "motion": _motion_summary(script["motion"]),
                    "findings": [], "outcome": err})
                results.put({"gen": job["gen"], "error": err,
                             "trace": trace, "rounds_log": rounds_log})
                break
            rules = ",".join(dict.fromkeys(
                f["rule"] for f in verdict["findings"]))
            entry = f"Round {attempt}: {verdict['kind']}" \
                + (f" {rules}" if rules else "")
            log_entry = {"round": attempt, "kind": verdict["kind"],
                         "rules": rules.split(",") if rules else [],
                         "findings": verdict["findings"],
                         "feedback": verdict["feedback"],
                         "why": verdict.get("why_path"),
                         "path": _motion_path(script["motion"],
                                              verdict["findings"]),
                         "graph": graph,
                         "proposal": {"model": model_name,
                                      "latency_s": latency,
                                      "n_steps": len(steps)},
                         "feedback_note": None, "error": None}
            rounds_log.append(log_entry)
            ev_base = {"run_id": job.get("run_id"),
                       "instruction": job["instruction"], "round": attempt,
                       "graph": learner_events.compact_graph(graph),
                       "motion": _motion_summary(script["motion"]),
                       "closest": _closest_approach(script["motion"],
                                                   graph),
                       "findings": verdict["findings"],
                       "outcome": verdict["kind"]}
            learner_events.append_event({"kind": "verdict", **ev_base})
            if any(f["rule"] == "unknown_object"
                   for f in verdict["findings"]):
                learner_events.append_event(
                    {"kind": "unknown_object", **ev_base})
            if not should_replan(verdict, rounds):
                trace.append(entry)
                results.put({"gen": job["gen"], "steps": steps,
                             "script": script, "verdict": verdict,
                             "rounds": rounds, "trace": trace,
                             "perceived": conf_summary,
                             "rounds_log": rounds_log})
                break
            rounds += 1
            note = format_replan_note(verdict, attempt)
            log_entry["feedback_note"] = note
            cons = "; ".join(constraints_for(verdict))
            trace.append(entry)
            trace.append(f"feedback: {cons}")
            print(f"replan round {rounds}/{MAX_REPLAN_ROUNDS}: "
                  f"{constraints_for(verdict)}")


def _clean_line(line: str) -> str:
    """Strip control characters from pasted input; "" means ignore."""
    return "".join(c for c in line if c == "\t" or ord(c) >= 32).strip()


def _reader(lines: queue.Queue) -> None:
    while True:
        try:
            lines.put(input(PROMPT))
        except EOFError:
            lines.put(None)
            return


def _reset_all(viewer, model, data, home, person, st) -> None:
    st["gen"] += 1  # invalidate any in-flight plan
    with viewer.lock():
        _restore(model, data, home, person)
        _clear_preview(viewer)
        _draw_orb(viewer, ORB_IDLE)
    st.update(phase="idle", instruction="", steps=None, script=None,
              seg_i=0, motion=None, verdict=None, error=None, current=None,
              trace=[], halt=None, halt_last=0.0, held_now=None,
              rounds=0, perceive_conf=None)


def _random_reach_target() -> np.ndarray:
    return np.array([random.uniform(0.15, 0.65),
                     random.uniform(-0.3, 0.25), 0.33])


CUP_NEAR_LAPTOP = (0.35, 0.06, 0.0)  # F3: 9 cm off the laptop edge
GLASS_AT_EDGE = (0.3, -0.32, 0.0)  # wine-glass demo: 3 cm off the edge


def _apply_preset(model, data, home, name: str) -> None:
    """Stage the scene: 'cup_next_to_laptop' (F3), 'glass_at_edge'
    (wine-glass demo) or 'default' (F4)."""
    cup = free_qposadr(model, "cup")
    glass = free_qposadr(model, "wine_glass")
    if name == "cup_next_to_laptop":
        data.qpos[cup:cup + 3] = CUP_NEAR_LAPTOP
    elif name == "glass_at_edge":
        data.qpos[glass:glass + 3] = GLASS_AT_EDGE
    elif name == "default":
        data.qpos[cup:cup + 7] = home["qpos"][cup:cup + 7]
        data.qpos[glass:glass + 7] = home["qpos"][glass:glass + 7]
    else:
        raise ValueError(f"unknown preset {name!r}")
    mujoco.mj_forward(model, data)


def _perceive_sync(model, data, props, tag: str = "live") -> tuple:
    """Render + perceive one state; (positions, perceived, summary, path)."""
    from perception.frames import perception_frame, save_frame
    from perception.perceive import perceive_frame
    from sim.world import OUT_DIR

    frame = perception_frame(model, data)
    path = save_frame(frame, OUT_DIR / f"perception_{tag}.png")
    out = perceive_frame(model, data, frame, path, props)
    summary = {k: round(v["conf"], 2)
               for k, v in out["perceived"].items()}
    print(f"perceived {len(out['positions'])} objects from {path.name} "
          f"(min conf {min(summary.values()):.2f})")
    return out["positions"], out["perceived"], summary, path


def _read_quarantine(model, data, props, image_path) -> dict:
    """Run the quarantined reader on a saved frame ({oid: [texts]})."""
    from loop.quarantine import project_props, quarantine_for
    from perception.frames import HEIGHT, WIDTH
    from perception.reader import read_scene_text

    texts = read_scene_text(image_path, WIDTH, HEIGHT)
    if not texts:
        return {}
    projected = project_props(model, data, props, "front", WIDTH, HEIGHT)
    quarantine = quarantine_for(texts, props, projected)
    if quarantine:
        print(f"quarantine: {quarantine}")
    return quarantine


def _render_idle_clip(model, data, out_path: str, fps: int = 30,
                      seconds: float = 3.0, sink=None) -> None:
    """Save a static clip: proof the robot did not move (BLOCK demo)."""
    import imageio.v2 as imageio
    from pathlib import Path

    from sim.world import HEIGHT, WIDTH

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with RENDER_LOCK:
        renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
    try:
        with imageio.get_writer(out, fps=fps, codec="libx264",
                                quality=8) as writer:
            n = int(fps * seconds)
            for i in range(n):
                renderer.update_scene(data, camera="demo")
                frame = renderer.render()
                writer.append_data(frame)
                if sink is not None and i % max(n // 5, 1) == 0:
                    from dashboard.events import (
                        encode_jpeg_b64,
                        frame_event,
                    )
                    sink(frame_event(encode_jpeg_b64(frame), [], "truth",
                                     i / fps))
    finally:
        with RENDER_LOCK:
            renderer.close()
    print(f"saved {out} (static: Sentinel refused to move)")


def _run_headless(instruction: str, out_path: str, fps: int = 30,
                  preset: str | None = None,
                  f6_at: float | None = None,
                  perception: str = "truth",
                  planner_model: str = "spark",
                  attack: str | None = None,
                  sink=None, ask_handler=None) -> None:
    """One instruction, no window: execute and save an mp4 (verification).

    Runs the same worker (with the L-06 replan loop) as the viewer loop,
    plus the L-07 HALT monitor on virtual time (person, freeze, clear,
    replan). f6_at fires the F6 intrusion at that exec time (seconds).
    perception="sam" perceives each planned state with G-09 (the HALT
    replan re-perceives too); anything else uses sim ground truth.
    ask_handler (the dashboard's ASK registry) lets a final soft ASK wait
    for the owner's approve/deny instead of stopping; without one a final
    ASK stops as before.
    """
    import imageio.v2 as imageio
    from pathlib import Path

    from sim.world import HEIGHT, WIDTH

    model, data = load_scene("kitchen")
    props = load_props()
    if preset is not None:
        _apply_preset(model, data, None, preset)
        print(f"preset: {preset}")
    halt_params = rule_params()
    positions, perceived, quarantine = (None, None, {})
    if perception == "sam":
        try:
            positions, perceived, _, frame_path = _perceive_sync(
                model, data, props)
            quarantine = _read_quarantine(model, data, props, frame_path)
        except Exception as e:  # noqa: BLE001 - reported, never raised
            print(f"perception error: {e} (not moving)")
            if sink is not None:
                from dashboard.events import done_event
                sink(done_event("error",
                                {"error": f"perception error: {e}"}))
            raise SystemExit(1)
    facts = scene_facts(model, data, props, perceived=positions,
                        quarantine=set(quarantine))
    hand_id = model.body("hand").id
    home_pos = data.xpos[hand_id].copy()
    home_quat = data.xquat[hand_id].copy()
    jobs: queue.Queue = queue.Queue()
    results: queue.Queue = queue.Queue()
    threading.Thread(target=_planner_worker, args=(model, jobs, results),
                     daemon=True).start()
    run_id = f"run-{uuid.uuid4().hex[:6]}"
    job = {"gen": 0, "instruction": instruction, "facts": facts,
           "data": data, "valid_ids": set(props["objects"]),
           "valid_people": set(props["people"]), "props": props,
           "home_pos": home_pos, "home_quat": home_quat,
           "perceived": perceived, "model": planner_model,
           "quarantine": quarantine, "run_id": run_id}
    if attack == "scene-text":
        from perception.reader import stage_attack_frame
        job["attack_frame"] = stage_attack_frame(model, data, props)
        print(f"attack staged: {job['attack_frame'].name}")
    jobs.put(job)

    def emit(event):
        if sink is not None:
            sink(event)

    def take_result():
        from dashboard.events import (
            done_event,
            feedback_event,
            graph_event,
            path_event,
            plan_event,
            proposal_event,
            verdict_event,
            why_path_for,
        )
        res = results.get()
        trace = list(res.get("trace", []))

        def emit_rounds():
            for entry in res.get("rounds_log", []):
                if entry.get("proposal") is not None:
                    p = entry["proposal"]
                    emit(proposal_event(entry["round"], p["model"],
                                        p["latency_s"], p["n_steps"]))
                if entry.get("graph") is not None:
                    emit(graph_event(entry["graph"]))
                if entry.get("path") is not None:
                    emit(path_event(entry["round"],
                                    entry["path"]["points"],
                                    entry["path"]["fires"]))
                if entry.get("kind") != "ERROR":
                    emit(verdict_event(
                        entry["round"], entry["kind"],
                        entry["findings"], entry["feedback"],
                        entry.get("why")
                        or why_path_for(trace, entry["round"]),
                        live_run_id=run_id))
                if entry.get("feedback_note"):
                    emit(feedback_event(entry["round"],
                                        entry["feedback_note"]))

        if "error" in res:
            if trace:
                print(" -> ".join(trace))
            print(f"{res['error']} (not moving)")
            jobs.put(None)
            emit_rounds()
            emit(done_event("error", {"error": res["error"]}))
            raise SystemExit(1)
        steps, script = res["steps"], res["script"]
        verdict = res["verdict"]
        _print_plan(steps)
        print(_motion_summary(script["motion"]))
        if trace:
            print(" -> ".join(trace))
        for f in verdict["findings"]:
            print(f"  ! {f['rule']}: {f['detail']}")
        emit(plan_event(steps, res["rounds"]))
        emit_rounds()
        ask = None
        if verdict["kind"] != "ALLOW":
            if verdict["kind"] == "ASK" and ask_handler is not None \
                    and not has_hard_finding(verdict):
                log = res.get("rounds_log") or []
                final_round = log[-1]["round"] if log \
                    else res["rounds"] + 1
                ask_id, decision = decide_ask(verdict, final_round,
                                              ask_handler, emit)
                ask = {"ask_id": ask_id, "decision": decision,
                       "round": final_round}
                graphs = [e["graph"] for e in (res.get("rounds_log") or [])
                          if e.get("graph")]
                learner_events.append_event({
                    "kind": "ask_answer", "run_id": run_id,
                    "instruction": instruction, "round": final_round,
                    "graph": learner_events.compact_graph(
                        graphs[-1] if graphs else None),
                    "motion": _motion_summary(script["motion"]),
                    "findings": verdict["findings"],
                    "outcome": decision,
                    "ask_id": ask_id, "who": "owner"})
                if decision == "approve":
                    print(f"Sentinel: ASK {ask_id} approved by owner, "
                          f"executing")
                    return steps, script, res["rounds"], trace, ask
                print(f"Sentinel: ASK {ask_id} denied (not moving)")
            else:
                print(f"Sentinel: {verdict['kind']} (not moving)")
            jobs.put(None)
            _render_idle_clip(model, data, out_path, fps, sink=sink)
            emit(done_event(verdict["kind"],
                            {"trace": trace[-4:], "ask": ask}))
            raise SystemExit(1)
        return steps, script, res["rounds"], trace, ask

    _, script, rounds, trace, ask = take_result()
    dt = 1.0 / fps
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with RENDER_LOCK:
        renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
    person = {"active": False, "t0": 0.0, "target": HANDOVER_HOVER,
              "face": None, "origin": None, "carrying": None, "f6": None}
    takers: list[tuple[str, bool]] = []
    vnow, last_check = 0.0, -1.0
    frame_i = 0
    seg_i, seg_k, guard = 0, 0, 0
    lh, halt, held_now, clear_since = None, None, None, None
    f6_done = f6_at is None
    segments = script["segments"]
    try:
        with imageio.get_writer(out, fps=fps, codec="libx264",
                                quality=8) as writer:
            while seg_i < len(segments):
                guard += 1
                if guard > 20000:
                    print("headless guard trip")
                    break
                kind, payload = segments[seg_i]
                if kind == "handover" and lh is None:
                    lh = payload["lh"].fresh(data)
                    hid0 = model.body(HAND_BODY).id
                    lh.reach_origin = data.xpos[hid0].copy()
                    if person.get("f6") is not None:
                        lh.f6 = person["f6"]
                        person.update(active=False, f6=None)
                if not f6_done and vnow >= f6_at:
                    f6_done = True
                    if halt is None and kind == "handover" \
                            and not lh.transferred:
                        lh.f6 = {}
                    elif person.get("carrying") is None:
                        person.update(active=True, t0=vnow, f6={})
                    print(f"F6 @ t={vnow:.2f}s (grabbing at gripper)")
                if halt is None:
                    suppressed = False
                    if kind == "prims":
                        frames = payload["frames"]
                        times, motion = payload["times"], payload["motion"]
                        dur = float(times[-1])
                        tau = min(seg_k * dt, dur)
                        idx = min(max(int(np.searchsorted(
                            times, tau, side="right") - 1), 0),
                            len(frames) - 1)
                        data.qpos[:] = frames[idx]
                        mujoco.mj_forward(model, data)
                        held_now = motion["held"][idx]
                        seg_motion, seg_tau = motion, tau
                        _step_person(model, data, person, vnow, dt)
                        if seg_k * dt >= dur:
                            seg_i += 1
                            seg_k = 0
                        else:
                            seg_k += 1
                    else:
                        _, done = step_handover(lh, dt)
                        held_now = lh.obj if not lh.transferred else None
                        seg_motion, seg_tau = lh.motion, lh.tau
                        suppressed = lh.tau >= lh.t_offer
                        if done:
                            takers.append((lh.obj, lh.transferred))
                            if not lh.transferred:
                                print("hand-over not taken")
                                seg_i = len(segments)
                            else:
                                seg_i += 1
                            if lh.f6 is not None \
                                    and not lh.transferred:
                                person.update(active=True, f6=lh.f6)
                            lh = None
                    if halt_params is not None and not suppressed \
                            and vnow - last_check >= MONITOR_DT_S:
                        last_check = vnow
                        fire, dist, what = check_halt(
                            model, data, seg_motion, seg_tau, held_now,
                            props, halt_params)
                        if fire:
                            halt = {"tau": seg_tau, "held": held_now,
                                    "motion": seg_motion}
                            clear_since = None
                            entry = (f"HALT person_in_path @ "
                                     f"t={vnow:.2f}s "
                                     f"({dist * 100:.0f} cm from {what})")
                            trace.append(entry)
                            print(f"HALT: {entry}")
                            if sink is not None:
                                from dashboard.events import halt_event
                                emit(halt_event(
                                    vnow, dist * 100.0, what))
                            learner_events.append_event({
                                "kind": "halt", "run_id": run_id,
                                "instruction": instruction, "round": None,
                                "graph": learner_events.compact_graph(
                                    graph_snapshot(model, data, props)),
                                "motion": _motion_summary(
                                    script["motion"]),
                                "findings": [],
                                "outcome": {"t": round(vnow, 2),
                                            "dist_cm": round(dist * 100.0, 1),
                                            "near": what}})
                else:
                    if kind == "handover" and lh is not None \
                            and lh.f6 is not None:
                        if step_f6(model, data, lh.f6, dt):
                            lh.f6 = None
                    _step_person(model, data, person, vnow, dt)
                    if halt_params is not None \
                            and vnow - last_check >= MONITOR_DT_S:
                        last_check = vnow
                        fire, _, _ = check_halt(
                            model, data, halt["motion"], halt["tau"],
                            halt["held"], props, halt_params)
                        if not fire:
                            if clear_since is None:
                                clear_since = vnow
                            if vnow - clear_since >= CLEAR_S:
                                if rounds + 1 > MAX_REPLAN_ROUNDS:
                                    print("HALT: replan budget exhausted "
                                          "(arm frozen)")
                                    jobs.put(None)
                                    if sink is not None:
                                        from dashboard.events import (
                                            done_event,
                                        )
                                        emit(done_event(
                                            "error",
                                            {"error": "HALT replan budget "
                                                      "exhausted"}))
                                    raise SystemExit(1)
                                scratch = mujoco.MjData(model)
                                mujoco.mj_copyData(scratch, model, data)
                                quarantine = {}
                                positions, perceived = (None, None)
                                if perception == "sam":
                                    positions, perceived, _, halt_path = \
                                        _perceive_sync(model, data, props,
                                                       tag="live_halt")
                                    quarantine = _read_quarantine(
                                        model, data, props, halt_path)
                                facts = scene_facts(
                                    model, data, props,
                                    reaching=person["active"],
                                    holding=halt["held"],
                                    perceived=positions,
                                    quarantine=set(quarantine))
                                rounds_start = rounds + 1
                                trace.append(
                                    f"clear {CLEAR_S:.0f}s -> fresh plan "
                                    f"(round {rounds_start + 1})")
                                jobs.put({"gen": 0,
                                          "instruction": instruction,
                                          "facts": facts, "data": scratch,
                                          "valid_ids": set(props["objects"]),
                                          "valid_people": set(
                                              props["people"]),
                                          "props": props,
                                          "home_pos": home_pos,
                                          "home_quat": home_quat,
                                          "rounds": rounds_start,
                                          "trace": trace,
                                          "perceived": perceived,
                                          "model": planner_model,
                                          "quarantine": quarantine,
                                          "run_id": run_id})
                                _, script, rounds, trace, ask = take_result()
                                segments = script["segments"]
                                seg_i, seg_k, lh = 0, 0, None
                                halt, held_now = None, None
                                clear_since = None
                                print(f"resumed at t={vnow:.2f}s")
                                if sink is not None:
                                    from dashboard.events import clear_event
                                    emit(clear_event(vnow, rounds))
                        else:
                            clear_since = None
                renderer.update_scene(data, camera="demo")
                video_frame = renderer.render()
                writer.append_data(video_frame)
                if sink is not None and frame_i % 3 == 0:
                    from dashboard.events import (
                        encode_jpeg_b64,
                        frame_event,
                        project_boxes,
                    )
                    boxes = project_boxes(
                        model, data, props, "demo", WIDTH, HEIGHT,
                        perceived if perception == "sam" else None)
                    emit(frame_event(
                        encode_jpeg_b64(video_frame), boxes,
                        "sam" if perception == "sam" else "truth", vnow))
                frame_i += 1
                vnow += dt
                data.time = vnow
    finally:
        with RENDER_LOCK:
            renderer.close()
    jobs.put(None)
    hid = model.body(HAND_BODY).id
    took = {}
    for obj, ok in takers:
        gap = float(np.linalg.norm(
            data.xpos[hid] - data.xpos[model.body(obj).id]))
        print(f"final: {obj} {'taken' if ok else 'NOT taken'}, "
              f"hand-object gap {gap * 100:.1f} cm")
        took[obj] = {"taken": ok, "gap_cm": round(gap * 100.0, 1)}
    print(f"saved {out}")
    if sink is not None:
        from dashboard.events import done_event
        emit(done_event("complete", {"takers": took, "rounds": rounds,
                                     "duration_s": round(vnow, 2),
                                     "ask": ask,
                                     "motion": _motion_summary(
                                         script["motion"])}))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live instruction loop (viewer + terminal prompt).")
    parser.add_argument("--instruction", default=None)
    parser.add_argument("--record", default=None, metavar="OUT.mp4",
                        help="headless: run one instruction, save a video")
    parser.add_argument("--preset", default=None,
                        choices=["cup_next_to_laptop", "glass_at_edge"],
                        help="headless: stage a scene preset first (F3 live)")
    parser.add_argument("--f6-at", default=None, type=float,
                        metavar="SEC",
                        help="headless: fire the F6 intrusion at SEC exec "
                        "time (F6 key live)")
    parser.add_argument("--perception", default="truth",
                        choices=["truth", "sam"],
                        help="scene graph source: sim ground truth, or "
                        "SAM 3.1 + Muse Spark from the front camera "
                        "(G-09; default truth until G-06 passes)")
    parser.add_argument("--model", default="spark",
                        choices=["spark", "spark-open"],
                        help="planner model (L-01; spark-open needs "
                        "BASETEN_API_KEY in .env.local)")
    parser.add_argument("--attack", default=None,
                        choices=["scene-text"],
                        help="DEMO ONLY: stage hostile scene text and "
                        "expose the planner to it, to prove the L-03 "
                        "quarantine BLOCKs it (never use otherwise)")
    args = parser.parse_args()
    if bool(args.record) != bool(args.instruction):
        parser.error("--record and --instruction go together")
    if args.f6_at is not None and not args.record:
        parser.error("--f6-at needs --record")
    if args.record:
        _run_headless(args.instruction, args.record, preset=args.preset,
                      f6_at=args.f6_at, perception=args.perception,
                      planner_model=args.model, attack=args.attack)
        return

    model, data = load_scene("kitchen")
    props = load_props()
    valid_ids = set(props["objects"])
    valid_people = set(props["people"])
    hand_id = model.body("hand").id
    home = {"qpos": data.qpos.copy(),
            "mocap_pos": data.mocap_pos.copy(),
            "mocap_quat": data.mocap_quat.copy(),
            "hand_pos": data.xpos[hand_id].copy(),
            "hand_quat": data.xquat[hand_id].copy()}
    person = {"active": False, "t0": 0.0, "target": HANDOVER_HOVER,
              "face": None, "origin": None, "carrying": None, "f6": None}
    flags = {"reach": False, "reset": False, "quit": False, "cam": False,
             "preset": None, "f6": False}
    st = {"phase": "idle", "instruction": "", "plan_start": 0.0,
          "steps": None, "script": None, "seg_i": 0, "seg_t0": 0.0,
          "motion": None, "verdict": None, "error": None,
          "exec_t0": 0.0, "preview_until": 0.0, "current": None,
          "gen": 0, "cam": "demo", "last_t": 0.0, "queued": 0,
          "trace": [], "halt": None, "halt_last": 0.0, "held_now": None,
          "rounds": 0, "perception": args.perception,
          "perceive_conf": None}
    halt_params = rule_params()
    if halt_params is None:
        print("warning: person_in_path rule missing: HALT monitor off")

    def key_callback(keycode: int) -> None:
        if keycode == KEY_F1:
            flags["reach"] = True
        elif keycode == KEY_F2:
            flags["cam"] = True
        elif keycode == KEY_F3:
            flags["preset"] = "cup_next_to_laptop"
        elif keycode == KEY_F4:
            flags["preset"] = "default"
        elif keycode == KEY_F5:
            flags["reset"] = True
        elif keycode == KEY_F6:
            flags["f6"] = True
        elif keycode == KEY_ESC:
            flags["quit"] = True

    import mujoco.viewer
    viewer = mujoco.viewer.launch_passive(
        model, data, key_callback=key_callback)
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = model.camera("demo").id

    jobs: queue.Queue = queue.Queue()
    results: queue.Queue = queue.Queue()
    threading.Thread(target=_planner_worker, args=(model, jobs, results),
                     daemon=True).start()
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(lines,), daemon=True).start()
    pending = deque()  # instructions waiting their turn

    def _capture() -> dict | None:
        """Render + save the perception frame (call under viewer lock)."""
        if args.perception != "sam":
            return None
        from perception.frames import perception_frame, save_frame
        from sim.world import OUT_DIR
        frame = perception_frame(model, data)
        path = save_frame(frame, OUT_DIR / "perception_live.png")
        return {"frame": frame, "path": path}

    def _capture_attack():
        """Stage the attack frame (call under viewer lock)."""
        if args.attack != "scene-text":
            return None
        from perception.reader import stage_attack_frame
        return stage_attack_frame(model, data, props, tag="live_attack")

    def _dispatch(text: str, now: float) -> None:
        with viewer.lock():
            scratch = mujoco.MjData(model)
            mujoco.mj_copyData(scratch, model, data)
            facts = scene_facts(model, data, props,
                                reaching=person["active"])
            captured = _capture()
            attacked = _capture_attack()
        st["run_id"] = f"run-{uuid.uuid4().hex[:6]}"
        job = {"gen": st["gen"], "instruction": text,
               "facts": facts, "data": scratch,
               "valid_ids": valid_ids,
               "valid_people": valid_people,
               "props": props,
               "home_pos": home["hand_pos"],
               "home_quat": home["hand_quat"],
               "model": args.model, "run_id": st["run_id"]}
        if captured is not None:
            job["frame"] = captured
        if attacked is not None:
            job["attack_frame"] = attacked
        jobs.put(job)
        st.update(phase="planning", instruction=text,
                  plan_start=now, steps=None, script=None,
                  seg_i=0, motion=None, verdict=None,
                  error=None, current=None)
        with viewer.lock():
            _draw_orb(viewer, ORB_IDLE)

    def _dispatch_halt(now: float) -> None:
        """Fresh plan from the frozen HALT state (consumes a round)."""
        if st["rounds"] + 1 > MAX_REPLAN_ROUNDS:
            st.update(phase="error", halt=None,
                      error="HALT: replan budget exhausted (arm frozen)")
            print("HALT: replan budget exhausted (arm frozen)")
            return
        with viewer.lock():
            scratch = mujoco.MjData(model)
            mujoco.mj_copyData(scratch, model, data)
            facts = scene_facts(model, data, props,
                                reaching=person["active"],
                                holding=st["held_now"])
            captured = _capture()
            attacked = _capture_attack()
        rounds_start = st["rounds"] + 1
        trace = (st.get("trace") or []) + [
            f"clear {CLEAR_S:.0f}s -> fresh plan (round "
            f"{rounds_start + 1})"]
        job = {"gen": st["gen"], "instruction": st["instruction"],
               "facts": facts, "data": scratch,
               "valid_ids": valid_ids,
               "valid_people": valid_people,
               "props": props,
               "home_pos": home["hand_pos"],
               "home_quat": home["hand_quat"],
               "rounds": rounds_start, "trace": trace,
               "model": args.model, "run_id": st.get("run_id")}
        if captured is not None:
            job["frame"] = captured
        if attacked is not None:
            job["attack_frame"] = attacked
        jobs.put(job)
        st.update(phase="planning", plan_start=now, steps=None,
                  script=None, seg_i=0, motion=None, verdict=None,
                  error=None, current=None, halt=None)
        with viewer.lock():
            _draw_orb(viewer, ORB_IDLE)
        print(f"replanning from HALT state (round {rounds_start + 1})")
    print("Kitchen live. Type instructions in THIS terminal (or quit).")
    print(f"perception: {'SAM 3.1 + Muse Spark' if args.perception == 'sam' else 'sim ground truth'}")
    print(f"planner model: {args.model}")
    if args.attack:
        print("ATTACK DEMO ONLY: scene text will be staged + exposed")
    print("[F1] person reaches in  [F2] camera  [F5] reset  [Esc] quit")
    print("[F3] cup next to laptop  [F4] default scene")
    print("[F6] person grabs at the gripper (HALT demo)")
    eof = False
    st["last_t"] = time.perf_counter()
    try:
        with viewer.lock():
            _draw_orb(viewer, ORB_IDLE)
        while viewer.is_running() and not flags["quit"] and not (
                eof and st["phase"] not in ("planning", "preview",
                                            "executing", "halt")
                and not pending):
            now = time.perf_counter()
            wall_dt = now - st["last_t"]
            st["last_t"] = now
            if flags["reset"]:
                flags["reset"] = False
                _reset_all(viewer, model, data, home, person, st)
                print("scene reset")
            if flags["cam"]:
                flags["cam"] = False
                st["cam"] = "handover" if st["cam"] == "demo" else "demo"
                with viewer.lock():
                    viewer.cam.fixedcamid = model.camera(st["cam"]).id
                print(f"camera: {st['cam']}")
            if flags["preset"]:
                name = flags["preset"]
                flags["preset"] = None
                with viewer.lock():
                    _apply_preset(model, data, home, name)
                print(f"preset: {name}")
            if flags["reach"]:
                flags["reach"] = False
                with viewer.lock():
                    origin = data.xpos[
                        model.body("human_hand").id].copy()
                    person.update(active=True, t0=now,
                                  target=_random_reach_target(), face=None,
                                  origin=origin)
                print("person reaching in")
            if flags["f6"]:
                flags["f6"] = False
                if person.get("carrying") is not None:
                    print("F6 ignored (person carrying)")
                elif (st["phase"] == "executing" and st["script"]
                        and st["script"][st["seg_i"]][0] == "handover"):
                    lh = st["script"][st["seg_i"]][1]["lh"]
                    if lh.transferred:
                        print("F6 ignored (already transferred)")
                    else:
                        with viewer.lock():
                            lh.f6 = {}
                        print("F6: person grabbing at the gripper")
                else:
                    with viewer.lock():
                        person.update(active=True, t0=now, f6={})
                    print("F6: person grabbing at the gripper")
            try:
                line = lines.get_nowait()
            except queue.Empty:
                line = ...
            if line is None:  # EOF: quit once idle, not mid-plan
                eof = True
                print("(stdin closed)")
                continue
            if line is not ...:
                text = _clean_line(line)
                if text.lower() in ("quit", "exit"):
                    break
                if text:
                    if st["phase"] in ("planning", "preview", "executing",
                                       "halt"):
                        pending.append(text)
                        st["queued"] = len(pending)
                        print(f"queued ({len(pending)})")
                    else:
                        _dispatch(text, now)
            try:
                res = results.get_nowait()
            except queue.Empty:
                res = None
            if res is not None and res["gen"] == st["gen"]:
                if "error" in res:
                    st.update(phase="error", error=res["error"],
                              trace=res.get("trace", []))
                    if res.get("trace"):
                        print(" -> ".join(res["trace"]))
                    print(f"{res['error']} (not moving)")
                else:
                    st.update(phase="preview", steps=res["steps"],
                              script=res["script"]["segments"],
                              motion=res["script"]["motion"], seg_i=0,
                              preview_until=now + PREVIEW_T,
                              trace=res.get("trace", []),
                              rounds=res["rounds"],
                              perceive_conf=res.get("perceived"))
                    _print_plan(res["steps"])
                    print(_motion_summary(res["script"]["motion"]))
                    if res.get("trace"):
                        print(" -> ".join(res["trace"]))
                    verdict = res["verdict"]
                    for f in verdict["findings"]:
                        print(f"  ! {f['rule']}: {f['detail']}")
                    if verdict["kind"] != "ALLOW":
                        st.update(phase="error", verdict=verdict,
                                  error=f"Sentinel: {verdict['kind']} "
                                        f"(not moving)")
                        print(f"Sentinel: {verdict['kind']} (not moving)")
                    else:
                        st["verdict"] = verdict
                        with viewer.lock():
                            _draw_orb(
                                viewer,
                                ORB_COLORS.get(verdict["kind"], ORB_IDLE))
                            _show_preview(viewer, model, data,
                                          res["script"]["motion"],
                                          res["steps"])
            if st["phase"] == "preview" and now >= st["preview_until"]:
                with viewer.lock():
                    _clear_preview(viewer)
                st.update(phase="executing", seg_i=0, seg_t0=now,
                          exec_t0=now)
            if st["phase"] == "executing":
                kind, payload = st["script"][st["seg_i"]]
                seg0 = st["seg_i"]
                seg_motion, seg_tau, suppressed = None, 0.0, False
                if kind == "prims":
                    tau = now - st["seg_t0"]
                    times, frames = payload["times"], payload["frames"]
                    dur = float(times[-1])
                    last = st["seg_i"] == len(st["script"]) - 1
                    if tau >= dur + (SETTLE_T if last else 0.0):
                        if last:
                            st.update(phase="done", current=None)
                            print("Done")
                        else:
                            st["seg_i"] += 1
                            st["seg_t0"] = now
                    else:
                        idx = min(max(int(np.searchsorted(
                            times, tau, side="right") - 1), 0),
                            len(frames) - 1)
                        st["current"] = payload["motion"][
                            "sample_steps"][idx]
                        st["held_now"] = payload["motion"]["held"][idx]
                        seg_motion, seg_tau = payload["motion"], tau
                        with viewer.lock():
                            data.qpos[:] = frames[idx]
                            data.time = now - st["exec_t0"]
                            mujoco.mj_forward(model, data)
                            _step_person(model, data, person, now,
                                         wall_dt)
                else:
                    lh = payload["lh"]
                    st["current"] = payload["hid"]
                    with viewer.lock():
                        if lh.data is not data:  # bind once, on segment entry
                            # Fresh reach origin: F1 during planning may have
                            # moved the live hand since the snapshot was taken.
                            lh = payload["lh"] = lh.fresh(data)
                            hid = model.body(HAND_BODY).id
                            lh.reach_origin = data.xpos[hid].copy()
                            if person.get("f6") is not None:
                                lh.f6 = person["f6"]
                                person.update(active=False, f6=None)
                        _, done = step_handover(lh, wall_dt)
                        data.time = now - st["exec_t0"]
                    st["held_now"] = lh.obj if not lh.transferred else None
                    seg_motion, seg_tau = lh.motion, lh.tau
                    suppressed = lh.tau >= lh.t_offer
                    if done:
                        if lh.f6 is not None and not lh.transferred:
                            person.update(active=True, f6=lh.f6)
                            lh.f6 = None
                        with viewer.lock():
                            hand_now = data.xpos[
                                model.body("human_hand").id].copy()
                        if lh.transferred:
                            person.update(
                                active=True, t0=now, target=park_pos(model),
                                face=None, origin=park_pos(model),
                                carrying={"obj": lh.obj,
                                          "offset": lh.transfer_offset})
                        else:
                            person.update(
                                active=True, t0=now, target=park_pos(model),
                                face=None, origin=hand_now)
                            st.update(phase="error",
                                      error="hand-over not taken")
                            print("hand-over not taken")
                        if st["seg_i"] == len(st["script"]) - 1:
                            st.update(phase="done", current=None)
                            print("Done")
                        else:
                            st["seg_i"] += 1
                            st["seg_t0"] = now
                if (st["phase"] == "executing" and seg_motion is not None
                        and st["seg_i"] == seg0 and not suppressed
                        and halt_params is not None
                        and now - st["halt_last"] >= MONITOR_DT_S):
                    st["halt_last"] = now
                    try:
                        fire, dist, what = check_halt(
                            model, data, seg_motion, seg_tau,
                            st["held_now"], props, halt_params)
                    except Exception as e:  # noqa: BLE001 - fail closed
                        print(f"monitor error (fail-closed HALT): {e}")
                        fire, dist, what = True, 0.0, "monitor error"
                    if fire:
                        exec_t = now - st["exec_t0"]
                        entry = (f"HALT person_in_path @ "
                                 f"t={exec_t:.2f}s "
                                 f"({dist * 100:.0f} cm from {what})")
                        st["trace"] = (st.get("trace") or []) + [entry]
                        st.update(phase="halt",
                                  halt={"tau": seg_tau, "dist": dist,
                                        "what": what, "clear_since": None,
                                        "clear_for": 0.0})
                        print(f"HALT: {entry}")
                        learner_events.append_event({
                            "kind": "halt",
                            "run_id": st.get("run_id"),
                            "instruction": st.get("instruction"),
                            "round": None,
                            "graph": learner_events.compact_graph(
                                graph_snapshot(model, data, props)),
                            "motion": _motion_summary(seg_motion),
                            "findings": [],
                            "outcome": {"t": round(exec_t, 2),
                                        "dist_cm": round(dist * 100.0, 1),
                                        "near": what}})
                        with viewer.lock():
                            _draw_orb(viewer, ORB_COLORS["HALT"])
            else:
                with viewer.lock():
                    _step_person(model, data, person, now, wall_dt)
            if st["phase"] == "halt":
                kind, payload = st["script"][st["seg_i"]]
                if kind == "handover" \
                        and payload["lh"].f6 is not None:
                    with viewer.lock():
                        if step_f6(model, data, payload["lh"].f6,
                                   wall_dt):
                            payload["lh"].f6 = None
            if st["phase"] == "halt" and halt_params is not None \
                    and now - st["halt_last"] >= MONITOR_DT_S:
                st["halt_last"] = now
                kind, payload = st["script"][st["seg_i"]]
                seg_motion = payload["motion"] if kind == "prims" \
                    else payload["lh"].motion
                try:
                    fire, _, _ = check_halt(
                        model, data, seg_motion, st["halt"]["tau"],
                        st["held_now"], props, halt_params)
                except Exception as e:  # noqa: BLE001 - fail closed
                    print(f"monitor error (fail-closed HALT): {e}")
                    fire = True
                h = st["halt"]
                if not fire:
                    if h["clear_since"] is None:
                        h["clear_since"] = now
                    h["clear_for"] = now - h["clear_since"]
                    if h["clear_for"] >= CLEAR_S:
                        print(f"clear {CLEAR_S:.0f}s, replanning...")
                        _dispatch_halt(now)
                else:
                    h["clear_since"] = None
                    h["clear_for"] = 0.0
            if pending and st["phase"] in ("done", "error", "idle"):
                nxt = pending.popleft()
                st["queued"] = len(pending)
                print(f"next: {nxt}")
                _dispatch(nxt, now)
            viewer.set_texts(
                (mujoco.mjtFontScale.mjFONTSCALE_150,
                 mujoco.mjtGridPos.mjGRID_TOPLEFT, _overlay_text(st), ""))
            viewer.sync()
            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        pass
    finally:
        jobs.put(None)
        viewer.close()


if __name__ == "__main__":
    main()
