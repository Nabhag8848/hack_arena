import re

from agent.config import APP_KEYWORDS

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
  Paginate with page_index/page_limit until empty page (use shared paginate helper).
- Song dicts use song_id (NOT id). Album dicts have song_ids: [int, ...] (NOT nested songs).
- show_playlist_library returns playlists with playlist_id and song_ids already on each item.
  show_playlist(playlist_id=...) returns nested songs list — different shape from library.
- For genre, play_count, release year: apis.spotify.show_song(access_token=tok, song_id=...)
  — has release_date (ISO string, NOT release_year). Year = int(song["release_date"][:4]).
- Collect unique song_ids in a set from song_library, album song_ids, and playlist song_ids.
- Count QA ("how many unique songs"): complete_task(answer=len(song_ids)).
- Year filter QA ("released this year"): use datetime.now().year and release_date[:4].
- List QA ("top N by play count"): filter genre, sort by play_count, take top N titles,
  complete_task(answer=",".join(titles)) in the same step.
- QA list answers: comma-separated titles, no spaces after commas unless in title.

WORKING PATTERN (adapt for your task — paginate defined in TASK-SPECIFIC PLAYBOOK):
```python
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
- show_current_song returns artists: [{"id": N, "name": "..."}] and title — NO top-level "artist" key.
- Match target by song title OR artist name from the instruction.
- Loop: while target not matched: previous_song(); refresh current_song
- Then complete_task(answer=None). Only spotify.MusicPlayer state should change.

```python
tok = access_tokens["spotify"]
target = "Luna Starlight"  # song title or artist from instruction
cur = apis.spotify.show_current_song(access_token=tok)
def matches(s, t):
    if t.lower() in s.get("title", "").lower():
        return True
    return any(t.lower() in a["name"].lower() for a in s.get("artists", []))
while not matches(cur, target):
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

PAGINATE_HELPER = """
PAGINATION HELPER (reuse across apps — define once per session):
```python
def paginate(api_fn, access_token=None, **kwargs):
    results, page = [], 0
    while True:
        call_kwargs = {**kwargs, "page_index": page, "page_limit": 20}
        if access_token is not None:
            call_kwargs["access_token"] = access_token
        batch = api_fn(**call_kwargs)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 20:
            break
        page += 1
    return results
```
"""

AMAZON_SHOP_PLAYBOOK = """
AMAZON SHOPPING PATTERN (search, cart, checkout):
- search_products(query=..., product_type=..., page_index=..., page_limit=...) returns product dicts
  with product_id, name, price, rating — paginate until you find the right item.
- show_product(product_id=...) for full details before adding to cart.
- add_product_to_cart(product_id=..., access_token=atok, quantity=1)
- place_order requires payment_card_id and address_id from show_payment_cards / show_addresses.
- apply_promo_code_to_cart(promo_code=..., access_token=atok) before place_order if instructed.
- Action flow: search → verify product_id → add to cart → place_order → complete_task(answer=None).

```python
atok = access_tokens["amazon"]
products = paginate(apis.amazon.search_products, None, query="wireless mouse")  # no token for search
# OR with token for cart ops:
cards = apis.amazon.show_payment_cards(access_token=atok)
addrs = apis.amazon.show_addresses(access_token=atok)
apis.amazon.add_product_to_cart(access_token=atok, product_id=products[0]["product_id"])
apis.amazon.place_order(access_token=atok, payment_card_id=cards[0]["payment_card_id"],
                        address_id=addrs[0]["address_id"])
apis.supervisor.complete_task(answer=None)
```
"""

AMAZON_ORDERS_PLAYBOOK = """
AMAZON ORDERS PATTERN (history, receipts, returns, QA):
- show_orders(access_token=atok, query=..., sort_by=...) — paginate for full history.
- Order dicts have order_id, order_items (list with product_id, ordered_quantity, price),
  status, created_at, paid_amount — NOT "products".
- show_order(order_id=..., access_token=atok) for single-order detail.
- download_order_receipt(order_id=..., access_token=atok, download_to_file_path="~/...",
  file_system_access_token=fs_tok) — needs file_system login too.
- initiate_return(order_id=..., product_id=..., deliverer_id=..., quantity=..., access_token=atok)
- QA ("how many orders", "total spent"): aggregate from paginated show_orders, then complete_task(answer=...).

```python
atok = access_tokens["amazon"]
orders = paginate(apis.amazon.show_orders, atok, query="headphones")
total = sum(
    item["price"] * item["ordered_quantity"]
    for o in orders for item in o["order_items"]
)
apis.supervisor.complete_task(answer=total)  # QA example
```
"""

