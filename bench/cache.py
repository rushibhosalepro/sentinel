"""B-04: model-call cache by prompt hash (bench/cache/).

cached_chat mirrors model_client.chat's signature so bench/run.py can
swap it in for planner.planner.model_chat. Hits return the recorded
content+usage with 0 latency and log a cached line (cost 0); misses
call through and record. Thread-safe; atomic writes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "bench" / "cache"

_lock = threading.Lock()
_local = threading.local()


def set_repeat(repeat: int) -> None:
    """Repeat context for cache keys (bench/run_one sets this per cell)."""
    _local.repeat = repeat


def current_repeat() -> int:
    return getattr(_local, "repeat", 1)


def cache_key(model: str, kwargs: dict, repeat: int = 1) -> str:
    """sha256 over model + the request payload (stable JSON).

    B-06: r1 keeps the legacy key (1029-1226 r1 stays reproducible);
    r2+ mix the repeat in so repeats are independent model calls.
    """
    payload = {"model": model}
    if repeat != 1:
        payload["repeat"] = repeat
    for k in ("messages", "response_format", "reasoning_effort",
              "temperature", "max_tokens"):
        if k in kwargs:
            payload[k] = kwargs[k]
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _cost_path(cache_dir: Path) -> Path:
    return Path(cache_dir) / "costs.jsonl"


def log_cached(cost_path: Path, alias: str, model: str, purpose: str,
               usage: dict | None) -> None:
    from planner.model_client import cost_usd, resolve

    _, spec = resolve(alias)
    pt = usage.get("prompt_tokens") if usage else None
    ct = usage.get("completion_tokens") if usage else None
    with open(cost_path, "a") as f:
        f.write(json.dumps({
            "ts": datetime.datetime.now(
                datetime.timezone.utc).isoformat(),
            "alias": alias, "model": model, "purpose": purpose,
            "prompt_tokens": pt, "completion_tokens": ct,
            "latency_s": 0.0, "cost_usd": 0.0,
            "uncached_usd": cost_usd(pt, ct, spec),
            "cached": True,
        }) + "\n")


def cached_chat(client, *, model: str, spec: dict, alias: str,
                purpose: str, log_path=None, cache_dir=None,
                tries: int = 4, repeat: int | None = None, **kwargs):
    """chat() with a prompt-hash cache. Returns (content, usage, secs).

    `repeat` defaults to the thread-local repeat context (set_repeat).
    """
    from planner.model_client import chat as model_chat

    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    if log_path is None:
        log_path = _cost_path(cache_dir)
    if repeat is None:
        repeat = current_repeat()
    key = cache_key(model, kwargs, repeat)
    path = cache_dir / f"{key}.json"
    with _lock:
        if path.exists():
            rec = json.loads(path.read_text())
            cost_path = Path(log_path)
            _mkdir(cost_path.parent)
            log_cached(cost_path, alias, model, purpose,
                       rec.get("usage"))
            return rec["content"], rec.get("usage"), 0.0
    content, usage, secs = model_chat(
        client, model=model, spec=spec, alias=alias, purpose=purpose,
        log_path=log_path, tries=tries, **kwargs)
    with _lock:
        _mkdir(cache_dir)
        if not path.exists():
            tmp = path.with_name(f"{path.stem}.{os.getpid()}"
                                 f".{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps({"content": content,
                                       "usage": usage}))
            try:
                tmp.rename(path)
            except FileExistsError:
                tmp.unlink(missing_ok=True)  # another thread won
    return content, usage, secs


def _mkdir(path: Path) -> None:
    """exist_ok mkdir immune to create races (Windows err 183)."""
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        pass
