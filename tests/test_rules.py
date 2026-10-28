"""C-01: rulebook files match the PLAN.md §4 Rule contract."""

import json
from pathlib import Path

RULES = Path(__file__).parent.parent / "sentinel" / "rules"

CONTRACT_KEYS = {"id", "when", "unless", "verdict", "hard", "fixable",
                 "constraint_hint", "reason", "origin", "learned_from",
                 "version"}


def _rules():
    out = []
    for path in sorted(RULES.rglob("*.json")):
        out.append((path, json.loads(path.read_text())))
    assert out, "no rules found"
    return out


def test_rule_files_match_contract():
    ids = set()
    for path, rule in _rules():
        assert set(rule) == CONTRACT_KEYS, path.name
        assert rule["verdict"] in {"ALLOW", "ASK", "BLOCK", "HALT"}
        assert rule["origin"] in {"handwritten", "learned"}
        assert isinstance(rule["when"], dict) and rule["when"]
        assert isinstance(rule["unless"], dict)
        assert isinstance(rule["version"], int) and rule["version"] >= 1
        assert rule["id"] not in ids, f"duplicate {rule['id']}"
        ids.add(rule["id"])


def test_hard_dir_means_hard():
    for path, rule in _rules():
        want_hard = path.parent.name == "hard"
        assert rule["hard"] is want_hard, path.name


def test_hard_block_never_gets_feedback():
    # PLAN.md §9 rule 2: a hard BLOCK is never sent back as feedback
    # (don't teach a jailbroken planner how to get around it). Soft
    # fixable findings may carry a constraint hint for replanning.
    for path, rule in _rules():
        if rule["hard"] and rule["verdict"] == "BLOCK":
            assert rule["fixable"] is False, path.name
            assert rule["constraint_hint"] == "", path.name


def test_expected_rule_ids():
    ids = {rule["id"] for _, rule in _rules()}
    assert ids == {"sharp_toward_person", "release_near_person_in_air",
                   "sharp_fast_near_person", "liquid_above_electronic",
                   "restricted_item", "unknown_object",
                   "scene_text_provenance", "person_in_path"}
