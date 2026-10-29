"""Suite-wide: keep the learner event log out of out/ during tests."""

import pytest


@pytest.fixture(autouse=True)
def _event_log_to_tmp(tmp_path, monkeypatch):
    from learner import events as learner_events

    monkeypatch.setattr(learner_events, "_path",
                        tmp_path / "events.jsonl")
