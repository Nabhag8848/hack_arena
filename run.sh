#!/usr/bin/env bash
# Quick commands for hackathon runs.
# Usage: bash run.sh [smoke|submit|dev|test_normal]
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export IPYTHONDIR="$(pwd)/.ipython"
export PYTHONUNBUFFERED=1

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "ERROR: OPENROUTER_API_KEY is not set in .env"
  echo "  Get a key at https://openrouter.ai/keys"
  exit 1
fi

EXPERIMENT="${APPWORLD_EXPERIMENT:-team_nabhag}"
EVAL_DATASET=agent_arena_eval
EVAL_TASKS=10

case "${1:-submit}" in
  smoke)
    echo "=== Smoke test: 2 ${EVAL_DATASET} tasks (~5-10 min) ==="
    MAX_TASKS=2 APPWORLD_DATASET="${EVAL_DATASET}" APPWORLD_EXPERIMENT="${EXPERIMENT}" \
      python -u agent.py
    ;;
  submit)
    echo "=== Official submission: ${EVAL_TASKS} ${EVAL_DATASET} tasks (see SUBMISSION.md) ==="
    echo "    Experiment: ${EXPERIMENT} — resumes with SKIP_COMPLETED=1"
    MAX_TASKS=0 SKIP_COMPLETED=1 APPWORLD_DATASET="${EVAL_DATASET}" \
      APPWORLD_EXPERIMENT="${EXPERIMENT}" python -u agent.py
    echo "=== Self-evaluate (TGC / SGC for the Google Form) ==="
    appworld evaluate "${EXPERIMENT}" "${EVAL_DATASET}"
    echo "Commit: experiments/outputs/${EXPERIMENT}/"
    echo "  evaluations/${EVAL_DATASET}.json  (required)"
    echo "  tasks/<task_id>/dbs/              (required for re-eval)"
    ;;
  dev)
    echo "=== Full dev benchmark: 57 tasks (~2-4 hrs) — resumes with SKIP_COMPLETED=1 ==="
    MAX_TASKS=0 SKIP_COMPLETED=1 APPWORLD_DATASET=dev APPWORLD_EXPERIMENT="${EXPERIMENT}" \
      python -u agent.py
    echo "=== Evaluate dev run ==="
    appworld evaluate "${EXPERIMENT}" dev
    ;;
  test_normal)
    echo "=== test_normal benchmark: 168 tasks ==="
    MAX_TASKS=0 SKIP_COMPLETED=1 APPWORLD_DATASET=test_normal APPWORLD_EXPERIMENT="${EXPERIMENT}" \
      python -u agent.py
    appworld evaluate "${EXPERIMENT}" test_normal
    ;;
  *)
    echo "Usage: bash run.sh [smoke|submit|dev|test_normal]"
    echo "  smoke        — 2 tasks from ${EVAL_DATASET} (quick check)"
    echo "  submit       — all ${EVAL_TASKS} ${EVAL_DATASET} tasks + evaluate (default)"
    echo "  dev          — full 57-task dev split"
    echo "  test_normal  — 168-task test_normal split"
    exit 1
    ;;
esac
