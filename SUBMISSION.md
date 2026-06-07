# 📥 How to Submit — ://agent_arena

You submit via the **Google Form** (link in the event chat). The form asks for a
link to your **public GitHub repo** plus the fields below. Get the format exactly
right — mismatches slow down or break scoring.

## Your submission — `team_nabhag`

Copy these into the Google Form (update **TGC / SGC** after `bash run.sh submit`):

| Field                       | What to enter                                      |
| --------------------------- | -------------------------------------------------- |
| **Team name**               | `nabhag`                                           |
| **GitHub repo URL**         | `https://github.com/Nabhag8848/hack_arena`         |
| **Model used**              | `meta-llama/llama-3.3-70b-instruct:free`           |
| **Self-reported TGC / SGC** | `20% / 20%` (2/10 tasks: `ba46d91_2`, `dbc0276_3`) |
| **HydraDB used?**           | `yes — API-doc retrieval + cross-task memory`      |
| **Integrity check**         | `confirmed`                                        |

## A. Fields the Google Form asks for

| Field                       | What to enter                                                                | Example (team_nabhag)                         |
| --------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------- |
| **Team name**               | lowercase letters/digits/underscores only, no spaces. This is your `<name>`. | `nabhag`                                      |
| **GitHub repo URL**         |                                                                              | `https://github.com/Nabhag8848/hack_arena`    |
| **Model used**              | the `provider/model` you ran                                                 | `meta-llama/llama-3.3-70b-instruct:free`      |
| **Self-reported TGC / SGC** | from your own `appworld evaluate` (see below)                                | `20% / 20%`                                   |
| **HydraDB used?**           | yes/no + one line on how (for the bonus)                                     | `yes — API-doc retrieval + cross-task memory` |
| **Integrity check**         | confirm: general agent, no `task_id` hardcoding                              | `confirmed`                                   |

## B. Required repo structure

Your repo **must** contain your agent code **and** your run outputs on the official
eval set `agent_arena_eval` (the 10 tasks in [`EVAL.md`](EVAL.md)):

```
<your-repo>/
├── README.md                       # team name, model, how to run, HydraDB notes
├── agent.py                        # (or src/…) the exact agent you ran
├── requirements.txt                # so we can reproduce your run
└── experiments/
    └── outputs/
        └── team_nabhag/            # folder name MUST be team_nabhag
            ├── evaluations/
            │   └── agent_arena_eval.json   # REQUIRED — your self-eval
            └── tasks/
                └── <task_id>/…             # all 10 tasks, INCLUDING each tasks/<id>/dbs/
```

- The folder **must** be named `team_nabhag` and `nabhag` **must** match the team
  name in the form. That string is how we attribute and rank you.
- Include the per-task `dbs/` folders — we **re-evaluate from them** to verify scores.

## C. Produce those outputs (before you submit)

```bash
source .venv/bin/activate
export APPWORLD_EXPERIMENT=team_nabhag
export APPWORLD_DATASET=agent_arena_eval MAX_TASKS=0
python agent.py                                   # runs all 10 tasks
appworld evaluate team_nabhag agent_arena_eval    # prints your TGC/SGC -> put in the form
```

Or: `bash run.sh submit`

Then commit `experiments/outputs/team_nabhag/` to your repo and submit the repo URL.

## D. If the outputs are too big for git

Zip `experiments/outputs/team_nabhag/`, attach it to a **GitHub Release** on your
repo, and paste that release link in the form's "GitHub repo URL" notes. (Still keep
`evaluations/agent_arena_eval.json` committed in the repo.)

## E. How we score it

We drop your `experiments/outputs/team_nabhag/` into the judge and run:

```bash
appworld evaluate team_nabhag agent_arena_eval        # + re-eval from your dbs
```

**Ranking:** TGC (primary) → SGC (tiebreak) → HydraDB bonus.

## F. Rules

- **One submission per team** (latest before the deadline wins).
- **Build a general agent.** No hardcoding answers keyed to specific `task_id`s —
  submitted code is reviewed; violations are disqualified.
- Submit **before the announced deadline**. Late forms aren't scored.
