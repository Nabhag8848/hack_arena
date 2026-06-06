import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from agent.config import API_DOCS_DIR, MAX_RETRIEVED_APIS

ESSENTIAL_APIS: dict[str, list[str]] = {
    "amazon": ["login", "show_orders", "show_products", "add_to_cart", "checkout"],
    "spotify": [
        "login", "show_song", "show_song_library", "show_album_library",
        "show_liked_songs", "show_playlist_library", "show_playlist",
        "show_current_song", "previous_song", "show_account",
    ],
    "venmo": [
        "login", "show_transactions", "show_friends", "search_friends",
        "search_users", "create_transaction",
    ],
    "gmail": ["login", "show_inbox", "send_email", "search_emails", "show_email"],
    "phone": ["login", "show_contacts", "search_contacts", "search_text_messages", "send_text_message"],
    "file_system": ["login", "show_directory", "show_file", "create_directory", "compress_files"],
    "simple_note": ["login", "show_notes", "search_notes", "show_note"],
    "todoist": ["login", "show_projects", "show_tasks", "create_task", "update_task"],
    "splitwise": ["login", "show_groups", "show_expenses", "create_expense"],
    "supervisor": ["show_account_passwords", "show_profile", "complete_task"],
}


@dataclass
class ApiDoc:
    app_name: str
    api_name: str
    method: str
    path: str
    description: str
    parameters: list[dict]
    text: str


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _format_api_markdown(doc: ApiDoc) -> str:
    lines = [
        f"### {doc.app_name}.{doc.api_name} ({doc.method} {doc.path})",
        doc.description,
        "Parameters:",
    ]
    for p in doc.parameters:
        req = "required" if p.get("required") else "optional"
        lines.append(
            f"  - {p.get('name')} ({p.get('type', 'string')}, {req}): "
            f"{p.get('description', '')}"
        )
    return "\n".join(lines)


class ApiIndex:
    def __init__(self, docs_dir: Path | None = None):
        self.docs: list[ApiDoc] = []
        self._df: dict[str, float] = {}
        self._load(docs_dir or API_DOCS_DIR)

    def _load(self, docs_dir: Path) -> None:
        if not docs_dir.exists():
            return
        for path in sorted(docs_dir.glob("*.json")):
            if path.name == "api_docs.json":
                continue
            raw = json.loads(path.read_text())
            app = path.stem
            for api_name, spec in raw.items():
                params = spec.get("parameters", [])
                desc = spec.get("description", "")
                param_text = " ".join(
                    f"{p.get('name', '')} {p.get('description', '')}" for p in params
                )
                text = f"{app} {api_name} {desc} {param_text} {spec.get('path', '')}"
                self.docs.append(
                    ApiDoc(
                        app_name=spec.get("app_name", app),
                        api_name=api_name,
                        method=spec.get("method", ""),
                        path=spec.get("path", ""),
                        description=desc,
                        parameters=params,
                        text=text,
                    )
                )
        self._build_idf()

    def _build_idf(self) -> None:
        n = len(self.docs)
        if n == 0:
            return
        doc_freq: dict[str, int] = {}
        for doc in self.docs:
            tokens = set(_tokenize(doc.text))
            for t in tokens:
                doc_freq[t] = doc_freq.get(t, 0) + 1
        self._df = {t: math.log((n + 1) / (df + 1)) + 1 for t, df in doc_freq.items()}

    def _score(self, query_tokens: list[str], doc: ApiDoc) -> float:
        doc_tokens = _tokenize(doc.text)
        if not doc_tokens:
            return 0.0
        tf: dict[str, int] = {}
        for t in doc_tokens:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for qt in query_tokens:
            if qt in tf:
                score += (1 + math.log(tf[qt])) * self._df.get(qt, 1.0)
            if qt in doc.app_name or qt in doc.api_name:
                score += 5.0
        return score

    def search(
        self,
        query: str,
        *,
        apps: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[ApiDoc]:
        top_k = top_k or MAX_RETRIEVED_APIS
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        candidates = self.docs
        if apps:
            app_set = {a.lower() for a in apps}
            candidates = [d for d in self.docs if d.app_name in app_set]

        scored = [(self._score(query_tokens, d), d) for d in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)

        seen: set[tuple[str, str]] = set()
        results: list[ApiDoc] = []
        for score, doc in scored:
            if score <= 0:
                continue
            key = (doc.app_name, doc.api_name)
            if key in seen:
                continue
            seen.add(key)
            results.append(doc)
            if len(results) >= top_k:
                break
        return results

    def get_docs_by_names(self, app_name: str, api_names: list[str]) -> list[ApiDoc]:
        names = set(api_names)
        return [d for d in self.docs if d.app_name == app_name and d.api_name in names]

    def format_search_results(self, query: str, apps: list[str] | None = None) -> str:
        essential: list[ApiDoc] = []
        if apps:
            for app in apps:
                api_names = ESSENTIAL_APIS.get(app, [])
                essential.extend(self.get_docs_by_names(app, api_names))
            essential.extend(self.get_docs_by_names("supervisor", ESSENTIAL_APIS["supervisor"]))

        searched = self.search(query, apps=apps)
        seen: set[tuple[str, str]] = set()
        merged: list[ApiDoc] = []
        for doc in essential + searched:
            key = (doc.app_name, doc.api_name)
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
            if len(merged) >= MAX_RETRIEVED_APIS:
                break
        if not merged:
            return ""
        return "\n\n".join(_format_api_markdown(d) for d in merged)

    def get_login_doc(self, app_name: str) -> ApiDoc | None:
        for doc in self.docs:
            if doc.app_name == app_name and doc.api_name == "login":
                return doc
        return None

    def all_docs_for_hydradb(self) -> list[tuple[str, str, dict]]:
        """Return (id, text, metadata) tuples for HydraDB knowledge seeding."""
        items = []
        for doc in self.docs:
            doc_id = f"{doc.app_name}__{doc.api_name}"
            items.append((
                doc_id,
                _format_api_markdown(doc),
                {"app": doc.app_name, "api": doc.api_name},
            ))
        return items


_index: ApiIndex | None = None


def get_api_index() -> ApiIndex:
    global _index
    if _index is None:
        _index = ApiIndex()
    return _index
