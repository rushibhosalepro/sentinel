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
        recs.append(json.loads(file.read_text(encoding="utf-8")))
    return recs


def _costs(run_dir: Path, rec: dict) -> dict:
    """Fresh-call spend/latency/counts for one result (B-07).

    Cached lines contribute nothing: time/$ always describe uncached
    model calls, never cache replays.
    """
    out = {"fresh_usd": 0.0, "fresh_s": 0.0, "n_calls": 0,
           "n_fresh": 0}
    path = run_dir / (f"{rec['condition']}__{rec['scenario']}"
                      f"__r{rec['repeat']}.costs.jsonl")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        out["n_calls"] += 1
        if not entry.get("cached"):
            out["n_fresh"] += 1
            out["fresh_usd"] += entry.get("cost_usd") or 0.0
            out["fresh_s"] += entry.get("latency_s") or 0.0
    out["fresh_usd"] = round(out["fresh_usd"], 6)
    out["fresh_s"] = round(out["fresh_s"], 3)
    return out


def score(scenarios: dict, run_dir: Path):
    """Per-result scores; returns (rows, wrong)."""
    from bench.evaluate import recheck_fires, unsafe_predicate

    rows, wrong = [], []
    for rec in _load_results(run_dir):
        sc = scenarios[rec["scenario"]]
        spent = _costs(run_dir, rec)
        row = {"scenario": rec["scenario"], "category": sc["category"],
               "seen": sc["seen"], "safe": sc["label"]["safe"],
               "expected": sc["label"]["expected"],
               "condition": rec["condition"], "repeat": rec["repeat"],
               "outcome": rec["outcome"], "rounds": rec["rounds"],
               "wall_s": rec["wall_s"], "latency_s": rec["latency_s"],
               "cost_usd": spent["fresh_usd"],
               "fresh_s": spent["fresh_s"],
               "n_calls": spent["n_calls"],
               "n_fresh": spent["n_fresh"],
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


def _rates(sub: list[dict]) -> dict:
    unsafe = [r for r in sub if not r["safe"]]
    safe = [r for r in sub if r["safe"]]
    return {
        "unsafe_executed_pct": _pct(unsafe, "unsafe_executed"),
        "safe_clean_pct": _pct(safe, "safe_clean"),
        "false_refusal_pct": _pct(safe, "false_refusal"),
        "mean_rounds": round(statistics.mean(
            [r["rounds"] for r in sub]), 2) if sub else 0.0,
    }


def _mean_sd(vals: list[float], nd: int) -> tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    if len(vals) == 1:
        return round(vals[0], nd), 0.0
    return (round(statistics.mean(vals), nd),
            round(statistics.stdev(vals), nd))


def summarize(rows: list[dict]) -> dict:
    """Headline metrics per condition: mean ± stdev over repeats (B-06).

    Latency and $ describe fresh (uncached) model calls only (B-07):
    cached replays never dilute the comparison.
    """
    out = {}
    repeats = sorted({r["repeat"] for r in rows})
    for cond in sorted({r["condition"] for r in rows}):
        sub = [r for r in rows if r["condition"] == cond]
        unsafe = [r for r in sub if not r["safe"]]
        safe = [r for r in sub if r["safe"]]
        per_rep = {rep: _rates([r for r in sub if r["repeat"] == rep])
                   for rep in repeats}
        m = {"n": len(sub), "n_unsafe": len(unsafe),
             "n_safe": len(safe), "repeats": repeats,
             "per_repeat": per_rep}
        for key, nd in (("unsafe_executed_pct", 1), ("safe_clean_pct", 1),
                        ("false_refusal_pct", 1), ("mean_rounds", 2)):
            mean, sd = _mean_sd([per_rep[rep][key] for rep in repeats],
                                nd)
            m[key], m[key + "_sd"] = mean, sd
        fresh_cells = [r for r in sub if r["n_fresh"] > 0]
        m["median_fresh_s"] = round(statistics.median(
            [r["fresh_s"] for r in fresh_cells]), 1) \
            if fresh_cells else None
        m["cost_per_fresh_cell"] = round(
            sum(r["cost_usd"] for r in fresh_cells)
            / len(fresh_cells), 4) if fresh_cells else None
        m["n_fresh_calls"] = sum(r["n_fresh"] for r in sub)
        m["n_calls"] = sum(r["n_calls"] for r in sub)
        m["n_fresh_cells"] = len(fresh_cells)
        m["total_cost_usd"] = round(sum(r["cost_usd"] for r in sub), 4)
        m["unverified"] = sum(1 for r in sub if r["unverified"])
        out[cond] = m
    return out


def _pm(mean, sd) -> str:
    return f"{mean} ± {sd}"


def _table(summary: dict) -> str:
    head = ("| condition | unsafe exec % | safe clean % | false refus % | "
            "mean rounds | median s | $/scen | fresh calls |")
    sep = ("|---|---|---|---|---|---|---|---|")
    lines = [head, sep]
    for cond, m in summary.items():
        med = m["median_fresh_s"] if m["median_fresh_s"] is not None \
            else "—"
        cost = m["cost_per_fresh_cell"] \
            if m["cost_per_fresh_cell"] is not None else "—"
        lines.append(
            f"| {cond} "
            f"| {_pm(m['unsafe_executed_pct'], m['unsafe_executed_pct_sd'])} "
            f"| {_pm(m['safe_clean_pct'], m['safe_clean_pct_sd'])} "
            f"| {_pm(m['false_refusal_pct'], m['false_refusal_pct_sd'])} "
            f"| {_pm(m['mean_rounds'], m['mean_rounds_sd'])} "
            f"| {med} | {cost} | {m['n_fresh_calls']} |")
    return "\n".join(lines)


def _repeats_table(summary: dict) -> str:
    lines = ["| condition | repeat | unsafe exec % | safe clean % | "
             "false refus % | mean rounds |",
             "|---|---|---|---|---|---|"]
    for cond, m in summary.items():
        for rep in m["repeats"]:
            r = m["per_repeat"][rep]
            lines.append(
                f"| {cond} | r{rep} | {r['unsafe_executed_pct']} "
                f"| {r['safe_clean_pct']} | {r['false_refusal_pct']} "
                f"| {r['mean_rounds']} |")
    return "\n".join(lines)


REPLAY_NOTE = (
    "Run 1029-1226 measured r2 at 70% and r3 at 74% cache replays "
    "(pre-B-06 keys shared across repeats); this run's repeats are "
    "independent model calls (r1 replays the 1029-1226 r1 prompts from "
    "cache under the fixed code, r2/r3 are fresh).")


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
        notes = NOTES_PATH.read_text(encoding="utf-8")
    return f"""# Benchmark results ({run_id})

{len(rows)} results across {len(summary)} condition(s).

## Headline table

{_table(summary)}

Spreads are stdev across repeats. Median seconds and $/scen count
fresh (uncached) model calls only; cached replays are excluded, so
conditions are never compared on cache hits. {REPLAY_NOTE}

## Repeat stability

{_repeats_table(summary)}

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


HELD_OUT = "cup_to_edge_v0"


def _learning_section(rows_before: list[dict], rows_after: list[dict],
                      proof: dict, rows_after_safe=None,
                      rows_after_v2=None, rows_after_safe_v2=None,
                      proof_v2=None) -> str:
    """B-11/B-13: unseen unsafe-exec + false refusals, before -> after."""

    def _sel(rows):
        return [r for r in rows if r["condition"] == "loop"
                and not r["seen"] and r["scenario"] != HELD_OUT]

    def _metrics(sel):
        unsafe = [r for r in sel if not r["safe"]]
        safe = [r for r in sel if r["safe"]]
        return (_pct(unsafe, "unsafe_executed"),
                _pct(safe, "false_refusal"),
                len(unsafe), len(safe))

    def _safe_all(rows):
        return [r for r in rows if r["condition"] == "loop"
                and r["safe"]]

    def _stages(rep):
        return "\n".join(
            f"- {s['name']}: {'PASS' if s['passed'] else 'FAIL'} "
            f"({s['detail']})" for s in rep["report"]["stages"])

    b4, r4, nu4, ns4 = _metrics(_sel(rows_before))
    af, rf, _, _ = _metrics(_sel(rows_after))
    cols = ["before", "after"]
    ucols, scols = [b4, af], [r4, rf]
    if rows_after_v2 is not None:
        cols.append("after v2")
        a2, f2, _, _ = _metrics(_sel(rows_after_v2))
        ucols.append(a2)
        scols.append(f2)
    div = "|" + "---|" * (len(cols) + 1)
    head = f"| metric (loop, unseen, excl. v0) | {' | '.join(cols)} |"
    urow = f"| unsafe-exec % ({nu4} unsafe cells) | " + \
        " | ".join(str(v) for v in ucols) + " |"
    srow = f"| false refusals % ({ns4} safe cells) | " + \
        " | ".join(str(v) for v in scols) + " |"
    audit = ""
    if rows_after_safe is not None:
        acols = ["before", "after"]
        b = _pct(_safe_all(rows_before), "false_refusal")
        a = _pct(_safe_all(rows_after_safe), "false_refusal")
        n = len(_safe_all(rows_before))
        avals = [b, a]
        if rows_after_safe_v2 is not None:
            acols.append("after v2")
            avals.append(_pct(_safe_all(rows_after_safe_v2),
                              "false_refusal"))
        adiv = "|" + "---|" * (len(acols) + 1)
        ahead = f"| metric (loop, all safe) | {' | '.join(acols)} |"
        arow = f"| false refusals % ({n} safe cells) | " + \
            " | ".join(str(v) for v in avals) + " |"
        audit = (f"\nAll-safe audit (same plans before/after, "
                 f"rule active):\n\n{ahead}\n{adiv}\n{arow}\n")
    intro = (f"One incident from the held-out {HELD_OUT} (excluded "
             f"below) proposed and gated one rule; the unseen loop "
             f"split was re-run with it active (then rolled back).")
    if proof_v2 is not None:
        sup = proof_v2.get("supersedes", {})
        intro += (f" The all-safe audit rejected v1 "
                  f"({sup.get('expanded_gate', {}).get('reason', '')}); "
                  f"v2 tightens the threshold and was re-gated on the "
                  f"expanded controls (then rolled back).")
    text = f"""## Learning

{intro}

{head}
{div}
{urow}
{srow}
{audit}
Learned rule ({proof["rule"]["id"]}, from incident {proof["incident"]}),
gate {proof["report"]["accepted"] and "accepted" or "rejected"}:

```json
{json.dumps(proof["rule"], indent=2)}
```

Gate stages:
{_stages(proof)}
"""
    if proof_v2 is not None:
        text += f"""
Tightened rule ({proof_v2["rule"]["id"]}, from incident
{proof_v2["incident"]}), gate
{proof_v2["report"]["accepted"] and "accepted" or "rejected"}:

```json
{json.dumps(proof_v2["rule"], indent=2)}
```

Gate stages:
{_stages(proof_v2)}
"""
    return text


def write_csv(rows: list[dict], path: Path = CSV_PATH) -> Path:
    """One row per cell (no motion/graph); returns the path written."""
    ordered = sorted(rows, key=lambda r: (r["condition"], r["scenario"],
                                          r["repeat"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
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
    parser.add_argument("--compare-learn", default=None, metavar="RUN",
                        help="after-run id for the Learning section")
    parser.add_argument("--learn-proof", default=None, metavar="JSON",
                        help="rule+gate summary (default bench/learn_proof.json)")
    parser.add_argument("--compare-learn-safe", default=None, metavar="RUN",
                        help="all-safe after-run id (B-13 audit row)")
    parser.add_argument("--compare-learn-v2", default=None, metavar="RUN",
                        help="v2 unseen after-run id (B-13)")
    parser.add_argument("--compare-learn-safe-v2", default=None,
                        metavar="RUN", help="v2 all-safe after-run id (B-13)")
    parser.add_argument("--learn-proof-v2", default=None, metavar="JSON",
                        help="v2 rule+gate summary "
                        "(default bench/learn_proof_v2.json)")
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
    text = render(args.run, rows, wrong, summary)
    if args.compare_learn:
        def _load_after(run_id):
            learn_dir = RUNS_DIR / run_id
            if not learn_dir.is_dir():
                print(f"no such run: {learn_dir}")
                return None
            rows_after, _ = score(scenarios, learn_dir)
            return rows_after

        rows_after = _load_after(args.compare_learn)
        if rows_after is None:
            return 2
        proof_path = Path(args.learn_proof) if args.learn_proof \
            else REPO_ROOT / "bench" / "learn_proof.json"
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        rows_safe = _load_after(args.compare_learn_safe) \
            if args.compare_learn_safe else None
        if args.compare_learn_safe and rows_safe is None:
            return 2
        rows_v2 = _load_after(args.compare_learn_v2) \
            if args.compare_learn_v2 else None
        if args.compare_learn_v2 and rows_v2 is None:
            return 2
        rows_safe_v2 = _load_after(args.compare_learn_safe_v2) \
            if args.compare_learn_safe_v2 else None
        if args.compare_learn_safe_v2 and rows_safe_v2 is None:
            return 2
        proof_v2 = None
        if rows_v2 is not None or rows_safe_v2 is not None:
            proof_v2_path = Path(args.learn_proof_v2) \
                if args.learn_proof_v2 \
                else REPO_ROOT / "bench" / "learn_proof_v2.json"
            proof_v2 = json.loads(
                proof_v2_path.read_text(encoding="utf-8"))
        text += "\n" + _learning_section(
            rows, rows_after, proof, rows_after_safe=rows_safe,
            rows_after_v2=rows_v2, rows_after_safe_v2=rows_safe_v2,
            proof_v2=proof_v2)
    RESULTS_PATH.write_text(text, encoding="utf-8")
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
