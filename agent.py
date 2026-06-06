"""
://agent_arena — AppWorld PRER agent (Plan-Retrieve-Execute-Reflect).

Run (all settings via .env or env vars — see .env.example):
  source .venv/bin/activate
  python agent.py
"""

import sys
import time

import agent.config  # noqa: F401 — loads .env, sets IPYTHONDIR, creates runtime dirs

from appworld import AppWorld, load_task_ids

from agent.api_index import get_api_index
from agent.config import (
    APPWORLD_DATASET,
    APPWORLD_EXPERIMENT,
    EXPERIMENTS_OUTPUT_DIR,
    MAX_TASKS,
    MODEL,
    SKIP_COMPLETED,
    validate_llm_config,
)
from agent.hydradb_ctx import get_hydra_context
from agent.loop import solve


def _task_already_completed(task_id: str) -> bool:
    log_path = (
        EXPERIMENTS_OUTPUT_DIR
        / APPWORLD_EXPERIMENT
        / "tasks"
        / task_id
        / "logs"
        / "environment_io.md"
    )
    if not log_path.exists():
        return False
    text = log_path.read_text()
    if "Marked the active task complete" in text:
        return True
    blocks = text.split("### Environment Interaction")
    if len(blocks) < 2:
        return False
    last = blocks[-1]
    return "complete_task" in last and "Execution successful" in last


def main() -> None:
    print("Starting agent...", flush=True)
    validate_llm_config()

    print("Loading API index...", flush=True)
    api_index = get_api_index()
    print(f"API index loaded: {len(api_index.docs)} endpoints", flush=True)

    print("Initializing HydraDB...", flush=True)
    hydra = get_hydra_context()
    if hydra.enabled:
        print(f"HydraDB enabled (tenant: {hydra.tenant_id}, ingest-only mode)")
        hydra.seed_knowledge()
    else:
        print("HydraDB disabled — using local API index only")

    task_ids = load_task_ids(APPWORLD_DATASET)
    if MAX_TASKS:
        task_ids = task_ids[:MAX_TASKS]

    print(
        f"Running '{APPWORLD_EXPERIMENT}' on {len(task_ids)} "
        f"'{APPWORLD_DATASET}' tasks with groq/{MODEL}"
    )
    if SKIP_COMPLETED:
        print("SKIP_COMPLETED=1 — resuming past finished tasks", flush=True)

    completed = 0
    skipped = 0
    for i, task_id in enumerate(task_ids, 1):
        if SKIP_COMPLETED and _task_already_completed(task_id):
            print(f"[{i}/{len(task_ids)}] {task_id} — skip (already done)", flush=True)
            completed += 1
            skipped += 1
            continue

        print(f"[{i}/{len(task_ids)}] {task_id}", flush=True)
        print("  opening AppWorld...", flush=True)
        try:
            with AppWorld(task_id=task_id, experiment_name=APPWORLD_EXPERIMENT) as world:
                if solve(world):
                    completed += 1
        except RuntimeError as e:
            if "daily token limit" in str(e).lower():
                print(f"  ! stopping run: {e}", flush=True)
                break
            print(f"  ! error: {e}")
        except Exception as e:
            print(f"  ! error: {e}")
        time.sleep(2)

    ran = len(task_ids) - skipped
    output_dir = EXPERIMENTS_OUTPUT_DIR / APPWORLD_EXPERIMENT
    print(f"\nCompleted {completed}/{len(task_ids)} tasks ({skipped} skipped, {ran} attempted)")
    print(f"Outputs in {output_dir}/")
    print("Hand that folder to the organizers (or zip and submit per instructions).")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
