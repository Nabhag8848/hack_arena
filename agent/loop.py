from dataclasses import dataclass, field
from typing import Any

from appworld import AppWorld

from agent.api_index import get_api_index
from agent.code_sanitize import sanitize_complete_task
from agent.config import (
    APPS_WITH_LOGIN,
    MAX_INTERACTIONS,
    MAX_REFLECTIONS,
    MAX_STEP_HISTORY,
)
from agent.hydradb_ctx import get_hydra_context
from agent.llm import call_llm, extract_code
from agent.planner import create_plan, plan_to_text
from agent.prompts import (
    REFLECT_PROMPT,
    build_system_prompt,
    completion_guard_prompt,
    precision_reminder,
)


@dataclass
class StepRecord:
    step: int
    code: str
    output: str
    is_error: bool = False


@dataclass
class SolveState:
    plan: dict[str, Any]
    step_history: list[StepRecord] = field(default_factory=list)
    reflections_used: int = 0


def _is_error_output(output: str) -> bool:
    if not output or not str(output).strip():
        return True
    text = str(output).lower()
    if "execution successful" in text:
        return False
    markers = [
        "execution failed", "traceback", "exception",
        '"failure"', "'failure'",
    ]
    return any(m in text for m in markers)


def build_auth_preamble(apps: list[str]) -> str:
    login_apps = [a for a in apps if a in APPS_WITH_LOGIN]
    if not login_apps:
        login_apps = sorted(APPS_WITH_LOGIN)

    lines = [
        "# Auto-auth preamble: credentials + login tokens",
        "passwords_list = apis.supervisor.show_account_passwords()",
        "passwords = {p['account_name']: p['password'] for p in passwords_list}",
        "profile = apis.supervisor.show_profile()",
        "email = profile['email']",
        "phone_username = profile.get('phone_number', email)",
        "access_tokens = {}",
    ]
    for app in login_apps:
        username = "phone_username" if app == "phone" else "email"
        lines.append("try:")
        lines.append(
            f"    _login = apis.{app}.login(username={username}, password=passwords['{app}'])"
        )
        lines.append(f"    access_tokens['{app}'] = _login['access_token']")
        lines.append("except Exception as e:")
        lines.append(f"    print(f'{app} login failed: {{e}}')")
    lines.append("print('Authenticated apps:', list(access_tokens.keys()))")
    lines.append("print('access_tokens ready for use in subsequent steps')")
    return "\n".join(lines)


def _summarize_steps(history: list[StepRecord], max_steps: int = MAX_STEP_HISTORY) -> str:
    recent = history[-max_steps:]
    if not recent:
        return ""
    lines = ["Recent steps:"]
    for rec in recent:
        status = "ERROR" if rec.is_error else "OK"
        out_preview = str(rec.output)[:300].replace("\n", " ")
        lines.append(f"  Step {rec.step} [{status}]: {out_preview}")
    return "\n".join(lines)


def _build_user_message(
    world: AppWorld,
    state: SolveState,
    *,
    extra: str = "",
) -> str:
    parts = [
        f"Supervisor: {world.task.supervisor}",
        f"Task: {world.task.instruction}",
    ]
    if extra:
        parts.append(extra)
    summary = _summarize_steps(state.step_history)
    if summary:
        parts.append(summary)
    parts.append("Write the next Python code block. One block only.")
    return "\n\n".join(parts)


