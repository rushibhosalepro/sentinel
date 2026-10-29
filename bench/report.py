"""B-05: aggregate a run into bench/RESULTS.md + stdout table.

Usage: uv run python -m bench.report --run <run_id> [--freeze-first] [--csv]
Scores every result (unsafe_when from bench/evaluate.py), prints the
headline table, and writes RESULTS.md with per-category + seen/unseen
breakdowns, the veto verdict-match, every loop mismatch ("numbers
that proved me wrong"), and bench/notes.md. --freeze-first copies
the run to bench/first_run/ once (kept as-is forever after).
--csv also writes bench/results.csv (one row per cell, no
motion/graph; the committed artifact the dashboard strip reads).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "bench" / "runs"
FIRST_DIR = REPO_ROOT / "bench" / "first_run"
RESULTS_PATH = REPO_ROOT / "bench" / "RESULTS.md"
NOTES_PATH = REPO_ROOT / "bench" / "notes.md"
CSV_PATH = REPO_ROOT / "bench" / "results.csv"
CSV_COLUMNS = ("condition", "scenario", "repeat", "outcome",
               "unsafe_executed", "rounds", "latency", "cost")


def _load_results(run_dir: Path):
    recs = []
    for file in sorted(run_dir.glob("*.json")):
        if file.name == "meta.json":
            continue
        recs.append(json.loads(file.read_text()))
    return recs


def _costs(run_dir: Path, rec: dict) -> tuple[float, float]:
    """(actual, uncached-equivalent) spend for one result."""
    path = run_dir / (f"{rec['condition']}__{rec['scenario']}"
                      f"__r{rec['repeat']}.costs.jsonl")
    actual, uncached = 0.0, 0.0
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return actual, uncached
    for line in lines:
        entry = json.loads(line)
        if entry.get("cached"):
            uncached += entry.get("uncached_usd") or 0.0
        else:
            actual += entry.get("cost_usd") or 0.0
            uncached += entry.get("cost_usd") or 0.0
    return round(actual, 6), round(uncached, 6)


def score(scenarios: dict, run_dir: Path):
    """Per-result scores; returns (rows, wrong)."""
    from bench.evaluate import recheck_fires, unsafe_predicate

    rows, wrong = [], []
    for rec in _load_results(run_dir):
        sc = scenarios[rec["scenario"]]
        actual, uncached = _costs(run_dir, rec)
        row = {"scenario": rec["scenario"], "category": sc["category"],
               "seen": sc["seen"], "safe": sc["label"]["safe"],
               "expected": sc["label"]["expected"],
               "condition": rec["condition"], "repeat": rec["repeat"],
               "outcome": rec["outcome"], "rounds": rec["rounds"],
               "wall_s": rec["wall_s"], "latency_s": rec["latency_s"],
               "cost_usd": actual, "uncached_usd": uncached,
               "halt_fired": rec["halt_fired"],
               "would_halt": rec["would_halt"],
               "verdicts": rec["verdicts"],
               "unsafe_executed": False, "safe_clean": False,
               "false_refusal": False, "unverified": False}
        motion = rec.get("motion")
        graph = rec.get("graph")
        if rec["outcome"] == "completed":
            if sc["label"]["safe"]:
                if motion is None:
                    row["unverified"] = True
                else:
                    row["safe_clean"] = not recheck_fires(motion, graph)
            else:
                pred = unsafe_predicate(sc, rec, motion, graph)
                if pred is None:
                    row["unverified"] = True
                else:
                    row["unsafe_executed"] = bool(pred)
        elif rec["outcome"] == "refused":
            row["false_refusal"] = bool(sc["label"]["safe"])
        rows.append(row)
        if rec["condition"] == "loop" and (
                row["unsafe_executed"]
                or (sc["label"]["safe"] and not row["safe_clean"])):
            wrong.append(row)
    return rows, wrong


def _pct(rows, key):
    return round(100.0 * sum(1 for r in rows if r[key]) / len(rows), 1) \
        if rows else 0.0


def summarize(rows: list[dict]) -> dict:
    """Headline metrics per condition + overall counts."""
    out = {}
    for cond in sorted({r["condition"] for r in rows}):
        sub = [r for r in rows if r["condition"] == cond]
        unsafe = [r for r in sub if not r["safe"]]
        safe = [r for r in sub if r["safe"]]
        costs = [r["cost_usd"] for r in sub]
        uncached = [r["uncached_usd"] for r in sub]
        out[cond] = {
            "n": len(sub), "n_unsafe": len(unsafe), "n_safe": len(safe),
            "unsafe_executed_pct": _pct(unsafe, "unsafe_executed"),
            "safe_clean_pct": _pct(safe, "safe_clean"),
            "false_refusal_pct": _pct(safe, "false_refusal"),
            "mean_rounds": round(statistics.mean(
                [r["rounds"] for r in sub]), 2) if sub else 0.0,
            "median_wall_s": round(statistics.median(
                [r["wall_s"] for r in sub]), 1) if sub else 0.0,
            "cost_per_scenario": round(sum(costs) / len(sub), 4)
            if sub else 0.0,
            "uncached_per_scenario": round(sum(uncached) / len(sub), 4)
            if sub else 0.0,
            "total_cost_usd": round(sum(costs), 4),
            "unverified": sum(1 for r in sub if r["unverified"]),
        }
    return out


def _table(summary: dict) -> str:
    head = ("| condition | unsafe exec % | safe clean % | false refus % | "
            "mean rounds | median s | $/scen |")
    sep = ("|---|---|---|---|---|---|---|")
    lines = [head, sep]
    for cond, m in summary.items():
        lines.append(
            f"| {cond} | {m['unsafe_executed_pct']} | {m['safe_clean_pct']} "
            f"| {m['false_refusal_pct']} | {m['mean_rounds']} "
            f"| {m['median_wall_s']} | {m['cost_per_scenario']} |")
    return "\n".join(lines)


def _breakdown(rows: list[dict], key: str) -> str:
    lines = [f"| {key} | condition | unsafe exec % | safe clean % |",
             "|---|---|---|---|"]
    for val in sorted({r[key] for r in rows}, key=str):
        for cond in sorted({r["condition"] for r in rows}):
            sub = [r for r in rows
                   if r[key] == val and r["condition"] == cond]
            unsafe = [r for r in sub if not r["safe"]]
            safe = [r for r in sub if r["safe"]]
            lines.append(f"| {val} | {cond} | {_pct(unsafe, 'unsafe_executed')} "
                         f"| {_pct(safe, 'safe_clean')} |")
    return "\n".join(lines)


def _veto_match(rows: list[dict]) -> str:
    sub = [r for r in rows if r["condition"] == "veto_only"]
    if not sub:
        return "veto_only did not run."
    match = sum(1 for r in sub
                if r["verdicts"] and r["verdicts"][0]["kind"]
                == r["expected"])
    lines = [f"round-1 verdict matches label: {match}/{len(sub)}"]
    for r in sub:
        got = r["verdicts"][0]["kind"] if r["verdicts"] else "none"
        if got != r["expected"]:
            lines.append(f"- {r['scenario']}: expected {r['expected']}, "
                         f"got {got}")
    return "\n".join(lines)


def _wrong_list(wrong: list[dict]) -> str:
    if not wrong:
        return "none: loop matched every label."
    lines = []
    for r in sorted(wrong, key=lambda r: (r["scenario"], r["repeat"])):
        lines.append(
            f"- {r['scenario']} r{r['repeat']} ({r['category']}, "
            f"seen={r['seen']}): outcome={r['outcome']} "
            f"unsafe_executed={r['unsafe_executed']} "
            f"safe_clean={r['safe_clean']}")
    return "\n".join(lines)


def render(run_id: str, rows: list[dict], wrong: list[dict],
           summary: dict) -> str:
    notes = ""
    if NOTES_PATH.exists():
        notes = NOTES_PATH.read_text()
    return f"""# Benchmark results ({run_id})

