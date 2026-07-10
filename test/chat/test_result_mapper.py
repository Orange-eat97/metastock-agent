from __future__ import annotations

from chat.models import ChatContext
from chat.result_mapper import update_context_from_tool_result
from tools.tool_contracts import ToolResult, ToolStatus


def test_updates_nested_explorer_ids() -> None:
    result = ToolResult(
        tool_name="generate_explorer",
        ok=True,
        status=ToolStatus.SUCCESS,
        message="ok",
        data={
            "explorer": {
                "explorer_id": "explorer-2",
                "service_log_id": "log-2",
            }
        },
    )

    context = update_context_from_tool_result(
        ChatContext(
            active_explorer_id="explorer-1",
            active_service_log_id="log-1",
        ),
        result,
    )

    assert context.active_explorer_id == "explorer-2"
    assert context.active_service_log_id == "log-2"


def test_preserves_existing_ids_when_result_has_none() -> None:
    context = update_context_from_tool_result(
        ChatContext(
            active_explorer_id="explorer-1",
            active_service_log_id="log-1",
        ),
        ToolResult(
            tool_name="run_explorer_in_metastock",
            ok=False,
            status=ToolStatus.BLOCKED,
            message="blocked",
        ),
    )

    assert context.active_explorer_id == "explorer-1"
    assert context.active_service_log_id == "log-1"
