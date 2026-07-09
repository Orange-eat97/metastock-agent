from __future__ import annotations

import traceback
from typing import Any

from services.explorer_repository import ExplorerRepository
from workflows.explorer_review_workflow import (
    ExplorerReviewState,
    ExplorerReviewWorkflow,
)

from tools.tool_contracts import (
    ExplorerColumnDTO,
    ExplorerDTO,
    GenerateExplorerInput,
    GenerateExplorerOutput,
    GetExplorerInput,
    GetExplorerOutput,
    GetRagLogInput,
    GetRagLogOutput,
    RepairExplorerInput,
    RepairExplorerOutput,
    ReviseExplorerInput,
    RunExplorerInput,
    ToolDisplay,
    ToolError,
    ToolResult,
    ToolStatus,
    ValidationDTO,
)


class ExplorerToolService:
    """
    LLM-facing tool facade.

    The future orchestrator should call this layer, not RagClient or Supabase
    directly.
    """

    def __init__(
        self,
        *,
        review_workflow: ExplorerReviewWorkflow,
        explorer_repository: ExplorerRepository,
    ):
        self.review_workflow = review_workflow
        self.explorer_repository = explorer_repository

    def generate_explorer(self, payload: GenerateExplorerInput) -> ToolResult:
        try:
            state = self.review_workflow.generate_for_review(payload.user_query)
            explorer = self._state_to_explorer_dto(state)

            output = GenerateExplorerOutput(
                explorer=explorer,
                retrieved_refs=[],
            )

            return ToolResult(
                tool_name="generate_explorer",
                ok=True,
                status=ToolStatus.SUCCESS,
                message="Explorer generated and prepared for review.",
                data=output.model_dump(mode="json"),
                display=self._explorer_display(
                    title="Generated Explorer",
                    explorer=explorer,
                ),
            )

        except Exception as exc:
            return self._exception_result(
                tool_name="generate_explorer",
                exc=exc,
            )

    def repair_explorer(self, payload: RepairExplorerInput) -> ToolResult:
        try:
            state = self.review_workflow.repair_for_review(
                explorer_id=payload.explorer_id,
                repair_instruction=payload.repair_instruction,
            )
            explorer = self._state_to_explorer_dto(state)

            output = RepairExplorerOutput(
                explorer=explorer,
                retrieved_refs=[],
                repaired_from_explorer_id=payload.explorer_id,
            )

            return ToolResult(
                tool_name="repair_explorer",
                ok=True,
                status=ToolStatus.SUCCESS,
                message="Explorer repair completed and saved as a new row.",
                data=output.model_dump(mode="json"),
                display=self._explorer_display(
                    title="Repaired Explorer",
                    explorer=explorer,
                ),
            )

        except Exception as exc:
            return self._exception_result(
                tool_name="repair_explorer",
                exc=exc,
            )

    def revise_explorer(self, payload: ReviseExplorerInput) -> ToolResult:
        """
        Future MITL correction tool.

        Keep this separate from repair_explorer:
        - repair_explorer = syntax/contract repair
        - revise_explorer = human-requested strategy change
        """
        return ToolResult(
            tool_name="revise_explorer",
            ok=False,
            status=ToolStatus.NOT_IMPLEMENTED,
            message="Explorer revision is not implemented yet.",
            error=ToolError(
                code="TOOL_NOT_IMPLEMENTED",
                message=(
                    "revise_explorer is reserved for future MITL correction. "
                    "Use repair_explorer only for syntax/contract repair."
                ),
            ),
            display=ToolDisplay(
                title="Revision Not Implemented",
                markdown=(
                    "Explorer revision is not implemented yet. "
                    "This will later support human instructions such as "
                    "`change RSI threshold to 35` or `use 50-day volume average`."
                ),
                severity="warning",
            ),
        )

    def get_explorer(self, payload: GetExplorerInput) -> ToolResult:
        try:
            row = self.explorer_repository.get_explorer(payload.explorer_id)
            explorer = self._row_to_explorer_dto(row)

            output = GetExplorerOutput(
                explorer=explorer,
                raw_row=row,
            )

            return ToolResult(
                tool_name="get_explorer",
                ok=True,
                status=ToolStatus.SUCCESS,
                message="Explorer fetched.",
                data=output.model_dump(mode="json"),
                display=self._explorer_display(
                    title="Explorer",
                    explorer=explorer,
                ),
            )

        except Exception as exc:
            return self._exception_result(
                tool_name="get_explorer",
                exc=exc,
            )

    def get_rag_log(self, payload: GetRagLogInput) -> ToolResult:
        try:
            row = self.explorer_repository.get_service_log(payload.log_id)

            output = GetRagLogOutput(
                log_id=str(row.get("log_id")),
                created_at=self._optional_str(row.get("created_at")),
                event_type=self._optional_str(row.get("event_type")),
                stdout_text=str(row.get("stdout_text") or ""),
                stderr_text=str(row.get("stderr_text") or ""),
                metadata=row.get("metadata") or {},
            )

            markdown_parts = [
                f"**Log ID:** `{output.log_id}`",
                "",
                f"**Event:** `{output.event_type}`",
                "",
                "```text",
                output.stdout_text[:3000],
                "```",
            ]

            if output.stderr_text:
                markdown_parts.extend(
                    [
                        "",
                        "**STDERR**",
                        "",
                        "```text",
                        output.stderr_text[:1500],
                        "```",
                    ]
                )

            return ToolResult(
                tool_name="get_rag_log",
                ok=True,
                status=ToolStatus.SUCCESS,
                message="RAG service log fetched.",
                data=output.model_dump(mode="json"),
                display=ToolDisplay(
                    title="RAG Service Log",
                    markdown="\n".join(markdown_parts),
                    severity="info",
                ),
            )

        except Exception as exc:
            return self._exception_result(
                tool_name="get_rag_log",
                exc=exc,
            )

    def run_explorer_in_metastock(self, payload: RunExplorerInput) -> ToolResult:
        """
        Future execution tool. Keep blocked until AutomatorClient is standardized.
        """
        return ToolResult(
            tool_name="run_explorer_in_metastock",
            ok=False,
            status=ToolStatus.BLOCKED,
            message="MetaStock execution is not connected yet.",
            error=ToolError(
                code="TOOL_BLOCKED",
                message=(
                    "AutomatorClient is not implemented in this agent app yet. "
                    "Explorer execution should stay disabled for now."
                ),
            ),
            display=ToolDisplay(
                title="MetaStock Execution Not Connected",
                markdown=(
                    "The Explorer was not run. The execution tool is reserved "
                    "for the next milestone after AutomatorClient is standardized."
                ),
                severity="warning",
            ),
        )

    def _state_to_explorer_dto(self, state: ExplorerReviewState) -> ExplorerDTO:
        row = state.explorer_row

        return self._row_to_explorer_dto(
            row=row,
            source=state.source,
            service_log_id=state.service_log_id,
            service_log_created_at=state.service_log_created_at,
            can_run_in_metastock=state.can_run_in_metastock,
            can_repair=state.can_repair,
            validation_passed=state.validation_passed,
            validation_errors=state.validation_errors,
        )

    def _row_to_explorer_dto(
        self,
        row: dict[str, Any],
        *,
        source: str | None = None,
        service_log_id: str | None = None,
        service_log_created_at: str | None = None,
        can_run_in_metastock: bool | None = None,
        can_repair: bool | None = None,
        validation_passed: bool | None = None,
        validation_errors: list[str] | None = None,
    ) -> ExplorerDTO:
        row_validation_passed = bool(row.get("validation_passed"))
        row_validation_errors = row.get("validation_errors") or []

        if not isinstance(row_validation_errors, list):
            row_validation_errors = [str(row_validation_errors)]

        final_validation_passed = (
            row_validation_passed
            if validation_passed is None
            else validation_passed
        )

        final_validation_errors = (
            [str(error) for error in row_validation_errors]
            if validation_errors is None
            else [str(error) for error in validation_errors]
        )

        columns = self._parse_columns(row.get("col_definitions"))

        return ExplorerDTO(
            explorer_id=str(row.get("id")),
            explorer_created_at=self._optional_str(row.get("created_at")),
            name=str(row.get("explorer_name") or ""),
            description=str(row.get("explorer_description") or ""),
            filter_code=str(row.get("explorer_code_body") or ""),
            columns=columns,
            validation=ValidationDTO(
                passed=final_validation_passed,
                errors=final_validation_errors,
            ),
            can_run_in_metastock=(
                final_validation_passed
                if can_run_in_metastock is None
                else can_run_in_metastock
            ),
            can_repair=(
                not final_validation_passed
                if can_repair is None
                else can_repair
            ),
            source=source,
            service_log_id=service_log_id,
            service_log_created_at=service_log_created_at,
        )

    def _parse_columns(self, value: Any) -> list[ExplorerColumnDTO]:
        if not isinstance(value, list):
            return []

        columns: list[ExplorerColumnDTO] = []

        for item in value:
            if not isinstance(item, dict):
                continue

            letter = str(item.get("col_letter") or "").strip()
            code = str(item.get("col_code") or "").strip()

            if not letter and not code:
                continue

            columns.append(
                ExplorerColumnDTO(
                    col_letter=letter,
                    col_code=code,
                )
            )

        return columns

    def _explorer_display(
        self,
        *,
        title: str,
        explorer: ExplorerDTO,
    ) -> ToolDisplay:
        validation_text = "PASSED" if explorer.validation.passed else "FAILED"
        severity = "success" if explorer.validation.passed else "warning"

        columns_text = "\n".join(
            f"- Column {col.col_letter}: `{col.col_code}`"
            for col in explorer.columns
        )

        if not columns_text:
            columns_text = "- No columns."

        errors_text = "\n".join(
            f"- {error}"
            for error in explorer.validation.errors
        )

        if not errors_text:
            errors_text = "- None."

        markdown_parts = [
            f"**Explorer ID:** `{explorer.explorer_id}`  ",
            f"**Created At:** `{explorer.explorer_created_at}`  ",
            f"**Validation:** **{validation_text}**",
            "",
            f"## {explorer.name}",
            "",
            explorer.description,
            "",
            "## Filter",
            "",
            "```text",
            explorer.filter_code,
            "```",
            "",
            "## Columns",
            "",
            columns_text,
            "",
            "## Validation Errors",
            "",
            errors_text,
        ]

        markdown = "\n".join(markdown_parts)

        return ToolDisplay(
            title=title,
            markdown=markdown,
            severity=severity,
        )

    def _exception_result(self, *, tool_name: str, exc: Exception) -> ToolResult:
        return ToolResult(
            tool_name=tool_name,
            ok=False,
            status=ToolStatus.FAILED,
            message=str(exc),
            error=ToolError(
                code=type(exc).__name__,
                message=str(exc),
                details={
                    "traceback": traceback.format_exc(),
                },
            ),
            display=ToolDisplay(
                title=f"{tool_name} failed",
                markdown="\n".join(
                    [
                        "```text",
                        traceback.format_exc(),
                        "```",
                    ]
                ),
                severity="error",
            ),
        )

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)