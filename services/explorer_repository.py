from __future__ import annotations

from typing import Any

from services.rag_client import LocalRagClient


class ExplorerRepository:
    """
    Read-side repository for Explorer review.

    This deliberately does not create a Supabase client.

    Read path:
        ExplorerRepository
        → LocalRagClient
        → RAG repo RagExplorerReadService
        → Supabase
    """

    def __init__(self, rag_client: LocalRagClient):
        self.rag_client = rag_client

    def get_explorer(self, explorer_id: str) -> dict[str, Any]:
        cleaned = self._clean_required_text(explorer_id, "explorer_id")
        return self.rag_client.get_explorer(cleaned)

    def get_service_log(self, log_id: str) -> dict[str, Any]:
        cleaned = self._clean_required_text(log_id, "log_id")
        return self.rag_client.get_service_log(cleaned)

    def _clean_required_text(self, value: str, field_name: str) -> str:
        cleaned = str(value or "").strip()

        if not cleaned:
            raise ValueError(f"{field_name} is required.")

        return cleaned