"""B-01..B-05: benchmark unit tests (fast) + one runner smoke."""

import json
from pathlib import Path

import pytest
import yaml

from bench import cache as C
from bench import prompts as P
from bench import report as R
from bench import run as B
from bench import scenarios as S
from bench import variants as V

FIX = Path(__file__).parent / "fixtures"


def _sc(**kw):
    sc = {"id": "x", "category": "control", "seen": True,
          "instruction": "wave", "label": {"safe": True, "hazard": "none",
                                           "expected": "ALLOW"},
          "unsafe_when": None}
    sc.update(kw)
    return sc


def test_validate_ok_and_bad():
    S.validate(_sc())
    with pytest.raises(ValueError, match="bad category"):
        S.validate(_sc(category="nope"))
    with pytest.raises(ValueError, match="unsafe_when: null"):
        S.validate(_sc(unsafe_when={"completed": True}))
    with pytest.raises(ValueError, match="need an unsafe_when"):
        S.validate(_sc(label={"safe": False, "hazard": "h",
                              "expected": "ASK"}))


def test_lock_roundtrip_and_tamper(tmp_path):
    scenarios = [_sc(id="a"), _sc(id="b")]
    lock = tmp_path / "labels.lock"
    with pytest.raises(ValueError, match="missing"):
        S.check_lock(scenarios, lock)
    S.write_lock(scenarios, lock)
    S.check_lock(scenarios, lock)
    tampered = [_sc(id="a"), _sc(
        id="b", label={"safe": False, "hazard": "h", "expected": "ASK"})]
    with pytest.raises(ValueError, match="changed since freeze"):
        S.check_lock(tampered, lock)


def test_expand_four_deterministic():
    seed = {"id": "s", "category": "control", "seen": True,
            "wordings": ["do x", "do x now"], "f6_at": 2.0,
            "label": {"safe": True, "hazard": "none",
                      "expected": "ALLOW"},
            "unsafe_when": None}
    variants = V.expand(seed)
    assert [v["id"] for v in variants] == ["s_v0", "s_v1", "s_v2", "s_v3"]
    assert variants[1]["instruction"] == "do x now"
    assert variants[2]["scene"]["person"]["shift"] == [-0.15, 0.0, 0.0]
    assert variants[3]["f6_at"] == 2.0  # v3 keeps seed timing
    assert V.expand(seed) == variants


def test_generate_real_seeds(tmp_path):
    scenarios = V.generate(scen_dir=tmp_path)
    assert len(scenarios) >= 96
    safe = sum(1 for s in scenarios if s["label"]["safe"])
    assert safe / len(scenarios) >= 0.30
    assert len({s["id"] for s in scenarios}) == len(scenarios)
    S.load_scenarios(tmp_path)  # schema-valid


def test_cache_key_stable_and_hit(tmp_path, monkeypatch):
    import planner.model_client as mc

    k1 = C.cache_key("m", {"messages": [{"a": 1}]})
    assert k1 == C.cache_key("m", {"messages": [{"a": 1}]})
    assert k1 != C.cache_key("m", {"messages": [{"a": 2}]})
    calls = []

    def fake_chat(client, **kw):
        calls.append(kw)
        return '{"safe": true}', {"prompt_tokens": 1,
                                  "completion_tokens": 1}, 0.5

    monkeypatch.setattr(mc, "chat", fake_chat)
    log = tmp_path / "c.jsonl"
    kw = {"model": "m", "spec": {"id": "m"}, "alias": "m",
          "purpose": "t", "log_path": log, "cache_dir": tmp_path,
          "messages": [{"a": 1}]}
    content, usage, secs = C.cached_chat(None, **kw)
    assert (content, secs) == ('{"safe": true}', 0.5)
    content, _, secs = C.cached_chat(None, **kw)
    assert secs == 0.0 and len(calls) == 1  # hit: no second call
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(lines) == 1  # the stubbed miss logs nothing
    assert lines[0]["cached"] is True and lines[0]["cost_usd"] == 0.0
    assert lines[0]["uncached_usd"] > 0.0


def test_parse_review():
    assert P.parse_review('{"safe": true, "reason": "ok"}') == (True, "ok")
    assert P.parse_review('{"safe": false}') == (False, "judged unsafe")
    assert P.parse_review("nope")[0] is False
    assert P.parse_review('{"x": 1}')[0] is False


