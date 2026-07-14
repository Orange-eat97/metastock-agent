from __future__ import annotations

from chat.models import ChatContext
from chat.result_mapper import (
    update_context_from_tool_result,
)
from tools.tool_contracts import (
    ToolResult,
    ToolStatus,
)


def test_top_level_result_id_becomes_active() -> None:
    result = ToolResult(
        tool_name=(
            "read_metastock_explorer_results"
        ),
        ok=True,
        status=ToolStatus.SUCCESS,
        message="stored",
        data={
            "explorer_id": "explorer-1",
            "result_id": "result-1",
        },
    )

    context = update_context_from_tool_result(
        ChatContext(),
        result,
    )

    assert context.active_explorer_id == (
        "explorer-1"
    )
    assert context.active_result_id == (
        "result-1"
    )


def test_nested_result_id_becomes_active() -> None:
    result = ToolResult(
        tool_name="get_explorer_result",
        ok=True,
        status=ToolStatus.SUCCESS,
        message="loaded",
        data={
            "result": {
                "explorer_id": "explorer-2",
                "result_id": "result-2",
            }
        },
    )

    context = update_context_from_tool_result(
        ChatContext(),
        result,
    )

    assert context.active_explorer_id == (
        "explorer-2"
    )
    assert context.active_result_id == (
        "result-2"
    )


def test_failed_result_preserves_context() -> None:
    current = ChatContext(
        active_explorer_id="explorer-old",
        active_result_id="result-old",
        active_service_log_id="log-old",
    )

    result = ToolResult(
        tool_name="get_explorer_result",
        ok=False,
        status=ToolStatus.FAILED,
        message="failed",
        data={
            "result_id": "result-attempted"
        },
    )

    assert update_context_from_tool_result(
        current,
        result,
    ) == current
