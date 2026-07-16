from __future__ import annotations

from orchestration.command_resolution import (
    NormalizedExplorerCommand,
)
from orchestration.conversation_workflow_nodes import (
    ExecuteConversationWorkflowStepNode,
)
from orchestration.registry_executor import (
    RegistryToolExecutor,
)
from orchestration.workflows import (
    StaticWorkflowCatalog,
)
from tools.tool_contracts import (
    ToolResult,
    ToolStatus,
)


NEW_ID = (
    "22222222-2222-4222-8222-222222222222"
)


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict]
        ] = []

    def execute(self, name, arguments):
        self.calls.append(
            (name, dict(arguments))
        )

        if name == "generate_explorer":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="generated",
                data={
                    "explorer": {
                        "explorer_id": NEW_ID,
                    }
                },
            )

        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="ok",
            data={
                "explorer_id": arguments[
                    "explorer_id"
                ]
            },
        )


def test_generated_id_is_used_by_every_metastock_step() -> None:
    command = NormalizedExplorerCommand(
        artifact_action="generate",
        resolved_instruction="Generate an RSI Explorer.",
        metastock_action="create_and_run",
        result_action="none",
        instruments="all",
    )
    plan = StaticWorkflowCatalog().prepare(
        workflow_name=command.workflow_name,
        workflow_arguments={
            "command": command.model_dump(
                mode="json"
            )
        },
    )
    registry = FakeRegistry()
    node = ExecuteConversationWorkflowStepNode(
        RegistryToolExecutor(registry)
    )
    state = {
        "workflow_plan": plan.model_dump(
            mode="json"
        ),
        "workflow_index": 0,
        "workflow_results": [],
        "workflow_context": {},
    }

    for _ in plan.steps:
        state.update(node(state))

    assert registry.calls[0] == (
        "generate_explorer",
        {
            "user_query": (
                "Generate an RSI Explorer."
            )
        },
    )

    for _, arguments in registry.calls[1:]:
        assert arguments["explorer_id"] == NEW_ID
        assert arguments["instruments"] == "all"

    assert state["workflow_succeeded"] is True
    assert state["workflow_context"][
        "active_explorer_metastock_state"
    ] == "created"
