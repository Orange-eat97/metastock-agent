from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest

from mcp_adapters.agent_gateway import AgentGateway


class FakeModel:
    def __init__(self, **value):
        self.value = value

    def model_dump(self, mode="json"):
        return self.value


class FakeService:
    def __init__(self):
        self.conversation_id = uuid4()
        self.calls = []

    def create_conversation(self, title):
        return FakeModel(conversation_id=str(self.conversation_id), title=title)

    def get_conversation(self, conversation_id):
        assert conversation_id == self.conversation_id
        return FakeModel(conversation_id=str(conversation_id))

    def get_conversation_turns(self, conversation_id):
        assert conversation_id == self.conversation_id
        return [FakeModel(user_content="hello", assistant_content="hi")]

    def execute_conversation_turn(self, **kwargs):
        self.calls.append(kwargs)
        return FakeModel(assistant_message="hi", replayed=False)


def test_transport_does_not_choose_tools():
    service = FakeService()
    gateway = AgentGateway(service)
    cid = str(service.conversation_id)
    turn_id = str(uuid4())
    assert gateway.create_conversation("Test")["title"] == "Test"
    assert gateway.get_history(cid)["turns"][0]["assistant_content"] == "hi"
    assert gateway.chat(cid, "hello", turn_id)["assistant_message"] == "hi"
    assert service.calls == [{
        "conversation_id": UUID(cid),
        "user_content": "hello",
        "client_turn_id": UUID(turn_id),
    }]


def test_blank_message_rejected():
    with pytest.raises(ValueError):
        AgentGateway(FakeService()).chat(str(uuid4()), "   ")
