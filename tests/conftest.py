"""Suite-wide: learner event log to tmp; no real network in tests."""

import pytest


@pytest.fixture(autouse=True)
def _event_log_to_tmp(tmp_path, monkeypatch):
    from learner import events as learner_events

    monkeypatch.setattr(learner_events, "_path",
                        tmp_path / "events.jsonl")


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """B-09: fail any test whose HTTP leaves the machine.

    The OpenAI SDK rides on httpx, so guarding httpx.Client.send
    covers model calls and raw httpx alike; loopback stays open for
    the dashboard's own test server.
    """
    import httpx

    real_send = httpx.Client.send

    def _guard(self, request, **kwargs):
        if request.url.host not in _LOOPBACK:
            raise AssertionError(
                f"network call blocked in tests: "
                f"{request.method} {request.url}")
        return real_send(self, request, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", _guard)
