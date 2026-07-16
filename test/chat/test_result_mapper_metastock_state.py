from __future__ import annotations

from chat.models import ChatContext
from chat.result_mapper import (
    update_context_from_tool_result,
)
from tools.tool_contracts import (
    ToolResult,
    ToolStatus,
)


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)


def success(
    tool_name: str,
    data: dict,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        ok=True,
        status=ToolStatus.SUCCESS,
        message="ok",
        data=data,
    )


def test_generation_marks_new_explorer_not_created() -> None:
    context = update_context_from_tool_result(
        ChatContext(),
        success(
            "generate_explorer",
            {
                "explorer": {
                    "explorer_id": EXPLORER_ID,
                }
            },
        ),
    )

    assert context.active_explorer_id == EXPLORER_ID
    assert (
        context.active_explorer_metastock_state
        == "not_created"
    )


def test_successful_create_marks_active_explorer_created() -> None:
    context = update_context_from_tool_result(
        ChatContext(
            active_explorer_id=EXPLORER_ID,
            active_explorer_metastock_state=(
                "not_created"
            ),
        ),
        success(
            "create_explorer_in_metastock",
            {"explorer_id": EXPLORER_ID},
        ),
    )

    assert (
        context.active_explorer_metastock_state
        == "created"
    )
