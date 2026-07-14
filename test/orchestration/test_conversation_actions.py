from __future__ import annotations

from dataclasses import dataclass

from orchestration.conversation_actions import (
    COMMAND_ACTION_NAME,
    build_conversation_actions,
)
from tools.tool_registry import ToolExposure


@dataclass
class Definition:
    name: str
    description: str
    enabled: bool
    exposure: ToolExposure


class Registry:
    def list_tools(self):
        return [
            Definition(
                name="generate_explorer",
                description="Generate.",
                enabled=True,
                exposure=ToolExposure.CONVERSATION,
            ),
            Definition(
                name="revise_explorer",
                description="Revise.",
                enabled=True,
                exposure=ToolExposure.CONVERSATION,
            ),
            Definition(
                name="get_explorer",
                description="Get.",
                enabled=True,
                exposure=ToolExposure.CONVERSATION,
            ),
            Definition(
                name="create_explorer_in_metastock",
                description="Internal.",
                enabled=True,
                exposure=ToolExposure.WORKFLOW_INTERNAL,
            ),
            Definition(
                name="select_explorer_in_metastock",
                description="Internal.",
                enabled=True,
                exposure=ToolExposure.WORKFLOW_INTERNAL,
            ),
            Definition(
                name="run_selected_explorer_in_metastock",
                description="Internal.",
                enabled=True,
                exposure=ToolExposure.WORKFLOW_INTERNAL,
            ),
        ]


def test_model_sees_one_lifecycle_command_and_read_tools() -> None:
    actions = build_conversation_actions(Registry())
    names = {action.name for action in actions}

    assert COMMAND_ACTION_NAME in names
    assert "generate_explorer" not in names
    assert "revise_explorer" not in names
    assert "create_explorer_in_metastock" not in names
    assert "run_explorer" not in names
    assert "get_explorer" in names
