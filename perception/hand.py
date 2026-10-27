"""Human-hand velocity + short-horizon prediction. (G-05)

HandTrack consumes hand positions from any source (sim mocap here, SAM
"hand" detections later) and fits a constant-velocity model over a short
window. Prediction is linear extrapolation: exact for steady motion,
overshooting when the hand decelerates into a stop -- the conservative
direction for a safety layer (we over-estimate intrusion, never miss it).
"""

from __future__ import annotations

from collections import deque

import numpy as np

PREDICT_HORIZONS = (0.25, 0.5, 0.75, 1.0)  # seconds ahead
WINDOW = 5  # samples in the velocity fit


class HandTrack:
    """Constant-velocity track over recent (ts, pos) samples."""

    def __init__(self, horizons=PREDICT_HORIZONS, window: int = WINDOW):
        self.horizons = tuple(horizons)
        self.samples: deque = deque(maxlen=window)

    def update(self, ts: float, pos) -> dict:
        """Add one observation (stale timestamps ignored) + estimate."""
        pos = np.asarray(pos, dtype=float)
        if not self.samples or ts > self.samples[-1][0]:
            self.samples.append((float(ts), pos))
        return self.estimate()

    def estimate(self) -> dict:
        """{pos, velocity, predicted[]} from the current window."""
        if len(self.samples) < 2:
            p = self.samples[0][1] if self.samples else np.zeros(3)
            v = np.zeros(3)  # unknown velocity: assume static (honest)
        else:
            t = np.array([s for s, _ in self.samples])
            t = t - t[-1]  # centre for numerical stability
            p = self.samples[-1][1]
            v = np.array([np.polyfit(t, [q[i] for _, q in self.samples], 1)[0]
                          for i in range(3)])
        return {"pos": np.asarray(p).tolist(),
                "velocity": v.tolist(),
                "predicted": [(np.asarray(p) + v * h).tolist()
                              for h in self.horizons]}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Reach-in hand tracking demo.")
    parser.add_argument("--demo", choices=["reach"])
    args = parser.parse_args()
    if args.demo != "reach":
        parser.print_help()
        return
    from graph.scene_graph import (init_perception_graph, load_props,
                                   update_from_detections, update_hand_track)
    from perception.lift3d import Detection
    from sim.geometry import body_aabb
    from sim.human import reach_to_counter
    from sim.world import load_scene

    model, data = load_scene("kitchen")
    hid = model.body("human_hand").id
    g = init_perception_graph(model, data)
    # Perfect-perception stand-in: one exact detection per prop, so the
    # reached hand has objects to relate to (G-06 uses real SAM boxes).
    props = load_props()
    dets = []
    for name, spec in props["objects"].items():
        lo, hi = body_aabb(model, data, model.body(name).id)
        dets.append(Detection(prompt=spec["prompts"][0], conf=1.0,
                              box2d=(0, 0, 1, 1), centroid=(lo + hi) / 2,
                              bbox_min=lo, bbox_max=hi, n_points=1000))
    stats = update_from_detections(g, dets, ts=0.0)
    print(f"seeded {len(stats['assigned'])} objects "
          f"(dropped {len(stats['dropped'])})")
    track = HandTrack()
    dt, dur = 0.05, 2.0
    traj: dict[float, np.ndarray] = {}
    forecast = None
    steps = 0
    t = 0.0
    while t <= dur + 1e-9:
        reach_to_counter(model, data, t, start_t=0.0, duration=dur)
        pos = data.xpos[hid].copy()
        traj[round(t, 9)] = pos
        est = update_hand_track(g, track, t, pos)
        if forecast is None and abs(t - 1.0) < dt / 2:
            forecast = (t, [np.array(p) for p in est["predicted"]])
        steps += 1
        t = round(t + dt, 9)
    print(f"reach: {steps} steps over {dur}s, "
          f"park {traj[0.0].round(2).tolist()} -> "
          f"hover {traj[dur].round(2).tolist()}")
    print(f"final velocity: {np.array(est['velocity']).round(3).tolist()} m/s "
          f"(settled, expect ~0)")
    t_f, preds = forecast
    print(f"forecast from t={t_f:.2f}s vs actuals:")
    for h, pred in zip(PREDICT_HORIZONS, preds):
        err = float(np.linalg.norm(pred - traj[round(t_f + h, 9)])) * 100
        print(f"  +{h:.2f}s err {err:.1f} cm")
    print("hand relations after the reach:")
    for a, b, d in sorted(g.edges(data=True),
                         key=lambda e: (e[0], e[1], e[2]["type"])):
        if ("human_hand" in a or "human_hand" in b) and d["type"] in (
                "ON", "NEAR", "ABOVE", "INSIDE"):
            print(f"  {d['type']:6s} {a} {b} {d.get('dist_cm')} cm")


if __name__ == "__main__":
    main()
