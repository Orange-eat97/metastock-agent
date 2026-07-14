from __future__ import annotations

from orchestration.command_resolution import (
    NormalizedExplorerCommand,
)
from orchestration.workflows import (
    StaticWorkflowCatalog,
)


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)


def test_generate_create_run_capture_compiles_five_steps() -> None:
    command = NormalizedExplorerCommand(
        artifact_action="generate",
        resolved_instruction="Generate an RSI Explorer.",
        metastock_action="create_and_run",
        result_action="capture_new",
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

    assert [
        step.tool_name
        for step in plan.steps
    ] == [
        "generate_explorer",
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]
    assert plan.steps[0].explorer_source == "none"
    assert all(
        step.explorer_source == "active"
        for step in plan.steps[1:]
    )


def test_revision_run_compiles_create_before_select() -> None:
    command = NormalizedExplorerCommand(
        artifact_action="revise",
        explorer_reference="current",
        resolved_instruction=(
            "Change the RSI period from 14 to 7."
        ),
        metastock_action="create_and_run",
        result_action="none",
        instruments="all",
    )
    plan = StaticWorkflowCatalog().prepare(
        workflow_name=command.workflow_name,
        explorer_id=EXPLORER_ID,
        workflow_arguments={
            "command": command.model_dump(
                mode="json"
            )
        },
    )

    assert [
        step.tool_name
        for step in plan.steps
    ] == [
        "revise_explorer",
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
    ]
    assert plan.steps[0].explorer_source == "original"
    assert all(
        step.explorer_source == "active"
        for step in plan.steps[1:]
    )


def test_instruments_are_bound_to_metastock_steps() -> None:
    command = NormalizedExplorerCommand(
        artifact_action="none",
        metastock_action="create_and_run",
        result_action="none",
        instruments="DBS, OCBC",
    )
    plan = StaticWorkflowCatalog().prepare(
        workflow_name=command.workflow_name,
        explorer_id=EXPLORER_ID,
        workflow_arguments={
            "command": command.model_dump(
                mode="json"
            )
        },
    )

    assert plan.workflow_arguments[
        "instruments"
    ] == "DBS, OCBC"
    assert all(
        step.argument_bindings.get("instruments")
        == "instruments"
        for step in plan.steps
    )
