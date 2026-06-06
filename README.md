# ://agent_arena — team_nabhag

Build an **autonomous AI agent** that completes everyday-app tasks in
[AppWorld](https://appworld.dev). You are ranked by **Task Goal Completion (TGC)** —
the percentage of tasks your agent fully completes.

|             |                                                                                       |
| ----------- | ------------------------------------------------------------------------------------- |
| **Team**    | `team_nabhag`                                                                         |
| **Model**   | `meta-llama/llama-3.3-70b-instruct:free` (OpenRouter)                                 |
| **HydraDB** | yes — API-doc retrieval + cross-task memory (ingest-only; see `agent/hydradb_ctx.py`) |

## What AppWorld is

A simulated world of **9 apps** (Spotify, Gmail, Venmo, Amazon, Splitwise, Phone,
File System, Simple Note, + `supervisor`/`api_docs`), **457 APIs**, and ~100
simulated people. Your agent reads a natural-language instruction from its
"supervisor" and acts by **writing Python code** that calls the apps' APIs.

## 1. Setup (~3 min) — needs Python 3.11

```bash
git clone git@github.com:interface4agi/hack_agent_arena.git
cd hack_agent_arena
bash setup.sh                 # installs uv+py3.11, appworld + data, creates .env; verifies
source .venv/bin/activate
```

Then add your LLM key to **`.env`**:

```
OPENROUTER_API_KEY=sk-or-...
MODEL=meta-llama/llama-3.3-70b-instruct:free
APPWORLD_EXPERIMENT=team_nabhag
```

Get a free key at [openrouter.ai/keys](https://openrouter.ai/keys).

## 2. Run the agent

```bash
bash run.sh smoke      # 2 tasks — quick check (~5-10 min)
bash run.sh submit     # all 10 official eval tasks + self-evaluate (default)
bash run.sh dev        # 57-task dev split (practice)
```

Or manually (see [SUBMISSION.md](SUBMISSION.md)):

```bash
export APPWORLD_EXPERIMENT=team_nabhag
export APPWORLD_DATASET=agent_arena_eval MAX_TASKS=0
python agent.py
appworld evaluate team_nabhag agent_arena_eval
```

`agent.py` is a PRER (Plan-Retrieve-Execute-Reflect) code agent — read it, then
make it smarter. Explore a task by hand: `appworld play`

## 3. The rules your agent plays by

- One Python code block per turn; whatever you `print()` comes back as the next observation.
- Discover APIs at runtime:
  `apis.api_docs.show_api_descriptions(app_name='spotify')`, then
  `apis.api_docs.show_api_doc(app_name='spotify', api_name='login')`.
- Get credentials: `apis.supervisor.show_account_passwords()`, then log into each app.
- Finish a task: `apis.supervisor.complete_task(answer=<answer or None>)`.

## 4. Submit

See [SUBMISSION.md](SUBMISSION.md) for the Google Form and full rules.

**Required repo structure** after running `bash run.sh submit`:

```
├── README.md
├── agent.py
├── requirements.txt
└── experiments/
    └── outputs/
        └── team_nabhag/
            ├── evaluations/
            │   └── agent_arena_eval.json   # REQUIRED
            └── tasks/
                └── <task_id>/…             # all 10 tasks + dbs/
```

Commit `experiments/outputs/team_nabhag/` (or zip and attach to a GitHub Release
if too large — still keep `evaluations/agent_arena_eval.json` in the repo).

Official eval tasks: [EVAL.md](EVAL.md)

## Scoring

- **TGC** (primary) — % of tasks fully completed. **SGC** breaks ties.
- 🐉 **Bonus:** HydraDB integration (API-doc retrieval + cross-task memory).
- Reference baseline on `test_normal`: ReAct + GPT-4o ≈ **48.8 TGC**.

---

Built for **://agent_arena** · benchmark: [AppWorld](https://github.com/StonyBrookNLP/appworld) (ACL'24 Best Resource Paper)
