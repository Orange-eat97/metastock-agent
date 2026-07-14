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
    description: str = "tool"
    enabled: bool = True
    exposure: ToolExposure = ToolExposure.CONVERSATION


class Registry:
    def list_tools(self):
        names = [
            "generate_explorer",
            "repair_explorer",
            "revise_explorer",
            "get_explorer",
            "get_rag_log",
            "create_explorer_in_metastock",
            "select_explorer_in_metastock",
            "run_selected_explorer_in_metastock",
            "read_metastock_explorer_results",
            "get_explorer_result",
            "get_latest_explorer_result",
            "list_explorer_results",
        ]

        definitions = []

        for name in names:
            exposure = (
                ToolExposure.WORKFLOW_INTERNAL
                if name
                in {
                    "create_explorer_in_metastock",
                    "select_explorer_in_metastock",
                    "run_selected_explorer_in_metastock",
                    "read_metastock_explorer_results",
                }
                else ToolExposure.CONVERSATION
            )
            definitions.append(
                Definition(
                    name=name,
                    exposure=exposure,
                )
            )

        return definitions


def test_lifecycle_actions_collapse_to_one_semantic_command() -> None:
    names = {
        action.name
        for action in build_conversation_actions(
            Registry()
        )
    }

    assert COMMAND_ACTION_NAME in names
    assert "generate_explorer" not in names
    assert "revise_explorer" not in names
    assert "repair_explorer" not in names
    assert "run_explorer" not in names
    assert "run_and_capture" not in names
    assert "get_explorer" in names
    assert "get_latest_explorer_result" in names