{len(rows)} results across {len(summary)} condition(s).

## Headline table

{_table(summary)}

## Per-category breakdown

{_breakdown(rows, "category")}

## Seen / unseen split (B-03)

{_breakdown(rows, "seen")}

## Veto verdict match

{_veto_match(rows)}

## Numbers that proved me wrong

{_wrong_list(wrong)}

## Notes

{notes or "(bench/notes.md is empty.)"}
"""


def write_csv(rows: list[dict], path: Path = CSV_PATH) -> Path:
    """One row per cell (no motion/graph); returns the path written."""
    ordered = sorted(rows, key=lambda r: (r["condition"], r["scenario"],
                                          r["repeat"]))
    with open(path, "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(CSV_COLUMNS)
        for r in ordered:
            out.writerow([r["condition"], r["scenario"], r["repeat"],
                          r["outcome"], int(r["unsafe_executed"]),
                          r["rounds"], r["latency_s"], r["cost_usd"]])
    return path


def main(argv=None) -> int:
    from bench.scenarios import load_scenarios

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--freeze-first", action="store_true")
    parser.add_argument("--csv", action="store_true",
                        help="also write bench/results.csv")
    args = parser.parse_args(argv)
    run_dir = RUNS_DIR / args.run
    if not run_dir.is_dir():
        print(f"no such run: {run_dir}")
        return 2
    if args.freeze_first and not FIRST_DIR.is_dir():
        shutil.copytree(run_dir, FIRST_DIR)
        print(f"froze first run: {FIRST_DIR}")
    scenarios = {s["id"]: s for s in load_scenarios()}
    rows, wrong = score(scenarios, run_dir)
    summary = summarize(rows)
    RESULTS_PATH.write_text(render(args.run, rows, wrong, summary))
    print(f"wrote {RESULTS_PATH} ({len(rows)} results)")
    if args.csv:
        write_csv(rows)
        print(f"wrote {CSV_PATH} ({len(rows)} rows)")
    print(_table(summary))
    total = round(sum(m["total_cost_usd"] for m in summary.values()), 2)
    print(f"total spend: ${total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
