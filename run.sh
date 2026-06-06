#!/usr/bin/env bash
# Quick commands for hackathon runs. Usage: bash run.sh [smoke|dev|submit]
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

case "${1:-smoke}" in
  smoke)
    echo "=== Smoke test: 2 dev tasks (~3-5 min) ==="
    MAX_TASKS=10 APPWORLD_DATASET=dev python -u agent.py
    ;;
  dev)
    echo "=== Full dev benchmark: 57 tasks (~2-4 hrs) — resumes with SKIP_COMPLETED=1 ==="
    MAX_TASKS=0 SKIP_COMPLETED=1 APPWORLD_DATASET=dev APPWORLD_EXPERIMENT="${APPWORLD_EXPERIMENT:-team_nabhag}" python -u agent.py
    echo "=== Evaluate (after all 57 tasks have outputs) ==="
    appworld evaluate "${APPWORLD_EXPERIMENT:-team_nabhag}" dev
    ;;
  submit)
    echo "=== Official test_normal submission run ==="
    MAX_TASKS=0 APPWORLD_DATASET=test_normal APPWORLD_EXPERIMENT="${APPWORLD_EXPERIMENT:-team_nabhag}" python -u agent.py
    appworld evaluate "${APPWORLD_EXPERIMENT:-team_nabhag}" test_normal
    echo "Zip: experiments/outputs/${APPWORLD_EXPERIMENT:-team_nabhag}/"
    ;;
  *)
    echo "Usage: bash run.sh [smoke|dev|submit]"
    exit 1
    ;;
esac
