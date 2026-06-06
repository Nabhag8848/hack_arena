import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
API_DOCS_DIR = ROOT_DIR / "data" / "api_docs" / "standard"
IPYTHON_DIR = ROOT_DIR / ".ipython"
EXPERIMENTS_OUTPUT_DIR = ROOT_DIR / "experiments" / "outputs"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except Exception:
    pass

# --- AppWorld run ---
APPWORLD_DATASET = os.environ.get("APPWORLD_DATASET", "dev")
APPWORLD_EXPERIMENT = os.environ.get("APPWORLD_EXPERIMENT", "team_demo")
MAX_INTERACTIONS = int(os.environ.get("MAX_INTERACTIONS", "60"))
MAX_TASKS = int(os.environ.get("MAX_TASKS", "0"))
SKIP_COMPLETED = os.environ.get("SKIP_COMPLETED", "1") == "1"

# --- LLM (Groq) ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
DEFAULT_MODEL = "llama-3.3-70b-versatile"
MODEL = os.environ.get("MODEL", DEFAULT_MODEL)


def validate_llm_config() -> None:
    """Fail fast before running tasks if Groq API key is not configured."""
    if not GROQ_API_KEY.strip():
        raise RuntimeError(
            "GROQ_API_KEY is not set in .env.\n"
            "  Get a key at https://console.groq.com/keys"
        )


MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "2500"))
PLANNER_TEMPERATURE = float(os.environ.get("PLANNER_TEMPERATURE", "0.2"))
EXEC_TEMPERATURE = float(os.environ.get("EXEC_TEMPERATURE", "0.0"))

# --- HydraDB (https://hydradb.com) ---
HYDRA_DB_ENABLED = os.environ.get("HYDRA_DB_ENABLED", "1") == "1"
HYDRA_DB_API_KEY = os.environ.get("HYDRA_DB_API_KEY", "")
HYDRA_DB_TENANT = os.environ.get("HYDRA_DB_TENANT", APPWORLD_EXPERIMENT)
HYDRA_DB_SEED_ON_START = os.environ.get("HYDRA_DB_SEED_ON_START", "0") == "1"
HYDRA_DB_QUERY_ENABLED = os.environ.get("HYDRA_DB_QUERY_ENABLED", "0") == "1"
HYDRA_DB_SEED_MARKER = ROOT_DIR / ".hydradb_seeded"

# --- Agent tuning ---
MAX_RETRIEVED_APIS = int(os.environ.get("MAX_RETRIEVED_APIS", "12"))
MAX_STEP_HISTORY = int(os.environ.get("MAX_STEP_HISTORY", "6"))
MAX_REFLECTIONS = int(os.environ.get("MAX_REFLECTIONS", "3"))

APPS_WITH_LOGIN = {
    "amazon", "file_system", "gmail", "phone", "simple_note",
    "splitwise", "spotify", "todoist", "venmo",
}

APP_KEYWORDS: dict[str, list[str]] = {
    "amazon": ["amazon", "cart", "product", "shopping", "delivery", "purchase", "checkout", "prime"],
    "spotify": ["spotify", "song", "playlist", "album", "artist", "music", "player"],
    "venmo": ["venmo", "venmo payment", "payment request"],
    "gmail": ["gmail", "email", "inbox", "attachment", "mail thread", "send email"],
    "phone": ["phone", "text message", "texting", "roommate", "coworker", "parent", "call"],
    "file_system": ["file system", "folder", "directory", "path", "~/", "zip", "download", "upload"],
    "simple_note": ["simple note", "simplenote", "habit", "tracking"],
    "todoist": ["todoist", "project", "task", "todo", "subtask"],
    "splitwise": ["splitwise", "split the bill", "settle up", "splitwise expense"],
}


def setup_runtime_dirs() -> None:
    """Ensure writable runtime dirs exist (IPython, experiments output)."""
    IPYTHON_DIR.mkdir(exist_ok=True)
    EXPERIMENTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("IPYTHONDIR", str(IPYTHON_DIR))


setup_runtime_dirs()
