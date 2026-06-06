import re
import time

from openai import APIStatusError, OpenAI, RateLimitError

from agent.config import (
    EXEC_TEMPERATURE,
    MAX_TOKENS,
    MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    PLANNER_TEMPERATURE,
)

_client: OpenAI | None = None


def _is_quota_exhausted(exc: Exception) -> bool:
    msg = str(exc).lower()
    if any(s in msg for s in ("temporarily rate-limited", "retry shortly", "retry after")):
        return False
    return any(
        s in msg
        for s in ("tokens per day", "tpd", "insufficient credits", "quota exceeded")
    )


def _retry_wait_seconds(exc: Exception, attempt: int) -> int:
    msg = str(exc)
    for pattern in (
        r"'retry_after_seconds': (\d+)",
        r"'Retry-After': '(\d+)'",
        r"retry after (\d+) seconds",
    ):
        m = re.search(pattern, msg, re.I)
        if m:
            return int(m.group(1)) + 1
    return 6 * (attempt + 1)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set in .env")
        headers: dict[str, str] = {}
        if OPENROUTER_HTTP_REFERER:
            headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
        if OPENROUTER_APP_TITLE:
            headers["X-Title"] = OPENROUTER_APP_TITLE
        _client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
            default_headers=headers or None,
        )
    return _client


def call_llm(
    messages: list[dict],
    system_prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    for attempt in range(5):
        try:
            resp = get_client().chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": system_prompt}, *messages],
                max_tokens=max_tokens or MAX_TOKENS,
                temperature=temperature if temperature is not None else EXEC_TEMPERATURE,
            )
            content = resp.choices[0].message.content or ""
            time.sleep(1)
            return content
        except RateLimitError as e:
            if _is_quota_exhausted(e):
                raise RuntimeError(
                    "OpenRouter rate/quota limit reached. Wait and retry or check "
                    "https://openrouter.ai/settings/keys"
                ) from e
            if attempt == 4:
                raise
            wait = _retry_wait_seconds(e, attempt)
            print(f"  [llm] rate limited, retrying in {wait}s...", flush=True)
            time.sleep(wait)
        except APIStatusError as e:
            if e.status_code == 429 and _is_quota_exhausted(e):
                raise RuntimeError(
                    "OpenRouter rate/quota limit reached. Wait and retry or check "
                    "https://openrouter.ai/settings/keys"
                ) from e
            if e.status_code == 429 and attempt < 4:
                wait = _retry_wait_seconds(e, attempt)
                print(f"  [llm] rate limited ({e.status_code}), retrying in {wait}s...", flush=True)
                time.sleep(wait)
                continue
            raise
    return ""


def call_planner(messages: list[dict], system_prompt: str) -> str:
    return call_llm(
        messages,
        system_prompt,
        temperature=PLANNER_TEMPERATURE,
        max_tokens=600,
    )


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return m.group(1).strip() if m else text.strip()
