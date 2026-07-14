from __future__ import annotations

from orchestration.command_resolution import NormalizedExplorerCommand
from orchestration.conversation_workflow_nodes import (
    ExecuteConversationWorkflowStepNode,
)
from orchestration.registry_executor import RegistryToolExecutor
from orchestration.workflows import StaticWorkflowCatalog
from tools.tool_contracts import ToolResult, ToolStatus


ORIGINAL_ID = (
    "11111111-1111-4111-8111-111111111111"
)
REVISED_ID = (
    "22222222-2222-4222-8222-222222222222"
)


class FakeRegistry:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))

        if name == "revise_explorer":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="revised",
                data={
                    "explorer": {
                        "explorer_id": REVISED_ID,
                    }
                },
            )

        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="ok",
            data={
                "explorer_id": arguments["explorer_id"]
            },
        )


def test_revise_run_creates_and_uses_new_explorer_id() -> None:
    command = NormalizedExplorerCommand(
        artifact_action="revise",
        resolved_instruction=(
            "Change the RSI threshold from 30 to 25."
        ),
        metastock_action="create_and_run",
        result_action="none",
        instruments="all",
    )
    plan = StaticWorkflowCatalog().prepare(
        workflow_name=command.workflow_name,
        explorer_id=ORIGINAL_ID,
        workflow_arguments={
            "command": command.model_dump(mode="json")
        },
    )
    registry = FakeRegistry()
    node = ExecuteConversationWorkflowStepNode(
        RegistryToolExecutor(registry)
    )
    state = {
        "workflow_plan": plan.model_dump(mode="json"),
        "workflow_index": 0,
        "workflow_results": [],
        "workflow_context": {
            "active_explorer_id": ORIGINAL_ID
        },
    }

    for _ in plan.steps:
        state.update(node(state))

    assert registry.calls[0][0] == "revise_explorer"
    assert registry.calls[0][1][
        "explorer_id"
    ] == ORIGINAL_ID
    assert registry.calls[0][1][
        "revision_instruction"
    ] == "Change the RSI threshold from 30 to 25."

    assert [
        name
        for name, _ in registry.calls[1:]
    ] == [
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
    ]

    for _, arguments in registry.calls[1:]:
        assert arguments["explorer_id"] == REVISED_ID

    assert state["workflow_succeeded"] is True