GMAIL_PLAYBOOK = """
GMAIL PATTERN (inbox search, read, send, reply):
- Thread listing APIs (show_inbox_threads, show_outbox_threads, show_archived_threads) return
  SUMMARIES only — use show_thread(email_thread_id=..., access_token=gtok) for full email bodies.
- All thread APIs support query, from_email, to_email, label, page_index, page_limit filters.
- show_email(email_id=..., access_token=gtok) for a single email's body and attachments.
- send_email(email_addresses=[...], subject=..., body=..., access_token=gtok)
- reply_to_email(email_thread_id=..., email_id=..., body=..., access_token=gtok)
- forward_email_from_thread(email_thread_id=..., email_id=..., email_addresses=[...], access_token=gtok)
- Attachments: download_attachment(attachment_id=..., file_system_access_token=fs_tok,
  download_to_file_path="~/Downloads/file.pdf", access_token=gtok)
- search_users(query=...) to resolve names → email addresses (no login needed).
- QA: read-only thread/email inspection, then complete_task(answer=<value>).

```python
gtok = access_tokens["gmail"]
threads = paginate(apis.gmail.show_inbox_threads, gtok, query="invoice")
thread = apis.gmail.show_thread(access_token=gtok, email_thread_id=threads[0]["email_thread_id"])
body = thread["emails"][0]["body"]
apis.gmail.send_email(access_token=gtok, email_addresses=["friend@example.com"],
                      subject="Re: invoice", body="Here is the info.")
apis.supervisor.complete_task(answer=None)
```
"""

PHONE_PLAYBOOK = """
PHONE PATTERN (contacts, relationships, texts, alarms):
- Login uses profile phone_number as username (NOT email) — auth preamble handles this.
- search_contacts(access_token=ptok, query=..., relationship=...) — relationship filter for
  "roommates", "parents", "coworkers", etc. Use show_contact_relationships() to list valid values.
- Contact dicts: first_name, last_name, phone_number, email, relationships (list).
- search_text_messages(access_token=ptok, query=..., phone_number=...) — parse amounts/requests
  from message text before acting in other apps.
- send_text_message(access_token=ptok, phone_number=..., message=...)
- get_current_date_and_time() — no login needed; use for date-relative tasks.
- Alarms: show_alarms → create_alarm(time=..., access_token=ptok) / update_alarm / delete_alarm.

```python
ptok = access_tokens["phone"]
roommates = apis.phone.search_contacts(access_token=ptok, relationship="roommate")
for c in roommates:
    print(c["first_name"], c["phone_number"])
msgs = apis.phone.search_text_messages(access_token=ptok, query="dinner")
apis.phone.send_text_message(access_token=ptok, phone_number=roommates[0]["phone_number"],
                             message="On my way!")
apis.supervisor.complete_task(answer=None)
```
"""

FILE_SYSTEM_PLAYBOOK = """
FILE SYSTEM PATTERN (read, write, move, compress):
- All paths use ~/ prefix (e.g. "~/Documents/report.txt", "~/Downloads/").
- show_directory(access_token=fs_tok, directory_path="~/", recursive=True, entry_type="files")
- show_file(file_path=..., access_token=fs_tok) returns content and metadata.
- create_file(file_path=..., content=..., access_token=fs_tok, overwrite=True)
- update_file(file_path=..., content=..., access_token=fs_tok)
- move_file / copy_file: source_file_path, destination_file_path, access_token=fs_tok
- compress_directory(directory_path=..., access_token=fs_tok, compressed_file_path="~/archive.zip")
- file_exists / directory_exists for checks before read/write.
- Other apps (gmail, amazon, todoist) may need file_system_access_token when downloading attachments.

```python
fs_tok = access_tokens["file_system"]
entries = apis.file_system.show_directory(access_token=fs_tok, directory_path="~/Documents", recursive=True)
content = apis.file_system.show_file(access_token=fs_tok, file_path="~/Documents/notes.txt")["content"]
apis.file_system.create_file(access_token=fs_tok, file_path="~/Documents/summary.txt",
                             content=content[:500], overwrite=True)
apis.supervisor.complete_task(answer=None)
```
"""

