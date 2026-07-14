from __future__ import annotations

from dataclasses import dataclass

from chat.models import ChatContext
from orchestration.action_policy import ConversationActionPolicy
from orchestration.conversation_actions import (
    COMMAND_ACTION_NAME,
    ConversationActionCall,
    ConversationActionDefinition,
    ConversationModelRequest,
    ConversationModelResponse,
)
from tools.tool_registry import ToolExposure


EXPLORER_ID = (
    "11111111-1111-4111-8111-111111111111"
)


@dataclass
class Tool:
    name: str
    enabled: bool = True
    exposure: ToolExposure = ToolExposure.CONVERSATION


class Registry:
    def get_tool(self, name: str):
        return Tool(name=name)


def resolve(message: str, arguments: dict):
    action = ConversationActionDefinition(
        name=COMMAND_ACTION_NAME,
        description="command",
        kind="command",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )
    request = ConversationModelRequest(
        user_message=message,
        context=ChatContext(
            active_explorer_id=EXPLORER_ID
        ),
        actions=[action],
    )
    response = ConversationModelResponse(
        action_call=ConversationActionCall(
            name=COMMAND_ACTION_NAME,
            arguments=arguments,
        )
    )

    return ConversationActionPolicy(
        registry=Registry()
    ).resolve(
        request=request,
        response=response,
    )


def test_give_results_keeps_create_run_and_capture() -> None:
    result = resolve(
        (
            "Create this Explorer in MetaStock, run it, "
            "and give me the results."
        ),
        {
            "artifact_action": "none",
            "explorer_reference": "current",
            "metastock_action": "create_and_run",
            "result_action": "capture_new",
            "instruments": "all",
        },
    )

    assert result.outcome == "workflow"
    assert result.workflow_name == "create_run_and_capture"


def test_revision_forwards_resolved_instruction() -> None:
    result = resolve(
        "Okay, change it to 7 days instead.",
        {
            "artifact_action": "revise",
            "explorer_reference": "current",
            "resolved_instruction": (
                "Change the RSI period from 14 to 7."
            ),
            "metastock_action": "none",
            "result_action": "none",
            "instruments": "all",
        },
    )

    assert result.arguments["command"][
        "resolved_instruction"
    ] == "Change the RSI period from 14 to 7."
