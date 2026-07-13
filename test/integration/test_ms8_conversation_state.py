from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from psycopg.rows import dict_row

from chat.controller import ChatTurnController
from chat.models import ChatTurnInput
from infrastructure.agent_state import (
    AgentStateDatabase,
    AgentStateDatabaseSettings,
    ConversationRepository,
    LangChainHistoryFactory,
    TurnStreamRepository,
)
from infrastructure.agent_state.models import ConversationRecord
from infrastructure.agent_state.tool_call_repository import ToolCallRepository
from services.conversation_application_service import ConversationApplicationService
from tools.tool_contracts import ToolDisplay, ToolResult, ToolStatus


pytestmark = pytest.mark.filterwarnings(
    "ignore:RunnableWithMessageHistory is deprecated.*"
)


@dataclass(frozen=True)
class StateHarness:
    database: AgentStateDatabase
    conversations: ConversationRepository
    history: LangChainHistoryFactory
    streams: TurnStreamRepository
    tool_calls: ToolCallRepository


class FakeRegistry:
    """
    Deterministic registry used by the MS8 persistence tests.

    It leaves the agent-state database real, while avoiding calls to RAG,
    MetaStock, or the production Explorer/result database.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append((name, arguments))

        if name != "generate_explorer":
            raise ValueError(f"Unexpected fake tool: {name}")

        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="Explorer generated.",
            data={
                "explorer": {
                    "explorer_id": f"explorer-test-{uuid4().hex[:12]}",
                    "service_log_id": f"log-test-{uuid4().hex[:12]}",
                }
            },
            display=ToolDisplay(
                title="Generated Explorer",
                markdown="The test Explorer was generated.",
                severity="success",
            ),
        )


class FailingController:
    def handle_turn(self, payload: ChatTurnInput) -> None:
        del payload
        raise RuntimeError("Deliberate controller failure.")


@pytest.fixture(scope="module")
def state_harness() -> Iterator[StateHarness]:
    settings = AgentStateDatabaseSettings.from_environment()

    with AgentStateDatabase(settings) as database:
        yield StateHarness(
            database=database,
            conversations=ConversationRepository(database.pool),
            history=LangChainHistoryFactory(database.pool),
            streams=TurnStreamRepository(database.pool),
            tool_calls=ToolCallRepository(database.pool),
        )


@pytest.fixture
def created_conversation_ids(
    state_harness: StateHarness,
) -> Iterator[list[UUID]]:
    conversation_ids: list[UUID] = []
    yield conversation_ids

    for conversation_id in conversation_ids:
        state_harness.conversations.delete(conversation_id)


def _create_conversation(
    harness: StateHarness,
    created_ids: list[UUID],
    title: str,
) -> ConversationRecord:
    conversation = harness.conversations.create(title)
    created_ids.append(conversation.conversation_id)
    return conversation


def _build_service(
    harness: StateHarness,
    *,
    registry: FakeRegistry | None = None,
    controller_factory: Callable[[Any], Any] | None = None,
) -> ConversationApplicationService:
    resolved_registry = registry or FakeRegistry()
    resolved_controller_factory = controller_factory or (
        lambda wrapped_registry: ChatTurnController(wrapped_registry)
    )

    return ConversationApplicationService(
        conversations=harness.conversations,
        history=harness.history,
        streams=harness.streams,
        tool_calls=harness.tool_calls,
        registry=resolved_registry,
        controller_factory=resolved_controller_factory,
    )


def _raw_messages(
    harness: StateHarness,
    conversation_id: UUID,
) -> list[dict[str, Any]]:
    with harness.database.pool.connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, message, created_at
                FROM public.chat_history
                WHERE session_id = %s
                ORDER BY id
                """,
                (conversation_id,),
            )
            rows = cursor.fetchall()
        connection.commit()

    return [dict(row) for row in rows]


