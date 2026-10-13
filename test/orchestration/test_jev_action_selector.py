from chat.models import ChatContext
from orchestration.conversation_actions import (
    ConversationActionDefinition, ConversationModelRequest, ConversationModelResponse,
)
from orchestration.jev_action_selector import JevChoiceConversationDriver, JevDecision


class FakeDriver:
    def __init__(self):
        self.requests = []

    def converse(self, request):
        self.requests.append(request)
        return ConversationModelResponse(assistant_message="okay")


class FakeSelector:
    def __init__(self, name, confidence=0.99):
        self.name, self.confidence = name, confidence

    def choose(self, request):
        return JevDecision(choice=self.name, confidence=self.confidence)


def _request():
    return ConversationModelRequest(
        user_message="show my current explorer",
        context=ChatContext(),
        actions=[
            ConversationActionDefinition(name="get_explorer", description="Read", kind="tool", parameters={"type": "object"}),
            ConversationActionDefinition(name="execute_explorer_command", description="Command", kind="command", parameters={"type": "object"}),
        ],
    )


def test_jev_limits_only_tool_catalogue_not_argument_generation():
    underlying = FakeDriver()
    JevChoiceConversationDriver(underlying, FakeSelector("get_explorer")).converse(_request())
    assert [a.name for a in underlying.requests[0].actions] == ["get_explorer"]


def test_fallback_preserves_original_actions():
    underlying = FakeDriver()
    JevChoiceConversationDriver(underlying, FakeSelector("get_explorer", 0.2)).converse(_request())
    assert len(underlying.requests[0].actions) == 2


def test_no_action_blocks_tools():
    underlying = FakeDriver()
    JevChoiceConversationDriver(underlying, FakeSelector("__no_action__")).converse(_request())
    assert underlying.requests[0].actions == []


def test_unknown_choice_defers_to_original_driver():
    underlying = FakeDriver()
    JevChoiceConversationDriver(underlying, FakeSelector("invented_tool")).converse(_request())
    assert len(underlying.requests[0].actions) == 2
