from __future__ import annotations

import sys
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_postgres import PostgresChatMessageHistory

from infrastructure.agent_state.database import (
    AgentStateDatabase,
    AgentStateDatabaseSettings,
)


CHAT_HISTORY_TABLE = "chat_history"


def main() -> int:
    conversation_id = uuid4()
    client_turn_id = uuid4()

    try:
        settings = (
            AgentStateDatabaseSettings.from_environment()
        )

        with AgentStateDatabase(settings) as database:
            with database.pool.connection() as connection:
                create_conversation(
                    connection=connection,
                    conversation_id=conversation_id,
                )

                verify_langchain_history(
                    connection=connection,
                    conversation_id=conversation_id,
                )

                stream_id = verify_stream_storage(
                    connection=connection,
                    conversation_id=conversation_id,
                    client_turn_id=client_turn_id,
                )

                verify_tool_call_storage(
                    connection=connection,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                )

                verify_clear_history(
                    connection=connection,
                    conversation_id=conversation_id,
                )

                delete_conversation(
                    connection=connection,
                    conversation_id=conversation_id,
                )

                verify_cascade_delete(
                    connection=connection,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                )

        print("[PASSED] Agent-state schema integration")
        print("[PASSED] Conversation creation")
        print("[PASSED] LangChain message write/read")
        print("[PASSED] Partial stream persistence")
        print("[PASSED] Tool-call persistence")
        print("[PASSED] Message-history clear")
        print("[PASSED] Conversation cascade delete")

        return 0

    except Exception as exc:
        print(
            f"[FAILED] Agent-state schema check: {exc}",
            file=sys.stderr,
        )
        return 1


def create_conversation(
    *,
    connection,
    conversation_id: UUID,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.conversations (
                conversation_id,
                title
            )
            VALUES (%s, %s)
            """,
            (
                conversation_id,
                "MS8 schema integration test",
            ),
        )

    connection.commit()


def verify_langchain_history(
    *,
    connection,
    conversation_id: UUID,
) -> None:
    history = PostgresChatMessageHistory(
        CHAT_HISTORY_TABLE,
        str(conversation_id),
        sync_connection=connection,
    )

    history.add_messages(
        [
            HumanMessage(
                content="Create an RSI Explorer."
            ),
            AIMessage(
                content="The Explorer has been created."
            ),
        ]
    )

    messages = history.get_messages()

    if len(messages) != 2:
        raise AssertionError(
            f"Expected 2 messages, got {len(messages)}."
        )

    if not isinstance(messages[0], HumanMessage):
        raise AssertionError(
            "First message was not a HumanMessage."
        )

    if not isinstance(messages[1], AIMessage):
        raise AssertionError(
            "Second message was not an AIMessage."
        )

    if messages[0].content != "Create an RSI Explorer.":
        raise AssertionError(
            "Human message content did not round-trip."
        )

    if (
        messages[1].content
        != "The Explorer has been created."
    ):
        raise AssertionError(
            "AI message content did not round-trip."
        )


def verify_stream_storage(
    *,
    connection,
    conversation_id: UUID,
    client_turn_id: UUID,
) -> UUID:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.turn_streams (
                conversation_id,
                client_turn_id,
                user_content,
                assistant_content,
                last_sequence
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING stream_id
            """,
            (
                conversation_id,
                client_turn_id,
                "Run the Explorer.",
                "Starting Meta",
                1,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            raise AssertionError(
                "Stream insert returned no stream ID."
            )

        stream_id = row[0]

        cursor.execute(
            """
            UPDATE public.turn_streams
            SET
                assistant_content = %s,
                last_sequence = %s
            WHERE stream_id = %s
            """,
            (
                "Starting MetaStock exploration.",
                2,
                stream_id,
            ),
        )

        cursor.execute(
            """
            SELECT
                assistant_content,
                last_sequence,
                status
            FROM public.turn_streams
            WHERE stream_id = %s
            """,
            (stream_id,),
        )

        stream = cursor.fetchone()

    connection.commit()

    if stream is None:
        raise AssertionError(
            "Stored stream could not be loaded."
        )

    if stream[0] != "Starting MetaStock exploration.":
        raise AssertionError(
            "Partial assistant content was not updated."
        )

    if stream[1] != 2:
        raise AssertionError(
            "Stream sequence was not updated."
        )

    if stream[2] != "streaming":
        raise AssertionError(
            "Unexpected stream status."
        )

    return stream_id


def verify_tool_call_storage(
    *,
    connection,
    conversation_id: UUID,
    stream_id: UUID,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO public.tool_calls (
                conversation_id,
                stream_id,
                provider_call_id,
                ordinal,
                tool_name,
                arguments_json
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s::jsonb
            )
            """,
            (
                conversation_id,
                stream_id,
                "provider-call-test-1",
                0,
                "generate_explorer",
                '{"user_query": "RSI below 30"}',
            ),
        )

        cursor.execute(
            """
            SELECT
                tool_name,
                status
            FROM public.tool_calls
            WHERE stream_id = %s
            """,
            (stream_id,),
        )

        tool_call = cursor.fetchone()

    connection.commit()

    if tool_call is None:
        raise AssertionError(
            "Stored tool call could not be loaded."
        )

    if tool_call[0] != "generate_explorer":
        raise AssertionError(
            "Tool name did not round-trip."
        )

    if tool_call[1] != "running":
        raise AssertionError(
            "Unexpected tool-call status."
        )


def verify_clear_history(
    *,
    connection,
    conversation_id: UUID,
) -> None:
    history = PostgresChatMessageHistory(
        CHAT_HISTORY_TABLE,
        str(conversation_id),
        sync_connection=connection,
    )

    history.clear()

    if history.get_messages():
        raise AssertionError(
            "Chat history was not cleared."
        )


def delete_conversation(
    *,
    connection,
    conversation_id: UUID,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM public.conversations
            WHERE conversation_id = %s
            """,
            (conversation_id,),
        )

    connection.commit()


def verify_cascade_delete(
    *,
    connection,
    conversation_id: UUID,
    stream_id: UUID,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM public.turn_streams
            WHERE conversation_id = %s
            """,
            (conversation_id,),
        )

        stream_count = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT count(*)
            FROM public.tool_calls
            WHERE stream_id = %s
            """,
            (stream_id,),
        )

        tool_call_count = cursor.fetchone()[0]

    if stream_count != 0:
        raise AssertionError(
            "Turn streams did not cascade-delete."
        )

    if tool_call_count != 0:
        raise AssertionError(
            "Tool calls did not cascade-delete."
        )


if __name__ == "__main__":
    raise SystemExit(main())