def _raw_streams(
    harness: StateHarness,
    conversation_id: UUID,
) -> list[dict[str, Any]]:
    with harness.database.pool.connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    stream_id,
                    status,
                    error_code,
                    error_message,
                    completed_at
                FROM public.turn_streams
                WHERE conversation_id = %s
                ORDER BY started_at
                """,
                (conversation_id,),
            )
            rows = cursor.fetchall()
        connection.commit()

    return [dict(row) for row in rows]


def _row_counts(
    harness: StateHarness,
    conversation_id: UUID,
) -> dict[str, int]:
    with harness.database.pool.connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    (
                        SELECT count(*)
                        FROM public.conversations
                        WHERE conversation_id = %s
                    ) AS conversations,
                    (
                        SELECT count(*)
                        FROM public.chat_history
                        WHERE session_id = %s
                    ) AS chat_history,
                    (
                        SELECT count(*)
                        FROM public.turn_streams
                        WHERE conversation_id = %s
                    ) AS turn_streams,
                    (
                        SELECT count(*)
                        FROM public.tool_calls
                        WHERE conversation_id = %s
                    ) AS tool_calls
                """,
                (
                    conversation_id,
                    conversation_id,
                    conversation_id,
                    conversation_id,
                ),
            )
            row = cursor.fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Row-count query returned no result.")

    return {key: int(value) for key, value in row.items()}


def _raw_message_contents(
    harness: StateHarness,
    conversation_id: UUID,
) -> list[str]:
    return [
        str(row["message"]["data"]["content"])
        for row in _raw_messages(harness, conversation_id)
    ]


def test_completed_turn_stores_exactly_two_raw_messages(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    conversation = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 exactly-two-messages",
    )
    service = _build_service(state_harness)

    service.execute_conversation_turn(
        conversation_id=conversation.conversation_id,
        user_content="Find stocks where RSI is below 30",
    )

    rows = _raw_messages(state_harness, conversation.conversation_id)

    assert len(rows) == 2
    assert [row["message"]["type"] for row in rows] == ["human", "ai"]
    assert rows[0]["message"]["data"]["content"] == (
        "Find stocks where RSI is below 30"
    )
    assert rows[1]["message"]["data"]["content"] == (
        "The test Explorer was generated."
    )


def test_conversations_remain_isolated(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    first = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 isolation A",
    )
    second = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 isolation B",
    )
    service = _build_service(state_harness)

    first_query = "Find stocks where RSI is below 30"
    second_query = (
        "Find stocks where close is above the 50 day moving average"
    )

    service.execute_conversation_turn(
        conversation_id=first.conversation_id,
        user_content=first_query,
    )
    service.execute_conversation_turn(
        conversation_id=second.conversation_id,
        user_content=second_query,
    )

    first_contents = _raw_message_contents(
        state_harness,
        first.conversation_id,
    )
    second_contents = _raw_message_contents(
        state_harness,
        second.conversation_id,
    )

    assert first_contents == [
        first_query,
        "The test Explorer was generated.",
    ]
    assert second_contents == [
        second_query,
        "The test Explorer was generated.",
    ]
    assert second_query not in first_contents
    assert first_query not in second_contents


def test_controller_failure_stores_no_completed_messages(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    conversation = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 failure boundary",
    )
    service = _build_service(
        state_harness,
        controller_factory=lambda _: FailingController(),
    )

    with pytest.raises(
        RuntimeError,
        match="Deliberate controller failure",
    ):
        service.execute_conversation_turn(
            conversation_id=conversation.conversation_id,
            user_content="Find stocks where RSI is below 30",
        )

    assert _row_counts(
        state_harness,
        conversation.conversation_id,
    ) == {
        "conversations": 1,
        "chat_history": 0,
        "turn_streams": 1,
        "tool_calls": 0,
    }

    streams = _raw_streams(
        state_harness,
        conversation.conversation_id,
    )

    assert len(streams) == 1
    assert streams[0]["status"] == "failed"
    assert streams[0]["error_code"] == "RuntimeError"
    assert "Deliberate controller failure" in streams[0]["error_message"]
    assert streams[0]["completed_at"] is not None


def test_clear_one_conversation_leaves_another_untouched(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    first = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 clear A",
    )
    second = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 clear B",
    )
    service = _build_service(state_harness)

    service.execute_conversation_turn(
        conversation_id=first.conversation_id,
        user_content="Find stocks where RSI is below 30",
    )
    service.execute_conversation_turn(
        conversation_id=second.conversation_id,
        user_content="Find stocks where volume is above average",
    )

    service.clear_conversation(first.conversation_id)

    assert _row_counts(state_harness, first.conversation_id) == {
        "conversations": 1,
        "chat_history": 0,
        "turn_streams": 0,
        "tool_calls": 0,
    }
    assert _row_counts(state_harness, second.conversation_id) == {
        "conversations": 1,
        "chat_history": 2,
        "turn_streams": 1,
        "tool_calls": 1,
    }


