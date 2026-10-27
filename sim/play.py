"""Real knife hand-over scenarios live in the MuJoCo viewer. (S-07)

Timeline per scenario: approach (robot plan) -> offer (robot holds the knife
while the hand closes in) -> transfer (within TAKE_DIST of the handle, the
knife attaches to the hand) -> retreat (robot home, person carries the knife
back). If the hand never arrives within HANDOVER_TIMEOUT, the robot keeps
holding and the scenario holds ("hand-over not taken").

The human is fully scripted, so the take time resolves identically at build
and live: build_handover() simulates the wait once on a scratch copy (fixing
the loop/record timeline) and playback executes it; the transfer offset itself
is always computed from live poses, so attachment is exact by construction.

Usage:
    uv run python -m sim.play knife_handover_safe     # handle-first, slow
    uv run python -m sim.play knife_handover_unsafe   # blade-first
    uv run python -m sim.play knife_handover_safe --speed 0.5
    uv run python -m sim.play knife_handover_safe --record out/safe.mp4
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from sim.human import park_pos, reach_to_counter, retreat_to_park
from sim.ik import DOWN_QUAT, mat_to_quat_wxyz, quat_wxyz_to_mat
from sim.motion import (
    KNIFE_HANDOVER_PLAN,
    KNIFE_HANDOVER_SAFE_PLAN,
    plan_to_motion,
)
from sim.primitives import free_qposadr
from sim.world import HEIGHT, WIDTH, load_scene

# GLFW key codes (stable ABI; letters are physical keys, shift-independent).
KEY_SPACE = 32
KEY_R = 82
KEY_Q = 81

VIEW_FPS = 60  # viewer sync cap; the playhead itself tracks the wall clock
END_HOLD_T = 1.0  # hold the final state before looping (s, scenario-time)

KNIFE_BODY = "chef_knife"
HANDLE_GEOM = "chef_knife_handle"
HAND_BODY = "human_hand"
ROBOT_HAND = "hand"

TAKE_DIST = 0.05  # palm-to-handle distance that triggers the transfer (m)
HANDOVER_TIMEOUT = 5.0  # give up waiting this long after the robot arrives
REACH_DURATION = 2.0
RETREAT_DURATION = 2.0
RESOLVE_DT = 0.05
LIFT_CLEAR = 0.15  # retract lift before returning home (m)

SCENARIOS = {
    "knife_handover_safe": {"plan": KNIFE_HANDOVER_SAFE_PLAN},
    "knife_handover_unsafe": {"plan": KNIFE_HANDOVER_PLAN},
}


@dataclass
class Handover:
    scenario: str
    model: mujoco.MjModel
    data: mujoco.MjData
    approach_motion: dict
    approach_frames: np.ndarray
    approach_times: np.ndarray
    retract_motion: dict
    retract_frames: np.ndarray
    retract_times: np.ndarray
    handle_end: np.ndarray  # world pos of the handle at the offer
    human_start_t: float
    reach_origin: np.ndarray  # fixed hand-path start (grid-independent)
    retreat_origin: np.ndarray | None  # hand pose at take (captured live)
    take_tau: float | None  # resolved transfer time (None = not taken)
    qpos_home: np.ndarray
    mocap_pos_home: np.ndarray
    mocap_quat_home: np.ndarray
    timeout: float = HANDOVER_TIMEOUT
    hold_t: float = END_HOLD_T
    transfer_offset: np.ndarray | None = None  # T_hand^-1 @ T_knife at take
    transferred: bool = False

    @property
    def t_arrive(self) -> float:
        return float(self.approach_times[-1])

    @property
    def t_retract(self) -> float:
        return float(self.retract_times[-1])

    @property
    def cycle_t(self) -> float:
        if self.take_tau is None:
            return self.t_arrive + self.timeout + self.hold_t
        return (self.take_tau + max(self.t_retract, RETREAT_DURATION)
                + self.hold_t)


def _frame_at(times: np.ndarray, frames: np.ndarray, t: float) -> np.ndarray:
    idx = int(np.searchsorted(times, t, side="right") - 1)
    return frames[min(max(idx, 0), len(frames) - 1)]


def rollout_frames(model, data, plan, derived_from=None, on_sample=None,
                   initial_held: str | None = None):
    """Dry-run a plan, capturing robot qpos per Motion sample. (L-00)

    Shared by the handover scenarios and the live loop: returns
    (motion, frames, times). `on_sample` sees each dry-run sample too.
    `initial_held` starts the rollout already holding that body.
    """
    frames = []

    def hook(m, sim, state, ts):
        frames.append(sim.qpos.copy())
        if on_sample is not None:
            on_sample(m, sim, state, ts)

    motion = plan_to_motion(model, data, plan, derived_from,
                            on_sample=hook, initial_held=initial_held)
    return motion, np.stack(frames), np.array(motion["t"], dtype=float)


def handle_pos(model: mujoco.MjModel, data: mujoco.MjData) -> np.ndarray:
    return data.geom_xpos[model.geom(HANDLE_GEOM).id].copy()


def handover_dist(model: mujoco.MjModel, data: mujoco.MjData) -> float:
    """Palm-centre to knife-handle distance (the release condition)."""
    palm = data.xpos[model.body(HAND_BODY).id]
    return float(np.linalg.norm(palm - handle_pos(model, data)))


def _se3(pos: np.ndarray, quat_wxyz: np.ndarray) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = quat_wxyz_to_mat(quat_wxyz)
    t[:3, 3] = pos
    return t


def attach_to_hand(model, data, obj_body: str,
                   hand_body: str = HAND_BODY) -> np.ndarray:
    """Kinematic attach offset T_hand^-1 @ T_obj (grasp's offset logic)."""
    hid = model.body(hand_body).id
    oid = model.body(obj_body).id
    t_hand = _se3(data.xpos[hid], data.xquat[hid])
    t_obj = _se3(data.xpos[oid], data.xquat[oid])
    return np.linalg.inv(t_hand) @ t_obj


def drag_with_hand(model, data, obj_body: str, offset: np.ndarray,
                   hand_body: str = HAND_BODY) -> None:
    """Pose obj from the hand via a transfer offset; forwards."""
    hid = model.body(hand_body).id
    t = _se3(data.xpos[hid], data.xquat[hid]) @ offset
    adr = free_qposadr(model, obj_body)
    data.qpos[adr:adr + 3] = t[:3, 3]
    data.qpos[adr + 3:adr + 7] = mat_to_quat_wxyz(t[:3, :3])
    mujoco.mj_forward(model, data)


def resolve_take(model: mujoco.MjModel, home: mujoco.MjData,
                 end_qpos: np.ndarray, t_arrive: float, target: np.ndarray,
                 start_t: float, origin: np.ndarray,
                 duration: float = REACH_DURATION,
                 timeout: float = HANDOVER_TIMEOUT,
                 dt: float = RESOLVE_DT) -> float | None:
    """Simulate the wait on a scratch copy; take time or None on timeout."""
    scratch = mujoco.MjData(model)
    mujoco.mj_copyData(scratch, model, home)
    t = 0.0
    while t <= t_arrive + timeout + 1e-9:
        if t >= t_arrive:
            scratch.qpos[:] = end_qpos  # robot arrived, holds the offer
        reach_to_counter(model, scratch, t, start_t, duration,
                         target, face=target, origin=origin)
        if t >= t_arrive and handover_dist(model, scratch) < TAKE_DIST:
            return t
        t += dt
    print(f"hand-over not taken (hand never within {TAKE_DIST * 100:.0f} cm)")
    return None


def retract_plan(home_pos, home_quat, hover_pos, hover_quat,
                 serves: str = "give me the knife",
                 tag: str = "",
                 via_pos=None) -> list[dict]:
    """Lift and return home. (S-07, reused live.)

    Turned + via_pos (live): retrace the approach back to the carry site
    (the exact reverse of the offer move), flip down there (the reverse of
    the s4b turn: the one point proven in both orientations), then home.
    Turned without via (S-07 baked): legacy lift, un-turn at the lift, home.
    """
    hover_quat = np.asarray(hover_quat, dtype=float)
    lift = np.asarray(hover_pos, dtype=float) + np.array([0, 0, LIFT_CLEAR])
    down = np.asarray(DOWN_QUAT, dtype=float)
    turned = abs(float(np.dot(hover_quat / np.linalg.norm(hover_quat),
                              down / np.linalg.norm(down)))) < 0.99
    home_pos = np.asarray(home_pos, dtype=float)
    home_quat = np.asarray(home_quat, dtype=float)
    steps = []
    if turned and via_pos is not None:
        via = np.asarray(via_pos, dtype=float)
        # move_to is single-endpoint IK: a 180° flip is one giant seed jump
        # for the local solver (config drift after the offer excursion makes
        # it fail). Two 90° hops keep every solve near its seed.
        half = (Rotation.from_euler("z", 90, degrees=True)
                * Rotation.from_matrix(quat_wxyz_to_mat(down))).as_matrix()
        half_quat = mat_to_quat_wxyz(half)
        steps.append(
            {"id": f"{tag}r0", "primitive": "move_to",
             "args": {"pose": [*via, *hover_quat]},
             "serves_instruction": serves,
             "why": "retrace the offer back to the carry site"})
        steps.append(
            {"id": f"{tag}r1h", "primitive": "move_to",
             "args": {"pose": [*via, *half_quat]},
             "serves_instruction": serves,
             "why": "un-turn halfway where the turn happened"})
        steps.append(
            {"id": f"{tag}r1", "primitive": "move_to",
             "args": {"pose": [*via, *down]},
             "serves_instruction": serves,
             "why": "finish the un-turn"})
    elif turned:
        steps.append(
            {"id": f"{tag}r0", "primitive": "move_to",
             "args": {"pose": [*lift, *hover_quat]},
             "serves_instruction": serves,
             "why": "lift clear after the hand takes the knife"})
        steps.append(
            {"id": f"{tag}r1", "primitive": "move_to",
             "args": {"pose": [*lift, *down]},
             "serves_instruction": serves,
             "why": "un-turn to the carry orientation"})
    else:
        steps.append(
            {"id": f"{tag}r1", "primitive": "move_to",
             "args": {"pose": [*lift, *hover_quat]},
             "serves_instruction": serves,
             "why": "lift clear after the hand takes the knife"})
        steps.append(
            {"id": f"{tag}r2", "primitive": "move_to",
             "args": {"pose": [*home_pos, *home_quat]},
             "serves_instruction": serves,
             "why": "retract to home"})
    if turned:
        steps.append(
            {"id": f"{tag}r2", "primitive": "move_to",
             "args": {"pose": [*home_pos, *home_quat]},
             "serves_instruction": serves,
             "why": "retract to home"})
    steps.append(
        {"id": f"{tag}r3", "primitive": "stop", "args": {},
         "serves_instruction": serves,
         "why": "rest at home"})
    return steps


def build_handover(scenario: str) -> Handover:
    """Dry-run approach + retract and resolve the take; live data stays home."""
    try:
        plan = SCENARIOS[scenario]["plan"]
    except KeyError:
        raise KeyError(
            f"unknown scenario {scenario!r} (have: {sorted(SCENARIOS)})"
        ) from None
    model, data = load_scene("kitchen")
    qpos_home = data.qpos.copy()
    mocap_pos_home = data.mocap_pos.copy()
    mocap_quat_home = data.mocap_quat.copy()
    hand_id = model.body(ROBOT_HAND).id
    home_pos, home_quat = data.xpos[hand_id].copy(), data.xquat[hand_id].copy()

    handle_end = None

    def track_handle(m, sim, state, ts):
        nonlocal handle_end
        handle_end = handle_pos(m, sim)

    approach, frames_a, times_a = rollout_frames(
        model, data, plan, f"play:{scenario}", track_handle)
    t_arrive = float(times_a[-1])
    human_start = t_arrive  # the person starts reaching as the robot offers
    reach_origin = park_pos(model)
    take = resolve_take(model, data, frames_a[-1], t_arrive, handle_end,
                        human_start, reach_origin)

    tmp = mujoco.MjData(model)
    mujoco.mj_copyData(tmp, model, data)
    tmp.qpos[:] = frames_a[-1]
    mujoco.mj_forward(model, tmp)
    hover_pos = tmp.xpos[hand_id].copy()
    hover_quat = tmp.xquat[hand_id].copy()
    start = mujoco.MjData(model)
    mujoco.mj_copyData(start, model, data)
    start.qpos[:] = frames_a[-1]  # knife rests at the offer, robot released
    retract, rframes, times_r = rollout_frames(
        model, start, retract_plan(
            home_pos, home_quat, hover_pos, hover_quat),
        f"play:{scenario}:retract")

    hb = Handover(
        scenario=scenario, model=model, data=data,
        approach_motion=approach, approach_frames=frames_a,
        approach_times=times_a, retract_motion=retract,
        retract_frames=rframes, retract_times=times_r,
        handle_end=handle_end, human_start_t=human_start,
        reach_origin=reach_origin, retreat_origin=None, take_tau=take,
        qpos_home=qpos_home, mocap_pos_home=mocap_pos_home,
        mocap_quat_home=mocap_quat_home)
    if take is None:
        print(f"{scenario}: offer at {t_arrive:.2f} s, "
              f"cycle {hb.cycle_t:.2f} s (holding)")
    else:
        print(f"{scenario}: offer at {t_arrive:.2f} s, take at {take:.2f} s, "
              f"cycle {hb.cycle_t:.2f} s")
    return hb


def _drive_reach(hb: Handover, tau: float) -> None:
    reach_to_counter(hb.model, hb.data, tau, hb.human_start_t,
                     REACH_DURATION, hb.handle_end, face=hb.handle_end,
                     origin=hb.reach_origin)


def _transfer(hb: Handover, tau: float) -> None:
    """Kinematic attach: knife follows the hand (grasp's offset logic)."""
    hb.transfer_offset = attach_to_hand(hb.model, hb.data, KNIFE_BODY)
    hb.retreat_origin = hb.data.xpos[
        hb.model.body(HAND_BODY).id].copy()
    hb.transferred = True
    print(f"hand-over taken at t={tau:.2f} s")


def _drag_knife(hb: Handover) -> None:
    drag_with_hand(hb.model, hb.data, KNIFE_BODY, hb.transfer_offset)


def apply_at(hb: Handover, tau: float) -> str:
    """Step the scenario to time tau; returns the phase name."""
    tau = max(float(tau), 0.0)
    data = hb.data
    if hb.take_tau is None:  # timeout timeline: offer, then hold
        if tau < hb.t_arrive:
            data.qpos[:] = _frame_at(hb.approach_times, hb.approach_frames,
                                     tau)
            data.time = tau
            _drive_reach(hb, tau)
            return "approach"
        data.qpos[:] = hb.approach_frames[-1]
        data.time = tau
        _drive_reach(hb, tau)
        return "holding"
    if tau < hb.t_arrive:
        data.qpos[:] = _frame_at(hb.approach_times, hb.approach_frames, tau)
        data.time = tau
        _drive_reach(hb, tau)
        return "approach"
    if tau < hb.take_tau:
        data.qpos[:] = hb.approach_frames[-1]
        data.time = tau
        _drive_reach(hb, tau)
        return "offer"
    if not hb.transferred:
        data.qpos[:] = hb.approach_frames[-1]
        data.time = tau
        _drive_reach(hb, tau)
        _transfer(hb, tau)
    dt = tau - hb.take_tau
    data.qpos[:] = _frame_at(hb.retract_times, hb.retract_frames, dt)
    data.time = tau
    retreat_to_park(hb.model, data, tau, start_t=hb.take_tau,
                    duration=RETREAT_DURATION, origin=hb.retreat_origin)
    _drag_knife(hb)
    return "retreat"


def reset(hb: Handover) -> str:
    """Restore the home state (robot + person) for (re)play from t=0."""
    hb.data.qpos[:] = hb.qpos_home
    hb.data.mocap_pos[:] = hb.mocap_pos_home
    hb.data.mocap_quat[:] = hb.mocap_quat_home
    hb.data.time = 0.0
    hb.transferred = False
    hb.transfer_offset = None
    hb.retreat_origin = None
    mujoco.mj_forward(hb.model, hb.data)
    return "approach"


def run_viewer(hb: Handover, speed: float = 1.0,
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
        hb.model, hb.data, key_callback=key_callback)
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = hb.model.camera(camera).id
    print(f"{hb.scenario}: {hb.cycle_t:.2f} s cycle at {speed}x, looping. "
          f"[space] pause  [R] restart  [Q] quit")
    reset(hb)
    t_play, phase = 0.0, "approach"
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
                    phase = reset(hb)
                elif not flags["paused"]:
                    # Paused skips apply_at entirely (the hand paths use
                    # fixed origins, so re-applying would be idempotent,
                    # but there is no reason to spend the cycles).
                    t_play += wall_dt * speed
                    if t_play >= hb.cycle_t:
                        t_play = 0.0
                        phase = reset(hb)
                    else:
                        phase = apply_at(hb, t_play)
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


def record(hb: Handover, path: str | Path, speed: float = 1.0,
           fps: int = 30, camera: str = "demo") -> Path:
    """Render one playthrough to an mp4 (headless, no window)."""
    import imageio.v2 as imageio

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_frames = max(1, int(np.ceil(hb.cycle_t / speed * fps)))
    renderer = mujoco.Renderer(hb.model, height=HEIGHT, width=WIDTH)
    try:
        reset(hb)
        with imageio.get_writer(out, fps=fps, codec="libx264",
                                quality=8) as writer:
            for k in range(n_frames):
                apply_at(hb, min(k / fps * speed, hb.cycle_t))
                renderer.update_scene(hb.data, camera=camera)
                writer.append_data(renderer.render())
    finally:
        renderer.close()
    print(f"saved {out} ({n_frames} frames, {fps} fps, "
          f"{hb.cycle_t / speed:.1f} s)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play a hand-over scenario live in the MuJoCo viewer.")
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
    hb = build_handover(args.scenario)
    if args.record:
        record(hb, args.record, speed=args.speed, fps=args.fps,
               camera=args.camera)
    else:
        run_viewer(hb, speed=args.speed, camera=args.camera)


if __name__ == "__main__":
    main()
