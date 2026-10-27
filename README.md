# Sentinel

**The LLM decides how. Sentinel decides whether.**

Sentinel is a deterministic safety layer for robot actions: an LLM planner
proposes *how* to do something, and Sentinel verifies *whether* each motion
is safe against a live scene graph — with ALLOW / ASK / BLOCK / HALT
verdicts, fixable feedback so the LLM can replan, and a background rule
learner that keeps improving the rulebook safely.

Built from scratch during the **Meta Global AI Developer Hackathon
(Oct 27 – Nov 4, 2026)** — Indie track, *Push the Frontier* theme.
See [`PLAN.md`](../PLAN.md) (single source of truth) for the full build plan.

## Quickstart (Phase 0)

```bash
cd sentinel
uv venv --python 3.14
uv sync
cp .env.example .env.local   # then put your MODEL_API_KEY in .env.local
uv run python -m sim.world --demo
```

## Layout

`sim/` MuJoCo world · `perception/` SAM 3.1 + depth · `graph/` scene graph ·
`planner/` Meta Model API clients · `sentinel/` the checker · `loop/`
orchestrator · `learner/` rule learner · `bench/` benchmark · `server/` API ·
`web/` dashboard.

## Asset licences

Third-party MuJoCo assets live in `sim/assets/` (git-ignored, fetched by
`scripts/fetch_assets.py`); their licences are listed there as they are added:

- *(none yet — added in P0-03)*

## License

MIT — see [LICENSE](LICENSE).
