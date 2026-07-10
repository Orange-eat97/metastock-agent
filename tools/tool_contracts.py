from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


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
    severity: Literal["info", "success", "warning", "error"] = "info"


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
        description="Optional repair instruction. Use mainly for syntax/contract repair.",
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
    diagnostics: dict[str, Any] = Field(default_factory=dict)
