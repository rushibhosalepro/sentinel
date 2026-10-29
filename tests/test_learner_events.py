"""R-01: event log unit tests (auto-redirected to tmp by conftest)."""

import json

from learner import events as learner_events


def _read(tmp_path):
    with open(tmp_path / "events.jsonl") as f:
        return [json.loads(line) for line in f]


def test_append_stamps_ts_and_id(tmp_path):
    e = learner_events.append_event({"kind": "verdict", "outcome": "ALLOW"})
    assert e["id"].startswith("ev-")
    assert e["ts"]
    rows = _read(tmp_path)
    assert len(rows) == 1 and rows[0]["id"] == e["id"]


def test_incidents_numbered_sequentially(tmp_path):
    a = learner_events.append_event({"kind": "incident", "text": "a"})
    b = learner_events.append_event({"kind": "incident", "text": "b"})
    assert (a["id"], a["incident_n"]) == ("inc-001", 1)
    assert (b["id"], b["incident_n"]) == ("inc-002", 2)


def test_compact_graph_keeps_ids_and_props():
    g = {"objects": {"wine_glass": {"label": "wine glass",
                                    "properties": ["FRAGILE"],
                                    "conf": 0.9, "pos": [0, 0, 0]},
                     "plate": {"label": "plate", "properties": []}},
         "people": {"owner": {}}}
    c = learner_events.compact_graph(g)
    assert c == {"objects": {"wine_glass": {"properties": ["FRAGILE"],
                                            "owner": None, "conf": 0.9},
                             "plate": {"properties": [],
                                       "owner": None, "conf": None}},
                 "people": ["owner"]}
    assert learner_events.compact_graph(None) is None


def test_read_events_roundtrip(tmp_path):
    learner_events.append_event({"kind": "verdict", "outcome": "ASK"})
    rows = learner_events.read_events()
    assert len(rows) == 1 and rows[0]["outcome"] == "ASK"
    assert learner_events.read_events(tmp_path / "missing.jsonl") == []
