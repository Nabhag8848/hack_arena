import json
import time
from typing import Any

from agent.config import (
    APPWORLD_EXPERIMENT,
    HYDRA_DB_API_KEY,
    HYDRA_DB_ENABLED,
    HYDRA_DB_QUERY_ENABLED,
    HYDRA_DB_SEED_MARKER,
    HYDRA_DB_SEED_ON_START,
    HYDRA_DB_TENANT,
)
from agent.api_index import get_api_index


def _short_error(exc: Exception) -> str:
    msg = str(exc)
    if "TENANT_NOT_FOUND" in msg:
        return "TENANT_NOT_FOUND (tenant still provisioning)"
    if "status_code:" in msg:
        for part in msg.split(","):
            if "code" in part.lower() or "message" in part.lower():
                return part.strip()[:120]
    return msg[:160]


class HydraContext:
    """HydraDB v2 wrapper — optional, degrades gracefully if unavailable."""

    def __init__(self) -> None:
        self.enabled = False
        self.client: Any = None
        self.tenant_id = HYDRA_DB_TENANT or APPWORLD_EXPERIMENT
        self._seeded = False

        if not HYDRA_DB_ENABLED or not HYDRA_DB_API_KEY:
            return
        try:
            from hydra_db import HydraDB
            self.client = HydraDB(token=HYDRA_DB_API_KEY)
            self._ensure_tenant()
            self.enabled = True
        except Exception as e:
            print(f"  [hydra] disabled: {e}")

    def _tenant_ready(self) -> bool:
        if not self.client:
            return False
        try:
            status = self.client.tenants.status(tenant_id=self.tenant_id)
            return bool(status.data.infra.ready_for_ingestion)
        except Exception:
            return False

    def _ensure_tenant(self) -> None:
        if not self.client:
            return
        if self._tenant_ready():
            return
        try:
            self.client.tenants.create(tenant_id=self.tenant_id)
        except Exception:
            pass
        for attempt in range(30):
            if self._tenant_ready():
                if attempt:
                    print(f"  [hydra] tenant ready after {attempt * 2}s", flush=True)
                return
            time.sleep(2)
        print("  [hydra] warning: tenant may not be ready for ingestion yet", flush=True)

    def _ingest_knowledge_batch(self, batch: list[tuple[str, str, dict]]) -> bool:
        if not self.client:
            return False
        docs = [(doc_id, text.encode(), "text/markdown") for doc_id, text, _ in batch]
        meta = json.dumps([
            {
                "id": doc_id,
                "metadata": meta,
                "additional_metadata": meta,
            }
            for doc_id, _, meta in batch
        ])
        for attempt in range(4):
            if not self._tenant_ready():
                time.sleep(3)
                continue
            try:
                self.client.context.ingest(
                    type="knowledge",
                    tenant_id=self.tenant_id,
                    documents=docs,
                    document_metadata=meta,
                    upsert=True,
                )
                return True
            except Exception as e:
                if attempt == 3 or "TENANT_NOT_FOUND" not in str(e):
                    raise
                time.sleep(4 * (attempt + 1))
        return False

    def seed_knowledge(self) -> None:
        if not self.enabled or self._seeded or not self.client:
            return
        if not HYDRA_DB_SEED_ON_START and HYDRA_DB_SEED_MARKER.exists():
            self._seeded = True
            print("  [hydra] skip seed (already seeded — set HYDRA_DB_SEED_ON_START=1 to re-seed)")
            return

        self._ensure_tenant()
        index = get_api_index()
        items = index.all_docs_for_hydradb()
        batch_size = 50
        total_batches = (len(items) + batch_size - 1) // batch_size
        failed = 0
        for i in range(0, len(items), batch_size):
            batch_num = i // batch_size + 1
            print(f"  [hydra] seeding batch {batch_num}/{total_batches}...", flush=True)
            batch = items[i : i + batch_size]
            try:
                if not self._ingest_knowledge_batch(batch):
                    failed += 1
                    print(f"  [hydra] knowledge seed batch {batch_num} failed", flush=True)
            except Exception as e:
                failed += 1
                print(f"  [hydra] knowledge seed batch {batch_num} failed: {_short_error(e)}")

        conventions = (
            "AppWorld agent conventions: use access_token not token; "
            "supervisor.show_account_passwords() returns list of account_name/password; "
            "use supervisor email as login username (phone app uses phone_number); "
            "QA tasks must not mutate DB; action tasks use complete_task(answer=None)."
        )
        try:
            self._ingest_knowledge_batch([(
                "appworld_conventions",
                conventions,
                {"type": "conventions"},
            )])
        except Exception as e:
            print(f"  [hydra] conventions seed failed: {_short_error(e)}")
            failed += 1

        if failed:
            print(f"  [hydra] seeded with {failed} failed batch(es) — will retry next run")
            return

        self._seeded = True
        HYDRA_DB_SEED_MARKER.touch()
        print(f"  [hydra] seeded {len(items)} API docs + conventions")

    def recall_for_task(self, instruction: str, task_id: str) -> str:
        if not HYDRA_DB_QUERY_ENABLED or not self.enabled or not self.client:
            return ""
        try:
            from hydra_db.helpers import build_string
            result = self.client.query(
                tenant_id=self.tenant_id,
                sub_tenant_id=task_id,
                query=instruction,
                type="all",
                query_by="hybrid",
                mode="thinking",
                max_results=8,
            )
            return build_string(result)
        except Exception:
            return ""

    def recall_for_step(self, query: str, task_id: str) -> str:
        if not HYDRA_DB_QUERY_ENABLED or not self.enabled or not self.client:
            return ""
        try:
            from hydra_db.helpers import build_string
            result = self.client.query(
                tenant_id=self.tenant_id,
                sub_tenant_id=task_id,
                query=query,
                type="knowledge",
                query_by="hybrid",
                mode="fast",
                max_results=5,
            )
            return build_string(result)
        except Exception:
            return ""

    def recall_errors(self, task_id: str, error_text: str) -> str:
        if not HYDRA_DB_QUERY_ENABLED or not self.enabled or not self.client:
            return ""
        try:
            from hydra_db.helpers import build_string
            result = self.client.query(
                tenant_id=self.tenant_id,
                sub_tenant_id=task_id,
                query=error_text,
                type="memory",
                query_by="hybrid",
                mode="fast",
                max_results=5,
                recency_bias=0.4,
            )
            return build_string(result)
        except Exception:
            return ""

    def store_step(
        self,
        task_id: str,
        step: int,
        code: str,
        output: str,
        *,
        is_error: bool = False,
    ) -> None:
        if not self.enabled or not self.client:
            return
        try:
            self.client.context.ingest(
                type="memory",
                tenant_id=self.tenant_id,
                sub_tenant_id=task_id,
                memories=json.dumps([{
                    "id": f"{task_id}_step_{step}",
                    "text": f"Code:\n{code}\n\nOutput:\n{output[:2000]}",
                    "infer": False,
                    "metadata": {
                        "step": step,
                        "outcome": "error" if is_error else "ok",
                    },
                }]),
            )
        except Exception:
            pass

    def store_task_outcome(
        self,
        instruction: str,
        plan: dict[str, Any],
        *,
        success: bool,
        task_id: str,
    ) -> None:
        if not self.enabled or not self.client:
            return
        apps = ", ".join(plan.get("likely_apps", []))
        task_type = plan.get("task_type", "action")
        outcome = "success" if success else "failure"
        text = (
            f"Task {outcome}: type={task_type}, apps=[{apps}]. "
            f"Instruction: {instruction[:500]}"
        )
        try:
            self.client.context.ingest(
                type="memory",
                tenant_id=self.tenant_id,
                sub_tenant_id=APPWORLD_EXPERIMENT,
                memories=json.dumps([{
                    "id": f"{task_id}_{outcome}",
                    "text": text,
                    "infer": True,
                    "metadata": {
                        "outcome": outcome,
                        "task_type": task_type,
                        "apps": plan.get("likely_apps", []),
                    },
                }]),
            )
        except Exception:
            pass


_hydra: HydraContext | None = None


def get_hydra_context(*, reset: bool = False) -> HydraContext:
    global _hydra
    if reset:
        _hydra = None
    if _hydra is None:
        _hydra = HydraContext()
    return _hydra
