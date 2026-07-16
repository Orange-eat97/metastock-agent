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


def command_action() -> ConversationActionDefinition:
    return ConversationActionDefinition(
        name=COMMAND_ACTION_NAME,
        description="command",
        kind="command",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )


def test_no_action_is_normal_response() -> None:
    request = ConversationModelRequest(
        user_message="Why did you use RSI 14?",
        context=ChatContext(),
        actions=[],
    )
    response = ConversationModelResponse(
        assistant_message="It is the default period."
    )

    resolved = ConversationActionPolicy(
        registry=Registry()
    ).resolve(
        request=request,
        response=response,
    )

    assert resolved.outcome == "respond"
    assert resolved.message == "It is the default period."


def test_run_command_resolves_active_explorer() -> None:
    request = ConversationModelRequest(
        user_message="Run the Explorer as it is.",
        context=ChatContext(
            active_explorer_id=EXPLORER_ID
        ),
        actions=[command_action()],
    )
    response = ConversationModelResponse(
        action_call=ConversationActionCall(
            name=COMMAND_ACTION_NAME,
            arguments={
                "artifact_action": "none",
                "explorer_reference": "current",
                "metastock_action": "run",
                "result_action": "none",
                "instruments": "all",
            },
        )
    )

    resolved = ConversationActionPolicy(
        registry=Registry()
    ).resolve(
        request=request,
        response=response,
    )

    assert resolved.outcome == "workflow"
    assert resolved.workflow_name == "run_explorer"
    assert resolved.arguments["explorer_id"] == EXPLORER_ID


def test_generate_keeps_resolved_standalone_request() -> None:
    request = ConversationModelRequest(
        user_message="Create an RSI Explorer.",
        context=ChatContext(),
        actions=[command_action()],
    )
    response = ConversationModelResponse(
        action_call=ConversationActionCall(
            name=COMMAND_ACTION_NAME,
            arguments={
                "artifact_action": "generate",
                "resolved_instruction": (
                    "Find stocks where RSI(14) is below 30."
                ),
                "metastock_action": "create",
                "result_action": "none",
                "instruments": "all",
            },
        )
    )

    resolved = ConversationActionPolicy(
        registry=Registry()
    ).resolve(
        request=request,
        response=response,
    )

    assert resolved.workflow_name == "generate_create"
    assert resolved.arguments["command"][
        "resolved_instruction"
    ] == "Find stocks where RSI(14) is below 30."
