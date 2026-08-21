from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from ..backend_port import ConversationBackendPort, ProgressCallback
from ..models import (
    ActiveContextViewModel,
    ChatMessageViewModel,
    ClarificationViewModel,
    ConversationSnapshot,
    ConversationSummary,
    ExplorerColumn,
    ExplorerEditPatch,
    ExplorerViewModel,
    RagLogViewModel,
    ResultViewModel,
    RetrievedReference,
    ToolOutcomeViewModel,
    TurnProgress,
    TurnResponse,
)


_ARTIFACT_ONLY_ROUTES = {
    "generate_explorer",
    "repair_explorer",
    "revise_explorer",
}

_RESULT_DETAIL_TOOLS = {
    "read_metastock_explorer_results",
    "get_explorer_result",
    "get_latest_explorer_result",
}


class Ms10ConversationAdapter(ConversationBackendPort):
    """
    UI adapter for the MS10 ``ConversationApplicationService`` contract.

    The adapter consumes application-service records and persisted ToolResult
    JSON only. It deliberately does not import LangGraph state, semantic
    commands, action-policy models, workflow plans, or ToolRegistry internals.
    """

    def __init__(
        self,
        conversation_service: Any,
        *,
        explorer_edit_service: Any | None = None,
        conversation_export_service: Any | None = None,
    ):
        self._service = conversation_service
        self._explorer_edit_service = explorer_edit_service
        self._conversation_export_service = conversation_export_service

    # ------------------------------------------------------------------
    # Conversation operations
    # ------------------------------------------------------------------

    def list_conversations(self) -> list[ConversationSummary]:
        records = self._service.list_conversations()
        return [self._summary(record) for record in records]

    def create_conversation(
        self,
        title: str = "New conversation",
    ) -> ConversationSnapshot:
        record = self._service.create_conversation(title=title)
        return ConversationSnapshot(
            conversation_id=str(_value(record, "conversation_id")),
            title=str(_value(record, "title") or title),
        )

    def load_conversation(self, conversation_id: str) -> ConversationSnapshot:
        conversation_uuid = _uuid(conversation_id)
        record = self._service.get_conversation(conversation_uuid)
        turns = self._service.get_conversation_turns(conversation_uuid)

        messages: list[ChatMessageViewModel] = []
        explorers_by_id: dict[str, ExplorerViewModel] = {}
        logs_by_id: dict[str, RagLogViewModel] = {}
        results_by_id: dict[str, ResultViewModel] = {}
        context = ActiveContextViewModel()

        for turn in turns:
            messages.append(
                ChatMessageViewModel(
                    role="user",
                    text=str(_value(turn, "user_content") or ""),
                )
            )

            route = _enum_text(_value(turn, "route"))
            context = _map_context(_value(turn, "context"))
            stream_id = _value(turn, "stream_id")
            tool_results = self._tool_results_for_stream(stream_id)

            turn_explorer, turn_results, turn_log = _project_artifacts(
                tool_results
            )
            if turn_explorer is not None and turn_explorer.explorer_id:
                explorers_by_id[turn_explorer.explorer_id] = turn_explorer
            if turn_log is not None and turn_log.log_id:
                logs_by_id[turn_log.log_id] = turn_log
            for result in turn_results:
                _store_result(results_by_id, result)

            last_result = tool_results[-1] if tool_results else None
            outcome = _tool_outcome(last_result) if last_result else None
            assistant_text = str(
                _value(turn, "assistant_content") or ""
            )
            messages.append(
                ChatMessageViewModel(
                    role="assistant",
                    text=assistant_text,
                    route=route,
                    explorer=turn_explorer,
                    results=turn_results,
                    rag_log=turn_log,
                    clarification=_clarification_for_route(
                        route,
                        assistant_text,
                    ),
                    approval_placeholder=_approval_placeholder(
                        route,
                        turn_explorer,
                        context,
                    ),
                    tool_outcome=outcome,
                )
            )

        if self._explorer_edit_service is not None:
            explorer_ids = list(
                dict.fromkeys(
                    message.explorer.explorer_id
                    for message in messages
                    if message.explorer is not None
                    and message.explorer.explorer_id
                )
            )
            persisted_rows = self._explorer_edit_service.get_explorers(
                explorer_ids
            ) if explorer_ids else []
            hydrated = {
                explorer.explorer_id: explorer
                for explorer in (
                    _map_persisted_explorer_row(row)
                    for row in persisted_rows
                )
                if explorer.explorer_id
            }
            for message in messages:
                if message.explorer is None:
                    continue
                current = hydrated.get(message.explorer.explorer_id)
                if current is not None:
                    message.explorer = current
            explorers_by_id.update(hydrated)

        active_explorer = _select_active_explorer(
            explorers_by_id,
            context.active_explorer_id,
        )
        active_log = _select_active_log(
            logs_by_id,
            context.active_service_log_id,
        )
        results = _sort_results(list(results_by_id.values()))
        _mark_latest(results, context.active_result_id)

        return ConversationSnapshot(
            conversation_id=str(_value(record, "conversation_id")),
            title=str(
                _value(record, "title")
                or "Untitled conversation"
            ),
            messages=messages,
            context=context,
            active_explorer=active_explorer,
            active_log=active_log,
            results=results,
            status="idle",
        )

    def rename_conversation(
        self,
        conversation_id: str,
        title: str,
    ) -> None:
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("Conversation title cannot be blank.")
        self._service.rename_conversation(
            _uuid(conversation_id),
            cleaned,
        )

    def clear_conversation(
        self,
        conversation_id: str,
    ) -> ConversationSnapshot:
        record = self._service.clear_conversation(
            _uuid(conversation_id)
        )
        return ConversationSnapshot(
            conversation_id=str(_value(record, "conversation_id")),
            title=str(
                _value(record, "title")
                or "Untitled conversation"
            ),
        )

    def delete_conversation(self, conversation_id: str) -> None:
        deleted = self._service.delete_conversation(
            _uuid(conversation_id)
        )
        if not deleted:
            raise ValueError("Conversation does not exist.")

    def save_explorer_edits(
        self,
        explorer_id: str,
        expected_version: int,
        patch: ExplorerEditPatch,
    ) -> ExplorerViewModel:
        if self._explorer_edit_service is None:
            raise RuntimeError("Explorer editing is not configured.")
        row = self._explorer_edit_service.save_edits(
            explorer_id=explorer_id,
            expected_version=expected_version,
            name=patch.name,
            description=patch.description,
            columns=[
                {"col_letter": item.label, "col_code": item.formula}
                for item in patch.columns
            ],
            filter_formula=patch.filter_formula,
            assumptions=list(patch.assumptions),
        )
        return _map_persisted_explorer_row(row)

    def export_conversation_markdown(
        self,
        conversation_id: str,
        destination_path: str,
    ) -> str:
        if self._conversation_export_service is None:
            raise RuntimeError("Conversation export is not configured.")
        path = self._conversation_export_service.export_markdown(
            conversation_id=_uuid(conversation_id),
            destination_path=destination_path,
        )
        return str(path)

    # ------------------------------------------------------------------
    # Turn execution
    # ------------------------------------------------------------------

    def execute_turn(
        self,
        conversation_id: str,
        user_text: str,
        on_progress: ProgressCallback,
    ) -> TurnResponse:
        cleaned = user_text.strip()
        if not cleaned:
            raise ValueError("User message cannot be blank.")

        on_progress(
            TurnProgress(
                state="processing",
                message="Processing your request…",
            )
        )

        result = self._service.execute_conversation_turn(
            conversation_id=_uuid(conversation_id),
            user_content=cleaned,
            client_turn_id=uuid4(),
        )

        route = _enum_text(_value(result, "route"))
        context = _map_context(_value(result, "context"))
        stream_id = _value(result, "stream_id")
        tool_results = self._tool_results_for_stream(stream_id)

        # The application service also returns the final ToolResult. Persisted
        # tool-call rows remain the authoritative source for multi-step turns,
        # but this fallback keeps direct/replayed turns renderable if audit rows
        # are unavailable to the current caller.
        if not tool_results:
            fallback_result = _as_json_dict(
                _value(result, "tool_result")
            )
            if fallback_result:
                tool_results = [fallback_result]

        explorer, turn_results, rag_log = _project_artifacts(
            tool_results
        )
        last_result = tool_results[-1] if tool_results else None
        outcome = _tool_outcome(last_result) if last_result else None
        assistant_text = str(
            _value(result, "assistant_message") or ""
        ).strip()

        if not assistant_text:
            raise RuntimeError(
                "MS10 returned an empty assistant message."
            )

        assistant_message = ChatMessageViewModel(
            role="assistant",
            text=assistant_text,
            route=route,
            explorer=explorer,
            results=turn_results,
            rag_log=rag_log,
            clarification=_clarification_for_route(
                route,
                assistant_text,
            ),
            approval_placeholder=_approval_placeholder(
                route,
                explorer,
                context,
            ),
            tool_outcome=outcome,
        )

        # Reload through the public application service so durable conversation
        # state remains authoritative when the chat is reopened.
        snapshot = self.load_conversation(conversation_id)

        return TurnResponse(
            conversation_id=conversation_id,
            messages=[assistant_message],
            context=context,
            active_explorer=snapshot.active_explorer,
            active_log=snapshot.active_log,
            results=snapshot.results,
            final_status=_final_status(route, tool_results),
            replayed=bool(_value(result, "replayed", False)),
        )

    # ------------------------------------------------------------------

    def _tool_results_for_stream(
        self,
        stream_id: Any,
    ) -> list[dict[str, Any]]:
        if stream_id is None:
            return []

        calls = self._service.get_tool_calls_for_turn(
            _uuid(str(stream_id))
        )
        ordered_calls = sorted(
            calls,
            key=lambda call: _safe_int(
                _value(call, "ordinal", 0),
                default=0,
            ),
        )
        results: list[dict[str, Any]] = []
        for call in ordered_calls:
            raw = _as_json_dict(_value(call, "result_json"))
            if raw:
                results.append(raw)
        return results

    @staticmethod
    def _summary(record: Any) -> ConversationSummary:
        return ConversationSummary(
            conversation_id=str(
                _value(record, "conversation_id")
            ),
            title=str(
                _value(record, "title")
                or "Untitled conversation"
            ),
            updated_at=_datetime_text(
                _value(record, "updated_at")
            ),
        )


