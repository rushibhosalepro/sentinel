# Sentinel

**The LLM decides how. Sentinel decides whether.**

Sentinel is a deterministic safety layer for robot actions: an LLM planner
proposes *how* to do something, and Sentinel verifies *whether* each motion
is safe against a live scene graph — with ALLOW / ASK / BLOCK / HALT
verdicts, fixable feedback so the LLM can replan, and a background rule
learner that keeps improving the rulebook safely.

Built from scratch during the **Meta Global AI Developer Hackathon
(Oct 27 – Nov 4, 2026)** — Indie track, *Push the Frontier* theme.
See [`PLAN.md`](PLAN.md) (single source of truth) for the full build plan.

## Try it

- Public demo: run `modal deploy deploy/modal_app.py` (see
  [`deploy/modal_app.py`](deploy/modal_app.py) for the one-time secret
  setup) and open the `https://...` URL it prints. `/` is the
  with-vs-without split view, `/debug` the full dashboard.
- Local: `uv run uvicorn dashboard.server:app --port 8000`, then
  `cd dashboard/web && npm run dev` and open http://localhost:5173/
  (split view) or http://localhost:5173/debug (dashboard).

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

- `franka_emika_panda` (Panda arm + hand meshes, `panda.xml`) from
  [google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie),
  Apache-2.0 (see `sim/assets/mujoco_menagerie/LICENSE` after fetching).
- Table, mug, knife in `sim/scenes/day1.xml` are procedural MuJoCo
  primitives (boxes/cylinders) authored for this repo — no third-party licence.

## License

MIT — see [LICENSE](LICENSE).
