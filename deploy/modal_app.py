"""F-01: Modal deployment: FastAPI + built web app on one public endpoint.

One-time:
  modal secret create sentinel META_API_KEY=<..> BASETEN_API_KEY=<..> \\
      OWNER_TOKEN=<..>
Each deploy:
  cd dashboard/web && npm run build && cd ../..
  modal deploy deploy/modal_app.py
The printed https://... URL is the judge link (README "Try it").

Notes: headless MuJoCo via MUJOCO_GL=egl (+ libegl1/libgl1); the image
installs the pyproject dependency list (no project install, so the 3.14
pin does not apply -- keep DEPS in sync with pyproject.toml) and the
repo minus venv/out/cache/runs; bench/results.csv + scenarios ride
along for the strip. Single container (the app serializes runs
itself); costs.jsonl is container-local, so the daily budget resets
whenever Modal recycles the container. Syntax-checked only here
(py_compile): first real deploy needs a Modal account.
"""

import modal

APP_NAME = "sentinel"
SECRETS_NAME = "sentinel"
REMOTE = "/app"

# Mirrors pyproject.toml [project] dependencies (no dev group on Modal).
DEPS = [
    "daqp>=0.10.3",
    "fastapi>=0.162.0",
    "imageio[ffmpeg]>=2.38.1",
    "meta-sam-parser>=0.1.0",
    "mink>=1.3.0",
    "mujoco>=3.17.0",
    "networkx>=3.7",
    "numpy>=2.5.4",
    "openai>=3.39.0",
    "pillow>=13.0.0",
    "python-dotenv>=1.2.4",
    "pyyaml>=6.0.3",
    "uvicorn>=0.54.0",
    "websockets>=17.3",
]

image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("libgl1", "libegl1", "libglib2.0-0")
    .pip_install(*DEPS)
    .env({"MUJOCO_GL": "egl", "PYTHONPATH": REMOTE})
    # add_local_* last: files mount at startup instead of rebuilding.
    .add_local_dir(
        ".",
        remote_path=REMOTE,
        ignore=[
            ".venv",
            ".git",
            "out",
            "cache",
            "__pycache__",
            ".pytest_cache",
            ".uv-cache",
            "node_modules",
            "dashboard/web/node_modules",
            "bench/runs",
            "bench/first_run",
            "bench/cache",
            # keys come from the Modal secret; never ship local env files
            ".env",
            ".env.local",
            ".env.production",
            "video",
        ],
    )
)

app = modal.App(APP_NAME)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(SECRETS_NAME)],
    max_containers=1,
    timeout=900,
)
@modal.asgi_app()
def web():
    import os

    if "META_API_KEY" in os.environ:
        os.environ.setdefault("MODEL_API_KEY",
                              os.environ["META_API_KEY"])
    from dashboard.server import create_app

    return create_app(
        idle_render=True,
        public_mode=True,
        rate_limit_per_hour=10,
        daily_budget_usd=float(os.environ.get("DAILY_BUDGET_USD", "10")),
        web_dir=f"{REMOTE}/dashboard/web/dist",
    )