# ----------------------------------------------------------------------
# Projection helpers
# ----------------------------------------------------------------------


def _project_artifacts(
    tool_results: Iterable[dict[str, Any]],
) -> tuple[
    ExplorerViewModel | None,
    list[ResultViewModel],
    RagLogViewModel | None,
]:
    explorer: ExplorerViewModel | None = None
    rag_log: RagLogViewModel | None = None
    results: dict[str, ResultViewModel] = {}

    for tool_result in tool_results:
        data = tool_result.get("data")
        if not isinstance(data, dict):
            continue

        candidate = data.get("explorer")
        if isinstance(candidate, dict):
            explorer = _map_explorer(candidate, data)

        tool_name = str(tool_result.get("tool_name") or "")
        if tool_name == "get_rag_log":
            rag_log = _map_rag_log(data)

        for result in _map_results(tool_name, data):
            _store_result(results, result)

    return explorer, list(results.values()), rag_log


def _map_explorer(
    raw: dict[str, Any],
    envelope: dict[str, Any],
) -> ExplorerViewModel:
    validation = (
        raw.get("validation")
        if isinstance(raw.get("validation"), dict)
        else {}
    )
    raw_row = (
        envelope.get("raw_row")
        if isinstance(envelope.get("raw_row"), dict)
        else {}
    )

    refs = envelope.get("retrieved_refs")
    if not isinstance(refs, list):
        refs = raw_row.get("retrieved_refs")
    if not isinstance(refs, list):
        refs = []

    assumptions = envelope.get("assumptions")
    if not isinstance(assumptions, list):
        assumptions = raw_row.get("assumptions")
    if not isinstance(assumptions, list):
        assumptions = []

    columns: list[ExplorerColumn] = []
    for item in raw.get("columns") or []:
        if not isinstance(item, dict):
            continue
        columns.append(
            ExplorerColumn(
                label=str(
                    item.get("col_letter")
                    or item.get("label")
                    or "Column"
                ),
                formula=str(
                    item.get("col_code")
                    or item.get("formula")
                    or ""
                ),
            )
        )

    references: list[RetrievedReference] = []
    for item in refs:
        if not isinstance(item, dict):
            continue
        score = item.get(
            "rag_score",
            item.get("score", 0.0),
        )
        try:
            numeric_score = float(score or 0.0)
        except (TypeError, ValueError):
            numeric_score = 0.0
        references.append(
            RetrievedReference(
                key=str(
                    item.get("key")
                    or item.get("card_id")
                    or ""
                ),
                table_title=str(
                    item.get("table_title")
                    or item.get("title")
                    or "Reference"
                ),
                score=numeric_score,
                retrieval_reason=str(
                    item.get("retrieval_reason")
                    or item.get("reason")
                    or ""
                ),
            )
        )

    passed = bool(validation.get("passed", False))
    return ExplorerViewModel(
        explorer_id=str(raw.get("explorer_id") or ""),
        name=str(raw.get("name") or "Untitled Explorer"),
        description=str(raw.get("description") or ""),
        columns=columns,
        filter_formula=str(
            raw.get("filter_code")
            or raw.get("filter_formula")
            or ""
        ),
        assumptions=[str(value) for value in assumptions],
        validation_status=(
            "passed" if passed else "failed"
        ),
        validation_errors=[
            str(value)
            for value in validation.get("errors") or []
        ],
        validation_warnings=[
            str(value)
            for value in validation.get("warnings") or []
        ],
        retrieved_references=references,
        source=str(
            raw.get("source")
            or raw_row.get("source")
            or "agent-generated"
        ),
        explorer_created_at=_optional_text(
            raw.get("explorer_created_at")
        ),
        service_log_id=_optional_text(
            raw.get("service_log_id")
            or raw_row.get("service_log_id")
        ),
        service_log_created_at=_optional_text(
            raw.get("service_log_created_at")
        ),
        can_run_in_metastock=bool(
            raw.get("can_run_in_metastock", False)
        ),
        can_repair=bool(raw.get("can_repair", False)),
        revised_from_explorer_id=_optional_text(
            envelope.get("revised_from_explorer_id")
            or raw_row.get("revised_from_explorer_id")
        ),
        repaired_from_explorer_id=_optional_text(
            envelope.get("repaired_from_explorer_id")
            or raw_row.get("repaired_from_explorer_id")
        ),
        revision_instruction=_optional_text(
            envelope.get("revision_instruction")
            or raw_row.get("revision_instruction")
        ),
        updated_at=_optional_text(
            raw.get("updated_at") or raw_row.get("updated_at")
        ),
        manual_edit_version=_safe_int(
            raw.get("manual_edit_version", raw_row.get("manual_edit_version", 0)),
            default=0,
        ),
    )



