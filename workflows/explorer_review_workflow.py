from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.explorer_repository import ExplorerRepository
from services.rag_client import LocalRagClient


@dataclass(frozen=True)
class ExplorerReviewState:
    explorer_id: str
    explorer_created_at: str | None

    service_log_id: str | None
    service_log_created_at: str | None

    explorer_row: dict[str, Any]
    service_log_row: dict[str, Any] | None

    validation_passed: bool
    validation_errors: list[str]

    can_run_in_metastock: bool
    can_repair: bool

    source: str


class ExplorerReviewWorkflow:
    def __init__(
        self,
        *,
        rag_client: LocalRagClient,
        explorer_repository: ExplorerRepository,
    ):
        self.rag_client = rag_client
        self.explorer_repository = explorer_repository

    def generate_for_review(self, user_query: str) -> ExplorerReviewState:
        result = self.rag_client.generate_explorer(user_query)

        explorer_row = self.explorer_repository.get_explorer(result.explorer)

        service_log_row = None
        if result.service_log:
            service_log_row = self.explorer_repository.get_service_log(
                result.service_log
            )

        return ExplorerReviewState(
            explorer_id=result.explorer,
            explorer_created_at=result.explorer_created_at,
            service_log_id=result.service_log,
            service_log_created_at=result.service_log_created_at,
            explorer_row=explorer_row,
            service_log_row=service_log_row,
            validation_passed=result.validation_passed,
            validation_errors=result.validation_errors,
            can_run_in_metastock=result.validation_passed,
            can_repair=not result.validation_passed,
            source=result.source,
        )

    def repair_for_review(
        self,
        explorer_id: str,
        repair_instruction: str | None = None,
    ) -> ExplorerReviewState:
        result = self.rag_client.repair_explorer(
            explorer_id=explorer_id,
            repair_instruction=repair_instruction,
        )

        explorer_row = self.explorer_repository.get_explorer(result.explorer)

        service_log_row = None
        if result.service_log:
            service_log_row = self.explorer_repository.get_service_log(
                result.service_log
            )

        return ExplorerReviewState(
            explorer_id=result.explorer,
            explorer_created_at=result.explorer_created_at,
            service_log_id=result.service_log,
            service_log_created_at=result.service_log_created_at,
            explorer_row=explorer_row,
            service_log_row=service_log_row,
            validation_passed=result.validation_passed,
            validation_errors=result.validation_errors,
            can_run_in_metastock=result.validation_passed,
            can_repair=not result.validation_passed,
            source=result.source,
        )