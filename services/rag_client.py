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
    Desktop-agent-side wrapper around local RAG repository services.

    Supabase credentials remain in the RAG repository environment.
    The agent initiates persistence through this controlled client;
    it does not create or expose a raw Supabase client.
    """

    def __init__(
        self,
        rag_repo_path: str,
    ) -> None:
        self.rag_repo_path = Path(
            rag_repo_path
        )

        if not self.rag_repo_path.exists():
            raise FileNotFoundError(
                "RAG repo path not found: "
                f"{self.rag_repo_path}"
            )

        rag_env_path = (
            self.rag_repo_path / ".env"
        )

        if rag_env_path.exists():
            load_dotenv(
                rag_env_path,
                override=True,
            )

        rag_repo_path_str = str(
            self.rag_repo_path
        )

        if rag_repo_path_str not in sys.path:
            sys.path.insert(
                0,
                rag_repo_path_str,
            )

        from src.rag_read_service import (
            RagExplorerReadService,
        )
        from src.rag_result_store_service import (
            RagExplorerResultStoreService,
        )
        from src.rag_service import (
            RagExplorerRepairService,
            RagExplorerService,
        )

        self._generate_service = (
            RagExplorerService()
        )
        self._repair_service = (
            RagExplorerRepairService()
        )
        self._read_service = (
            RagExplorerReadService()
        )
        self._result_store_service = (
            RagExplorerResultStoreService()
        )

    def generate_explorer(
        self,
        user_message: str,
    ) -> RagGenerateResult:
        response = (
            self._generate_service
            .generate_explorer(user_message)
        )

        return RagGenerateResult(
            explorer=response.explorer,
            explorer_created_at=(
                response.explorer_created_at
            ),
            service_log=response.service_log,
            service_log_created_at=(
                response.service_log_created_at
            ),
            validation_passed=(
                response.validation.passed
            ),
            validation_errors=(
                response.validation.errors
            ),
            source=response.source,
        )

    def repair_explorer(
        self,
        explorer_id: str,
        repair_instruction: str | None = None,
    ) -> RagGenerateResult:
        response = (
            self._repair_service
            .repair_explorer(
                explorer=explorer_id,
                repair_instruction=(
                    repair_instruction
                ),
            )
        )

        return RagGenerateResult(
            explorer=response.explorer,
            explorer_created_at=(
                response.explorer_created_at
            ),
            service_log=response.service_log,
            service_log_created_at=(
                response.service_log_created_at
            ),
            validation_passed=(
                response.validation.passed
            ),
            validation_errors=(
                response.validation.errors
            ),
            source=response.source,
        )

    def get_explorer(
        self,
        explorer_id: str,
    ) -> dict[str, Any]:
        return (
            self._read_service
            .get_explorer(explorer_id)
        )

    def get_service_log(
        self,
        log_id: str,
    ) -> dict[str, Any]:
        return (
            self._read_service
            .get_service_log(log_id)
        )

    def save_explorer_results(
        self,
        *,
        explorer_id: str,
        schema_version: str,
        outcome: str,
        expected_count: int,
        matched_count: int,
        has_matches: bool,
        clipboard_verification: (
            dict[str, Any] | None
        ),
        rows: list[dict[str, Any]],
        capture_started_at: str | None,
        capture_finished_at: str | None,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        return (
            self._result_store_service
            .save_explorer_results(
                explorer_id=explorer_id,
                schema_version=schema_version,
                outcome=outcome,
                expected_count=expected_count,
                matched_count=matched_count,
                has_matches=has_matches,
                clipboard_verification=(
                    clipboard_verification
                ),
                rows=rows,
                capture_started_at=(
                    capture_started_at
                ),
                capture_finished_at=(
                    capture_finished_at
                ),
                diagnostics=diagnostics,
            )
        )
