from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(frozen=True)
class RagGenerateResult:
    explorer: str
    explorer_created_at: str | None
    service_log: str | None
    service_log_created_at: str | None
    validation_passed: bool
    validation_errors: list[str]
    source: str


class LocalRagClient:
    """
    Desktop-agent-side wrapper around the local RAG repo services.

    Important boundary:
    - metastock-agent does not create a Supabase client;
    - metastock-agent does not need SUPABASE_URL in its own .env;
    - Supabase credentials stay inside the RAG service environment;
    - the LLM/orchestrator only receives cleaned service outputs.
    """

    def __init__(self, rag_repo_path: str):
        self.rag_repo_path = Path(rag_repo_path)

        if not self.rag_repo_path.exists():
            raise FileNotFoundError(f"RAG repo path not found: {self.rag_repo_path}")

        rag_env_path = self.rag_repo_path / ".env"
        if rag_env_path.exists():
            load_dotenv(rag_env_path, override=True)

        rag_repo_path_str = str(self.rag_repo_path)
        if rag_repo_path_str not in sys.path:
            sys.path.insert(0, rag_repo_path_str)

        from src.rag_read_service import RagExplorerReadService
        from src.rag_service import RagExplorerRepairService, RagExplorerService

        self._generate_service = RagExplorerService()
        self._repair_service = RagExplorerRepairService()
        self._read_service = RagExplorerReadService()

    def generate_explorer(self, user_message: str) -> RagGenerateResult:
        response = self._generate_service.generate_explorer(user_message)

        return RagGenerateResult(
            explorer=response.explorer,
            explorer_created_at=response.explorer_created_at,
            service_log=response.service_log,
            service_log_created_at=response.service_log_created_at,
            validation_passed=response.validation.passed,
            validation_errors=response.validation.errors,
            source=response.source,
        )

    def repair_explorer(
        self,
        explorer_id: str,
        repair_instruction: str | None = None,
    ) -> RagGenerateResult:
        response = self._repair_service.repair_explorer(
            explorer=explorer_id,
            repair_instruction=repair_instruction,
        )

        return RagGenerateResult(
            explorer=response.explorer,
            explorer_created_at=response.explorer_created_at,
            service_log=response.service_log,
            service_log_created_at=response.service_log_created_at,
            validation_passed=response.validation.passed,
            validation_errors=response.validation.errors,
            source=response.source,
        )

    def get_explorer(self, explorer_id: str) -> dict[str, Any]:
        return self._read_service.get_explorer(explorer_id)

    def get_service_log(self, log_id: str) -> dict[str, Any]:
        return self._read_service.get_service_log(log_id)