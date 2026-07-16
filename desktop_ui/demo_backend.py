from __future__ import annotations

import copy
import time
import uuid
from datetime import datetime, timezone

from .backend_port import ConversationBackendPort, ProgressCallback
from .models import (
    ActiveContextViewModel,
    ChatMessageViewModel,
    ClarificationViewModel,
    ConversationSnapshot,
    ConversationSummary,
    ExplorerColumn,
    ExplorerViewModel,
    RagLogViewModel,
    ResultViewModel,
    RetrievedReference,
    ToolOutcomeViewModel,
    TurnProgress,
    TurnResponse,
)


def now_text() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def time_only() -> str:
    return datetime.now().strftime("%H:%M")


def make_explorer(
    name: str = "MA Crossover — SMA(10) / SMA(50)",
    *,
    revised_from: str | None = None,
    revision_instruction: str | None = None,
) -> ExplorerViewModel:
    return ExplorerViewModel(
        explorer_id=str(uuid.uuid4()),
        explorer_created_at=now_text(),
        name=name,
        description=(
            "Finds securities where the 10-period simple moving average crosses "
            "above the 50-period simple moving average."
        ),
        columns=[
            ExplorerColumn("A", "C"),
            ExplorerColumn("B", "Mov(C,10,S)"),
            ExplorerColumn("C", "Mov(C,50,S)"),
        ],
        filter_formula="Cross(ColB,ColC)",
        assumptions=[
            "Moving-average method defaults to simple.",
            "The scan evaluates the latest available bar.",
        ],
        validation_status="passed",
        validation_warnings=[],
        retrieved_references=[
            RetrievedReference(
                key="function.mov",
                table_title="Mov",
                score=0.96,
                retrieval_reason="Required for both moving-average calculations.",
            ),
            RetrievedReference(
                key="function.cross",
                table_title="Cross",
                score=0.94,
                retrieval_reason="Required for the crossover event.",
            ),
        ],
        source="demo-ms10-frozen-contract",
        service_log_id=str(uuid.uuid4()),
        service_log_created_at=now_text(),
        can_run_in_metastock=True,
        can_repair=True,
        revised_from_explorer_id=revised_from,
        revision_instruction=revision_instruction,
    )


def make_results(explorer_id: str) -> list[ResultViewModel]:
    return [
        ResultViewModel(
            result_id=str(uuid.uuid4()),
            explorer_id=explorer_id,
            created_at="2026-07-15 22:31:02",
            outcome="matched",
            matched_count=7,
            expected_count=7,
            columns=["Instrument", "Symbol", "A", "B", "C"],
            rows=[
                ["Apple Inc.", "AAPL", "189.42", "187.20", "183.91"],
                ["Microsoft Corp.", "MSFT", "428.15", "424.80", "418.32"],
                ["NVIDIA Corp.", "NVDA", "131.38", "128.70", "121.54"],
                ["Meta Platforms", "META", "561.22", "554.10", "542.86"],
                ["Advanced Micro Devices", "AMD", "178.64", "175.30", "168.22"],
                ["Tesla Inc.", "TSLA", "248.50", "244.90", "239.11"],
                ["Alphabet Inc.", "GOOG", "191.75", "189.20", "185.43"],
            ],
            is_latest=True,
            capture_started_at="2026-07-15 22:30:47",
            capture_completed_at="2026-07-15 22:31:02",
            clipboard_verified=True,
            diagnostics={
                "symbols_scanned": 4821,
                "scan_duration_ms": 1342,
                "capture_mode": "UIA + clipboard",
            },
        ),
        ResultViewModel(
            result_id=str(uuid.uuid4()),
            explorer_id=explorer_id,
            created_at="2026-07-14 15:40:12",
            outcome="no_match",
            matched_count=0,
            expected_count=0,
            columns=["Instrument", "Symbol", "A", "B", "C"],
            rows=[],
            is_latest=False,
            capture_started_at="2026-07-14 15:39:58",
            capture_completed_at="2026-07-14 15:40:12",
            clipboard_verified=True,
            diagnostics={"symbols_scanned": 4821, "capture_mode": "UIA + clipboard"},
        ),
    ]


def make_log(log_id: str | None = None) -> RagLogViewModel:
    return RagLogViewModel(
        log_id=log_id or str(uuid.uuid4()),
        created_at=now_text(),
        event_type="generate_explorer",
        stdout_text=(
            "Retrieved 8 knowledge cards.\n"
            "Generated Explorer passed validation.\n"
            "Persisted Explorer and service log."
        ),
        stderr_text="",
        metadata={"source": "demo", "validation_passed": True},
    )


