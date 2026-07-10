from __future__ import annotations

from typing import Any

from chat.models import ChatContext
from tools.tool_contracts import ToolResult


def update_context_from_tool_result(
    current: ChatContext,
    result: ToolResult,
) -> ChatContext:
    """
    Carry durable IDs returned by existing tools into the next local turn.

    Current tool payloads use:
      data.explorer.explorer_id
      data.explorer.service_log_id

    The top-level fallbacks make this tolerant of future DTO flattening.
    """
    data: dict[str, Any] = result.data or {}
    explorer = data.get("explorer")

    explorer_data = explorer if isinstance(explorer, dict) else {}

    active_explorer_id = _first_non_empty_string(
        explorer_data.get("explorer_id"),
        data.get("explorer_id"),
        current.active_explorer_id,
    )
    active_service_log_id = _first_non_empty_string(
        explorer_data.get("service_log_id"),
        data.get("service_log_id"),
        data.get("log_id"),
        current.active_service_log_id,
    )

    return ChatContext(
        active_explorer_id=active_explorer_id,
        active_service_log_id=active_service_log_id,
    )


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue

        text = str(value).strip()
        if text:
            return text

    return None
