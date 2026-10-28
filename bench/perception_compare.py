"""G-10: text-prompt SAM vs Muse Spark+SAM on default/F3/F4. (G-10)

Renders 1280x960 perception frames, runs both methods (live API calls on
cache miss, pure replay after), scores every object (found / label right
/ surface-distance error / confidence), evaluates the G-06 gate, and
writes out/perception_report.md. F4 re-stages the default scene through
the live F3->F4 path, so its frame hash must equal default's.

Scoring (spatial, no trust in labels): for each truth object, the
method's graph node with that id scores found (present), label_ok
(within 25 cm of the truth box), err_cm (surface distance: 0 inside the
truth AABB, else the distance to it), and conf. Surface distance, not
origin distance: a mask lifts to the visible surface, which sits ~1
radius off the body origin on fat objects (the jug's front wall is 3.5
cm ahead of its origin). The G-06 gate needs every object label_ok with
err <= 3 cm and identical HAS edges to ground truth.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from graph.scene_graph import (
    ASSOC_GATE_M,
    build_ground_truth,
    init_perception_graph,
    load_props,
    update_from_detections,
)
from loop.live import CUP_NEAR_LAPTOP, _apply_preset
from perception.detect import detect_cache_path
from perception.detections import detections_from_cache
from perception.frames import WIDTH, HEIGHT, perception_frame
from perception.perceive import perceive_frame
from perception.sam import box_cache_path, draw_overlay, segment
from sim.geometry import body_aabb
from sim.world import load_scene

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "out"
CACHE_DIR = REPO_ROOT / "cache"
REPORT_PATH = OUT_DIR / "perception_report.md"

GATE_ERR_CM = 3.0

SCENES = ["default", "F3", "F4"]


def stage_scene(name: str):
    """Fresh kitchen + scene staging; returns (model, data, frame_note)."""
    model, data = load_scene("kitchen")
    if name == "default":
        return model, data, "home keyframe"
    home = {"qpos": data.qpos.copy()}
    _apply_preset(model, data, home, "cup_next_to_laptop")
    if name == "F3":
        return model, data, f"cup -> {CUP_NEAR_LAPTOP} (F3)"
    _apply_preset(model, data, home, "default")  # F4: back to default
    return model, data, "F3 then F4 restore (must equal default)"


def _new_cache_files(before: set) -> list[Path]:
    return sorted(p for p in CACHE_DIR.glob("*.json")
                  if p.name not in before)


def _call_kind(path: Path) -> str:
    if path.name.startswith("spark_"):
        return "spark_detect"
    if path.name.startswith("sam_box_"):
        return "sam_box"
    return "sam_text"


def primary_prompts(props: dict) -> list[str]:
    prompts = []
    for spec in props["objects"].values():
        p = spec.get("prompts", [spec["label"]])[0]
        if p not in prompts:
            prompts.append(p)
    return prompts


def run_method_a(model, data, frame, image_path, props) -> tuple:
    """Text-prompt SAM alone: primary prompt per object, one call each."""
    prompts = primary_prompts(props)
    for prompt in prompts:  # live on cache miss, replay after
        segment(image_path, prompt)
    dets = detections_from_cache(image_path, frame["depth"], frame["cam"],
                                 prompts=prompts)
    graph = init_perception_graph(model, data, props)
    update_from_detections(graph, dets, ts=data.time)
    return graph, dets


def run_method_b(model, data, frame, image_path, props) -> dict:
    """Muse Spark {label, box} + one multi-box SAM call."""
    return perceive_frame(model, data, frame, image_path, props)


def surface_dist(pos, lo, hi) -> float:
    """Distance from a point to an AABB (0 inside), in metres."""
    pos, lo, hi = (np.asarray(a, dtype=float) for a in (pos, lo, hi))
    return float(np.linalg.norm(np.maximum(lo - pos, 0.0)
                                + np.maximum(pos - hi, 0.0)))


def gt_boxes(model, data, props) -> dict:
    boxes = {}
    for oid in props["objects"]:
        lo, hi = body_aabb(model, data, model.body(oid).id)
        boxes[oid] = (np.asarray(lo, dtype=float),
                      np.asarray(hi, dtype=float))
    return boxes


def gt_properties(gt) -> dict:
    out = {}
    for node, attrs in gt.nodes(data=True):
        if attrs.get("type") == "object" and not attrs.get("static"):
            out[node] = sorted(
                b.split("prop:", 1)[1] for a, b, d in gt.edges(node, data=True)
                if d.get("type") == "HAS")
    return out


def score_graph(graph, boxes: dict, gt_props: dict, props: dict) -> dict:
    """Per-object found / label_ok / err_cm / ctr_cm / conf / props_ok."""
    rows = {}
    for oid in props["objects"]:
        node = graph.nodes.get(oid)
        if node is None or not node.get("tracked"):
            rows[oid] = {"found": False, "label_ok": False, "err_cm": None,
                         "ctr_cm": None, "conf": None, "props_ok": False}
            continue
        lo, hi = boxes[oid]
        err = surface_dist(node["pos"], lo, hi) * 100.0
        ctr = float(np.linalg.norm(np.asarray(node["pos"], dtype=float)
                                   - (lo + hi) / 2.0)) * 100.0
        label_ok = err <= ASSOC_GATE_M * 100.0
        mine = sorted(b.split("prop:", 1)[1]
                      for a, b, d in graph.edges(oid, data=True)
                      if d.get("type") == "HAS")
        rows[oid] = {"found": True, "label_ok": label_ok,
                     "err_cm": round(err, 2), "ctr_cm": round(ctr, 2),
                     "conf": round(float(node["conf"]), 2),
                     "props_ok": mine == gt_props.get(oid, [])}
    return rows


def gate_verdict(rows: dict) -> tuple[bool, list[str]]:
    problems = []
    for oid, r in rows.items():
        if not r["label_ok"]:
            problems.append(f"{oid}: "
                            + ("missing" if not r["found"]
                               else f"err {r['err_cm']} cm > 25 cm"))
        elif r["err_cm"] > GATE_ERR_CM:
            problems.append(f"{oid}: err {r['err_cm']} cm > 3 cm")
        elif not r["props_ok"]:
            problems.append(f"{oid}: properties mismatch")
    return not problems, problems


def fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def scene_table(rows_a: dict, rows_b: dict) -> list[str]:
    lines = ["| object | text-SAM found | label | err cm | ctr cm | conf | "
             "Spark+SAM found | label | err cm | ctr cm | conf |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for oid in rows_a:
        a, b = rows_a[oid], rows_b[oid]
        lines.append(f"| {oid} | {fmt(a['found'])} | {fmt(a['label_ok'])} | "
                     f"{fmt(a['err_cm'])} | {fmt(a['ctr_cm'])} | "
                     f"{fmt(a['conf'])} | "
                     f"{fmt(b['found'])} | {fmt(b['label_ok'])} | "
                     f"{fmt(b['err_cm'])} | {fmt(b['ctr_cm'])} | "
                     f"{fmt(b['conf'])} |")
    return lines + [""]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare text-SAM vs Spark+SAM perception (G-10).")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore caches and call the APIs")
    parser.add_argument("--save-fixtures", default=None, metavar="DIR",
                        help="copy default-scene Spark + SAM-box caches "
                             "there as test fixtures")
    args = parser.parse_args()
    props = load_props()

    if args.refresh:
        for p in list(CACHE_DIR.glob("spark_*.json")) \
                + list(CACHE_DIR.glob("sam_*.json")):
            p.unlink()

    report: list[str] = [
        "# Perception report (G-10)", "",
        f"Date: {datetime.date.today().isoformat()}  ",
        f"Models: Spark `muse-spark-1.3` (minimal) + SAM `sam-3.1`  ",
        f"Frames: {WIDTH}x{HEIGHT} from `front`  ", ""]
    cache_before = {p.name for p in CACHE_DIR.glob("*.json")} \
        if CACHE_DIR.exists() else set()
    all_live: list[Path] = []
    gate_all_ok, gate_notes = True, []
    frame_hashes = {}

    for scene in SCENES:
        model, data, note = stage_scene(scene)
        frame = perception_frame(model, data)
        image_path = OUT_DIR / f"perception_{scene.lower()}.png"
        Image.fromarray(frame["rgb"]).save(image_path)
        sha = hashlib.sha256(image_path.read_bytes()).hexdigest()[:16]
        frame_hashes[scene] = sha
        gt = build_ground_truth(model, data, props)
        boxes = gt_boxes(model, data, props)
        gt_props = gt_properties(gt)

        graph_a, _ = run_method_a(model, data, frame, image_path, props)
        out_b = run_method_b(model, data, frame, image_path, props)
        rows_a = score_graph(graph_a, boxes, gt_props, props)
        rows_b = score_graph(out_b["graph"], boxes, gt_props, props)
        ok, problems = gate_verdict(rows_b)
        gate_all_ok &= ok
        gate_notes.append((scene, ok, problems))

        overlay = draw_overlay(frame["rgb"],
                                 _box_result(image_path, out_b))
        overlay.save(OUT_DIR / f"perception_{scene.lower()}_overlay.png")

        report.append(f"## Scene {scene} ({note})")
        report.append(f"Frame: `out/perception_{scene.lower()}.png` "
                      f"(sha {sha})  ")
        report.append(f"Overlay: `out/perception_{scene.lower()}_overlay.png`"
                      "  ")
        report.append("")
        report.extend(scene_table(rows_a, rows_b))
        n_a = sum(r["label_ok"] for r in rows_a.values())
        n_b = sum(r["label_ok"] for r in rows_b.values())
        print(f"{scene}: text-SAM {n_a}/11 label-ok, "
              f"Spark+SAM {n_b}/11 label-ok")

    from perception.sam import cache_path
    touched: dict[str, Path] = {}  # every cache file this run consumed
    for scene in SCENES:
        image_path = OUT_DIR / f"perception_{scene.lower()}.png"
        for prompt in primary_prompts(props):
            p = cache_path(image_path, prompt)
            touched[p.name] = p
        p = detect_cache_path(image_path)
        touched[p.name] = p
        spark_dets = json.loads(p.read_text())
        boxes = [d["box"] for d in
                 json.loads(spark_dets["content"])["detections"]]
        p = box_cache_path(image_path, boxes)
        touched[p.name] = p

    def _tally(paths) -> tuple:
        kinds: dict[str, int] = {}
        prompt_tokens = completion_tokens = 0
        for p in paths:
            kinds[_call_kind(p)] = kinds.get(_call_kind(p), 0) + 1
            usage = json.loads(p.read_text()).get("usage") or {}
            prompt_tokens += usage.get("prompt_tokens") \
                or usage.get("input_tokens") or 0
            completion_tokens += usage.get("completion_tokens") \
                or usage.get("output_tokens") or 0
        return kinds, prompt_tokens, completion_tokens

    all_live = _new_cache_files(cache_before)
    kinds, prompt_tokens, completion_tokens = _tally(all_live)
    fresh_kinds, fresh_pt, fresh_ct = _tally(touched.values())

    report.append("## G-06 gate (Spark+SAM)")
    report.append("")
    for scene, ok, problems in gate_notes:
        report.append(f"- {scene}: **{'PASS' if ok else 'FAIL'}**" + (
            "" if ok else " — " + "; ".join(problems)))
    report.append("")
    report.append(f"Gate: **{'PASS' if gate_all_ok else 'FAIL'}** "
                  f"(every object found, err <= {GATE_ERR_CM:.0f} cm, "
                  f"sharp/liquid/electronic correct)")
    report.append("")
    def _cost(kinds, pt, ct) -> tuple[float, float, int]:
        sam_calls = kinds.get("sam_text", 0) + kinds.get("sam_box", 0)
        spark = pt / 1e6 * 1.25 + ct / 1e6 * 4.25
        return spark, sam_calls * 2.5 / 1000, sam_calls

    spark_cost, sam_cost, sam_calls = _cost(
        kinds, prompt_tokens, completion_tokens)
    fresh_spark, fresh_sam, fresh_sam_calls = _cost(
        fresh_kinds, fresh_pt, fresh_ct)
    report.append("## Cost of this run")
    report.append("")
    if all_live:
        report.append(f"Live API calls: {len(all_live)} "
                      f"({', '.join(f'{k} x{v}' for k, v in sorted(kinds.items()))})  ")
    else:
        report.append("Live API calls: 0 (full cache replay)  ")
    report.append(f"Spark tokens: {prompt_tokens} prompt + "
                  f"{completion_tokens} completion "
                  f"(~${spark_cost:.4f} @ $1.25/$4.25 per M)  ")
    report.append(f"SAM images: {sam_calls} (~${sam_cost:.4f} @ $2.50 "
                  f"per 1K images)  ")
    report.append(f"**Total: ~${spark_cost + sam_cost:.4f}** "
                  f"(Spark Standard pricing; SAM per MetaEra launch "
                  f"pricing; SAM reports no token usage)")
    report.append(f"Fresh-run value of the caches consumed: "
                  f"~${fresh_spark + fresh_sam:.4f} "
                  f"({len(touched)} calls: "
                  f"{', '.join(f'{k} x{v}' for k, v in sorted(fresh_kinds.items()))}; "
                  f"spark {fresh_pt}+{fresh_ct} tokens)")
    report.append("")
    report.append("## Notes")
    report.append("")
    report.append("- err cm is the surface distance: 0 when the perceived "
                  "base point lands inside the truth box. Masks lift to "
                  "the visible surface, ~1 radius off the body origin on "
                  "fat objects, so origin distance would mis-score them.")
    report.append("- ctr cm is the centre distance: perceived base point "
                  "to the truth box centre. It runs hot on tall/wide "
                  "objects (the base point is not the centre); the gate "
                  "uses surface distance.")
    f4_match = frame_hashes["F4"] == frame_hashes["default"]
    report.append("- F4 re-stages default through the live F3->F4 path; "
                  f"frame sha {'matches' if f4_match else 'DIFFERS'} "
                  f"(default {frame_hashes['default']}, "
                  f"F3 {frame_hashes['F3']}, F4 {frame_hashes['F4']}).")
    report.append("- Known limitation: SAM segments the laptop base top, "
                  "not the screen, so the perceived laptop box misses the "
                  "screen's -y / +z extent (x edges, used by the cup "
                  "preset geometry, are correct).")
    REPORT_PATH.write_text("\n".join(report) + "\n")
    print(f"wrote {REPORT_PATH}")
    print(f"G-06 gate: {'PASS' if gate_all_ok else 'FAIL'}")
    print(f"live calls: {len(all_live)} {dict(kinds)}; "
          f"spark tokens {prompt_tokens}+{completion_tokens}")

    if args.save_fixtures:
        dest = Path(args.save_fixtures)
        dest.mkdir(parents=True, exist_ok=True)
        default_png = OUT_DIR / "perception_default.png"
        spark_src = detect_cache_path(default_png)
        shutil.copy(spark_src, dest / "spark_default.json")
        spark_dets = json.loads(spark_src.read_text())
        boxes = [d["box"] for d in
                 json.loads(spark_dets["content"])["detections"]]
        shutil.copy(box_cache_path(default_png, boxes),
                    dest / "sam_box_default.json")
        print(f"saved fixtures to {dest}")


def _box_result(image_path: Path, out_b: dict):
    """Re-parse the cached box result for the overlay (no network)."""
    from perception.sam import parse_raw_output
    boxes = [d["box"] for d in out_b["spark"]]
    cached = box_cache_path(image_path, boxes)
    return parse_raw_output(json.loads(cached.read_text())["raw_output"])


if __name__ == "__main__":
    main()
