from __future__ import annotations

from typing import Any

from chat.models import ChatContext
from tools.tool_contracts import ToolResult


ARTIFACT_CREATING_TOOLS = {
    "generate_explorer",
    "repair_explorer",
    "revise_explorer",
}
METASTOCK_PROOF_TOOLS = {
    "create_explorer_in_metastock",
    "select_explorer_in_metastock",
    "run_selected_explorer_in_metastock",
}


def update_context_from_tool_result(
    current: ChatContext,
    result: ToolResult,
) -> ChatContext:
    """
    Update durable conversational context from documented ToolResult paths.

    Failed, blocked, and not-implemented calls preserve the current context.
    Successful artifact creation marks the new Explorer as not yet created in
    MetaStock. Successful create/select/run proves that it exists there.
    """
    if not result.ok:
        return current.model_copy(deep=True)

    data: dict[str, Any] = result.data or {}
    explorer_data = _as_dict(
        data.get("explorer")
    )
    result_data = _as_dict(
        data.get("result")
    )

    active_explorer_id = _first_non_empty_string(
        explorer_data.get("explorer_id"),
        result_data.get("explorer_id"),
        data.get("explorer_id"),
        current.active_explorer_id,
    )
    active_result_id = _first_non_empty_string(
        data.get("result_id"),
        result_data.get("result_id"),
        current.active_result_id,
    )
    active_service_log_id = _first_non_empty_string(
        explorer_data.get("service_log_id"),
        data.get("service_log_id"),
        data.get("log_id"),
        current.active_service_log_id,
    )

    metastock_state = (
        current.active_explorer_metastock_state
    )

    if result.tool_name in ARTIFACT_CREATING_TOOLS:
        metastock_state = "not_created"
    elif result.tool_name == "get_explorer":
        fetched_id = _first_non_empty_string(
            explorer_data.get("explorer_id"),
            data.get("explorer_id"),
        )

        if (
            fetched_id
            and fetched_id
            != current.active_explorer_id
        ):
            metastock_state = "unknown"
    elif result.tool_name in METASTOCK_PROOF_TOOLS:
        metastock_state = "created"

    return ChatContext(
        active_explorer_id=active_explorer_id,
        active_explorer_metastock_state=(
            metastock_state
        ),
        active_result_id=active_result_id,
        active_service_log_id=(
            active_service_log_id
        ),
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return (
        value
        if isinstance(value, dict)
        else {}
    )


def _first_non_empty_string(
    *values: Any,
) -> str | None:
    for value in values:
        if value is None:
            continue

        text = str(value).strip()

        if text:
            return text

    return None
