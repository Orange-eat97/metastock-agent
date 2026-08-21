from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ValidationStatus = Literal["passed", "failed", "pending"]
ResultOutcome = Literal["matched", "no_match", "error"]
TurnStatus = Literal[
    "idle",
    "loading",
    "processing",
    "clarifying",
    "completed",
    "no_matches",
    "blocked",
    "failed",
    "resumed",
]
MetaStockSyncState = Literal["unknown", "not_created", "created"]
ToolOutcomeStatus = Literal[
    "success",
    "failed",
    "blocked",
    "not_implemented",
]


@dataclass(frozen=True)
class RetrievedReference:
    key: str
    table_title: str
    score: float
    retrieval_reason: str


@dataclass(frozen=True)
class ExplorerColumn:
    label: str
    formula: str


@dataclass(frozen=True)
class ExplorerEditPatch:
    """Editable projection of fields persisted inside full_output_json."""

    name: str
    description: str
    columns: list[ExplorerColumn]
    filter_formula: str
    assumptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExplorerSaveFailure:
    explorer_id: str
    errors: list[str]



@dataclass
class ExplorerViewModel:
    explorer_id: str
    name: str
    description: str
    columns: list[ExplorerColumn]
    filter_formula: str
    assumptions: list[str] = field(default_factory=list)
    validation_status: ValidationStatus = "pending"
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    retrieved_references: list[RetrievedReference] = field(default_factory=list)
    source: str = "agent-generated"
    explorer_created_at: str | None = None
    service_log_id: str | None = None
    service_log_created_at: str | None = None
    can_run_in_metastock: bool = False
    can_repair: bool = False
    revised_from_explorer_id: str | None = None
    repaired_from_explorer_id: str | None = None
    revision_instruction: str | None = None
    updated_at: str | None = None
    manual_edit_version: int = 0


@dataclass
class ResultViewModel:
    result_id: str
    explorer_id: str
    created_at: str
    outcome: ResultOutcome
    matched_count: int
    expected_count: int | None
    columns: list[str]
    rows: list[list[Any]]
    is_latest: bool = False
    capture_started_at: str | None = None
    capture_completed_at: str | None = None
    clipboard_verified: bool | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    is_summary_only: bool = False

    @property
    def has_matches(self) -> bool:
        return self.matched_count > 0


@dataclass
class RagLogViewModel:
    log_id: str
    created_at: str | None = None
    event_type: str | None = None
    stdout_text: str = ""
    stderr_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClarificationViewModel:
    title: str
    options: list[str] = field(default_factory=list)
    placeholder: str = "Provide the missing detail…"


@dataclass(frozen=True)
class ToolOutcomeViewModel:
    """Safe user-facing projection of the final ToolResult for a turn."""

    status: ToolOutcomeStatus
    message: str
    display_title: str | None = None
    display_severity: str | None = None
    display_markdown: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ActiveContextViewModel:
    active_explorer_id: str | None = None
    active_result_id: str | None = None
    active_service_log_id: str | None = None
    active_explorer_metastock_state: MetaStockSyncState = "unknown"


@dataclass
class ChatMessageViewModel:
    role: Literal["user", "assistant"]
    text: str
    created_at: str = ""
    route: str | None = None
    explorer: ExplorerViewModel | None = None
    results: list[ResultViewModel] = field(default_factory=list)
    rag_log: RagLogViewModel | None = None
    clarification: ClarificationViewModel | None = None
    approval_placeholder: str | None = None
    tool_outcome: ToolOutcomeViewModel | None = None


@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: str
    title: str
    updated_at: str


@dataclass
class ConversationSnapshot:
    conversation_id: str
    title: str
    messages: list[ChatMessageViewModel] = field(default_factory=list)
    context: ActiveContextViewModel = field(default_factory=ActiveContextViewModel)
    active_explorer: ExplorerViewModel | None = None
    active_log: RagLogViewModel | None = None
    results: list[ResultViewModel] = field(default_factory=list)
    status: TurnStatus = "idle"


@dataclass(frozen=True)
class TurnProgress:
    """Coarse UI progress only; MS10 remains a synchronous turn service."""

    state: TurnStatus
    message: str


@dataclass
class TurnResponse:
    conversation_id: str
    messages: list[ChatMessageViewModel]
    context: ActiveContextViewModel = field(default_factory=ActiveContextViewModel)
    active_explorer: ExplorerViewModel | None = None
    active_log: RagLogViewModel | None = None
    results: list[ResultViewModel] = field(default_factory=list)
    final_status: TurnStatus = "completed"
    replayed: bool = False
