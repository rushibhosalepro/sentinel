"""Live vertical slice: type an instruction, Muse Spark plans, robot acts. (L-00)

Opens the kitchen in a viewer, then loops: read an instruction from the
terminal, plan it with Muse Spark from ground-truth facts (no image),
validate, dry-run the Motion, pass the Sentinel stub, and execute live.

Usage:
    uv run python -m loop.live

Keys: H = person reaches in (scripted), R = reset scene, Q = quit.
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
from sim.play import KEY_Q, KEY_R, REACH_DURATION, rollout_frames
from sim.primitives import PrimitiveError
from sim.world import load_scene

KEY_H = 72  # GLFW physical key H
FPS = 60
SETTLE_T = 0.5  # hold the final frame briefly after executing
PROMPT = "instruction> "


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


def _execute(viewer, model, data, frames, times, person, flags) -> str:
    """Replay a Motion in real time; returns 'done', 'reset', or 'quit'."""
    dur = float(times[-1])
    t0 = time.perf_counter()
    while True:
        if flags["quit"]:
            return "quit"
        if flags["reset"]:
            flags["reset"] = False
            return "reset"
        tau = time.perf_counter() - t0
        if tau >= dur + SETTLE_T:
            return "done"
        idx = min(max(int(np.searchsorted(times, tau, side="right") - 1),
                      0), len(frames) - 1)
        with viewer.lock():
            data.qpos[:] = frames[idx]
            data.time = min(tau, dur)
            mujoco.mj_forward(model, data)
            _step_person(model, data, person)
        viewer.sync()
        time.sleep(1.0 / FPS)


def _handle_instruction(line, viewer, model, data, props, valid_ids,
                        home, person, flags):
    """Plan + check + execute one instruction; 'quit'/'reset'/None."""
    line = line.strip()
    if not line:
        return None
    if line.lower() in ("quit", "exit", "q"):
        return "quit"
    facts = scene_facts(model, data, props)
    try:
        content = plan_instruction(line, facts)
    except Exception as e:
        print(f"planner error: {e} (not moving)")
        return None
    steps, err = plan_from_content(content, valid_ids)
    if err is not None:
        print(f"invalid plan: {err} (not moving)")
        return None
    _print_plan(steps)
    try:
        motion, frames, times = rollout_frames(
            model, data, steps, derived_from=f"live:{line[:40]}")
    except PrimitiveError as e:
        print(f"cannot build Motion: {e} (not moving)")
        return None
    print(_motion_summary(motion))
    verdict = check(motion)
    if verdict["kind"] != "ALLOW":
        print(f"Sentinel: {verdict['kind']} (not moving)")
        return None
    return _execute(viewer, model, data, frames, times, person, flags)


def _reader(lines: queue.Queue) -> None:
    while True:
        try:
            lines.put(input(PROMPT))
        except EOFError:
            lines.put(None)
            return


def main() -> None:
    model, data = load_scene("kitchen")
    props = load_props()
    valid_ids = set(props["objects"])
    home = {"qpos": data.qpos.copy(),
            "mocap_pos": data.mocap_pos.copy(),
            "mocap_quat": data.mocap_quat.copy()}
    person = {"active": False, "t0": 0.0}
    flags = {"reset": False, "quit": False}

    def key_callback(keycode: int) -> None:
        if keycode == KEY_H and not person["active"]:
            person["active"] = True
            person["t0"] = time.perf_counter()
            print("person reaching in")
        elif keycode == KEY_R:
            flags["reset"] = True
        elif keycode == KEY_Q:
            flags["quit"] = True

    import mujoco.viewer
    viewer = mujoco.viewer.launch_passive(
        model, data, key_callback=key_callback)
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = model.camera("demo").id

    lines: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(lines,), daemon=True).start()
    print("Kitchen live. Type an instruction, or quit. "
          "[H] reach in  [R] reset  [Q] quit")
    try:
        while viewer.is_running() and not flags["quit"]:
            if flags["reset"]:
                flags["reset"] = False
                with viewer.lock():
                    _restore(model, data, home, person)
                print("scene reset")
            try:
                line = lines.get_nowait()
            except queue.Empty:
                line = ...
            if line is None:  # EOF on stdin
                break
            if line is not ...:
                outcome = _handle_instruction(
                    line, viewer, model, data, props, valid_ids,
                    home, person, flags)
                if outcome == "quit":
                    break
                if outcome == "reset":
                    with viewer.lock():
                        _restore(model, data, home, person)
                    print("scene reset")
            with viewer.lock():
                _step_person(model, data, person)
            viewer.sync()
            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.close()


if __name__ == "__main__":
    main()
