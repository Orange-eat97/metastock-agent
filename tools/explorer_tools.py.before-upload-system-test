from __future__ import annotations

import traceback
from typing import Any

from services.automator_client import (
    AutomatorClient,
    AutomatorExplorerColumn,
    AutomatorRunRequest,
    UnavailableAutomatorClient,
)
from services.explorer_repository import ExplorerRepository
from agent_workflows.explorer_review_workflow import (
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
    ReviseExplorerOutput,
    RunExplorerInput,
    RunExplorerOutput,
    ToolDisplay,
    ToolError,
    ToolResult,
    ToolStatus,
    ValidationDTO,
)


class ExplorerToolService:
    """
    LLM-facing tool facade.

    The orchestrator calls this layer rather than RAG, Supabase, or UI
    automation internals directly.
    """

    def __init__(
        self,
        *,
        review_workflow: ExplorerReviewWorkflow,
        explorer_repository: ExplorerRepository,
        automator_client: AutomatorClient | None = None,
    ):
        self.review_workflow = review_workflow
        self.explorer_repository = explorer_repository
        self.automator_client = automator_client or UnavailableAutomatorClient()

    def generate_explorer(self, payload: GenerateExplorerInput) -> ToolResult:
        try:
            state = self.review_workflow.generate_for_review(payload.user_query)
            explorer = self._state_to_explorer_dto(state)

            output = GenerateExplorerOutput(
                explorer=explorer,
                assumptions=list(
                    state.assumptions
                ),
                retrieved_refs=[
                    dict(ref)
                    for ref in state.retrieved_refs
                ],
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
                assumptions=list(
                    state.assumptions
                ),
                retrieved_refs=[
                    dict(ref)
                    for ref in state.retrieved_refs
                ],
                repaired_from_explorer_id=(
                    payload.explorer_id
                ),
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
        try:
            state = self.review_workflow.revise_for_review(
                explorer_id=payload.explorer_id,
                revision_instruction=(
                    payload.revision_instruction
                ),
            )
            explorer = self._state_to_explorer_dto(state)
            output = ReviseExplorerOutput(
                explorer=explorer,
                assumptions=list(state.assumptions),
                retrieved_refs=[
                    dict(ref)
                    for ref in state.retrieved_refs
                ],
                revised_from_explorer_id=(
                    payload.explorer_id
                ),
                revision_instruction=(
                    payload.revision_instruction
                ),
            )

            return ToolResult(
                tool_name="revise_explorer",
                ok=True,
                status=ToolStatus.SUCCESS,
                message=(
                    "Explorer revision completed and "
                    "saved as a new row."
                ),
                data=output.model_dump(mode="json"),
                display=self._explorer_display(
                    title="Revised Explorer",
                    explorer=explorer,
                ),
            )

        except Exception as exc:
            return self._exception_result(
                tool_name="revise_explorer",
                exc=exc,
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

    def _build_automator_request(
        self,
        *,
        explorer: ExplorerDTO,
        payload: RunExplorerInput,
    ) -> AutomatorRunRequest:
        instrument_names, select_all = (
            self._parse_instruments(
                payload.instruments
            )
        )

        return AutomatorRunRequest(
            explorer_id=explorer.explorer_id,
            name=explorer.name,
            description=explorer.description,
            filter_code=explorer.filter_code,
            columns=[
                AutomatorExplorerColumn(
                    col_letter=column.col_letter,
                    col_code=column.col_code,
                )
                for column in explorer.columns
            ],
            instruments=instrument_names,
            select_all_instruments=select_all,
            max_execution_wait_sec=(
                payload.max_execution_wait_sec
            ),
        )

    def _metastock_boundary_tool(
        self,
        payload: RunExplorerInput,
        *,
        tool_name: str,
        client_method_name: str,
        success_title: str,
        failed_title: str,
        require_validation: bool,
    ) -> ToolResult:
        try:
            row = (
                self.explorer_repository
                .get_explorer(
                    payload.explorer_id
                )
            )
            explorer = (
                self._row_to_explorer_dto(row)
            )

            if (
                require_validation
                and not explorer.validation.passed
            ):
                return self._blocked_result(
                    tool_name=tool_name,
                    code=(
                        "EXPLORER_VALIDATION_FAILED"
                    ),
                    message=(
                        "Explorer validation failed; "
                        "MetaStock action is blocked."
                    ),
                    title="Explorer Cannot Be Used",
                    markdown=(
                        "The Explorer failed validation. "
                        "Repair it before creating or "
                        "running it in MetaStock."
                    ),
                    details={
                        "explorer_id": (
                            explorer.explorer_id
                        ),
                        "validation_errors": (
                            explorer.validation.errors
                        ),
                    },
                )

            if not explorer.name.strip():
                return self._blocked_result(
                    tool_name=tool_name,
                    code="EXPLORER_NAME_MISSING",
                    message=(
                        "Explorer is missing a name."
                    ),
                    title="Explorer Cannot Be Used",
                    markdown=(
                        "The Explorer cannot be "
                        "selected without a name."
                    ),
                    details={
                        "explorer_id": (
                            explorer.explorer_id
                        )
                    },
                )

            if (
                require_validation
                and not explorer.filter_code.strip()
            ):
                return self._blocked_result(
                    tool_name=tool_name,
                    code="EXPLORER_FILTER_MISSING",
                    message=(
                        "Explorer is missing its "
                        "filter formula."
                    ),
                    title="Explorer Cannot Be Used",
                    markdown=(
                        "The Explorer cannot be "
                        "created or run because its "
                        "filter formula is empty."
                    ),
                    details={
                        "explorer_id": (
                            explorer.explorer_id
                        )
                    },
                )

            if not self.automator_client.configured:
                return self._blocked_result(
                    tool_name=tool_name,
                    code="AUTOMATOR_NOT_CONFIGURED",
                    message=(
                        "MetaStock automation is "
                        "not configured."
                    ),
                    title=(
                        "MetaStock Automation "
                        "Not Connected"
                    ),
                    markdown=(
                        "The requested MetaStock "
                        "action was not performed "
                        "because the AutomatorClient "
                        "is not connected."
                    ),
                    details={
                        "explorer_id": (
                            explorer.explorer_id
                        )
                    },
                )

            request = (
                self._build_automator_request(
                    explorer=explorer,
                    payload=payload,
                )
            )
            client_method = getattr(
                self.automator_client,
                client_method_name,
            )
            automator_result = (
                client_method(request)
            )

            output = RunExplorerOutput(
                explorer_id=explorer.explorer_id,
                succeeded=(
                    automator_result.succeeded
                ),
                message=automator_result.message,
                started_at=(
                    automator_result.started_at
                ),
                finished_at=(
                    automator_result.finished_at
                ),
                result_available=(
                    automator_result
                    .result_available
                ),
                diagnostics=(
                    automator_result.diagnostics
                ),
            )

            if not automator_result.succeeded:
                return ToolResult(
                    tool_name=tool_name,
                    ok=False,
                    status=ToolStatus.FAILED,
                    message=(
                        automator_result.message
                    ),
                    data=output.model_dump(
                        mode="json"
                    ),
                    error=ToolError(
                        code=(
                            "AUTOMATOR_ACTION_FAILED"
                        ),
                        message=(
                            automator_result.message
                        ),
                        details=(
                            automator_result
                            .diagnostics
                        ),
                    ),
                    display=ToolDisplay(
                        title=failed_title,
                        markdown=(
                            automator_result.message
                        ),
                        severity="error",
                    ),
                )

            return ToolResult(
                tool_name=tool_name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message=automator_result.message,
                data=output.model_dump(
                    mode="json"
                ),
                display=ToolDisplay(
                    title=success_title,
                    markdown=(
                        automator_result.message
                    ),
                    severity="success",
                ),
            )

        except Exception as exc:
            return self._exception_result(
                tool_name=tool_name,
                exc=exc,
            )

    def create_explorer_in_metastock(
        self,
        payload: RunExplorerInput,
    ) -> ToolResult:
        return self._metastock_boundary_tool(
            payload,
            tool_name=(
                "create_explorer_in_metastock"
            ),
            client_method_name=(
                "create_explorer"
            ),
            success_title=(
                "Explorer Created in MetaStock"
            ),
            failed_title=(
                "MetaStock Explorer Creation "
                "Failed"
            ),
            require_validation=True,
        )

    def select_explorer_in_metastock(
        self,
        payload: RunExplorerInput,
    ) -> ToolResult:
        return self._metastock_boundary_tool(
            payload,
            tool_name=(
                "select_explorer_in_metastock"
            ),
            client_method_name=(
                "select_explorer"
            ),
            success_title=(
                "Explorer Selected in MetaStock"
            ),
            failed_title=(
                "MetaStock Explorer Selection "
                "Failed"
            ),
            require_validation=False,
        )

    def run_selected_explorer_in_metastock(
        self,
        payload: RunExplorerInput,
    ) -> ToolResult:
        return self._metastock_boundary_tool(
            payload,
            tool_name=(
                "run_selected_explorer_in_metastock"
            ),
            client_method_name=(
                "run_selected_explorer"
            ),
            success_title=(
                "Selected Explorer Run Completed"
            ),
            failed_title=(
                "MetaStock Selected-Explorer "
                "Run Failed"
            ),
            require_validation=False,
        )

    def run_explorer_in_metastock(
        self,
        payload: RunExplorerInput,
    ) -> ToolResult:
        """
        Compatibility entry point.

        The public registry does not expose this composite operation.
        """
        return ToolResult(
            tool_name=(
                "run_explorer_in_metastock"
            ),
            ok=False,
            status=ToolStatus.BLOCKED,
            message=(
                "Composite "
                "run_explorer_in_metastock is "
                "disabled. Use the separate "
                "create, select, and run-selected "
                "tools."
            ),
            error=ToolError(
                code="COMPOSITE_TOOL_DISABLED",
                message=(
                    "Create, select, and run must "
                    "remain separate service "
                    "boundaries."
                ),
            ),
            display=ToolDisplay(
                title="Composite Tool Disabled",
                markdown=(
                    "Use the separate MetaStock "
                    "tools: create, select, and "
                    "run selected."
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
            validation_warnings=(
                state.validation_warnings
            ),
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
        validation_warnings: list[str] | None = None,
    ) -> ExplorerDTO:
        row_validation_passed = bool(
            row.get("validation_passed")
        )
        row_validation_errors = (
            row.get("validation_errors")
            or []
        )
        row_validation_warnings = (
            row.get("validation_warnings")
            or []
        )

        if not isinstance(
            row_validation_errors,
            list,
        ):
            row_validation_errors = [
                str(row_validation_errors)
            ]

        if not isinstance(
            row_validation_warnings,
            list,
        ):
            row_validation_warnings = [
                str(row_validation_warnings)
            ]

        final_validation_passed = (
            row_validation_passed
            if validation_passed is None
            else validation_passed
        )

        final_validation_errors = (
            [
                str(error)
                for error in row_validation_errors
            ]
            if validation_errors is None
            else [
                str(error)
                for error in validation_errors
            ]
        )

        final_validation_warnings = (
            [
                str(warning)
                for warning
                in row_validation_warnings
            ]
            if validation_warnings is None
            else [
                str(warning)
                for warning
                in validation_warnings
            ]
        )

        columns = self._parse_columns(
            row.get("col_definitions")
        )

        final_service_log_id = (
            self._optional_str(row.get("service_log_id"))
            if service_log_id is None
            else service_log_id
        )

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
                warnings=(
                    final_validation_warnings
                ),
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
            service_log_id=final_service_log_id,
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

    def _parse_instruments(
        self,
        value: str,
    ) -> tuple[list[str] | None, bool]:
        raw = str(value or "").strip()

        if not raw or raw.lower() in {"all", "all-instruments", "*"}:
            return None, True

        instruments = [
            item.strip()
            for item in raw.split(",")
            if item.strip()
        ]

        if not instruments:
            return None, True

        return instruments, False

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

        warnings_text = "\n".join(
            f"- {warning}"
            for warning
            in explorer.validation.warnings
        )

        if not warnings_text:
            warnings_text = "- None."

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
            "",
            "## Validation Warnings",
            "",
            warnings_text,
        ]

        return ToolDisplay(
            title=title,
            markdown="\n".join(markdown_parts),
            severity=severity,
        )

    def _blocked_result(
        self,
        *,
        tool_name: str,
        code: str,
        message: str,
        title: str,
        markdown: str,
        details: dict[str, Any] | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=tool_name,
            ok=False,
            status=ToolStatus.BLOCKED,
            message=message,
            error=ToolError(
                code=code,
                message=message,
                details=details or {},
            ),
            display=ToolDisplay(
                title=title,
                markdown=markdown,
                severity="warning",
            ),
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