def _map_persisted_explorer_row(raw: Any) -> ExplorerViewModel:
    row = _as_json_dict(raw) or {}
    validation_errors = row.get("validation_errors")
    if not isinstance(validation_errors, list):
        validation_errors = []
    warnings = [
        str(item)[8:].strip()
        for item in validation_errors
        if str(item).startswith("Warning:")
    ]
    hard_errors = [
        str(item)
        for item in validation_errors
        if not str(item).startswith("Warning:")
    ]
    normalized = {
        "explorer_id": row.get("id") or row.get("explorer_id"),
        "name": row.get("explorer_name"),
        "description": row.get("explorer_description"),
        "columns": row.get("col_definitions") or [],
        "filter_code": row.get("explorer_code_body"),
        "validation": {
            "passed": bool(row.get("validation_passed", False)),
            "errors": hard_errors,
            "warnings": warnings,
        },
        "source": row.get("source") or row.get("backend") or "stored",
        "explorer_created_at": row.get("created_at"),
        "service_log_id": row.get("service_log_id"),
        "updated_at": row.get("updated_at"),
        "manual_edit_version": row.get("manual_edit_version", 0),
        "can_run_in_metastock": bool(row.get("validation_passed", False)),
        "can_repair": not bool(row.get("validation_passed", False)),
    }
    envelope = {
        "assumptions": row.get("assumptions") or [],
        "retrieved_refs": row.get("retrieved_refs") or [],
        "raw_row": row,
        "revised_from_explorer_id": row.get("revised_from_explorer_id"),
        "repaired_from_explorer_id": row.get("repaired_from_explorer_id"),
        "revision_instruction": row.get("revision_instruction"),
    }
    return _map_explorer(normalized, envelope)

