"""P0-07: SAM responses replay from a committed fixture (no network)."""

import json
from pathlib import Path

from perception.sam import parse_raw_output

FIXTURE = Path(__file__).parent / "fixtures" / "sam_mug_day1.json"


def test_replay_empty_output():
    result = parse_raw_output("")
    assert len(result.records) == 0
    assert result.outcome.status == "completed"


def test_replay_fixture_response():
    raw_output = json.loads(FIXTURE.read_text())["raw_output"]
    result = parse_raw_output(raw_output)
    boxes = [r for r in result.records if r.kind == "box"]
    masks = [r for r in result.records if r.kind == "mask"]
    assert boxes and masks
    assert all(b.confidence is not None for b in boxes)
    assert all(m.confidence is not None for m in masks)
