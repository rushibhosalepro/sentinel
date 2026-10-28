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

import mujoco
import numpy as np

from graph.scene_graph import load_props
from loop.handover import build_execution_script, step_handover
from loop.feedback import (MAX_REPLAN_ROUNDS, constraints_for,
                           format_error_note, format_replan_note,
                           should_replan)
from planner.planner import plan_from_content, plan_instruction, scene_facts
from sentinel.check import check
from sentinel.graph_view import graph_snapshot
from sim.primitives import free_qposadr
from sim.human import HANDOVER_HOVER, park_pos, reach_to_counter
from sim.play import HAND_BODY, REACH_DURATION, drag_with_hand
from sim.world import load_scene

KEY_F1 = 290  # GLFW physical keys (no letters: safe while typing)
KEY_F2 = 291
KEY_F3 = 292
KEY_F4 = 293
KEY_F5 = 294
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
    phase = st["phase"]
    if phase == "planning":
        lines.append(f"Muse Spark planning... "
                     f"{time.perf_counter() - st['plan_start']:.0f} s")
    elif phase == "preview":
        lines.append("previewing path...")
    elif phase == "executing":
        n = len(st["script"]) if st["script"] else 0
        lines.append(f"executing... (segment {st['seg_i'] + 1}/{n})")
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


def _motion_summary(motion: dict) -> str:
    t = motion["t"]
    return (f"Motion: {len(t)} samples over {t[-1]:.2f} s, "
            f"held={motion['held'][-1]}, "
            f"{len(motion['end_state'])} end relations")


def _step_person(model, data, person: dict) -> None:
    if not person["active"]:
        return
    elapsed = time.perf_counter() - person["t0"]
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
                  origin=None, carrying=None)
    mujoco.mj_forward(model, data)


def _planner_worker(model, jobs: queue.Queue, results: queue.Queue) -> None:
    """Background thread: propose -> motion -> check -> replan (L-06).

    Retries ASK and SOFT-BLOCK verdicts with fixable feedback, plus
    invalid plans and build errors (error text as feedback); never
    retries a verdict with a hard finding. Max 3 rounds. Records the
    round trace for the overlay.
    """
    while True:
        job = jobs.get()
        if job is None:
            return
        note = None
        rounds = 0
        trace: list[str] = []
        while True:  # replan loop
            attempt = rounds + 1
            try:
                content = plan_instruction(job["instruction"], job["facts"],
                                           note=note)
            except Exception as e:  # noqa: BLE001 - reported, never raised
                trace.append(f"Round {attempt}: ERROR planner error")
                results.put({"gen": job["gen"],
                             "error": f"planner error: {e}", "trace": trace})
                break
            steps, err = plan_from_content(content, job["valid_ids"],
                                           job["valid_people"])
            if err is not None:
                err = f"invalid plan: {err}"
                if rounds >= MAX_REPLAN_ROUNDS:
                    trace.append(f"Round {attempt}: ERROR {err}"[:80])
                    results.put({"gen": job["gen"], "error": err,
                                 "trace": trace})
                    break
                rounds += 1
                note = format_error_note(err, attempt)
                trace.append(f"Round {attempt}: ERROR {err}"[:80])
                trace.append(f"feedback: {err}"[:80])
                print(f"replan round {rounds}/{MAX_REPLAN_ROUNDS}: {err}")
                continue
            script, err = build_execution_script(
                model, job["data"], steps, job["home_pos"],
                job["home_quat"], job["instruction"])
            if err is not None:
                if rounds >= MAX_REPLAN_ROUNDS:
                    trace.append(f"Round {attempt}: ERROR {err}"[:80])
                    results.put({"gen": job["gen"], "error": err,
                                 "trace": trace})
                    break
                rounds += 1
                note = format_error_note(err, attempt)
                trace.append(f"Round {attempt}: ERROR {err}"[:80])
                trace.append(f"feedback: {err}"[:80])
                print(f"replan round {rounds}/{MAX_REPLAN_ROUNDS}: {err}")
                continue
            graph = graph_snapshot(model, job["data"], job["props"])
            try:
                verdict = check(script["motion"], graph)
            except Exception as e:  # noqa: BLE001 - reported, never raised
                trace.append(f"Round {attempt}: ERROR Sentinel error")
                results.put({"gen": job["gen"],
                             "error": f"Sentinel error: {e}", "trace": trace})
                break
            rules = ",".join(dict.fromkeys(
                f["rule"] for f in verdict["findings"]))
            entry = f"Round {attempt}: {verdict['kind']}" \
                + (f" {rules}" if rules else "")
            if not should_replan(verdict, rounds):
                trace.append(entry)
                results.put({"gen": job["gen"], "steps": steps,
                             "script": script, "verdict": verdict,
                             "rounds": rounds, "trace": trace})
                break
            rounds += 1
            note = format_replan_note(verdict, attempt)
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
              trace=[])