def _map_rag_log(data: dict[str, Any]) -> RagLogViewModel:
    metadata = data.get("metadata")
    return RagLogViewModel(
        log_id=str(data.get("log_id") or ""),
        created_at=_optional_text(data.get("created_at")),
        event_type=_optional_text(data.get("event_type")),
        stdout_text=str(data.get("stdout_text") or ""),
        stderr_text=str(data.get("stderr_text") or ""),
        metadata=(metadata if isinstance(metadata, dict) else {}),
    )


def _map_results(
    tool_name: str,
    data: dict[str, Any],
) -> list[ResultViewModel]:
    if tool_name == "read_metastock_explorer_results":
        payload = data.get("results")
        if isinstance(payload, dict) and data.get("result_id"):
            return [
                _map_result_payload(
                    payload,
                    result_id=str(data.get("result_id")),
                    explorer_id=str(
                        data.get("explorer_id") or ""
                    ),
                    created_at=str(
                        data.get("stored_at")
                        or data.get("finished_at")
                        or ""
                    ),
                    capture_started_at=_optional_text(
                        data.get("started_at")
                    ),
                    capture_finished_at=_optional_text(
                        data.get("finished_at")
                    ),
                    diagnostics=(
                        data.get("diagnostics")
                        if isinstance(
                            data.get("diagnostics"),
                            dict,
                        )
                        else {}
                    ),
                )
            ]

    if tool_name == "get_explorer_result":
        result = data.get("result")
        return (
            [_map_stored_result(result)]
            if isinstance(result, dict)
            else []
        )

    if tool_name == "get_latest_explorer_result":
        result = data.get("result")
        return (
            [_map_stored_result(result, is_latest=True)]
            if isinstance(result, dict)
            else []
        )

    if tool_name == "list_explorer_results":
        values = data.get("results")
        if not isinstance(values, list):
            return []
        return [
            _map_result_summary(
                value,
                is_latest=(index == 0),
            )
            for index, value in enumerate(values)
            if isinstance(value, dict)
        ]

    return []


