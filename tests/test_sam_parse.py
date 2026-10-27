"""P0-07: SAM responses replay from cache (no network) into box+mask+conf."""

import json

import pytest

from perception.sam import CACHE_DIR, parse_raw_output


def test_replay_empty_output():
    result = parse_raw_output("")
    assert len(result.records) == 0
    assert result.outcome.status == "completed"


def test_replay_cached_response():
    cached = sorted(CACHE_DIR.glob("sam_*.json"))
    if not cached:
        pytest.skip("no cached SAM response; run perception.sam --demo once")
    raw_output = json.loads(cached[0].read_text())["raw_output"]
    result = parse_raw_output(raw_output)
    boxes = [r for r in result.records if r.kind == "box"]
    masks = [r for r in result.records if r.kind == "mask"]
    assert boxes and masks
    assert all(b.confidence is not None for b in boxes)
    assert all(m.confidence is not None for m in masks)
