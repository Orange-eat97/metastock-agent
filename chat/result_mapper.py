from __future__ import annotations

from typing import Any

from chat.models import ChatContext
from tools.tool_contracts import ToolResult


def update_context_from_tool_result(
    current: ChatContext,
    result: ToolResult,
) -> ChatContext:
    """
    Update context from documented ToolResult paths only.

    Failed, blocked, and not-implemented calls preserve the current context.
    This avoids replacing valid active IDs with attempted or partial values
    returned by unsuccessful side-effecting operations.
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

    active_service_log_id = (
        _first_non_empty_string(
            explorer_data.get(
                "service_log_id"
            ),
            data.get("service_log_id"),
            data.get("log_id"),
            current.active_service_log_id,
        )
    )

    return ChatContext(
        active_explorer_id=active_explorer_id,
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