def _random_reach_target() -> np.ndarray:
    return np.array([random.uniform(0.15, 0.65),
                     random.uniform(-0.3, 0.25), 0.33])


CUP_NEAR_LAPTOP = (0.35, 0.06, 0.0)  # F3: 9 cm off the laptop edge


def _apply_preset(model, data, home, name: str) -> None:
    """Stage the scene: 'cup_next_to_laptop' (F3) or 'default' (F4)."""
    adr = free_qposadr(model, "cup")
    if name == "cup_next_to_laptop":
        data.qpos[adr:adr + 3] = CUP_NEAR_LAPTOP
    elif name == "default":
        data.qpos[adr:adr + 7] = home["qpos"][adr:adr + 7]
    else:
        raise ValueError(f"unknown preset {name!r}")
    mujoco.mj_forward(model, data)


def _run_headless(instruction: str, out_path: str, fps: int = 30,
                  preset: str | None = None) -> None:
    """One instruction, no window: execute and save an mp4 (verification).

    Runs the same worker (with the L-06 replan loop) as the viewer loop.
    """
    import imageio.v2 as imageio
    from pathlib import Path

    from sim.world import HEIGHT, WIDTH

    model, data = load_scene("kitchen")
    props = load_props()
    if preset is not None:
        _apply_preset(model, data, None, preset)
        print(f"preset: {preset}")
    facts = scene_facts(model, data, props)
    hand_id = model.body("hand").id
    jobs: queue.Queue = queue.Queue()
    results: queue.Queue = queue.Queue()
    threading.Thread(target=_planner_worker, args=(model, jobs, results),
                     daemon=True).start()
    jobs.put({"gen": 0, "instruction": instruction, "facts": facts,
              "data": data, "valid_ids": set(props["objects"]),
              "valid_people": set(props["people"]), "props": props,
              "home_pos": data.xpos[hand_id].copy(),
              "home_quat": data.xquat[hand_id].copy()})
    res = results.get()
    jobs.put(None)
    if "error" in res:
        if res.get("trace"):
            print(" -> ".join(res["trace"]))
        print(f"{res['error']} (not moving)")
        raise SystemExit(1)
    steps, script, verdict = res["steps"], res["script"], res["verdict"]
    _print_plan(steps)
    print(_motion_summary(script["motion"]))
    if res.get("trace"):
        print(" -> ".join(res["trace"]))
    for f in verdict["findings"]:
        print(f"  ! {f['rule']}: {f['detail']}")
    if verdict["kind"] != "ALLOW":
        print(f"Sentinel: {verdict['kind']} (not moving)")
        raise SystemExit(1)
    dt = 1.0 / fps
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
    takers: list[tuple[str, bool]] = []
    try:
        with imageio.get_writer(out, fps=fps, codec="libx264",
                                quality=8) as writer:
            for kind, payload in script["segments"]:
                if kind == "prims":
                    frames, times = payload["frames"], payload["times"]
                    n = max(1, int(np.ceil(float(times[-1]) / dt)))
                    for k in range(n + 1):
                        tau = min(k * dt, float(times[-1]))
                        idx = min(max(int(np.searchsorted(
                            times, tau, side="right") - 1), 0),
                            len(frames) - 1)
                        data.qpos[:] = frames[idx]
                        mujoco.mj_forward(model, data)
                        renderer.update_scene(data, camera="demo")
                        writer.append_data(renderer.render())
                else:
                    lh = payload["lh"].fresh(data)
                    guard = 0
                    while True:
                        _, done = step_handover(lh, dt)
                        renderer.update_scene(data, camera="demo")
                        writer.append_data(renderer.render())
                        guard += 1
                        if done or guard > 5000:
                            break
                    takers.append((lh.obj, lh.transferred))
                    if not lh.transferred:
                        print("hand-over not taken")
                        break
    finally:
        renderer.close()
    hid = model.body(HAND_BODY).id
    for obj, ok in takers:
        gap = float(np.linalg.norm(
            data.xpos[hid] - data.xpos[model.body(obj).id]))
        print(f"final: {obj} {'taken' if ok else 'NOT taken'}, "
              f"hand-object gap {gap * 100:.1f} cm")
    print(f"saved {out}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live instruction loop (viewer + terminal prompt).")
    parser.add_argument("--instruction", default=None)
    parser.add_argument("--record", default=None, metavar="OUT.mp4",
                        help="headless: run one instruction, save a video")
    parser.add_argument("--preset", default=None,
                        choices=["cup_next_to_laptop"],
                        help="headless: stage a scene preset first (F3 live)")
    args = parser.parse_args()
    if bool(args.record) != bool(args.instruction):
        parser.error("--record and --instruction go together")
    if args.record:
        _run_headless(args.instruction, args.record, preset=args.preset)
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
              "face": None, "origin": None, "carrying": None}
    flags = {"reach": False, "reset": False, "quit": False, "cam": False,
             "preset": None}
    st = {"phase": "idle", "instruction": "", "plan_start": 0.0,
          "steps": None, "script": None, "seg_i": 0, "seg_t0": 0.0,
          "motion": None, "verdict": None, "error": None,
          "exec_t0": 0.0, "preview_until": 0.0, "current": None,
          "gen": 0, "cam": "demo", "last_t": 0.0, "queued": 0,
          "trace": []}

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

    def _dispatch(text: str, now: float) -> None:
        with viewer.lock():
            scratch = mujoco.MjData(model)
            mujoco.mj_copyData(scratch, model, data)
            facts = scene_facts(model, data, props,
                                reaching=person["active"])
        jobs.put({"gen": st["gen"], "instruction": text,
                  "facts": facts, "data": scratch,
                  "valid_ids": valid_ids,
                  "valid_people": valid_people,
                  "props": props,
                  "home_pos": home["hand_pos"],
                  "home_quat": home["hand_quat"]})
        st.update(phase="planning", instruction=text,
                  plan_start=now, steps=None, script=None,
                  seg_i=0, motion=None, verdict=None,
                  error=None, current=None)
        with viewer.lock():
            _draw_orb(viewer, ORB_IDLE)
    print("Kitchen live. Type instructions in THIS terminal (or quit).")
    print("[F1] person reaches in  [F2] camera  [F5] reset  [Esc] quit")
    print("[F3] cup next to laptop  [F4] default scene")
    eof = False
    st["last_t"] = time.perf_counter()
    try:
        with viewer.lock():
            _draw_orb(viewer, ORB_IDLE)
        while viewer.is_running() and not flags["quit"] and not (
                eof and st["phase"] not in ("planning", "preview",
                                            "executing") and not pending):
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
                    if st["phase"] in ("planning", "preview", "executing"):
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
                              trace=res.get("trace", []))
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
                        with viewer.lock():
                            data.qpos[:] = frames[idx]
                            data.time = now - st["exec_t0"]
                            mujoco.mj_forward(model, data)
                            _step_person(model, data, person)
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
                        _, done = step_handover(lh, wall_dt)
                        data.time = now - st["exec_t0"]
                    if done:
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
            else:
                with viewer.lock():
                    _step_person(model, data, person)
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
