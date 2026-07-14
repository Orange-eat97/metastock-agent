from __future__ import annotations

import pytest

from chat.models import ChatContext
from orchestration.command_resolution import (
    CommandResolutionError,
    SemanticCommandResolver,
)


def resolve(
    message: str,
    **arguments,
):
    return SemanticCommandResolver().resolve(
        user_message=message,
        arguments={
            "artifact_action": "none",
            "metastock_action": "none",
            "result_action": "none",
            "instruments": "all",
            **arguments,
        },
        context=ChatContext(),
    )


def test_generate_defaults_to_metastock_creation() -> None:
    command = resolve(
        "Create an Explorer for RSI below 30.",
        artifact_action="generate",
        resolved_instruction=(
            "Find stocks where RSI(14) is below 30."
        ),
    )

    assert command.workflow_name == "generate_create"


def test_explicit_draft_does_not_create_in_metastock() -> None:
    command = resolve(
        "Draft an Explorer for review only.",
        artifact_action="generate",
        resolved_instruction=(
            "Find stocks where RSI(14) is below 30."
        ),
    )

    assert command.workflow_name == "generate_explorer"


def test_give_me_results_completes_run_dependency() -> None:
    command = resolve(
        "Run this Explorer and give me the results.",
        result_action="capture_new",
    )

    assert command.workflow_name == "run_and_capture"


def test_known_not_created_explorer_is_created_before_run() -> None:
    command = SemanticCommandResolver().resolve(
        user_message="Run this Explorer.",
        arguments={
            "artifact_action": "none",
            "metastock_action": "run",
            "result_action": "none",
            "instruments": "all",
        },
        context=ChatContext(
            active_explorer_metastock_state=(
                "not_created"
            )
        ),
    )

    assert command.workflow_name == "create_and_run"


def test_revision_run_requires_creation_of_new_version() -> None:
    command = resolve(
        "Change RSI from 14 to 7 and run it.",
        artifact_action="revise",
        resolved_instruction=(
            "Change the RSI period from 14 to 7."
        ),
        metastock_action="run",
    )

    assert command.workflow_name == "revise_create_run"
    assert command.resolved_instruction == (
        "Change the RSI period from 14 to 7."
    )


def test_create_without_running_is_not_rejected() -> None:
    command = resolve(
        "Create this Explorer in MetaStock without running it.",
        metastock_action="create",
    )

    assert command.workflow_name == "create_in_metastock"


def test_negated_run_is_rejected_only_when_run_selected() -> None:
    with pytest.raises(
        CommandResolutionError,
        match="not to run",
    ):
        resolve(
            "Do not run this Explorer.",
            metastock_action="run",
        )
