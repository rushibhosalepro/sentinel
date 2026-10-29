"""B-02/B-04: benchmark runner (conditions x scenarios x repeats).

Usage: uv run python -m bench.run --condition loop --repeat 3 --jobs 4
Resumable (existing result files are skipped); refuses unless
labels.lock matches. Planner calls are cached by prompt hash
(bench/cache/); costs land per-result; the event log is redirected
under the run dir so out/events.jsonl stays clean.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "bench" / "runs"

CONDITIONS = {
    # planner executes: build errors retry, verdicts never replan
    "naive": {"max_rounds": 3, "verdict_final": True,
              "skip_check": True, "passive_monitor": True,
              "reviewer": None},
    "self_check": {"max_rounds": 3, "verdict_final": True,
                   "skip_check": True, "passive_monitor": True,
                   "reviewer": "self_check"},
    "spark_judge": {"max_rounds": 3, "verdict_final": True,
                    "skip_check": True, "passive_monitor": True,
                    "reviewer": "spark_judge"},
    "wonder_judge": {"max_rounds": 3, "verdict_final": True,
                     "skip_check": True, "passive_monitor": True,
                     "reviewer": "wonder_judge"},
    # one static check, then execute iff ALLOW (passive monitor)
    "veto_only": {"max_rounds": 3, "verdict_final": True,
                  "skip_check": False, "passive_monitor": True,
                  "reviewer": None},
    # full LLM x Sentinel loop (active monitor, 3 replans)
    "loop": {"max_rounds": None, "verdict_final": False,
             "skip_check": False, "passive_monitor": False,
             "reviewer": None},
}

CORE = ["naive", "veto_only", "loop", "spark_judge"]


def _reduce(events: list[dict]) -> dict:
    plans = [e["steps"] for e in events if e["type"] == "plan"]
    verdicts = [{"round": e["round"], "kind": e["kind"],
                 "rules": [f.get("rule") for f in e["findings"]]}
                for e in events if e["type"] == "verdict"]
    halts = [e for e in events if e["type"] == "halt"]
    dones = [e for e in events if e["type"] == "done"]
    done = dones[-1] if dones else {"status": "error", "detail": {}}
    status = done["status"]
    if status == "complete":
        outcome = "completed"
    elif status in ("BLOCK", "ASK", "refused"):
        outcome = "refused"
    else:
        outcome = "error"
    rounds = done["detail"].get("rounds")
    if rounds is None:
        plan_rounds = [e.get("rounds", 0) for e in events
                       if e["type"] == "plan"]
        rounds = max(plan_rounds + [0])
    latency = round(sum(e.get("latency_s", 0.0)
                        for e in events if e["type"] == "proposal"), 1)
    return {"outcome": outcome, "done_status": status,
            "done_detail": done["detail"],
            "verdicts": verdicts, "final_plan": plans[-1] if plans else None,
            "halt_fired": any(not h.get("passive") for h in halts),
            "would_halt": any(h.get("passive") for h in halts),
            "rounds": rounds, "latency_s": latency}


def run_one(scenario: dict, condition: str, repeat: int, ctx: dict) -> dict:
    """Run one cell; write the result file; return the record."""
    from bench import cache as bench_cache
    from bench.evaluate import rebuild_motion
    from bench.prompts import make_reviewer
    from dashboard.events import to_jsonable
    from loop.live import _run_headless

    bench_cache.set_repeat(repeat)  # B-06: independent repeats per thread
    run_dir = ctx["run_dir"]
    stem = f"{condition}__{scenario['id']}__r{repeat}"
    out_path = run_dir / f"{stem}.json"
    if out_path.exists():
        return {"skipped": True, "path": str(out_path)}
    cfg = CONDITIONS[condition]
    cost_log = run_dir / f"{stem}.costs.jsonl"
    reviewer = None
    if cfg["reviewer"] is not None:
        reviewer = make_reviewer(cfg["reviewer"],
                                 planner_model=ctx["model"],
                                 log_path=cost_log)
    events: list[dict] = []
    t0 = time.perf_counter()
    error = None
    try:
        _run_headless(
            scenario["instruction"], str(run_dir / "video" / stem),
            preset=scenario.get("preset"), f6_at=scenario.get("f6_at"),
            perception="truth", planner_model=ctx["model"],
            attack=scenario.get("attack"), sink=events.append,
            render=False, scene=scenario.get("scene"),
            max_rounds=cfg["max_rounds"], skip_check=cfg["skip_check"],
            reviewer=reviewer, passive_monitor=cfg["passive_monitor"],
            cost_log=cost_log, verdict_final=cfg["verdict_final"],
            repeat=repeat)
    except SystemExit:
        pass
    except Exception as e:  # noqa: BLE001 - one bad cell never kills a run
        error = f"{type(e).__name__}: {e}"
    wall = round(time.perf_counter() - t0, 1)
    rec = _reduce(events)
    rec.update({"scenario": scenario["id"], "condition": condition,
                "repeat": repeat, "wall_s": wall,
                "model": ctx["model"], "transport_error": error,
                "review_calls": reviewer.calls if reviewer else []})
    if rec["latency_s"] is not None and reviewer:
        rec["latency_s"] = round(rec["latency_s"] + sum(
            c.get("latency_s", 0.0) for c in reviewer.calls), 1)
    motion, graph = None, None
    if rec["final_plan"] is not None:
        try:
            motion, graph = rebuild_motion(scenario, rec["final_plan"])
        except Exception as e:  # noqa: BLE001 - recorded, scored later
            rec["rebuild_error"] = f"{type(e).__name__}: {e}"
    rec["motion"] = to_jsonable(motion) if motion else None
    rec["graph"] = to_jsonable(graph) if graph else None
    out_path.write_text(json.dumps(rec))
    print(f"{condition} {scenario['id']} r{repeat}: {rec['outcome']} "
          f"({wall}s)", flush=True)
    return rec


def main(argv=None) -> int:
    from bench import cache as bench_cache
    from bench.scenarios import check_lock, load_scenarios
    from learner import events as learner_events
    import planner.planner as planner_mod

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", action="append", default=None,
                        help=f"repeatable; default: {','.join(CORE)}")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--model", default="muse-spark-1.3-contributor")
    parser.add_argument("--filter", default=None,
                        help="only scenario ids containing this substring")
    parser.add_argument("--only-ids", default=None,
                        help="comma-separated exact scenario ids (B-11 "
                        "unseen-split reruns)")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    conditions = args.condition or CORE
    for c in conditions:
        if c not in CONDITIONS:
            print(f"unknown condition {c!r} (have {sorted(CONDITIONS)})")
            return 2
    scenarios = load_scenarios()
    if args.filter:
        scenarios = [s for s in scenarios if args.filter in s["id"]]
    if args.only_ids:
        want = {i.strip() for i in args.only_ids.split(",") if i.strip()}
        scenarios = [s for s in scenarios if s["id"] in want]
        missing = want - {s["id"] for s in scenarios}
        if missing:
            print(f"unknown scenario ids: {sorted(missing)}")
            return 2
    if not scenarios:
        print("no scenarios selected")
        return 2
    try:
        check_lock(load_scenarios())
    except ValueError as e:
        print(f"labels not frozen: {e}")
        return 2
    run_id = args.run_id or datetime.datetime.now().strftime("%m%d-%H%M")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "meta.json").write_text(json.dumps({
        "run_id": run_id, "conditions": conditions,
        "repeats": args.repeat, "model": args.model,
        "scenarios": [s["id"] for s in scenarios]}))
    learner_events.set_log_path(run_dir / "events.jsonl")
    planner_mod.model_chat = bench_cache.cached_chat
    ctx = {"run_dir": run_dir, "model": args.model}
    cells = [(s, c, r) for s in scenarios for c in conditions
             for r in range(1, args.repeat + 1)]
    print(f"run {run_id}: {len(cells)} cells, {args.jobs} jobs")
    with futures.ThreadPoolExecutor(
            max_workers=args.jobs) as pool:
        futs = [pool.submit(run_one, s, c, r, ctx)
                for s, c, r in cells]
        for fut in futures.as_completed(futs):
            fut.result()  # raises nothing (run_one is total), reaps errors
    print(f"run {run_id} done: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
