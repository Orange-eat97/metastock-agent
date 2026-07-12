from __future__ import annotations

import sys
from uuid import UUID, uuid4

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
)

from infrastructure.agent_state import (
    AgentStateDatabase,
    AgentStateDatabaseSettings,
    ConversationRepository,
    LangChainHistoryFactory,
    TurnStreamRepository,
    TurnStreamStatus,
)


def main() -> int:
    conversation_id: UUID | None = None

    try:
        settings = (
            AgentStateDatabaseSettings.from_environment()
        )

        with AgentStateDatabase(settings) as database:
            conversations = ConversationRepository(
                database.pool
            )
            history = LangChainHistoryFactory(
                database.pool
            )
            streams = TurnStreamRepository(
                database.pool
            )

            # ------------------------------------------------
            # Conversation repository
            # ------------------------------------------------

            conversation = conversations.create(
                "MS8.3 repository test"
            )
            conversation_id = conversation.conversation_id

            loaded_conversation = conversations.require(
                conversation_id
            )

            assert (
                loaded_conversation.title
                == "MS8.3 repository test"
            )

            renamed = conversations.rename(
                conversation_id,
                "MS8.3 renamed test",
            )

            assert renamed.title == "MS8.3 renamed test"

            recent = conversations.list_recent(limit=20)

            assert any(
                item.conversation_id == conversation_id
                for item in recent
            )

            # ------------------------------------------------
            # LangChain history
            # ------------------------------------------------

            history.add_messages(
                conversation_id,
                [
                    HumanMessage(
                        content="Create an RSI Explorer."
                    ),
                    AIMessage(
                        content=(
                            "I created an RSI Explorer."
                        )
                    ),
                ],
            )

            messages = history.get_messages(
                conversation_id
            )

            assert len(messages) == 2
            assert isinstance(messages[0], HumanMessage)
            assert isinstance(messages[1], AIMessage)

            assert (
                messages[0].content
                == "Create an RSI Explorer."
            )
            assert (
                messages[1].content
                == "I created an RSI Explorer."
            )

            history.clear(conversation_id)

            assert history.get_messages(
                conversation_id
            ) == []

            # ------------------------------------------------
            # Turn stream repository
            # ------------------------------------------------

            client_turn_id = uuid4()

            stream = streams.start(
                conversation_id=conversation_id,
                client_turn_id=client_turn_id,
                user_content="Run the Explorer.",
            )

            duplicate_start = streams.start(
                conversation_id=conversation_id,
                client_turn_id=client_turn_id,
                user_content="Run the Explorer.",
            )

            assert (
                duplicate_start.stream_id
                == stream.stream_id
            )

            first_append = streams.append_delta(
                stream_id=stream.stream_id,
                sequence=1,
                content_delta="Starting ",
            )

            assert first_append.applied is True
            assert (
                first_append.stream.assistant_content
                == "Starting "
            )

            second_append = streams.append_delta(
                stream_id=stream.stream_id,
                sequence=2,
                content_delta="MetaStock.",
            )

            assert second_append.applied is True
            assert (
                second_append.stream.assistant_content
                == "Starting MetaStock."
            )

            duplicate_append = streams.append_delta(
                stream_id=stream.stream_id,
                sequence=2,
                content_delta="MetaStock.",
            )

            assert duplicate_append.applied is False
            assert (
                duplicate_append.stream.assistant_content
                == "Starting MetaStock."
            )

            active = streams.get_active_for_conversation(
                conversation_id
            )

            assert active is not None
            assert active.stream_id == stream.stream_id

            completed = streams.complete(
                stream_id=stream.stream_id,
                final_content=(
                    "MetaStock exploration completed."
                ),
            )

            assert (
                completed.status
                == TurnStreamStatus.COMPLETED
            )
            assert (
                completed.assistant_content
                == "MetaStock exploration completed."
            )
            assert completed.completed_at is not None

            assert (
                streams.get_active_for_conversation(
                    conversation_id
                )
                is None
            )

            # ------------------------------------------------
            # Archive and restore
            # ------------------------------------------------

            archived = conversations.archive(
                conversation_id
            )
            assert archived.archived_at is not None

            active_conversations = (
                conversations.list_recent(limit=20)
            )

            assert all(
                item.conversation_id != conversation_id
                for item in active_conversations
            )

            restored = conversations.restore(
                conversation_id
            )
            assert restored.archived_at is None

            # ------------------------------------------------
            # Cascade deletion
            # ------------------------------------------------

            deleted = conversations.delete(
                conversation_id
            )
            assert deleted is True

            conversation_id = None

            assert conversations.get(
                restored.conversation_id
            ) is None

            assert streams.get(
                completed.stream_id
            ) is None

        print("[PASSED] MS8.3 repository integration")
        print("[PASSED] Conversation create/get/list")
        print("[PASSED] Conversation rename/archive/restore")
        print("[PASSED] LangChain history write/read/clear")
        print("[PASSED] Idempotent stream creation")
        print("[PASSED] Ordered partial-content append")
        print("[PASSED] Duplicate sequence rejection")
        print("[PASSED] Stream completion")
        print("[PASSED] Conversation cascade deletion")

        return 0

    except Exception as exc:
        print(
            f"[FAILED] MS8.3 repository check: {exc}",
            file=sys.stderr,
        )

        if conversation_id is not None:
            cleanup_conversation(conversation_id)

        return 1


def cleanup_conversation(
    conversation_id: UUID,
) -> None:
    """
    Best-effort cleanup if the integration check fails midway.
    """
    try:
        settings = (
            AgentStateDatabaseSettings.from_environment()
        )

        with AgentStateDatabase(settings) as database:
            repository = ConversationRepository(
                database.pool
            )
            repository.delete(conversation_id)

    except Exception as cleanup_error:
        print(
            "[WARNING] Could not clean up the test "
            f"conversation: {cleanup_error}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())