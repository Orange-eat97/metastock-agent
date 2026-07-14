from __future__ import annotations

from typing import Any, TypedDict


class GraphInputState(TypedDict):
    turn_input: dict[str, Any]


class GraphRuntimeContext(TypedDict):
    """Run-scoped data deliberately excluded from checkpointed state."""

    recent_messages: list[
        dict[str, Any]
    ]


class MetaStockGraphState(
    GraphInputState,
    total=False,
):
    # New production conversational path.
    conversation_request: dict[str, Any]
    conversation_response: dict[str, Any]

    # Legacy structured-planner compatibility path.
    planner_request: dict[str, Any]
    decision: dict[str, Any]

    # Shared validated execution path.
    resolution: dict[str, Any]
    tool_result: dict[str, Any]
    updated_context: dict[str, Any]

    workflow_plan: dict[str, Any]
    workflow_index: int
    workflow_results: list[
        dict[str, Any]
    ]
    workflow_context: dict[str, Any]
    workflow_complete: bool
    workflow_succeeded: bool
    workflow_failed_tool: str | None

    composed_response: str
    turn_output: dict[str, Any]


class GraphOutputState(TypedDict):
    turn_output: dict[str, Any]
