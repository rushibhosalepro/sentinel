"""Live vertical slice: type an instruction, Muse Spark plans, robot acts. (L-00)

Opens the kitchen in a viewer, then loops: read an instruction from the
terminal, plan it with Muse Spark from ground-truth facts (no image),
validate, dry-run the Motion, pass Sentinel, preview the path, and execute.

Planning + rollout run in a background thread; the main thread only renders
(60 fps), steps execution, and updates the overlay, so the viewer never
freezes while the model thinks.

Usage:
    uv run python -m loop.live

Keys: F1 = person reaches in, F2 = toggle camera, F5 = reset, Esc = quit.
"""

from __future__ import annotations

import queue
import threading
import time

import mujoco
import numpy as np

from graph.scene_graph import load_props
from planner.planner import plan_from_content, plan_instruction, scene_facts
from sentinel.check import check
from sim.human import HANDOVER_HOVER, reach_to_counter
from sim.play import REACH_DURATION, rollout_frames
from sim.primitives import PrimitiveError
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
        lines.append("executing...")
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
    if person["active"]:
        elapsed = time.perf_counter() - person["t0"]
        reach_to_counter(model, data, elapsed, 0.0, REACH_DURATION,
                         HANDOVER_HOVER)


def _restore(model, data, home: dict, person: dict) -> None:
    data.qpos[:] = home["qpos"]
    data.mocap_pos[:] = home["mocap_pos"]
    data.mocap_quat[:] = home["mocap_quat"]
    data.time = 0.0
    person["active"] = False
    mujoco.mj_forward(model, data)


def _planner_worker(model, jobs: queue.Queue, results: queue.Queue) -> None:
    """Background thread: plan + dry-run off a snapshot (never live data)."""
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
        steps, err = plan_from_content(content, job["valid_ids"])
        if err is not None:
            results.put({"gen": job["gen"],
                         "error": f"invalid plan: {err}"})
            continue
        try:
            motion, frames, times = rollout_frames(
                model, job["data"], steps,
                derived_from=f"live:{job['instruction'][:40]}")
        except PrimitiveError as e:
            results.put({"gen": job["gen"],
                         "error": f"cannot build Motion: {e}"})
            continue
        results.put({"gen": job["gen"], "steps": steps, "motion": motion,
                     "frames": frames, "times": times})


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
    st.update(phase="idle", instruction="", steps=None, motion=None,
              frames=None, times=None, verdict=None, error=None,
              current=None)


def main() -> None:
    model, data = load_scene("kitchen")
    props = load_props()
    valid_ids = set(props["objects"])
    home = {"qpos": data.qpos.copy(),
            "mocap_pos": data.mocap_pos.copy(),
            "mocap_quat": data.mocap_quat.copy()}
    person = {"active": False, "t0": 0.0}
    flags = {"reset": False, "quit": False, "cam": False}
    st = {"phase": "idle", "instruction": "", "plan_start": 0.0,
          "steps": None, "motion": None, "frames": None, "times": None,
          "verdict": None, "error": None, "exec_t0": 0.0,
          "preview_until": 0.0, "current": None, "gen": 0, "cam": "demo"}

    def key_callback(keycode: int) -> None:
        if keycode == KEY_F1:
            person["active"] = True
            person["t0"] = time.perf_counter()
            print("person reaching in")
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
    try:
        with viewer.lock():
            _draw_orb(viewer, ORB_IDLE)
        while viewer.is_running() and not flags["quit"] and not (
                eof and st["phase"] not in ("planning", "preview",
                                            "executing")):
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
                            facts = scene_facts(model, data, props)
                        jobs.put({"gen": st["gen"], "instruction": text,
                                  "facts": facts, "data": scratch,
                                  "valid_ids": valid_ids})
                        st.update(phase="planning", instruction=text,
                                  plan_start=time.perf_counter(),
                                  steps=None, motion=None, frames=None,
                                  times=None, verdict=None, error=None,
                                  current=None)
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
                              motion=res["motion"], frames=res["frames"],
                              times=res["times"],
                              preview_until=time.perf_counter() + PREVIEW_T)
                    _print_plan(res["steps"])
                    print(_motion_summary(res["motion"]))
                    try:
                        verdict = check(res["motion"])
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
                                              res["motion"], res["steps"])
            if st["phase"] == "preview" and \
                    time.perf_counter() >= st["preview_until"]:
                with viewer.lock():
                    _clear_preview(viewer)
                st.update(phase="executing",
                          exec_t0=time.perf_counter())
            if st["phase"] == "executing":
                tau = time.perf_counter() - st["exec_t0"]
                times, frames = st["times"], st["frames"]
                if tau >= float(times[-1]) + SETTLE_T:
                    st.update(phase="done", current=None)
                    print("Done")
                else:
                    idx = min(max(int(np.searchsorted(
                        times, tau, side="right") - 1), 0), len(frames) - 1)
                    st["current"] = st["motion"]["sample_steps"][idx]
                    with viewer.lock():
                        data.qpos[:] = frames[idx]
                        data.time = min(tau, float(times[-1]))
                        mujoco.mj_forward(model, data)
                        _step_person(model, data, person)
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
