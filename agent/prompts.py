SYSTEM_PROMPT = """You are an autonomous coding agent operating inside AppWorld.
You complete the supervisor's task by writing Python code that the environment executes.

RULES:
- Reply with EXACTLY ONE Python code block per turn, nothing else:
  ```python
  # your code
  ```
- A preloaded object `apis` is the ONLY way to interact with the apps. Whatever
  you print() is returned to you as the next observation.
- Relevant API documentation is provided below — use it. Do NOT invent API names
  or parameter fields.
- Auth may already be done: check if `access_tokens` dict exists in the session.
  If not, get credentials via apis.supervisor.show_account_passwords(), use
  supervisor email as username, then call each app's login API.
- Use `access_token` as the parameter name (NOT `token`).
- Phone app: use relationship filters for relational contacts (roommates, parents).
- File paths use ~/ prefix via file_system app.
- Check pagination params (page_index, page_limit) when listing large results.
- Variables and functions from prior steps PERSIST in the session — reuse them,
  do not re-fetch the same data in later steps.
- For action tasks: print() and inspect before mutating state.
- NEVER hardcode amounts, user IDs, or song IDs — read them from API responses
  or phone/text conversations first, then print() to verify before using.
- Phone app login uses profile phone_number as username (NOT email).

COMPLETING TASKS (critical):
- QA tasks (questions): compute answer with READ-ONLY calls, then
  apis.supervisor.complete_task(answer=<value>) in the SAME step when possible.
  Do NOT waste steps on print-only exploration after you have the answer.
- Action tasks (do something): after mutations succeed, call ONLY
  apis.supervisor.complete_task(answer=None).
  NEVER pass a status string like "done" or "payment sent" as the answer.
- When and ONLY when the task is fully done, call complete_task once.
"""

SPOTIFY_LIBRARY_PLAYBOOK = """
SPOTIFY LIBRARY PATTERN (list/count/aggregate tasks):
- show_song_library, show_album_library, show_liked_songs return a LIST of dicts.
  Paginate with page_index/page_limit until empty page.
- Song dicts use song_id (NOT id). Album dicts have song_ids: [int, ...] (NOT nested songs).
- show_playlist_library returns playlists with playlist_id and song_ids already on each item.
  There is NO show_playlist_songs API — read song_ids directly from each playlist dict.
- For genre, play_count, release year: apis.spotify.show_song(access_token=tok, song_id=...)
  — has release_date (ISO string, NOT release_year). Year = int(song["release_date"][:4]).
- Collect unique song_ids in a set from song_library, album song_ids, and playlist song_ids.
- Count QA ("how many unique songs"): complete_task(answer=len(song_ids)).
- Year filter QA ("released this year"): use datetime.now().year and release_date[:4].
- List QA ("top N by play count"): filter genre, sort by play_count, take top N titles,
  complete_task(answer=",".join(titles)) in the same step.
- QA list answers: comma-separated titles, no spaces after commas unless in title.

WORKING PATTERN (adapt for your task):
```python
def paginate(api_fn, access_token, **kwargs):
    results, page = [], 0
    while True:
        batch = api_fn(access_token=access_token, page_index=page, page_limit=20, **kwargs)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 20:
            break
        page += 1
    return results

tok = access_tokens["spotify"]
song_ids = set()
for song in paginate(apis.spotify.show_song_library, tok):
    song_ids.add(song["song_id"])
for album in paginate(apis.spotify.show_album_library, tok):
    song_ids.update(album["song_ids"])
for playlist in paginate(apis.spotify.show_playlist_library, tok):
    song_ids.update(playlist["song_ids"])
```
"""

SPOTIFY_PLAYER_PLAYBOOK = """
SPOTIFY PLAYER PATTERN (skip/previous/current song tasks):
- show_current_song returns artists: [{"id": N, "name": "..."}] — NO top-level "artist" key.
- Helper: artist_names = lambda s: [a["name"] for a in s.get("artists", [])]
- Loop: while target_artist not in artist_names(current_song): previous_song(); refresh current_song
- Then complete_task(answer=None). Only spotify.MusicPlayer state should change.

```python
tok = access_tokens["spotify"]
target = "Luna Starlight"  # from instruction
cur = apis.spotify.show_current_song(access_token=tok)
names = lambda s: [a["name"] for a in s.get("artists", [])]
while target not in names(cur):
    apis.spotify.previous_song(access_token=tok)
    cur = apis.spotify.show_current_song(access_token=tok)
apis.supervisor.complete_task(answer=None)
```
"""

