from __future__ import annotations

import sys
from dataclasses import dataclass, field
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

    assumptions: list[str] = field(
        default_factory=list
    )
    retrieved_refs: list[
        dict[str, Any]
    ] = field(default_factory=list)
    validation_warnings: list[str] = field(
        default_factory=list
    )


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
        from src.rag_explorer_update_service import (
            RagExplorerUpdateService,
        )
        from src.rag_result_store_service import (
            RagExplorerResultStoreService,
        )
        from src.rag_revision_service import (
            RagExplorerRevisionService,
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
        self._revision_service = (
            RagExplorerRevisionService()
        )
        self._read_service = (
            RagExplorerReadService()
        )
        self._update_service = (
            RagExplorerUpdateService()
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
            validation_errors=[
                str(error)
                for error in response.validation.errors
            ],
            source=response.source,
            assumptions=[
                str(assumption)
                for assumption
                in response.assumptions
            ],
            retrieved_refs=[
                (
                    ref.model_dump(mode="json")
                    if hasattr(ref, "model_dump")
                    else dict(ref)
                )
                for ref in response.retrieved_refs
            ],
            validation_warnings=[
                str(warning)
                for warning in getattr(
                    response.validation,
                    "warnings",
                    [],
                )
            ],
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
            validation_errors=[
                str(error)
                for error in response.validation.errors
            ],
            source=response.source,
            assumptions=[
                str(assumption)
                for assumption
                in response.assumptions
            ],
            retrieved_refs=[
                (
                    ref.model_dump(mode="json")
                    if hasattr(ref, "model_dump")
                    else dict(ref)
                )
                for ref in response.retrieved_refs
            ],
            validation_warnings=[
                str(warning)
                for warning in getattr(
                    response.validation,
                    "warnings",
                    [],
                )
            ],
        )

    def revise_explorer(
        self,
        explorer_id: str,
        revision_instruction: str,
    ) -> RagGenerateResult:
        response = (
            self._revision_service
            .revise_explorer(
                explorer=explorer_id,
                revision_instruction=(
                    revision_instruction
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
            validation_errors=[
                str(error)
                for error in response.validation.errors
            ],
            source=response.source,
            assumptions=[
                str(assumption)
                for assumption in response.assumptions
            ],
            retrieved_refs=[
                (
                    ref.model_dump(mode="json")
                    if hasattr(ref, "model_dump")
                    else dict(ref)
                )
                for ref in response.retrieved_refs
            ],
            validation_warnings=[
                str(warning)
                for warning in getattr(
                    response.validation,
                    "warnings",
                    [],
                )
            ],
        )

    def get_explorer(
        self,
        explorer_id: str,
    ) -> dict[str, Any]:
        return (
            self._read_service
            .get_explorer(explorer_id)
        )

    def get_explorers_by_ids(
        self,
        explorer_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Load current Explorer rows in one controlled read."""
        return (
            self._read_service
            .get_explorers_by_ids(explorer_ids)
        )

    def update_explorer_full_json(
        self,
        *,
        explorer_id: str,
        expected_version: int,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist allowlisted manual edits without invoking AI."""
        return (
            self._update_service
            .update_explorer_full_json(
                explorer_id=explorer_id,
                expected_version=expected_version,
                patch=patch,
            )
        )

    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        """
        Resolve an exact Explorer name through the RAG read service.

        Matching, normalization, and ambiguity handling remain owned by
        RagExplorerReadService. This client only exposes the controlled
        service boundary to the desktop agent.
        """
        return (
            self._read_service
            .resolve_explorer_id_by_name(
                explorer_name
            )
        )

    def get_service_log(
        self,
        log_id: str,
    ) -> dict[str, Any]:
        return (
            self._read_service
            .get_service_log(log_id)
        )

    def save_explorer_result(
        self,
        *,
        explorer_id: str,
        result_payload: dict[str, Any],
        capture_started_at: str | None,
        capture_finished_at: str | None,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Persist one normalized MetaStock result artifact.

        The agent passes the complete versioned result payload. This
        adapter translates it into the narrower RAG result-service call.
        """
        if not isinstance(
            result_payload,
            dict,
        ):
            raise ValueError(
                "result_payload must be a dictionary."
            )

        rows = result_payload.get("rows") or []

        if not isinstance(rows, list):
            raise ValueError(
                "result_payload.rows must be a list."
            )

        if not isinstance(diagnostics, dict):
            raise ValueError(
                "diagnostics must be a dictionary."
            )

        return (
            self._result_store_service
            .save_explorer_results(
                explorer_id=explorer_id,
                schema_version=str(
                    result_payload.get(
                        "schema_version"
                    )
                    or ""
                ),
                outcome=str(
                    result_payload.get(
                        "outcome"
                    )
                    or ""
                ),
                expected_count=int(
                    result_payload.get(
                        "expected_count",
                        0,
                    )
                ),
                matched_count=int(
                    result_payload.get(
                        "matched_count",
                        0,
                    )
                ),
                has_matches=bool(
                    result_payload.get(
                        "has_matches",
                        False,
                    )
                ),
                clipboard_verification=(
                    result_payload.get(
                        "clipboard_verification"
                    )
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

    def get_explorer_result(
        self,
        result_id: str,
    ) -> dict[str, Any]:
        """
        Load one complete stored result by result ID.
        """
        return (
            self._result_store_service
            .get_result(result_id)
        )

    def get_latest_explorer_result(
        self,
        explorer_id: str,
    ) -> dict[str, Any] | None:
        """
        Load the newest stored result for an Explorer.

        None means the Explorer has no stored results.
        """
        return (
            self._result_store_service
            .get_latest_result(explorer_id)
        )

    def list_explorer_results(
        self,
        explorer_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        List newest-first result summaries for an Explorer.
        """
        return (
            self._result_store_service
            .list_results(
                explorer_id,
                limit=limit,
            )
        )