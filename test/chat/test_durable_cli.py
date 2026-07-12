from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from chat.durable_cli import DurableChatCli
from chat.models import ChatContext
from chat.routes import ChatRoute
from infrastructure.agent_state.models import (
    ConversationRecord,
)
from services.conversation_models import (
    ConversationTurn,
    ExecuteConversationTurnResult,
)


NOW = datetime.now(timezone.utc)


class FakeConversationService:
    def __init__(self) -> None:
        self.conversations: dict[
            UUID,
            ConversationRecord,
        ] = {}

        self.turns: dict[
            UUID,
            list[ConversationTurn],
        ] = {}

        self.executed_messages: list[
            tuple[UUID, str]
        ] = []

        self.cleared: list[UUID] = []
        self.deleted: list[UUID] = []

    def create_conversation(
        self,
        title=None,
    ):
        conversation_id = uuid4()

        conversation = ConversationRecord(
            conversation_id=conversation_id,
            title=title,
            created_at=NOW,
            updated_at=NOW,
            archived_at=None,
        )

        self.conversations[
            conversation_id
        ] = conversation

        self.turns[conversation_id] = []

        return conversation

    def get_conversation(
        self,
        conversation_id,
    ):
        return self.conversations[
            conversation_id
        ]

    def list_conversations(
        self,
        *,
        limit=50,
        include_archived=False,
    ):
        del include_archived

        return list(
            self.conversations.values()
        )[:limit]

    def rename_conversation(
        self,
        conversation_id,
        title,
    ):
        current = self.conversations[
            conversation_id
        ]

        renamed = current.model_copy(
            update={"title": title}
        )

        self.conversations[
            conversation_id
        ] = renamed

        return renamed

    def get_conversation_turns(
        self,
        conversation_id,
    ):
        return list(
            self.turns[conversation_id]
        )

    def execute_conversation_turn(
        self,
        *,
        conversation_id,
        user_content,
        client_turn_id=None,
    ):
        del client_turn_id

        self.executed_messages.append(
            (
                conversation_id,
                user_content,
            )
        )

        stream_id = uuid4()
        turn_client_id = uuid4()

        context = ChatContext(
            active_explorer_id="explorer-test",
            active_service_log_id="log-test",
        )

        turn = ConversationTurn(
            user_content=user_content,
            assistant_content="Test response",
            route=ChatRoute.GENERATE_EXPLORER,
            context=context,
            stream_id=stream_id,
            tool_call_ids=[],
        )

        self.turns[
            conversation_id
        ].append(turn)

        return ExecuteConversationTurnResult(
            conversation_id=conversation_id,
            stream_id=stream_id,
            client_turn_id=turn_client_id,
            assistant_message="Test response",
            route=ChatRoute.GENERATE_EXPLORER,
            context=context,
            tool_result=None,
            replayed=False,
        )

    def clear_conversation(
        self,
        conversation_id,
    ):
        self.turns[conversation_id] = []
        self.cleared.append(conversation_id)

        return self.conversations[
            conversation_id
        ]

    def delete_conversation(
        self,
        conversation_id,
    ):
        self.conversations.pop(
            conversation_id,
            None,
        )

        self.turns.pop(
            conversation_id,
            None,
        )

        self.deleted.append(
            conversation_id
        )

        return True

    def get_active_partial_turn(
        self,
        conversation_id,
    ):
        del conversation_id
        return None


def test_requires_selected_conversation() -> None:
    service = FakeConversationService()
    output: list[str] = []

    cli = DurableChatCli(
        service=service,
        output=output.append,
    )

    cli.handle_line(
        "Find stocks where RSI is below 30"
    )

    assert service.executed_messages == []
    assert any(
        "No conversation is selected"
        in line
        for line in output
    )


def test_new_conversation_and_execute_turn() -> None:
    service = FakeConversationService()
    output: list[str] = []

    cli = DurableChatCli(
        service=service,
        output=output.append,
    )

    cli.handle_line(
        '/new "RSI research"'
    )

    conversation_id = (
        cli.active_conversation_id
    )

    assert conversation_id is not None

    assert (
        service.conversations[
            conversation_id
        ].title
        == "RSI research"
    )

    cli.handle_line(
        "Find stocks where RSI is below 30"
    )

    assert service.executed_messages == [
        (
            conversation_id,
            "Find stocks where RSI is below 30",
        )
    ]

    assert any(
        "Test response" in line
        for line in output
    )


def test_use_existing_conversation() -> None:
    service = FakeConversationService()
    conversation = (
        service.create_conversation(
            "Existing"
        )
    )

    output: list[str] = []

    cli = DurableChatCli(
        service=service,
        output=output.append,
    )

    cli.handle_line(
        f"/use {conversation.conversation_id}"
    )

    assert (
        cli.active_conversation_id
        == conversation.conversation_id
    )


def test_history_clear_and_delete() -> None:
    service = FakeConversationService()
    conversation = (
        service.create_conversation(
            "Lifecycle test"
        )
    )

    output: list[str] = []

    cli = DurableChatCli(
        service=service,
        active_conversation_id=(
            conversation.conversation_id
        ),
        output=output.append,
    )

    cli.handle_line("Create an Explorer")
    cli.handle_line("/history")

    assert any(
        "Create an Explorer" in line
        for line in output
    )

    cli.handle_line("/clear confirm")

    assert (
        conversation.conversation_id
        in service.cleared
    )

    assert (
        service.turns[
            conversation.conversation_id
        ]
        == []
    )

    cli.handle_line("/delete confirm")

    assert (
        conversation.conversation_id
        in service.deleted
    )

    assert (
        cli.active_conversation_id
        is None
    )