SIMPLE_NOTE_PLAYBOOK = """
SIMPLE NOTE PATTERN (search, read, create, update):
- search_notes(access_token=ntok, query=..., tags=..., pinned=...) returns note METADATA only
  (note_id, title, tags) — NO content. Call show_note(note_id=..., access_token=ntok) for content.
- Note dicts: note_id, title, content, tags (list), pinned (bool).
- create_note(title=..., content=..., access_token=ntok, tags=[...])
- update_note(note_id=..., access_token=ntok, title=..., content=..., tags=...)
- add_content_to_note(note_id=..., append_or_prepend="append"|"prepend", added_content=..., access_token=ntok)
- QA ("what does my habit note say"): search → show_note → complete_task(answer=extracted_value).

```python
ntok = access_tokens["simple_note"]
notes = paginate(apis.simple_note.search_notes, ntok, query="habit")
note = apis.simple_note.show_note(access_token=ntok, note_id=notes[0]["note_id"])
apis.supervisor.complete_task(answer=note["content"])  # QA example
```
"""

TODOIST_PLAYBOOK = """
TODOIST PATTERN (projects, tasks, create, complete):
- show_projects(access_token=ttok, query=..., is_archived=False) → project_id, name.
- show_sections(project_id=..., access_token=ttok) → section_id (optional grouping).
- show_tasks(project_id=..., access_token=ttok, is_completed=False, due_today=..., overdue=...)
  — paginate; task dicts have task_id, title, description, due_date, priority, is_completed.
- show_task(task_id=..., access_token=ttok) for full detail including subtasks.
- create_task(project_id=..., title=..., access_token=ttok, due_date=..., priority=..., section_id=...)
- update_task(task_id=..., access_token=ttok, is_completed=True) to mark done.
- create_sub_task(task_id=..., title=..., access_token=ttok)
- QA: count/list tasks with read-only show_tasks, complete_task(answer=...).

```python
ttok = access_tokens["todoist"]
projects = apis.todoist.show_projects(access_token=ttok, query="Work")
pid = projects[0]["project_id"]
tasks = paginate(apis.todoist.show_tasks, ttok, project_id=pid, is_completed=False)
apis.todoist.create_task(access_token=ttok, project_id=pid, title="Review PR", due_date="2026-06-10")
apis.todoist.update_task(access_token=ttok, task_id=tasks[0]["task_id"], is_completed=True)
apis.supervisor.complete_task(answer=None)
```
"""

SPLITWISE_PLAYBOOK = """
SPLITWISE PATTERN (groups, expenses, balances, settle up):
- show_groups(access_token=stok) → group_id, name, members.
- show_group_expenses(group_id=..., access_token=stok, query=...) — paginate for history.
- show_group_balance(access_token=stok, group_id=...) — who owes whom in a group.
- show_person_balance(email=..., access_token=stok) — total balance with one person.
- show_people_balance(access_token=stok) — aggregate across all contacts.
- record_expense(description=..., paid_amount=..., payer_email=..., debtor_emails=[...],
  access_token=stok, group_id=..., debt_amounts=[...]) — equal split if debt_amounts omitted.
- record_payment(payer_email=..., receiver_email=..., amount=..., access_token=stok, group_id=...)
- settle_up(email=..., access_token=stok, group_id=...) — clear outstanding group balance.
- search_users(access_token=stok, query=...) to resolve names → emails.
- QA: read balances/expenses only, complete_task(answer=<amount or count>).

```python
stok = access_tokens["splitwise"]
groups = apis.splitwise.show_groups(access_token=stok)
gid = groups[0]["group_id"]
balance = apis.splitwise.show_group_balance(access_token=stok, group_id=gid)
apis.splitwise.record_expense(access_token=stok, group_id=gid, description="Dinner",
    paid_amount=120.0, payer_email=email,
    debtor_emails=["friend1@example.com", "friend2@example.com"])
apis.supervisor.complete_task(answer=None)
```
"""

