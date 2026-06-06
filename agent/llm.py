import re
import time

from groq import APIStatusError, Groq, RateLimitError

from agent.config import (
    EXEC_TEMPERATURE,
    GROQ_API_KEY,
    MAX_TOKENS,
    MODEL,
    PLANNER_TEMPERATURE,
)

_client: Groq | None = None


def _is_daily_quota_exhausted(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "tokens per day" in msg or "tpd" in msg


def get_client() -> Groq:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        _client = Groq(api_key=GROQ_API_KEY)
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
            if _is_daily_quota_exhausted(e):
                raise RuntimeError(
                    "Groq daily token limit reached. Wait for reset or upgrade at "
                    "https://console.groq.com/settings/billing"
                ) from e
            if attempt == 4:
                raise
            wait = 6 * (attempt + 1)
            print(f"  [llm] rate limited, retrying in {wait}s...", flush=True)
            time.sleep(wait)
        except APIStatusError as e:
            if e.status_code == 429 and _is_daily_quota_exhausted(e):
                raise RuntimeError(
                    "Groq daily token limit reached. Wait for reset or upgrade at "
                    "https://console.groq.com/settings/billing"
                ) from e
            if e.status_code == 429 and attempt < 4:
                wait = 6 * (attempt + 1)
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
