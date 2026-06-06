import re


def sanitize_complete_task(code: str, task_type: str) -> str:
    """Enforce correct complete_task(answer=...) for task type."""
    if task_type == "qa":
        # Block QA tasks from completing with answer=None (including answer=None.join(...))
        code = re.sub(
            r"complete_task\s*\(\s*answer\s*=\s*None\.join\s*\([^)]*\)\s*\)",
            "# complete_task blocked: QA tasks need answer=<computed value>",
            code,
        )
        code = re.sub(
            r"complete_task\s*\(\s*answer\s*=\s*None\s*\)",
            "# complete_task blocked: QA tasks need answer=<computed value>",
            code,
        )
        if re.search(r"complete_task\s*\(\s*\)", code):
            code = re.sub(
                r"complete_task\s*\(\s*\)",
                "# complete_task blocked: QA tasks need answer=<computed value>",
                code,
            )
        return code

    # Action tasks must call complete_task(answer=None), never a status string.
    if "complete_task" not in code:
        return code

    # complete_task(answer="...") or complete_task(answer='...')
    code = re.sub(
        r"complete_task\s*\(\s*answer\s*=\s*(['\"]).*?\1",
        "complete_task(answer=None",
        code,
        flags=re.DOTALL,
    )
    # complete_task(answer=f"...")
    code = re.sub(
        r"complete_task\s*\(\s*answer\s*=\s*f(['\"]).*?\1",
        "complete_task(answer=None",
        code,
        flags=re.DOTALL,
    )
    return code