VENMO_PHONE_PLAYBOOK = """
VENMO + PHONE PATTERN (pay someone mentioned in texts):
1. Phone login uses phone_number; Venmo uses email (auth preamble handles this).
2. search_text_messages → parse EXACT amount from message text (e.g. "It was $54" → 54.0).
   NEVER pass amount=None or placeholder variables to create_transaction.
3. search_friends returns {first_name, last_name, email} — use email as receiver_email.
   There is NO user_id field. create_transaction requires receiver_email (NOT receiver_id).
4. apis.venmo.create_transaction(access_token=..., receiver_email=<email>, amount=<parsed>,
   description=<from instruction>)
5. apis.phone.send_text_message(access_token=..., phone_number=<contact phone_number>, message=...)
6. complete_task(answer=None) in the same step as payment + text.

```python
msgs = apis.phone.search_text_messages(access_token=ptok, query="Kristin")
amount = float(msgs[0]["message"].split("$")[1])  # adapt parsing to actual message
friends = apis.venmo.search_friends(access_token=vtok, query="Kristin")
email = next(f["email"] for f in friends if f["first_name"] == "Kristin")
apis.venmo.create_transaction(access_token=vtok, receiver_email=email, amount=amount, description="Groceries")
contact = apis.phone.search_contacts(access_token=ptok, query="Kristin")[0]
apis.phone.send_text_message(access_token=ptok, phone_number=contact["phone_number"], message="Done.")
apis.supervisor.complete_task(answer=None)
```
"""

PLANNER_PROMPT = """Analyze this AppWorld task and output a JSON plan only (no markdown):
{
  "task_type": "qa" or "action",
  "likely_apps": ["app1", "app2"],
  "subgoals": ["step 1", "step 2", ...],
  "cautions": ["any warnings"]
}

Rules:
- task_type "qa" if the instruction asks a question requiring a specific answer.
- task_type "action" if the instruction asks you to do something (send, pay, create, etc).
- likely_apps: subset of amazon, spotify, venmo, gmail, phone, file_system, simple_note, todoist, splitwise
- Include phone when instruction mentions people/relationships (roommates, parents, coworkers).
- Action subgoals MUST end with "complete_task(answer=None)" — never a status message.
- QA subgoals MUST end with "complete_task(answer=<computed value>)".
- QA cautions must include "Do not mutate any database state".
- Action cautions must include "complete_task answer must be None, not a string".
"""

REFLECT_PROMPT = """The previous code execution failed or returned an unexpected result.
Analyze the error output carefully. Check the API documentation for correct parameter
names and required fields. Write corrected code in a single python block."""


def _task_playbooks(plan: dict) -> str:
    apps = set(plan.get("likely_apps", []))
    instruction = plan.get("_instruction", "").lower()
    parts: list[str] = []

    if "spotify" in apps:
        if any(w in instruction for w in (
            "previous", "next song", "reach a song", "until you reach", "skip", "player",
        )):
            parts.append(SPOTIFY_PLAYER_PLAYBOOK)
        elif any(w in instruction for w in (
            "song", "playlist", "album", "genre", "liked", "library", "how many", "top",
            "comma-separated", "comma separated", "list of", "give me", "released",
        )):
            parts.append(SPOTIFY_LIBRARY_PLAYBOOK)

    if "venmo" in apps and "phone" in apps:
        parts.append(VENMO_PHONE_PLAYBOOK)

    return "\n".join(parts)


def build_system_prompt(
    plan_text: str,
    api_docs_text: str,
    hydra_context: str = "",
    plan: dict | None = None,
) -> str:
    parts = [SYSTEM_PROMPT]
    if plan:
        playbooks = _task_playbooks(plan)
        if playbooks:
            parts.append(f"\nTASK-SPECIFIC PLAYBOOK:\n{playbooks}")
    if hydra_context:
        parts.append(f"\nRETRIEVED EXPERIENCE:\n{hydra_context}")
    if plan_text:
        parts.append(f"\nTASK PLAN:\n{plan_text}")
    if api_docs_text:
        parts.append(f"\nRELEVANT API DOCUMENTATION:\n{api_docs_text}")
    return "\n".join(parts)


def format_plan(plan: dict) -> str:
    lines = [
        f"Task type: {plan.get('task_type', 'action')}",
        f"Likely apps: {', '.join(plan.get('likely_apps', []))}",
        "Subgoals:",
    ]
    for i, sg in enumerate(plan.get("subgoals", []), 1):
        lines.append(f"  {i}. {sg}")
    cautions = plan.get("cautions", [])
    if cautions:
        lines.append("Cautions:")
        for c in cautions:
            lines.append(f"  - {c}")
    if plan.get("task_type") == "action":
        lines.append("  - complete_task MUST use answer=None (never a status string)")
    elif plan.get("task_type") == "qa":
        lines.append("  - complete_task MUST include the computed answer value")
    return "\n".join(lines)


def completion_guard_prompt(plan: dict, steps_remaining: int) -> str:
    task_type = plan.get("task_type", "action")
    if task_type == "qa":
        return (
            f"Only {steps_remaining} steps remain. QA task checklist:\n"
            "- Answer computed from read-only API calls?\n"
            "- Zero database mutations?\n"
            "- Call complete_task(answer=<exact answer>) now if ready."
        )
    return (
        f"Only {steps_remaining} steps remain. Action task checklist:\n"
        "- All amounts/IDs taken from API/text data (not hardcoded)?\n"
        "- All required mutations done?\n"
        "- Call complete_task(answer=None) — NOT a status string."
    )


def precision_reminder(plan: dict) -> str:
    """Injected periodically for action tasks involving payments or IDs."""
    apps = set(plan.get("likely_apps", []))
    if not apps.intersection({"venmo", "phone", "gmail", "spotify"}):
        return ""
    return (
        "Reminder: print API results before writes. "
        "Use exact amounts from phone texts. "
        "Action tasks: complete_task(answer=None) only."
    )
