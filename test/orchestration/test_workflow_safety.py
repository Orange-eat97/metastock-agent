from __future__ import annotations

from chat.models import ChatContext
from orchestration.context_resolver import (
    DecisionContextResolver,
)
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
)


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)


def resolve(
    *,
    message: str,
    workflow_name: str,
):
    return DecisionContextResolver().resolve(
        request=PlannerRequest(
            user_message=message,
            context=ChatContext(
                active_explorer_id=(
                    EXPLORER_ID
                )
            ),
            tools=[],
            available_workflows=[
                "run_explorer",
                "run_and_capture",
                "create_run_and_capture",
            ],
        ),
        decision=OrchestratorDecision(
            action="workflow",
            workflow_name=workflow_name,
            explorer_reference="current",
            decision_reason="Workflow.",
        ),
    )


def test_negated_run_is_blocked() -> None:
    result = resolve(
        message=(
            "Do not run this Explorer."
        ),
        workflow_name="run_explorer",
    )

    assert result.outcome == "clarify"


def test_capture_requires_explicit_result_intent() -> None:
    result = resolve(
        message="Run this Explorer.",
        workflow_name="run_and_capture",
    )

    assert result.outcome == "clarify"


def test_create_workflow_requires_explicit_create() -> None:
    result = resolve(
        message=(
            "Run this Explorer and capture "
            "the results."
        ),
        workflow_name=(
            "create_run_and_capture"
        ),
    )

    assert result.outcome == "clarify"


def test_explicit_create_run_capture_is_allowed() -> None:
    result = resolve(
        message=(
            "Create this Explorer in MetaStock, "
            "run it, and capture the results."
        ),
        workflow_name=(
            "create_run_and_capture"
        ),
    )

    assert result.outcome == "workflow"
    assert result.arguments[
        "explorer_id"
    ] == EXPLORER_ID
