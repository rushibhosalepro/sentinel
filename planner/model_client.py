"""L-01: one chat client for Meta Model API + Baseten.

Aliases: "spark" -> muse-spark-1.3 on api.meta.ai (MODEL_API_KEY);
"spark-open" -> meta-models/muse-spark-open on Baseten
(BASETEN_API_KEY). Full model ids pass through to Meta (backward
compat, e.g. muse-spark-1.3-contributor). chat() retries transient
errors with exponential backoff and appends every call to
out/costs.jsonl.
"""

from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path

import openai
from dotenv import load_dotenv
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "out"
COSTS_PATH = OUT_DIR / "costs.jsonl"

META_BASE_URL = "https://api.meta.ai/v1"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"

# price_in/out: USD per M tokens (Standard pricing for both hosts).
MODELS = {
    "spark": {"id": "muse-spark-1.3",
              "base_url": META_BASE_URL, "key_env": "MODEL_API_KEY",
              "base_url_env": "META_API_BASE_URL",
              "price_in": 1.25, "price_out": 4.25, "effort_ok": True},
    "spark-open": {"id": "meta-models/muse-spark-open",
                   "base_url": BASETEN_BASE_URL,
                   "key_env": "BASETEN_API_KEY", "base_url_env": None,
                   "price_in": 1.25, "price_out": 4.25,
                   "effort_ok": False},
}

RETRYABLE = (openai.RateLimitError, openai.APIConnectionError,
             openai.APITimeoutError, openai.InternalServerError)
MAX_TRIES = 4
BACKOFF_S = 1.0


def resolve(which: str | None) -> tuple[str, dict]:
    """Resolve an alias or full model id to (alias, spec).

    Unknown strings pass through as Meta model ids (yesterday's
    behaviour for PLANNER_MODEL overrides like -contributor).
    """
    if which is None:
        which = os.environ.get("PLANNER_MODEL", "spark")
    if which in MODELS:
        return which, MODELS[which]
    spec = dict(MODELS["spark"])
    spec["id"] = which
    return "spark", spec


def get_client(which: str | None = None):
    """Build the OpenAI SDK client; (client, model_id, spec, alias)."""
    load_dotenv(REPO_ROOT / ".env.local")
    alias, spec = resolve(which)
    base_url = spec["base_url"]
    if spec["base_url_env"] is not None:
        base_url = os.environ.get(spec["base_url_env"], base_url)
    api_key = os.environ.get(spec["key_env"], "")
    if not api_key:
        raise RuntimeError(
            f"{spec['key_env']} is not set. Add it to .env.local "
            "(never commit it)."
        )
    client = OpenAI(base_url=base_url, api_key=api_key,
                    timeout=300.0, max_retries=0)
    return client, spec["id"], spec, alias


def cost_usd(prompt_tokens: int | None, completion_tokens: int | None,
             spec: dict) -> float | None:
    if prompt_tokens is None or completion_tokens is None:
        return None
    return round(prompt_tokens / 1e6 * spec["price_in"]
                 + completion_tokens / 1e6 * spec["price_out"], 6)


def log_cost(path: Path | None, alias: str, model: str, purpose: str,
             usage: dict | None, latency_s: float, spec: dict) -> None:
    path = COSTS_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    pt = usage.get("prompt_tokens") if usage else None
    ct = usage.get("completion_tokens") if usage else None
    with open(path, "a") as f:
        f.write(json.dumps({
            "ts": datetime.datetime.now(
                datetime.timezone.utc).isoformat(),
            "alias": alias, "model": model, "purpose": purpose,
            "prompt_tokens": pt, "completion_tokens": ct,
            "latency_s": round(latency_s, 2),
            "cost_usd": cost_usd(pt, ct, spec),
        }) + "\n")


def chat(client: OpenAI, *, model: str, spec: dict, alias: str,
         purpose: str, log_path: Path | None = None,
         tries: int = MAX_TRIES, **kwargs):
    """chat.completions with backoff + cost log.

    Returns (content, usage, latency_s). Retries transient errors
    (rate limits, timeouts, 5xx); auth/bad-request errors raise at
    once. Every attempt outcome is logged; only the final call's
    usage is returned.
    """
    last = None
    for attempt in range(tries):
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(model=model, **kwargs)
        except RETRYABLE as e:
            last = e
            if attempt + 1 < tries:
                time.sleep(BACKOFF_S * 2 ** attempt)
                continue
            raise
        latency = time.perf_counter() - t0
        content = resp.choices[0].message.content
        usage = None
        if resp.usage is not None:
            usage = {"prompt_tokens": resp.usage.prompt_tokens,
                     "completion_tokens": resp.usage.completion_tokens,
                     "total_tokens": resp.usage.total_tokens}
        log_cost(log_path, alias, model, purpose, usage, latency, spec)
        return content, usage, latency
    raise last  # unreachable (tries >= 1): keeps linters calm
