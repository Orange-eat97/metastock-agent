from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestration.decisions import (
    OrchestratorDecision,
)


def test_single_tool_requires_tool_name() -> None:
    with pytest.raises(ValidationError):
        OrchestratorDecision(
            action="single_tool",
            decision_reason="Route.",
        )


def test_clarify_requires_message() -> None:
    with pytest.raises(ValidationError):
        OrchestratorDecision(
            action="clarify",
            decision_reason="Ambiguous.",
        )


def test_workflow_rejects_tool_name() -> None:
    with pytest.raises(ValidationError):
        OrchestratorDecision(
            action="workflow",
            workflow_name="run_explorer",
            tool_name="get_explorer",
            decision_reason="Route.",
        )


def test_valid_single_tool_decision() -> None:
    decision = OrchestratorDecision(
        action="single_tool",
        tool_name="get_explorer",
        explorer_reference="Current",
        decision_reason=(
            "The user asked to inspect "
            "the active Explorer."
        ),
    )

    assert decision.tool_name == (
        "get_explorer"
    )
