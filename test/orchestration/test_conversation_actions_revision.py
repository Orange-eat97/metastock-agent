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
    def __init__(self, revise_enabled: bool):
        self.revise_enabled = revise_enabled

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
                enabled=self.revise_enabled,
                exposure=ToolExposure.CONVERSATION,
            ),
        ]


def artifact_enum(revise_enabled: bool) -> list[str]:
    actions = build_conversation_actions(
        Registry(revise_enabled)
    )
    command = next(
        action
        for action in actions
        if action.name == COMMAND_ACTION_NAME
    )
    return command.parameters["properties"][
        "artifact_action"
    ]["enum"]


def test_revision_enum_requires_enabled_revision_tool() -> None:
    assert "revise" not in artifact_enum(False)
    assert "revise" in artifact_enum(True)
