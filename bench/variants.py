"""B-01: deterministic seed expansion (bench/seeds/ -> bench/scenarios/).

Each seed yields 4 scenarios (~124 total): as-written, a wording
variant, the owner 15 cm nearer, and an object shift (or the owner
15 cm farther + a later intrusion for f6 seeds). No RNG: the output
is a pure function of the seeds. Run: uv run python -m bench.variants
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS_DIR = REPO_ROOT / "bench" / "seeds"
SCEN_DIR = REPO_ROOT / "bench" / "scenarios"

PERSON_NEAR = [-0.15, 0.0, 0.0]
PERSON_FAR = [0.15, 0.0, 0.0]
SHIFT_DX = 0.05


def _base_pos(object_id: str, preset: str | None):
    """Live position of an object after a preset (for +5 cm shifts)."""
    from loop.live import _apply_preset
    from sim.world import load_scene

    model, data = load_scene("kitchen")
    if preset:
        _apply_preset(model, data, {"qpos": data.qpos.copy()}, preset)
    p = data.xpos[model.body(object_id).id]
    return [round(float(v), 3) for v in p]


def _merge_scene(seed_scene: dict | None, objects: dict | None = None,
                 person_add: list | None = None) -> dict | None:
    scene = {"objects": dict((seed_scene or {}).get("objects") or {}),
             "person": dict((seed_scene or {}).get("person") or {})}
    if objects:
        scene["objects"].update(objects)
    if person_add is not None:
        cur = scene["person"].get("shift") or [0.0, 0.0, 0.0]
        scene["person"]["shift"] = [round(c + d, 3)
                                    for c, d in zip(cur, person_add)]
    if not scene["objects"] and not scene["person"]:
        return None
    if not scene["objects"]:
        del scene["objects"]
    if not scene["person"]:
        del scene["person"]
    return scene


def expand(seed: dict) -> list[dict]:
    """One seed -> 4 scenarios (v0..v3)."""
    out = []

    def make(vid, instruction, scene, f6_at):
        return {"id": f"{seed['id']}_v{vid}",
                "category": seed["category"], "seen": seed["seen"],
                "preset": seed.get("preset"),
                "scene": scene, "f6_at": f6_at,
                "attack": seed.get("attack"),
                "instruction": instruction, "label": seed["label"],
                "unsafe_when": seed.get("unsafe_when")}

    w0, w1 = seed["wordings"][0], seed["wordings"][1]
    base_scene = seed.get("scene")
    out.append(make(0, w0, base_scene, seed.get("f6_at")))
    out.append(make(1, w1, base_scene, seed.get("f6_at")))
    out.append(make(2, w0, _merge_scene(base_scene,
                                        person_add=PERSON_NEAR),
                    seed.get("f6_at")))
    if seed.get("shift_object"):
        oid = seed["shift_object"]
        pos = _base_pos(oid, seed.get("preset"))
        pos[0] = round(pos[0] + SHIFT_DX, 3)
        scene = _merge_scene(base_scene, objects={oid: pos})
    else:
        scene = _merge_scene(base_scene, person_add=PERSON_FAR)
    # v3 keeps the seed's f6_at: shifted intrusion timings fizzle.
    out.append(make(3, w0, scene, seed.get("f6_at")))
    return out


def load_seeds(seeds_dir=None) -> list[dict]:
    root = Path(seeds_dir) if seeds_dir else SEEDS_DIR
    seeds = []
    for file in sorted(root.glob("*.yaml")):
        with open(file) as f:
            for doc in yaml.safe_load_all(f):
                if doc is None:
                    continue
                if isinstance(doc, list):
                    seeds.extend(doc)
                else:
                    seeds.append(doc)
    return seeds


def generate(seeds_dir=None, scen_dir=None) -> list[dict]:
    """Expand every seed; write one YAML per category; return scenarios."""
    from bench.scenarios import validate

    root = Path(scen_dir) if scen_dir else SCEN_DIR
    root.mkdir(parents=True, exist_ok=True)
    for file in root.glob("*.yaml"):
        file.unlink()
    by_cat: dict[str, list] = {}
    for seed in load_seeds(seeds_dir):
        for sc in expand(seed):
            validate(sc)
            by_cat.setdefault(sc["category"], []).append(sc)
    for cat, scenarios in sorted(by_cat.items()):
        with open(root / f"{cat}.yaml", "w") as f:
            yaml.safe_dump_all(scenarios, f, sort_keys=False)
    all_scenarios = [s for cat in sorted(by_cat) for s in by_cat[cat]]
    safe = sum(1 for s in all_scenarios if s["label"]["safe"])
    print(f"{len(all_scenarios)} scenarios, "
          f"{100.0 * safe / len(all_scenarios):.0f}% safe")
    return all_scenarios


if __name__ == "__main__":
    generate()
