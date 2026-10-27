"""Play a scenario live in the MuJoCo viewer. (S-06)

Builds the scenario's Motion with sim/motion.py -- capturing a full qpos
snapshot per sample so the held object follows the gripper exactly as in the
dry run -- drives the human hand with sim/human.py, and plays both back in
real time in a passive viewer on the wide demo camera.

Usage:
    uv run python -m sim.play knife_handover              # live window, loops
    uv run python -m sim.play knife_handover --speed 0.5  # slow motion
    uv run python -m sim.play knife_handover --record out/knife_handover.mp4

Viewer keys: space = pause/resume, R = restart, Q = quit. Playback loops
when finished (after a short hold on the final state).
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import mujoco
import numpy as np

from sim.human import reach_to_counter
from sim.motion import KNIFE_HANDOVER_PLAN, plan_to_motion
from sim.world import HEIGHT, WIDTH, load_scene

# GLFW key codes (stable ABI; letters are physical keys, shift-independent).
KEY_SPACE = 32
KEY_R = 82
KEY_Q = 81

VIEW_FPS = 60  # viewer sync cap; the playhead itself tracks the wall clock
END_HOLD_T = 1.0  # hold the final state before looping (s, motion-time)

SCENARIOS = {
    "knife_handover": {
        "plan": KNIFE_HANDOVER_PLAN,
        "human_start_t": 1.5,
        "human_duration": 2.0,
    },
}


@dataclass
class Playback:
    scenario: str
    model: mujoco.MjModel
    data: mujoco.MjData
    motion: dict
    frames: np.ndarray  # (N, nq) qpos snapshots, one per Motion sample
    times: np.ndarray  # (N,) virtual seconds, == motion["t"]
    qpos_home: np.ndarray
    mocap_home: np.ndarray
    human_start_t: float
    human_duration: float
    hold_t: float = END_HOLD_T

    @property
    def end_t(self) -> float:
        return float(self.times[-1])

    @property
    def cycle_t(self) -> float:
        return float(self.times[-1]) + self.hold_t


def build_playback(scenario: str = "knife_handover") -> Playback:
    """Load kitchen.xml at home and roll the scenario into replayable frames."""
    try:
        spec = SCENARIOS[scenario]
    except KeyError:
        raise KeyError(
            f"unknown scenario {scenario!r} (have: {sorted(SCENARIOS)})"
        ) from None
    model, data = load_scene("kitchen")
    frames: list[np.ndarray] = []

    def hook(m, sim, state, ts):
        frames.append(sim.qpos.copy())

    motion = plan_to_motion(model, data, spec["plan"],
                            derived_from=f"play:{scenario}", on_sample=hook)
    return Playback(
        scenario=scenario,
        model=model,
        data=data,
        motion=motion,
        frames=np.stack(frames),
        times=np.array(motion["t"], dtype=float),
        qpos_home=data.qpos.copy(),
        mocap_home=data.mocap_pos.copy(),
        human_start_t=spec["human_start_t"],
        human_duration=spec["human_duration"],
    )


def frame_index(pb: Playback, t: float) -> int:
    """Latest sample at or before motion-time t (clamped; holds past the end)."""
    idx = int(np.searchsorted(pb.times, t, side="right") - 1)
    return min(max(idx, 0), len(pb.frames) - 1)


def apply_at(pb: Playback, t: float) -> int:
    """Pose the robot from the Motion frame and drive the hand; returns idx."""
    idx = frame_index(pb, t)
    pb.data.qpos[:] = pb.frames[idx]
    pb.data.time = float(max(t, 0.0))
    # reach_to_counter's mj_forward covers the qpos above as well as the hand.
    reach_to_counter(pb.model, pb.data, t,
                     start_t=pb.human_start_t, duration=pb.human_duration)
    return idx


def reset(pb: Playback) -> int:
    """Restore the home state (robot + parked hand) for (re)play from t=0."""
    pb.data.mocap_pos[:] = pb.mocap_home
    return apply_at(pb, 0.0)


def run_viewer(pb: Playback, speed: float = 1.0,
               camera: str = "demo") -> None:
    """Play the scenario in a passive viewer, looping until quit."""
    import mujoco.viewer

    flags = {"paused": False, "restart": False, "quit": False}

    def key_callback(keycode: int) -> None:
        if keycode == KEY_SPACE:
            flags["paused"] = not flags["paused"]
            print("paused" if flags["paused"] else "resumed", flush=True)
        elif keycode == KEY_R:
            flags["restart"] = True
        elif keycode == KEY_Q:
            flags["quit"] = True

    viewer = mujoco.viewer.launch_passive(
        pb.model, pb.data, key_callback=key_callback)
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = pb.model.camera(camera).id
    print(f"{pb.scenario}: {pb.end_t:.2f} s motion at {speed}x, looping. "
          f"[space] pause  [R] restart  [Q] quit")
    reset(pb)
    t_play = 0.0
    last_wall = time.perf_counter()
    next_sync = last_wall
    try:
        while viewer.is_running() and not flags["quit"]:
            now = time.perf_counter()
            wall_dt = now - last_wall
            last_wall = now
            with viewer.lock():
                if flags["restart"]:
                    flags["restart"] = False
                    t_play = 0.0
                    reset(pb)
                elif not flags["paused"]:
                    # Paused skips apply_at entirely: reach_to_counter
                    # re-anchors to the current hand pose each call, so
                    # re-applying a frozen t would creep toward the target.
                    t_play += wall_dt * speed
                    if t_play >= pb.cycle_t:
                        t_play = 0.0
                        reset(pb)
                    else:
                        apply_at(pb, t_play)
            viewer.sync()
            next_sync += 1.0 / VIEW_FPS
            delay = next_sync - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_sync = time.perf_counter()  # slipped; don't spiral
    except KeyboardInterrupt:
        pass
    finally:
        viewer.close()


def record(pb: Playback, path: str | Path, speed: float = 1.0,
           fps: int = 30, camera: str = "demo") -> Path:
    """Render one playthrough to an mp4 (headless, no window)."""
    import imageio.v2 as imageio

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_frames = max(1, int(np.ceil(pb.cycle_t / speed * fps)))
    renderer = mujoco.Renderer(pb.model, height=HEIGHT, width=WIDTH)
    try:
        reset(pb)
        with imageio.get_writer(out, fps=fps, codec="libx264",
                                quality=8) as writer:
            for k in range(n_frames):
                apply_at(pb, min(k / fps * speed, pb.cycle_t))
                renderer.update_scene(pb.data, camera=camera)
                writer.append_data(renderer.render())
    finally:
        renderer.close()
    print(f"saved {out} ({n_frames} frames, {fps} fps, "
          f"{pb.cycle_t / speed:.1f} s)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play a scenario live in the MuJoCo viewer.")
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--speed", type=float, default=1.0,
                        help="playhead rate multiplier (0.5 = slow motion)")
    parser.add_argument("--record", default=None, metavar="OUT.mp4",
                        help="save a video instead of opening a window")
    parser.add_argument("--fps", type=int, default=30,
                        help="record-mode frame rate")
    parser.add_argument("--camera", default="demo",
                        help="viewer/record camera (default: demo)")
    args = parser.parse_args()
    if args.speed <= 0:
        parser.error("--speed must be > 0")
    pb = build_playback(args.scenario)
    if args.record:
        record(pb, args.record, speed=args.speed, fps=args.fps,
               camera=args.camera)
    else:
        run_viewer(pb, speed=args.speed, camera=args.camera)


if __name__ == "__main__":
    main()