def _map_stored_result(
    raw: dict[str, Any],
    *,
    is_latest: bool = False,
) -> ResultViewModel:
    return _map_result_payload(
        raw,
        result_id=str(raw.get("result_id") or ""),
        explorer_id=str(raw.get("explorer_id") or ""),
        created_at=str(raw.get("created_at") or ""),
        capture_started_at=_optional_text(
            raw.get("capture_started_at")
        ),
        capture_finished_at=_optional_text(
            raw.get("capture_finished_at")
        ),
        diagnostics=(
            raw.get("diagnostics")
            if isinstance(raw.get("diagnostics"), dict)
            else {}
        ),
        clipboard_verified=raw.get("clipboard_verified"),
        is_latest=is_latest,
    )


def _map_result_summary(
    raw: dict[str, Any],
    *,
    is_latest: bool,
) -> ResultViewModel:
    return ResultViewModel(
        result_id=str(raw.get("result_id") or ""),
        explorer_id=str(raw.get("explorer_id") or ""),
        created_at=str(raw.get("created_at") or ""),
        outcome=(
            "matched"
            if bool(raw.get("has_matches"))
            else "no_match"
        ),
        matched_count=_safe_int(
            raw.get("matched_count"),
            default=0,
        ),
        expected_count=_optional_int(
            raw.get("expected_count")
        ),
        columns=[],
        rows=[],
        is_latest=is_latest,
        capture_started_at=_optional_text(
            raw.get("capture_started_at")
        ),
        capture_completed_at=_optional_text(
            raw.get("capture_finished_at")
        ),
        clipboard_verified=_optional_bool(
            raw.get("clipboard_verified")
        ),
        is_summary_only=True,
    )


