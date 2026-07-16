from __future__ import annotations

import pytest
from pydantic import ValidationError

from chat.routes import ChatRoute
from orchestration.workflows import (
    MAX_WORKFLOW_STEPS,
    StaticWorkflowCatalog,
    WorkflowPlan,
    WorkflowStep,
)


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)


def test_workflow_catalog_is_bounded() -> None:
    catalog = StaticWorkflowCatalog()

    for workflow_name in (
        catalog.list_workflows()
    ):
        plan = catalog.prepare(
            workflow_name=workflow_name,
            explorer_id=EXPLORER_ID,
        )

        assert 1 <= len(plan.steps) <= (
            MAX_WORKFLOW_STEPS
        )


def test_run_and_capture_order() -> None:
    plan = StaticWorkflowCatalog().prepare(
        workflow_name="run_and_capture",
        explorer_id=EXPLORER_ID,
    )

    assert plan.route is (
        ChatRoute.RUN_AND_READ_EXPLORER
    )
    assert [
        step.tool_name
        for step in plan.steps
    ] == [
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]


def test_model_rejects_more_than_maximum_steps() -> None:
    with pytest.raises(ValidationError):
        WorkflowPlan(
            workflow_name="too_long",
            route=ChatRoute.PLANNED_WORKFLOW,
            explorer_id=EXPLORER_ID,
            steps=[
                WorkflowStep(
                    tool_name=f"tool-{index}"
                )
                for index in range(
                    MAX_WORKFLOW_STEPS + 1
                )
            ],
        )
