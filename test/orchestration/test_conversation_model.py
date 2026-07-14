from __future__ import annotations

from types import SimpleNamespace

from chat.models import (
    ChatContext,
    PlannerConversationMessage,
)
from orchestration.conversation_actions import (
    COMMAND_ACTION_NAME,
    ConversationActionDefinition,
    ConversationModelRequest,
)
from orchestration.conversation_model import OpenAIConversationDriver


class FakeResponses:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response) -> None:
        self.responses = FakeResponses(response)


def request() -> ConversationModelRequest:
    return ConversationModelRequest(
        user_message="Run the Explorer as it is.",
        recent_messages=[
            PlannerConversationMessage(
                role="assistant",
                content=(
                    "The current Explorer uses RSI(14) < 30."
                ),
            )
        ],
        context=ChatContext(
            active_explorer_id=(
                "11111111-1111-4111-8111-111111111111"
            )
        ),
        actions=[
            ConversationActionDefinition(
                name=COMMAND_ACTION_NAME,
                description="Resolve lifecycle command.",
                kind="command",
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            )
        ],
    )


def test_plain_text_requires_no_action() -> None:
    client = FakeClient(
        SimpleNamespace(
            output_text="RSI(14) is the default period.",
            output=[],
        )
    )
    driver = OpenAIConversationDriver(client=client)

    result = driver.converse(request())

    assert result.assistant_message
    assert result.action_call is None
    assert client.responses.kwargs[
        "parallel_tool_calls"
    ] is False


def test_semantic_command_call_is_optional_metadata() -> None:
    arguments = (
        '{"artifact_action":"none",'
        '"metastock_action":"run",'
        '"result_action":"none",'
        '"explorer_reference":"current",'
        '"instruments":"all"}'
    )
    client = FakeClient(
        SimpleNamespace(
            output_text="",
            output=[
                SimpleNamespace(
                    type="function_call",
                    name=COMMAND_ACTION_NAME,
                    arguments=arguments,
                    call_id="call-1",
                )
            ],
        )
    )
    driver = OpenAIConversationDriver(client=client)

    result = driver.converse(request())

    assert result.action_call is not None
    assert result.action_call.name == COMMAND_ACTION_NAME
    assert result.action_call.arguments[
        "metastock_action"
    ] == "run"