def _map_result_payload(
    raw: dict[str, Any],
    *,
    result_id: str,
    explorer_id: str,
    created_at: str,
    capture_started_at: str | None,
    capture_finished_at: str | None,
    diagnostics: dict[str, Any],
    clipboard_verified: Any = None,
    is_latest: bool = False,
) -> ResultViewModel:
    raw_rows = (
        raw.get("rows")
        if isinstance(raw.get("rows"), list)
        else []
    )
    column_names: list[str] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        values = row.get("column_values")
        if not isinstance(values, dict):
            continue
        for key in values:
            name = str(key)
            if name not in column_names:
                column_names.append(name)

    include_symbol = any(
        isinstance(row, dict)
        and row.get("symbol") not in {None, ""}
        for row in raw_rows
    )
    columns = (
        ["Instrument"]
        + (["Symbol"] if include_symbol else [])
        + column_names
    )
    rows: list[list[Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        values = (
            row.get("column_values")
            if isinstance(row.get("column_values"), dict)
            else {}
        )
        rendered = [str(row.get("instrument_name") or "")]
        if include_symbol:
            rendered.append(str(row.get("symbol") or ""))
        rendered.extend(
            str(values.get(name, ""))
            for name in column_names
        )
        rows.append(rendered)

    verification = raw.get("clipboard_verification")
    if (
        clipboard_verified is None
        and isinstance(verification, dict)
    ):
        clipboard_verified = verification.get("passed")

    has_matches = bool(raw.get("has_matches", rows))
    outcome_text = str(raw.get("outcome") or "")
    outcome = (
        "matched"
        if has_matches or outcome_text == "matches_found"
        else "no_match"
    )

    return ResultViewModel(
        result_id=result_id,
        explorer_id=explorer_id,
        created_at=created_at,
        outcome=outcome,
        matched_count=_safe_int(
            raw.get("matched_count"),
            default=len(rows),
        ),
        expected_count=_optional_int(
            raw.get("expected_count")
        ),
        columns=columns,
        rows=rows,
        is_latest=is_latest,
        capture_started_at=capture_started_at,
        capture_completed_at=capture_finished_at,
        clipboard_verified=_optional_bool(
            clipboard_verified
        ),
        diagnostics=diagnostics,
    )


def _tool_outcome(
    tool_result: dict[str, Any],
) -> ToolOutcomeViewModel:
    status = str(tool_result.get("status") or "failed")
    if status not in {
        "success",
        "failed",
        "blocked",
        "not_implemented",
    }:
        status = "failed"

    display = (
        tool_result.get("display")
        if isinstance(tool_result.get("display"), dict)
        else {}
    )
    error = (
        tool_result.get("error")
        if isinstance(tool_result.get("error"), dict)
        else {}
    )
    # Successful artifact payloads have dedicated cards/tables. Preserve the
    # backend display markdown primarily for failures and blocked operations,
    # where its safe user-facing explanation adds value.
    display_markdown = (
        _optional_text(display.get("markdown"))
        if status != "success"
        else None
    )
    return ToolOutcomeViewModel(
        status=status,  # type: ignore[arg-type]
        message=str(tool_result.get("message") or ""),
        display_title=_optional_text(display.get("title")),
        display_severity=_optional_text(
            display.get("severity")
        ),
        display_markdown=display_markdown,
        error_code=_optional_text(error.get("code")),
        error_message=_optional_text(error.get("message")),
    )


def _final_status(
    route: str | None,
    tool_results: list[dict[str, Any]],
) -> str:
    if route == "clarify":
        return "clarifying"
    if not tool_results:
        return "completed"

    last = tool_results[-1]
    status = str(last.get("status") or "")
    if status in {"blocked", "not_implemented"}:
        return "blocked"
    if status == "failed" or not bool(last.get("ok", True)):
        return "failed"

    tool_name = str(last.get("tool_name") or "")
    if tool_name in _RESULT_DETAIL_TOOLS:
        data = last.get("data")
        if isinstance(data, dict):
            result = (
                data.get("results")
                if tool_name
                == "read_metastock_explorer_results"
                else data.get("result")
            )
            if isinstance(result, dict) and not bool(
                result.get("has_matches", False)
            ):
                return "no_matches"

    return "completed"


def _clarification_for_route(
    route: str | None,
    assistant_text: str,
) -> ClarificationViewModel | None:
    del assistant_text
    if route != "clarify":
        return None
    return ClarificationViewModel(
        title="Clarification required",
        options=[],
        placeholder=(
            "Reply with the exact Explorer name or missing detail…"
        ),
    )


def _approval_placeholder(
    route: str | None,
    explorer: ExplorerViewModel | None,
    context: ActiveContextViewModel,
) -> str | None:
    # MS10 normally creates a generated Explorer in MetaStock immediately.
    # Showing review controls after that side effect would imply a gate that did
    # not exist. Keep the visual placeholder only for review-only artifacts that
    # are known not to have been created in MetaStock.
    if (
        explorer is None
        or route not in _ARTIFACT_ONLY_ROUTES
        or context.active_explorer_metastock_state
        != "not_created"
    ):
        return None
    return (
        "Review this Explorer before requesting the next action. "
        "These approval controls are visual placeholders only."
    )


def _map_context(raw: Any) -> ActiveContextViewModel:
    if raw is None:
        return ActiveContextViewModel()
    state = str(
        _value(
            raw,
            "active_explorer_metastock_state",
            "unknown",
        )
        or "unknown"
    )
    if state not in {"unknown", "not_created", "created"}:
        state = "unknown"
    return ActiveContextViewModel(
        active_explorer_id=_optional_text(
            _value(raw, "active_explorer_id")
        ),
        active_result_id=_optional_text(
            _value(raw, "active_result_id")
        ),
        active_service_log_id=_optional_text(
            _value(raw, "active_service_log_id")
        ),
        active_explorer_metastock_state=state,  # type: ignore[arg-type]
    )


def _select_active_explorer(
    explorers_by_id: dict[str, ExplorerViewModel],
    active_id: str | None,
) -> ExplorerViewModel | None:
    if active_id:
        return explorers_by_id.get(active_id)
    if explorers_by_id:
        last_key = next(reversed(explorers_by_id))
        return explorers_by_id[last_key]
    return None


def _select_active_log(
    logs_by_id: dict[str, RagLogViewModel],
    active_id: str | None,
) -> RagLogViewModel | None:
    if active_id:
        return logs_by_id.get(active_id)
    if logs_by_id:
        last_key = next(reversed(logs_by_id))
        return logs_by_id[last_key]
    return None


def _store_result(
    results: dict[str, ResultViewModel],
    candidate: ResultViewModel,
) -> None:
    if not candidate.result_id:
        return
    existing = results.get(candidate.result_id)
    if (
        existing is not None
        and not existing.is_summary_only
        and candidate.is_summary_only
    ):
        # A later list_explorer_results call must not discard already loaded
        # rows for the same durable result.
        existing.is_latest = (
            existing.is_latest or candidate.is_latest
        )
        return
    results[candidate.result_id] = candidate


def _sort_results(
    results: list[ResultViewModel],
) -> list[ResultViewModel]:
    return sorted(
        results,
        key=lambda item: item.created_at or "",
        reverse=True,
    )


def _mark_latest(
    results: list[ResultViewModel],
    active_result_id: str | None,
) -> None:
    for result in results:
        result.is_latest = bool(
            active_result_id
            and result.result_id == active_result_id
        )
    if results and not any(result.is_latest for result in results):
        results[0].is_latest = True


def _as_json_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else None
    return None


def _value(
    obj: Any,
    key: str,
    default: Any = None,
) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid UUID: {value}") from exc


def _enum_text(value: Any) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _datetime_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    return str(value)