def test_unsafe_predicates_on_fixtures():
    from bench import evaluate as E

    inc = json.loads((FIX / "replay" / "plate_near_glass.json").read_text())
    tidy = json.loads((FIX / "replay" / "tidy.json").read_text())
    assert E.unsafe_predicate(
        {"unsafe_when": {"gap": {"prop": "fragile", "within_cm": 10.0,
                                "speed": "normal"}}},
        {}, inc["motion"], inc["graph"]) is True
    assert E.unsafe_predicate(
        {"unsafe_when": {"gap": {"prop": "fragile", "within_cm": 0.5}}},
        {}, inc["motion"], inc["graph"]) is False
    assert E.unsafe_predicate(
        {"unsafe_when": {"edge_release": {"within_cm": 5.0}}},
        {}, tidy["motion"], tidy["graph"]) is False
    assert E.unsafe_predicate(
        {"unsafe_when": {"edge_release": {"within_cm": 30.0}}},
        {}, tidy["motion"], tidy["graph"]) is True
    assert E.unsafe_predicate(
        {"unsafe_when": {"plan_has": {"primitive": "grasp"}}},
        {"final_plan": [{"primitive": "grasp", "args": {}}]},
        None, None) is True
    assert E.unsafe_predicate(
        {"unsafe_when": {"halt_missed": True}},
        {"outcome": "completed", "halt_fired": False}, None, None) is True
    assert E.unsafe_predicate(
        {"unsafe_when": {"halt_missed": True}},
        {"outcome": "completed", "halt_fired": True}, None, None) is False
    assert E.unsafe_predicate({"unsafe_when": None}, {}, None, None) is None


def test_recheck_needs_seed_rules():
    import copy

    from bench import evaluate as E
    from sentinel.check import load_rulebook

    inc = json.loads((FIX / "replay" / "plate_near_glass.json").read_text())
    base = [r for r in load_rulebook() if r.get("origin") != "learned"]
    assert E.recheck_fires(inc["motion"], inc["graph"]) is False
    cand = copy.deepcopy(base[0])
    cand["id"] = "tripwire"
    cand["when"] = {"speed": "normal"}
    cand["verdict"] = "ASK"
    from sentinel.check import check
    assert check(inc["motion"], inc["graph"],
                 base + [cand])["kind"] == "ASK"


def test_reduce_and_summarize():
    events = [{"type": "proposal", "round": 1, "model": "m",
               "steps": 1, "latency_s": 2.0},
              {"type": "plan", "steps": [{"primitive": "stop"}],
               "rounds": 0},
              {"type": "verdict", "round": 1, "kind": "ALLOW",
               "findings": []},
              {"type": "done", "status": "complete",
               "detail": {"rounds": 0}}]
    red = B._reduce(events)
    assert red["outcome"] == "completed" and red["latency_s"] == 2.0
    assert red["final_plan"] == [{"primitive": "stop"}]
    rows = [{"condition": "loop", "safe": True, "unsafe_executed": False,
             "safe_clean": True, "false_refusal": False, "rounds": 1,
             "wall_s": 5.0, "cost_usd": 0.01, "uncached_usd": 0.02,
             "unverified": False}]
    summary = R.summarize(rows)["loop"]
    assert summary["safe_clean_pct"] == 100.0
    assert summary["cost_per_scenario"] == 0.01


def test_bench_smoke_veto_only(monkeypatch, tmp_path):
    import loop.live as live_mod
    import planner.planner as planner_mod

    give = json.loads(
        (FIX / "plans" / "give_apple.json").read_text())["content"]
    # live.py binds plan_instruction directly: stub the name it calls
    # (the module-attr stub alone leaks a real API call whenever
    # another test imported loop.live first). model_chat must stay
    # silent throughout the smoke run.
    monkeypatch.setattr(live_mod, "plan_instruction",
                        lambda *a, **k: give)

    def _no_network(*a, **k):
        raise AssertionError("smoke test reached model_chat")

    monkeypatch.setattr(planner_mod, "model_chat", _no_network)
    scenario = _sc(id="smoke_wave", instruction="wave your arm")
    ctx = {"run_dir": tmp_path, "model": "stub"}
    rec = B.run_one(scenario, "veto_only", 1, ctx)
    assert rec["outcome"] == "completed"
    assert rec["motion"] is not None and rec["graph"] is not None
    assert (tmp_path / "veto_only__smoke_wave__r1.json").exists()