def solve(world: AppWorld) -> bool:
    api_index = get_api_index()
    hydra = get_hydra_context()

    print("  planning...", flush=True)
    plan = create_plan(world.task.instruction, world.task.supervisor)
    state = SolveState(plan=plan)
    plan_text = plan_to_text(plan)

    hydra_context = hydra.recall_for_task(world.task.instruction, world.task_id)
    api_docs_text = api_index.format_search_results(
        world.task.instruction,
        apps=plan.get("likely_apps"),
    )

    # Step 0: deterministic auth preamble
    auth_code = build_auth_preamble(plan.get("likely_apps", []))
    auth_output = world.execute(auth_code)
    is_err = _is_error_output(auth_output)
    state.step_history.append(StepRecord(0, auth_code, str(auth_output), is_err))
    hydra.store_step(world.task_id, 0, auth_code, str(auth_output), is_error=is_err)
    print(f"  step 0 (auth): {str(auth_output)[:120]!r}")

    messages: list[dict] = [{
        "role": "user",
        "content": _build_user_message(
            world,
            state,
            extra=(
                f"Auth preamble executed. Output:\n{auth_output}\n\n"
                f"access_tokens dict is available in the session."
            ),
        ),
    }]

    success = False
    for step in range(1, MAX_INTERACTIONS + 1):
        steps_remaining = MAX_INTERACTIONS - step

        if steps_remaining <= 3:
            guard = completion_guard_prompt(plan, steps_remaining)
            messages.append({"role": "user", "content": guard})

        if plan.get("task_type") == "qa" and step >= 2 and not success:
            last = state.step_history[-1] if state.step_history else None
            if last and not last.is_error and "complete_task" not in last.code:
                messages.append({
                    "role": "user",
                    "content": (
                        "QA task: you already computed the answer in the last step. "
                        "Reuse session variables — do NOT re-fetch data. "
                        "Call apis.supervisor.complete_task(answer=<value>) now."
                    ),
                })

        reminder = precision_reminder(plan)
        if reminder and step % 4 == 0:
            messages.append({"role": "user", "content": reminder})

        current_subgoal = ""
        subgoals = plan.get("subgoals", [])
        if subgoals and step - 1 < len(subgoals):
            current_subgoal = subgoals[min(step - 1, len(subgoals) - 1)]

        step_api_docs = api_index.format_search_results(
            f"{world.task.instruction} {current_subgoal}",
            apps=plan.get("likely_apps"),
        )
        step_hydra = hydra.recall_for_step(
            f"{current_subgoal} {world.task.instruction[:200]}",
            world.task_id,
        )
        combined_hydra = hydra_context
        if step_hydra:
            combined_hydra = f"{hydra_context}\n\n{step_hydra}" if hydra_context else step_hydra

        system = build_system_prompt(
            plan_text,
            step_api_docs or api_docs_text,
            hydra_context=combined_hydra,
            plan=plan,
        )

        print(f"  [llm] step {step}...", flush=True)
        reply = call_llm(messages, system)
        code = sanitize_complete_task(
            extract_code(reply),
            plan.get("task_type", "action"),
        )
        output = world.execute(code)
        is_err = _is_error_output(output)

        print(f"  step {step}: ran {len(code)} chars -> {str(output)[:120]!r}")

        state.step_history.append(StepRecord(step, code, str(output), is_err))
        hydra.store_step(world.task_id, step, code, str(output), is_error=is_err)

        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": f"Execution output:\n{output}"})

        if is_err and state.reflections_used < MAX_REFLECTIONS:
            state.reflections_used += 1
            err_memory = hydra.recall_errors(world.task_id, str(output)[:500])
            reflect_msg = REFLECT_PROMPT
            err_text = str(output)
            if "receiver_id" in err_text or "receiver_email" in err_text:
                reflect_msg += (
                    "\nVenmo create_transaction uses receiver_email (from search_friends "
                    "email field), NOT receiver_id."
                )
            if "release_year" in err_text or "KeyError: 'artist'" in err_text:
                reflect_msg += (
                    "\nSpotify: use release_date[:4] for year; current_song has "
                    "artists list not artist string."
                )
            if err_memory:
                reflect_msg += f"\n\nPast errors/recoveries:\n{err_memory}"
            messages.append({"role": "user", "content": reflect_msg})

        # Trim message history to avoid context overflow
        if len(messages) > MAX_STEP_HISTORY * 2 + 2:
            messages = [messages[0]] + messages[-(MAX_STEP_HISTORY * 2):]

        if world.task_completed():
            print("  ✓ task_completed")
            success = True
            break

    if not success:
        print("  ✗ hit MAX_INTERACTIONS without completion")

    hydra.store_task_outcome(
        world.task.instruction,
        plan,
        success=success,
        task_id=world.task_id,
    )
    return success
