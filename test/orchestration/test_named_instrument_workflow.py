from __future__ import annotations

from chat.models import ChatContext
from orchestration.command_resolution import SemanticCommandResolver
from orchestration.workflows import StaticWorkflowCatalog


def test_named_instruments_survive_command_and_workflow() -> None:
    command = SemanticCommandResolver().resolve(
        user_message=(
            "Run the current Explorer on SGX Mainboard "
            "and My Momentum List."
        ),
        arguments={
            "artifact_action": "none",
            "metastock_action": "run",
            "result_action": "none",
            "instruments": "SGX Mainboard, My Momentum List",
        },
        context=ChatContext(),
    )

    assert command.instruments == "SGX Mainboard, My Momentum List"

    plan = StaticWorkflowCatalog().prepare(
        workflow_name=command.workflow_name,
        explorer_id="11111111-1111-4111-8111-111111111111",
        workflow_arguments={
            "command": command.model_dump(mode="json")
        },
    )

    assert plan.workflow_arguments["instruments"] == (
        "SGX Mainboard, My Momentum List"
    )

    metastock_steps = [
        step
        for step in plan.steps
        if step.tool_name in {
            "select_explorer_in_metastock",
            "run_selected_explorer_in_metastock",
        }
    ]

    assert [step.tool_name for step in metastock_steps] == [
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
    ]
    assert all(
        step.argument_bindings == {"instruments": "instruments"}
        for step in metastock_steps
    )
