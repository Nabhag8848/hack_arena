import json
import re
from typing import Any

from agent.config import APP_KEYWORDS
from agent.llm import call_planner
from agent.prompts import PLANNER_PROMPT, format_plan


QA_PATTERNS = re.compile(
    r"^(what|how many|how much|which|when|who|where|count|total|number of|give me|tell me|list)\b",
    re.I,
)

QA_EXTRA_PATTERNS = [
    re.compile(r"\bhow much (?:do )?i owe\b", re.I),
    re.compile(r"\bfind out\b", re.I),
    re.compile(r"\bfigure out\b", re.I),
    re.compile(r"\btell me (?:what|how|which|the)\b", re.I),
    re.compile(r"\bcalculate\b", re.I),
    re.compile(r"\bdetermine\b", re.I),
]


def _matches_keyword(text: str, keyword: str) -> bool:
    """Match whole words/phrases; avoid substring traps like 'expense' in 'expenses'."""
    if keyword.startswith("~/") or " " in keyword:
        return keyword in text
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text))


def detect_apps(instruction: str) -> list[str]:
    text = instruction.lower()
    found: list[str] = []
    for app, keywords in APP_KEYWORDS.items():
        if any(_matches_keyword(text, kw) for kw in keywords):
            found.append(app)
    relational = [
        "roommate", "coworker", "parent", "contact",
        "brother", "sister", "wife", "husband", "family",
    ]
    if any(_matches_keyword(text, r) for r in relational) and "phone" not in found:
        found.append("phone")
    # Bare "note" for simple_note — exclude todoist/file contexts
    if _matches_keyword(text, "note") and "simple note" not in text and "simplenote" not in text:
        if "todoist" not in found and "to my file" not in text and "to the file" not in text:
            if "simple_note" not in found:
                found.append("simple_note")
    # file_system when file/path context appears
    if "file_system" not in found:
        if any(x in text for x in ("~/", "directory", "folder", "path", "zip", "download", "upload", "compress")):
            found.append("file_system")
        elif any(x in text for x in ("to my file", "to the file", "in my file", "the file at")):
            found.append("file_system")
        elif _matches_keyword(text, "file") and _matches_keyword(text, "note"):
            found.append("file_system")
    # Payment verbs → venmo only when splitwise not named
    if _matches_keyword(text, "pay") and "venmo" not in found and "splitwise" not in found:
        if any(_matches_keyword(text, w) for w in ("venmo", "friend", "transfer", "money")):
            found.append("venmo")
    return found


def classify_task_type(instruction: str) -> str:
    stripped = instruction.strip()
    lower = stripped.lower()
    if QA_PATTERNS.search(stripped):
        return "qa"
    if any(p.search(lower) for p in QA_EXTRA_PATTERNS):
        return "qa"
    action_verbs = [
        "send", "pay", "create", "delete", "remove", "add", "update",
        "befriend", "unfriend", "order", "buy", "mark", "complete",
        "transfer", "request", "share", "upload", "download", "zip",
        "invite", "set", "start", "stop", "play", "like", "unlike",
        "record", "compress", "move", "copy",
        "please do", "do them", "do it",
    ]
    if any(v in lower for v in action_verbs):
        return "action"
    if stripped.endswith("?"):
        return "qa"
    if any(p in lower for p in (
        "comma-separated", "comma separated", "list of", "top ", "how many", "give me",
    )):
        return "qa"
    return "action"


def _default_subgoals(task_type: str, apps: list[str]) -> list[str]:
    subgoals = []
    login_apps = [a for a in apps if a != "supervisor"]
    if login_apps:
        subgoals.append(f"Authenticate to: {', '.join(login_apps)}")
    if task_type == "qa":
        subgoals.append("Gather read-only data to compute the answer")
        subgoals.append("Call complete_task(answer=<computed answer>) without mutating state")
    else:
        subgoals.append("Execute required actions step by step")
        subgoals.append("Verify state changes are correct")
        subgoals.append("Call complete_task(answer=None)")
    return subgoals


def _default_cautions(task_type: str, apps: list[str]) -> list[str]:
    cautions = []
    if task_type == "qa":
        cautions.append("Do not mutate any database state")
        cautions.append("complete_task must include the computed answer")
    else:
        cautions.append("complete_task answer must be None, not a status string")
    if "phone" in apps:
        cautions.append("Use phone contacts to resolve relational references (roommates, parents, etc.)")
    if "venmo" in apps:
        cautions.append("Read exact payment amount from phone text messages — do not guess")
        cautions.append("Verify user IDs before befriending/unfriending or sending payments")
    if "spotify" in apps:
        cautions.append("Library APIs return a list directly, not a dict with a songs key")
    return cautions


def heuristic_plan(instruction: str) -> dict[str, Any]:
    task_type = classify_task_type(instruction)
    apps = detect_apps(instruction)
    if not apps and task_type == "qa":
        apps = ["simple_note", "spotify", "amazon"]
    return {
        "task_type": task_type,
        "likely_apps": apps,
        "subgoals": _default_subgoals(task_type, apps),
        "cautions": _default_cautions(task_type, apps),
    }


def _needs_llm_plan(plan: dict[str, Any]) -> bool:
    apps = plan.get("likely_apps", [])
    return len(apps) >= 3


def _parse_plan_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            return None
    return None


def create_plan(instruction: str, supervisor: Any) -> dict[str, Any]:
    base = heuristic_plan(instruction)
    base["_instruction"] = instruction
    if not _needs_llm_plan(base):
        return base

    sup_text = str(supervisor)
    messages = [{
        "role": "user",
        "content": (
            f"Supervisor: {sup_text}\n\n"
            f"Instruction: {instruction}\n\n"
            f"Heuristic guess: task_type={base['task_type']}, apps={base['likely_apps']}"
        ),
    }]
    try:
        reply = call_planner(messages, PLANNER_PROMPT)
        parsed = _parse_plan_json(reply)
        if parsed and "subgoals" in parsed:
            parsed.setdefault("task_type", base["task_type"])
            parsed.setdefault("likely_apps", base["likely_apps"])
            parsed.setdefault("cautions", base["cautions"])
            if not parsed["likely_apps"]:
                parsed["likely_apps"] = base["likely_apps"]
            parsed["_instruction"] = instruction
            return parsed
    except Exception:
        pass
    return base


def plan_to_text(plan: dict[str, Any]) -> str:
    return format_plan(plan)