class DemoConversationBackend(ConversationBackendPort):
    """In-memory demo of the frozen MS10 application-service outcomes."""

    def __init__(self) -> None:
        self._snapshots: dict[str, ConversationSnapshot] = {}
        self._seed()

    def _seed(self) -> None:
        explorer = make_explorer()
        results = make_results(explorer.explorer_id)
        rag_log = make_log(explorer.service_log_id)
        context = ActiveContextViewModel(
            active_explorer_id=explorer.explorer_id,
            active_result_id=results[0].result_id,
            active_service_log_id=explorer.service_log_id,
            active_explorer_metastock_state="created",
        )

        main = ConversationSnapshot(
            conversation_id=str(uuid.uuid4()),
            title="Moving average crossover setup",
            messages=[
                ChatMessageViewModel(
                    role="user",
                    text="Find stocks where the 10-day SMA just crossed above the 50-day SMA.",
                    created_at="09:27",
                ),
                ChatMessageViewModel(
                    role="assistant",
                    text="I generated, validated, and created this Explorer in MetaStock.",
                    created_at="09:29",
                    route="generate_and_create_explorer_sequence",
                    explorer=explorer,
                    tool_outcome=ToolOutcomeViewModel(
                        status="success",
                        message="Explorer created successfully.",
                        display_title="Generated Explorer",
                        display_severity="success",
                    ),
                ),
                ChatMessageViewModel(
                    role="user",
                    text="Why did you use simple moving averages?",
                    created_at="09:30",
                ),
                ChatMessageViewModel(
                    role="assistant",
                    text=(
                        "The request specified SMA, so the Explorer uses MetaStock's simple "
                        "moving-average method, `S`. No backend action was needed for this explanation."
                    ),
                    created_at="09:30",
                    route="respond",
                ),
                ChatMessageViewModel(
                    role="user",
                    text="Run it and give me the results.",
                    created_at="09:31",
                ),
                ChatMessageViewModel(
                    role="assistant",
                    text="The Explorer ran successfully and the newest result contains 7 matches.",
                    created_at="09:31",
                    route="run_current_explorer_and_read_results_sequence",
                    results=[results[0]],
                    tool_outcome=ToolOutcomeViewModel(
                        status="success",
                        message="MetaStock results were captured and stored.",
                        display_title="Explorer Results",
                        display_severity="success",
                    ),
                ),
            ],
            context=context,
            active_explorer=explorer,
            active_log=rag_log,
            results=results,
            status="completed",
        )

        clarify = ConversationSnapshot(
            conversation_id=str(uuid.uuid4()),
            title="Ambiguous Explorer reference",
            messages=[
                ChatMessageViewModel(
                    role="user",
                    text="Run the volume spike one.",
                    created_at="11:15",
                ),
                ChatMessageViewModel(
                    role="assistant",
                    text="No stored Explorer has that exact name. Provide the exact Explorer name.",
                    created_at="11:15",
                    route="clarify",
                    clarification=ClarificationViewModel(
                        title="Clarification required",
                        placeholder="Provide the exact Explorer name…",
                    ),
                ),
            ],
            status="clarifying",
        )

        revised_explorer = make_explorer(
            "MA Crossover — SMA(20) / SMA(50)",
            revised_from=explorer.explorer_id,
            revision_instruction=(
                "Change the fast simple moving average from 10 periods to 20 periods "
                "and preserve every other condition."
            ),
        )
        revised_log = make_log(revised_explorer.service_log_id)
        revision = ConversationSnapshot(
            conversation_id=str(uuid.uuid4()),
            title="Explorer revision",
            messages=[
                ChatMessageViewModel(
                    role="user",
                    text="Use a 20-day fast average instead, and keep everything else unchanged.",
                    created_at="13:05",
                ),
                ChatMessageViewModel(
                    role="assistant",
                    text="I revised the Explorer as a new stored version. The original remains unchanged.",
                    created_at="13:06",
                    route="revise_explorer",
                    explorer=revised_explorer,
                    tool_outcome=ToolOutcomeViewModel(
                        status="success",
                        message="Explorer revision completed and saved as a new row.",
                        display_title="Revised Explorer",
                        display_severity="success",
                    ),
                    approval_placeholder=(
                        "Review this revised Explorer. These approval controls are visual placeholders only."
                    ),
                ),
            ],
            context=ActiveContextViewModel(
                active_explorer_id=revised_explorer.explorer_id,
                active_service_log_id=revised_explorer.service_log_id,
                active_explorer_metastock_state="not_created",
            ),
            active_explorer=revised_explorer,
            active_log=revised_log,
            status="completed",
        )

        for snapshot in (main, clarify, revision):
            self._snapshots[snapshot.conversation_id] = snapshot

    def list_conversations(self) -> list[ConversationSummary]:
        return [
            ConversationSummary(snapshot.conversation_id, snapshot.title, now_text())
            for snapshot in self._snapshots.values()
        ]

    def create_conversation(self, title: str = "New conversation") -> ConversationSnapshot:
        conversation_id = str(uuid.uuid4())
        snapshot = ConversationSnapshot(
            conversation_id=conversation_id,
            title=title,
            messages=[
                ChatMessageViewModel(
                    role="assistant",
                    text=(
                        "Describe the Explorer you want, ask about the current one, or request "
                        "a MetaStock run. I will clarify rather than guess when a reference is unsafe."
                    ),
                    created_at=time_only(),
                    route="respond",
                )
            ],
        )
        self._snapshots[conversation_id] = snapshot
        return copy.deepcopy(snapshot)

    def load_conversation(self, conversation_id: str) -> ConversationSnapshot:
        try:
            return copy.deepcopy(self._snapshots[conversation_id])
        except KeyError as exc:
            raise ValueError("Conversation not found.") from exc

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        self._snapshots[conversation_id].title = title.strip() or "Untitled conversation"

    def clear_conversation(self, conversation_id: str) -> ConversationSnapshot:
        snapshot = self._snapshots[conversation_id]
        snapshot.messages = []
        snapshot.context = ActiveContextViewModel()
        snapshot.active_explorer = None
        snapshot.active_log = None
        snapshot.results = []
        snapshot.status = "idle"
        return copy.deepcopy(snapshot)

    def delete_conversation(self, conversation_id: str) -> None:
        if self._snapshots.pop(conversation_id, None) is None:
            raise ValueError("Conversation not found.")

    def execute_turn(
        self,
        conversation_id: str,
        user_text: str,
        on_progress: ProgressCallback,
    ) -> TurnResponse:
        snapshot = self._snapshots[conversation_id]
        on_progress(TurnProgress("processing", "Processing your request…"))
        time.sleep(0.35)

        lowered = user_text.casefold()
        explorer_for_message: ExplorerViewModel | None = None
        log_for_message: RagLogViewModel | None = None
        results_for_message: list[ResultViewModel] = []
        clarification: ClarificationViewModel | None = None
        outcome: ToolOutcomeViewModel | None = None
        route = "respond"
        final_status = "completed"
        approval = None

        if "why" in lowered or "explain" in lowered:
            assistant_text = (
                "This is a conversational explanation, so MS10 returns text directly without "
                "calling a function."
            )
        elif "unknown" in lowered or "which explorer" in lowered:
            route = "clarify"
            final_status = "clarifying"
            assistant_text = "There is no active Explorer in this conversation. Provide the exact Explorer name."
            clarification = ClarificationViewModel(
                title="Clarification required",
                placeholder="Provide the exact Explorer name…",
            )
        elif "log" in lowered:
            current = snapshot.active_log
            if current is None:
                route = "clarify"
                final_status = "clarifying"
                assistant_text = "There is no active RAG service log in this conversation."
                clarification = ClarificationViewModel(title="Clarification required")
            else:
                route = "get_rag_log"
                assistant_text = "Here is the active RAG service log."
                log_for_message = current
                outcome = ToolOutcomeViewModel(
                    status="success",
                    message="RAG service log fetched.",
                    display_title="RAG Service Log",
                    display_severity="info",
                )
        elif "revise" in lowered or "change" in lowered or "instead" in lowered:
            current = snapshot.active_explorer or make_explorer()
            revised = make_explorer(
                "Revised MA Crossover",
                revised_from=current.explorer_id,
                revision_instruction=(
                    "Apply the requested change and preserve every unmentioned condition."
                ),
            )
            snapshot.active_explorer = revised
            snapshot.active_log = make_log(revised.service_log_id)
            snapshot.context = ActiveContextViewModel(
                active_explorer_id=revised.explorer_id,
                active_service_log_id=revised.service_log_id,
                active_explorer_metastock_state="not_created",
            )
            route = "revise_explorer"
            assistant_text = "I revised the Explorer and saved the revision as a new durable row."
            explorer_for_message = revised
            approval = "Review this revised Explorer. These approval controls are visual placeholders only."
            outcome = ToolOutcomeViewModel(
                status="success",
                message="Explorer revision completed and saved as a new row.",
                display_title="Revised Explorer",
                display_severity="success",
            )
        elif "result" in lowered or "run" in lowered:
            current = snapshot.active_explorer
            if current is None:
                route = "clarify"
                final_status = "clarifying"
                assistant_text = "There is no active Explorer in this conversation. Which Explorer should I run?"
                clarification = ClarificationViewModel(
                    title="Clarification required",
                    placeholder="Provide the exact Explorer name…",
                )
            else:
                snapshot.results = make_results(current.explorer_id)
                snapshot.context = ActiveContextViewModel(
                    active_explorer_id=current.explorer_id,
                    active_result_id=snapshot.results[0].result_id,
                    active_service_log_id=current.service_log_id,
                    active_explorer_metastock_state="created",
                )
                route = "run_current_explorer_and_read_results_sequence"
                assistant_text = "The Explorer ran successfully and 7 matches were captured and stored."
                results_for_message = [snapshot.results[0]]
                outcome = ToolOutcomeViewModel(
                    status="success",
                    message="MetaStock results were captured and stored.",
                    display_title="Explorer Results",
                    display_severity="success",
                )
        elif "show" in lowered and "explorer" in lowered:
            current = snapshot.active_explorer
            if current is None:
                route = "clarify"
                final_status = "clarifying"
                assistant_text = "There is no active Explorer in this conversation."
                clarification = ClarificationViewModel(title="Clarification required")
            else:
                route = "get_explorer"
                assistant_text = "Here is the current stored Explorer."
                explorer_for_message = current
                outcome = ToolOutcomeViewModel(
                    status="success",
                    message="Explorer fetched.",
                    display_title="Explorer",
                    display_severity="info",
                )
        elif "draft" in lowered or "review only" in lowered:
            generated = make_explorer("Draft MA Crossover")
            snapshot.active_explorer = generated
            snapshot.active_log = make_log(generated.service_log_id)
            snapshot.context = ActiveContextViewModel(
                active_explorer_id=generated.explorer_id,
                active_service_log_id=generated.service_log_id,
                active_explorer_metastock_state="not_created",
            )
            route = "generate_explorer"
            assistant_text = "I generated and validated a review-only Explorer without creating it in MetaStock."
            explorer_for_message = generated
            approval = "Review this Explorer. These approval controls are visual placeholders only."
            outcome = ToolOutcomeViewModel(
                status="success",
                message="Explorer generated and prepared for review.",
                display_title="Generated Explorer",
                display_severity="success",
            )
        else:
            generated = make_explorer()
            snapshot.active_explorer = generated
            snapshot.active_log = make_log(generated.service_log_id)
            snapshot.context = ActiveContextViewModel(
                active_explorer_id=generated.explorer_id,
                active_service_log_id=generated.service_log_id,
                active_explorer_metastock_state="created",
            )
            route = "generate_and_create_explorer_sequence"
            assistant_text = "I generated, validated, and created this Explorer in MetaStock."
            explorer_for_message = generated
            outcome = ToolOutcomeViewModel(
                status="success",
                message="Explorer generated and created successfully.",
                display_title="Generated Explorer",
                display_severity="success",
            )

        assistant = ChatMessageViewModel(
            role="assistant",
            text=assistant_text,
            created_at=time_only(),
            route=route,
            explorer=explorer_for_message,
            results=results_for_message,
            rag_log=log_for_message,
            clarification=clarification,
            approval_placeholder=approval,
            tool_outcome=outcome,
        )
        snapshot.messages.extend(
            [
                ChatMessageViewModel("user", user_text, time_only()),
                assistant,
            ]
        )
        snapshot.status = final_status  # type: ignore[assignment]

        return TurnResponse(
            conversation_id=conversation_id,
            messages=[copy.deepcopy(assistant)],
            context=copy.deepcopy(snapshot.context),
            active_explorer=copy.deepcopy(snapshot.active_explorer),
            active_log=copy.deepcopy(snapshot.active_log),
            results=copy.deepcopy(snapshot.results),
            final_status=final_status,  # type: ignore[arg-type]
        )
