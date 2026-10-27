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
import random
import threading
import time

import mujoco
import numpy as np

from graph.scene_graph import load_props
from loop.handover import build_execution_script, step_handover
from planner.planner import plan_from_content, plan_instruction, scene_facts
from sentinel.check import check
from sim.human import HANDOVER_HOVER, park_pos, reach_to_counter
from sim.play import HAND_BODY, REACH_DURATION, drag_with_hand
from sim.world import load_scene

KEY_F1 = 290  # GLFW physical keys (no letters: safe while typing)
KEY_F2 = 291
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
        stub = " (stub)" if st["verdict"].get("stub") else ""
        lines.append(f"Sentinel: {st['verdict']['kind']}{stub}")
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
    """Background thread: plan + dry-run the script off a snapshot."""
    while True:
        job = jobs.get()
        if job is None:
            return
        try:
            content = plan_instruction(job["instruction"], job["facts"])
        except Exception as e:  # noqa: BLE001 - reported, never raised
            results.put({"gen": job["gen"],
                         "error": f"planner error: {e}"})
            continue
        steps, err = plan_from_content(content, job["valid_ids"],
                                       job["valid_people"])
        if err is not None:
            results.put({"gen": job["gen"],
                         "error": f"invalid plan: {err}"})
            continue
        script, err = build_execution_script(
            model, job["data"], steps, job["home_pos"], job["home_quat"],
            job["instruction"])
        if err is not None:
            results.put({"gen": job["gen"], "error": err})
            continue
        results.put({"gen": job["gen"], "steps": steps, "script": script})


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
              seg_i=0, motion=None, verdict=None, error=None, current=None)


def _random_reach_target() -> np.ndarray:
    return np.array([random.uniform(0.15, 0.65),
                     random.uniform(-0.3, 0.25), 0.33])


def _run_headless(instruction: str, out_path: str, fps: int = 30) -> None:
    """One instruction, no window: execute and save an mp4 (verification)."""
    import imageio.v2 as imageio
    from pathlib import Path

    from sim.world import HEIGHT, WIDTH

    model, data = load_scene("kitchen")
    props = load_props()
    facts = scene_facts(model, data, props)
    content = plan_instruction(instruction, facts)
    steps, err = plan_from_content(content, set(props["objects"]),
                                   set(props["people"]))
    if err is not None:
        print(f"invalid plan: {err} (not moving)")
        raise SystemExit(1)
    _print_plan(steps)
    hand_id = model.body("hand").id
    script, err = build_execution_script(
        model, data, steps, data.xpos[hand_id].copy(),
        data.xquat[hand_id].copy(), instruction)
    if err is not None:
        print(f"{err} (not moving)")
        raise SystemExit(1)
    print(_motion_summary(script["motion"]))
    verdict = check(script["motion"])
    print(f"Sentinel: {verdict['kind']}")
    if verdict["kind"] != "ALLOW":
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
    args = parser.parse_args()
    if bool(args.record) != bool(args.instruction):
        parser.error("--record and --instruction go together")
    if args.record:
        _run_headless(args.instruction, args.record)
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
    flags = {"reach": False, "reset": False, "quit": False, "cam": False}
    st = {"phase": "idle", "instruction": "", "plan_start": 0.0,
          "steps": None, "script": None, "seg_i": 0, "seg_t0": 0.0,
          "motion": None, "verdict": None, "error": None,
          "exec_t0": 0.0, "preview_until": 0.0, "current": None,
          "gen": 0, "cam": "demo", "last_t": 0.0}

    def key_callback(keycode: int) -> None:
        if keycode == KEY_F1:
            flags["reach"] = True
        elif keycode == KEY_F2:
            flags["cam"] = True
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
    print("Kitchen live. Type instructions in THIS terminal (or quit).")
    print("[F1] person reaches in  [F2] camera  [F5] reset  [Esc] quit")
    eof = False
    st["last_t"] = time.perf_counter()
    try:
        with viewer.lock():
            _draw_orb(viewer, ORB_IDLE)
        while viewer.is_running() and not flags["quit"] and not (
                eof and st["phase"] not in ("planning", "preview",
                                            "executing")):
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
                text = line.strip()
                if text.lower() in ("quit", "exit"):
                    break
                if text:
                    if st["phase"] in ("planning", "preview", "executing"):
                        print(f"busy ({st['phase']}); wait for Done")
                    else:
                        with viewer.lock():
                            scratch = mujoco.MjData(model)
                            mujoco.mj_copyData(scratch, model, data)
                            facts = scene_facts(
                                model, data, props,
                                reaching=person["active"])
                        jobs.put({"gen": st["gen"], "instruction": text,
                                  "facts": facts, "data": scratch,
                                  "valid_ids": valid_ids,
                                  "valid_people": valid_people,
                                  "home_pos": home["hand_pos"],
                                  "home_quat": home["hand_quat"]})
                        st.update(phase="planning", instruction=text,
                                  plan_start=now, steps=None, script=None,
                                  seg_i=0, motion=None, verdict=None,
                                  error=None, current=None)
                        with viewer.lock():
                            _draw_orb(viewer, ORB_IDLE)
            try:
                res = results.get_nowait()
            except queue.Empty:
                res = None
            if res is not None and res["gen"] == st["gen"]:
                if "error" in res:
                    st.update(phase="error", error=res["error"])
                    print(f"{res['error']} (not moving)")
                else:
                    st.update(phase="preview", steps=res["steps"],
                              script=res["script"]["segments"],
                              motion=res["script"]["motion"], seg_i=0,
                              preview_until=now + PREVIEW_T)
                    _print_plan(res["steps"])
                    print(_motion_summary(res["script"]["motion"]))
                    try:
                        verdict = check(res["script"]["motion"])
                    except Exception as e:  # noqa: BLE001 - stub never raises
                        st.update(phase="error",
                                  error=f"Sentinel error: {e}")
                        print(f"Sentinel error: {e} (not moving)")
                        verdict = None
                    if verdict is not None:
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
