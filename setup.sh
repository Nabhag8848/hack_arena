#!/usr/bin/env bash
# ://agent_arena — one-shot participant setup. AppWorld needs Python 3.11.
set -euo pipefail

echo "[1/6] Installing uv (manages Python 3.11 + venv; no conda needed)..."
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "[2/6] Python 3.11 + virtualenv..."
uv python install 3.11
uv venv --python 3.11 .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[3/6] Installing dependencies..."
uv pip install -r requirements.txt

echo "[4/6] AppWorld engine + data..."
appworld install
appworld download data

echo "[5/6] Creating .env (add your key)..."
[ -f .env ] || cp .env.example .env

echo "[6/6] Verify..."
# Official eval set (10 tasks) — see EVAL.md / SUBMISSION.md
if [[ ! -f data/datasets/agent_arena_eval.txt ]]; then
  if [[ -f data/datasets/agent_arena.txt ]]; then
    cp data/datasets/agent_arena.txt data/datasets/agent_arena_eval.txt
  fi
fi
python -c "from appworld import load_task_ids; print('dev:', len(load_task_ids('dev')), '| agent_arena_eval:', len(load_task_ids('agent_arena_eval')))"

cat <<'NEXT'

✅ Setup done. Next:
  source .venv/bin/activate
  # Edit .env — set OPENROUTER_API_KEY, APPWORLD_EXPERIMENT=team_<yourname>, HYDRA_DB_API_KEY (optional)
  python agent.py                              # reads all settings from .env

Explore tasks interactively:
  export IPYTHONDIR="$(pwd)/.ipython"          # same path agent.py uses
  appworld play
NEXT
