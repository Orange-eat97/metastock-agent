from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ToolStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_IMPLEMENTED = "not_implemented"


class ToolError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ToolDisplay(BaseModel):
    title: str
    markdown: str
    severity: Literal[
        "info",
        "success",
        "warning",
        "error",
    ] = "info"


class ToolResult(BaseModel):
    tool_name: str
    ok: bool
    status: ToolStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    display: ToolDisplay | None = None
    error: ToolError | None = None


class ValidationDTO(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExplorerColumnDTO(BaseModel):
    col_letter: str
    col_code: str


class ExplorerDTO(BaseModel):
    explorer_id: str
    explorer_created_at: str | None = None

    name: str
    description: str
    filter_code: str
    columns: list[ExplorerColumnDTO] = Field(default_factory=list)

    validation: ValidationDTO

    can_run_in_metastock: bool
    can_repair: bool

    source: str | None = None
    service_log_id: str | None = None
    service_log_created_at: str | None = None


class GenerateExplorerInput(BaseModel):
    user_query: str = Field(
        description="Natural-language request for a MetaStock Explorer."
    )


class GenerateExplorerOutput(BaseModel):
    explorer: ExplorerDTO
    retrieved_refs: list[dict[str, Any]] = Field(default_factory=list)


class RepairExplorerInput(BaseModel):
    explorer_id: str = Field(
        description="Primary key of the explorer_outputs row to repair."
    )
    repair_instruction: str | None = Field(
        default=None,
        description=(
            "Optional repair instruction. Use mainly for syntax/contract repair."
        ),
    )


class RepairExplorerOutput(BaseModel):
    explorer: ExplorerDTO
    retrieved_refs: list[dict[str, Any]] = Field(default_factory=list)
    repaired_from_explorer_id: str


class ReviseExplorerInput(BaseModel):
    explorer_id: str = Field(
        description="Primary key of the explorer_outputs row to revise."
    )
    revision_instruction: str = Field(
        description="Human instruction for changing the Explorer logic."
    )


class GetExplorerInput(BaseModel):
    explorer_id: str = Field(
        description="Primary key of the explorer_outputs row to inspect."
    )


class GetExplorerOutput(BaseModel):
    explorer: ExplorerDTO
    raw_row: dict[str, Any]


class GetRagLogInput(BaseModel):
    log_id: str = Field(
        description="Primary key of the rag_service_logs row to inspect."
    )


class GetRagLogOutput(BaseModel):
    log_id: str
    created_at: str | None = None
    event_type: str | None = None
    stdout_text: str
    stderr_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunExplorerInput(BaseModel):
    explorer_id: str = Field(
        description="Primary key of the explorer_outputs row to run in MetaStock."
    )
    instruments: str = Field(
        default="all",
        description=(
            "Instrument selection. Use 'all' for every instrument or provide "
            "comma-separated instrument names."
        ),
    )
    max_execution_wait_sec: int = Field(
        default=300,
        gt=0,
        description="Maximum seconds to wait for MetaStock execution.",
    )


class RunExplorerOutput(BaseModel):
    explorer_id: str
    succeeded: bool
    message: str
    started_at: str | None = None
    finished_at: str | None = None
    result_available: bool = False
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def derive_result_available(cls, value: Any) -> Any:
        """
        Keep compatibility with the Milestone 6 tool adapter while promoting
        result availability into a first-class field.
        """
        if not isinstance(value, dict):
            return value

        if "result_available" in value:
            return value

        diagnostics = value.get("diagnostics")
        if isinstance(diagnostics, dict):
            value["result_available"] = bool(
                diagnostics.get("result_available", False)
            )

        return value


class MetaStockClipboardVerificationDTO(BaseModel):
    passed: bool
    expected_count: int
    scraped_count: int
    clipboard_count: int
    missing_from_scrape: list[str] = Field(default_factory=list)
    unexpected_in_scrape: list[str] = Field(default_factory=list)
    clipboard_headers: list[str] = Field(default_factory=list)


class MetaStockResultRowDTO(BaseModel):
    row_index: int
    instrument_name: str
    symbol: str | None = None
    column_values: dict[str, str] = Field(default_factory=dict)


class MetaStockExplorerResultsDTO(BaseModel):
    schema_version: Literal["1.0"]
    outcome: Literal["matches_found", "no_matches"]
    expected_count: int
    matched_count: int
    has_matches: bool
    clipboard_verification: MetaStockClipboardVerificationDTO | None = None
    rows: list[MetaStockResultRowDTO] = Field(default_factory=list)


class ReadMetaStockResultsInput(BaseModel):
    explorer_id: str = Field(
        min_length=1,
        description=(
            "explorer_outputs ID associated with the "
            "currently open MetaStock result window. "
            "Required so the result artifact can be "
            "stored without becoming orphaned."
        ),
    )
    close_after_read: bool = Field(
        default=True,
        description=(
            "Close Exploration Execution after rows "
            "are captured and clipboard-verified."
        ),
    )


class ReadMetaStockResultsOutput(BaseModel):
    explorer_id: str
    result_id: str | None = None
    stored_at: str | None = None
    persisted: bool = False

    succeeded: bool
    message: str
    started_at: str | None = None
    finished_at: str | None = None

    results: (
        MetaStockExplorerResultsDTO | None
    ) = None
    diagnostics: dict[str, Any] = Field(
        default_factory=dict
    )

class GetExplorerResultInput(BaseModel):
    result_id: str = Field(
        min_length=1,
        description=(
            "Primary key of a stored "
            "explorer_result_sets result."
        ),
    )


class GetLatestExplorerResultInput(BaseModel):
    explorer_id: str = Field(
        min_length=1,
        description=(
            "Explorer ID whose newest stored "
            "result should be returned."
        ),
    )


class ListExplorerResultsInput(BaseModel):
    explorer_id: str = Field(
        min_length=1,
        description=(
            "Explorer ID whose stored result "
            "history should be listed."
        ),
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
    )

class StoredMetaStockExplorerResultDTO(BaseModel):
    result_id: str
    explorer_id: str
    created_at: str | None = None

    schema_version: Literal["1.0"]
    outcome: Literal[
        "matches_found",
        "no_matches",
    ]

    expected_count: int
    matched_count: int
    has_matches: bool

    clipboard_verified: bool | None = None
    clipboard_verification: (
        MetaStockClipboardVerificationDTO | None
    ) = None

    rows: list[
        MetaStockResultRowDTO
    ] = Field(default_factory=list)

    capture_started_at: str | None = None
    capture_finished_at: str | None = None

    diagnostics: dict[str, Any] = Field(
        default_factory=dict
    )


class MetaStockExplorerResultSummaryDTO(
    BaseModel
):
    result_id: str
    explorer_id: str
    created_at: str | None = None

    schema_version: Literal["1.0"]
    outcome: Literal[
        "matches_found",
        "no_matches",
    ]

    expected_count: int
    matched_count: int
    has_matches: bool

    clipboard_verified: bool | None = None

    capture_started_at: str | None = None
    capture_finished_at: str | None = None



class GetExplorerResultOutput(BaseModel):
    result: StoredMetaStockExplorerResultDTO



class GetLatestExplorerResultOutput(BaseModel):
    explorer_id: str
    found: bool
    result: (
        StoredMetaStockExplorerResultDTO | None
    ) = None



class ListExplorerResultsOutput(BaseModel):
    explorer_id: str
    count: int
    results: list[
        MetaStockExplorerResultSummaryDTO
    ] = Field(default_factory=list)