def test_delete_conversation_cascades_to_all_state_rows(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    conversation = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 cascade delete",
    )
    service = _build_service(state_harness)

    service.execute_conversation_turn(
        conversation_id=conversation.conversation_id,
        user_content="Find stocks where RSI is below 30",
    )

    assert _row_counts(
        state_harness,
        conversation.conversation_id,
    ) == {
        "conversations": 1,
        "chat_history": 2,
        "turn_streams": 1,
        "tool_calls": 1,
    }

    assert service.delete_conversation(conversation.conversation_id) is True

    assert _row_counts(
        state_harness,
        conversation.conversation_id,
    ) == {
        "conversations": 0,
        "chat_history": 0,
        "turn_streams": 0,
        "tool_calls": 0,
    }


def test_completed_turn_advances_conversation_updated_at(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    conversation = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 updated-at",
    )
    service = _build_service(state_harness)
    before = conversation.updated_at

    # Avoid an equality caused by coarse timestamp display precision.
    time.sleep(0.05)

    service.execute_conversation_turn(
        conversation_id=conversation.conversation_id,
        user_content="Find stocks where RSI is below 30",
    )

    after = state_harness.conversations.require(
        conversation.conversation_id
    ).updated_at

    assert after > before


def test_stored_json_deserializes_to_langchain_messages(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    conversation = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 LangChain deserialization",
    )
    service = _build_service(state_harness)

    result = service.execute_conversation_turn(
        conversation_id=conversation.conversation_id,
        user_content="Find stocks where RSI is below 30",
    )

    messages = state_harness.history.get_messages(
        conversation.conversation_id
    )

    assert len(messages) == 2
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert messages[0].content == "Find stocks where RSI is below 30"
    assert messages[1].content == "The test Explorer was generated."

    human_metadata = messages[0].additional_kwargs["metastock_agent"]
    ai_metadata = messages[1].additional_kwargs["metastock_agent"]

    assert human_metadata["stream_id"] == str(result.stream_id)
    assert ai_metadata["stream_id"] == str(result.stream_id)
    assert ai_metadata["route"] == "generate_explorer"
    assert (
        ai_metadata["context"]["active_explorer_id"]
        == result.context.active_explorer_id
    )
    assert len(ai_metadata["tool_call_ids"]) == 1


def test_history_factory_works_with_runnable_with_message_history(
    state_harness: StateHarness,
    created_conversation_ids: list[UUID],
) -> None:
    conversation = _create_conversation(
        state_harness,
        created_conversation_ids,
        "MS8.7 RunnableWithMessageHistory",
    )

    def respond(messages: list[Any]) -> AIMessage:
        human_contents = [
            str(message.content)
            for message in messages
            if isinstance(message, HumanMessage)
        ]
        return AIMessage(
            content="heard: " + " | ".join(human_contents)
        )

    runnable = RunnableLambda(respond)

    with state_harness.history.open(
        conversation.conversation_id
    ) as postgres_history:
        with_history = RunnableWithMessageHistory(
            runnable,
            lambda session_id: postgres_history,
        )
        config = {
            "configurable": {
                "session_id": str(conversation.conversation_id)
            }
        }

        first = with_history.invoke(
            [HumanMessage(content="first")],
            config,
        )
        second = with_history.invoke(
            [HumanMessage(content="second")],
            config,
        )

    assert isinstance(first, AIMessage)
    assert isinstance(second, AIMessage)
    assert first.content == "heard: first"
    assert second.content == "heard: first | second"

    messages = state_harness.history.get_messages(
        conversation.conversation_id
    )

    assert [type(message) for message in messages] == [
        HumanMessage,
        AIMessage,
        HumanMessage,
        AIMessage,
    ]
    assert [message.content for message in messages] == [
        "first",
        "heard: first",
        "second",
        "heard: first | second",
    ]
