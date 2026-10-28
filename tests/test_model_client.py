"""L-01: model aliases, retry/backoff, cost log. (No network: mocked.)"""

import json
from unittest.mock import MagicMock, patch

import openai
import pytest

from planner.model_client import (
    MODELS,
    chat,
    cost_usd,
    get_client,
    log_cost,
    resolve,
)


def _response(content='{"steps": []}', pt=100, ct=50):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = MagicMock(prompt_tokens=pt, completion_tokens=ct,
                           total_tokens=pt + ct)
    return resp


def _error(cls):
    if issubclass(cls, (openai.APITimeoutError, openai.APIConnectionError)):
        return cls(request=MagicMock())
    return cls(message="boom", response=MagicMock(status_code=500),
               body=None)


def test_resolve_aliases():
    alias, spec = resolve("spark")
    assert (alias, spec["id"]) == ("spark", "muse-spark-1.3")
    alias, spec = resolve("spark-open")
    assert spec["id"] == "meta-models/muse-spark-open"
    assert spec["base_url"] == "https://inference.baseten.co/v1"
    assert spec["key_env"] == "BASETEN_API_KEY"


def test_resolve_passthrough_and_default(monkeypatch):
    alias, spec = resolve("muse-spark-1.3-contributor")
    assert (alias, spec["id"]) == ("spark", "muse-spark-1.3-contributor")
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    assert resolve(None)[0] == "spark"
    monkeypatch.setenv("PLANNER_MODEL", "spark-open")
    assert resolve(None)[0] == "spark-open"


def test_cost_usd():
    assert cost_usd(1_000_000, 1_000_000, MODELS["spark"]) == 5.5
    assert cost_usd(None, 10, MODELS["spark"]) is None


def test_get_client_missing_key(monkeypatch):
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    with patch("planner.model_client.load_dotenv", lambda *a, **k: None):
        with pytest.raises(RuntimeError, match="BASETEN_API_KEY"):
            get_client("spark-open")


def test_chat_retries_transient_then_succeeds(tmp_path):
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _error(openai.RateLimitError), _error(openai.APITimeoutError),
        _response()]
    with patch("planner.model_client.time.sleep") as nap:
        content, usage, _ = chat(
            client, model="m", spec=MODELS["spark"], alias="spark",
            purpose="test", log_path=tmp_path / "c.jsonl",
            messages=[{"role": "user", "content": "hi"}])
    assert content == '{"steps": []}'
    assert usage["prompt_tokens"] == 100
    assert client.chat.completions.create.call_count == 3
    assert [c.args[0] for c in nap.call_args_list] == [1.0, 2.0]
    rec = json.loads((tmp_path / "c.jsonl").read_text())
    assert rec["alias"] == "spark" and rec["cost_usd"] == pytest.approx(
        0.000338)


def test_chat_raises_non_retryable_at_once():
    client = MagicMock()
    client.chat.completions.create.side_effect = _error(
        openai.AuthenticationError)
    with patch("planner.model_client.time.sleep") as nap:
        with pytest.raises(openai.AuthenticationError):
            chat(client, model="m", spec=MODELS["spark"], alias="spark",
                 purpose="test", log_path=None, messages=[])
    assert client.chat.completions.create.call_count == 1
    nap.assert_not_called()


def test_chat_exhausts_retries():
    client = MagicMock()
    client.chat.completions.create.side_effect = _error(
        openai.InternalServerError)
    with patch("planner.model_client.time.sleep"):
        with pytest.raises(openai.InternalServerError):
            chat(client, model="m", spec=MODELS["spark"], alias="spark",
                 purpose="test", log_path=None, tries=3, messages=[])
    assert client.chat.completions.create.call_count == 3


def test_plan_instruction_uses_alias(monkeypatch):
    import planner.planner as P

    monkeypatch.setenv("MODEL_API_KEY", "x")
    calls = {}

    def fake_chat(client, **kwargs):
        calls.update(kwargs)
        return '{"steps": []}', {"prompt_tokens": 1,
                                 "completion_tokens": 1}, 0.5

    monkeypatch.setattr(P, "model_chat", fake_chat)
    with patch("planner.model_client.load_dotenv", lambda *a, **k: None):
        P.plan_instruction("hi", {"objects": [], "people": []},
                           model="spark")
    assert calls["model"] == "muse-spark-1.3"
    assert "reasoning_effort" in calls  # Meta honours effort


def test_plan_instruction_spark_open_omits_effort(monkeypatch):
    import planner.planner as P

    monkeypatch.setenv("BASETEN_API_KEY", "x")
    calls = {}

    def fake_chat(client, **kwargs):
        calls.update(kwargs)
        return '{"steps": []}', None, 0.5

    monkeypatch.setattr(P, "model_chat", fake_chat)
    with patch("planner.model_client.load_dotenv", lambda *a, **k: None):
        P.plan_instruction("hi", {"objects": [], "people": []},
                           model="spark-open")
    assert calls["model"] == "meta-models/muse-spark-open"
    assert "reasoning_effort" not in calls  # Baseten takes no effort knob
    assert calls["alias"] == "spark-open"