VENMO_PLAYBOOK = """
VENMO PATTERN (payments, requests, transaction history):
- Login uses supervisor email as username.
- search_friends / search_users(access_token=vtok, query=...) → email (NOT user_id).
- create_transaction(access_token=vtok, receiver_email=..., amount=..., description=...)
  — amount must be a float, NEVER None.
- create_payment_request(user_email=..., amount=..., access_token=vtok, description=...)
- show_received_payment_requests(access_token=vtok, status="pending") → approve/deny.
- approve_payment_request(payment_request_id=..., access_token=vtok, payment_card_id=...)
- show_transactions(access_token=vtok, query=..., min_amount=..., max_amount=..., direction=...)
  — paginate for QA aggregation tasks.
- show_venmo_balance(access_token=vtok) for balance QA.
- Friend dicts: {first_name, last_name, email} — use email for all payment APIs.

```python
vtok = access_tokens["venmo"]
friends = apis.venmo.search_friends(access_token=vtok, query="Alex")
receiver = friends[0]["email"]
apis.venmo.create_transaction(access_token=vtok, receiver_email=receiver,
                              amount=25.0, description="Lunch")
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

MAX_PLAYBOOK_CHARS = 4500
MAX_PLAYBOOK_APPS = 3

_DATA_APPS = frozenset({
    "spotify", "amazon", "gmail", "phone", "simple_note", "todoist", "splitwise", "venmo",
})


def _score_app(app: str, instruction: str) -> int:
    score = 0
    for kw in APP_KEYWORDS.get(app, []):
        if _matches_keyword(instruction, kw):
            score += 3 if " " in kw else 1
    return score


def _matches_keyword(text: str, keyword: str) -> bool:
    if keyword.startswith("~/") or " " in keyword:
        return keyword in text
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text))


def _ranked_apps(plan: dict) -> list[str]:
    instruction = plan.get("_instruction", "").lower()
    apps = list(plan.get("likely_apps", []))
    return sorted(apps, key=lambda a: _score_app(a, instruction), reverse=True)


def _playbooks_for_app(app: str, apps: set[str], instruction: str) -> list[str]:
    parts: list[str] = []
    if app == "spotify":
        if any(w in instruction for w in (
            "previous", "next song", "reach a song", "until you reach", "skip", "player",
        )):
            parts.append(SPOTIFY_PLAYER_PLAYBOOK)
        else:
            parts.append(SPOTIFY_LIBRARY_PLAYBOOK)
    elif app == "amazon":
        if any(w in instruction for w in (
            "order", "return", "delivered", "receipt", "purchase history", "past order",
            "how many order", "shipped",
        )):
            parts.append(AMAZON_ORDERS_PLAYBOOK)
        else:
            parts.append(AMAZON_SHOP_PLAYBOOK)
    elif app == "gmail":
        parts.append(GMAIL_PLAYBOOK)
    elif app == "venmo":
        venmo_phone = (
            "phone" in apps
            and any(w in instruction for w in (
                "pay", "payment", "venmo", "text", "message", "money", "$", "transaction",
            ))
        )
        if venmo_phone:
            parts.append(VENMO_PHONE_PLAYBOOK)
        else:
            parts.append(VENMO_PLAYBOOK)
    elif app == "phone":
        venmo_phone = (
            "venmo" in apps
            and any(w in instruction for w in (
                "pay", "payment", "venmo", "text", "message", "money", "$", "transaction",
            ))
        )
        if not venmo_phone:
            parts.append(PHONE_PLAYBOOK)
    elif app == "file_system":
        parts.append(FILE_SYSTEM_PLAYBOOK)
    elif app == "simple_note":
        parts.append(SIMPLE_NOTE_PLAYBOOK)
    elif app == "todoist":
        parts.append(TODOIST_PLAYBOOK)
    elif app == "splitwise":
        parts.append(SPLITWISE_PLAYBOOK)
    return parts


def _task_playbooks(plan: dict) -> str:
    instruction = plan.get("_instruction", "").lower()
    all_apps = set(plan.get("likely_apps", []))
    ranked = _ranked_apps(plan)[:MAX_PLAYBOOK_APPS]

    parts: list[str] = []
    if all_apps & _DATA_APPS:
        parts.append(PAGINATE_HELPER)

    for app in ranked:
        parts.extend(_playbooks_for_app(app, all_apps, instruction))

    result = "\n".join(p for p in parts if p)
    if len(result) > MAX_PLAYBOOK_CHARS:
        result = result[:MAX_PLAYBOOK_CHARS] + "\n... (playbook truncated)"
    return result


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
    if plan.get("task_type") == "qa":
        return (
            "Reminder: QA task — read-only API calls only. "
            "Call complete_task(answer=<computed value>) when ready."
        )
    apps = set(plan.get("likely_apps", []))
    if not apps.intersection({
        "venmo", "phone", "gmail", "spotify", "amazon", "splitwise",
        "todoist", "file_system", "simple_note",
    }):
        return ""
    return (
        "Reminder: print API results before writes. "
        "Use exact amounts from phone texts, emails, or notes. "
        "Action tasks: complete_task(answer=None) only."
    )
