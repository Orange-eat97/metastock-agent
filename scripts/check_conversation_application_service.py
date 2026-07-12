from __future__ import annotations

import sys
from typing import Any
from uuid import UUID, uuid4

from chat.controller import ChatTurnController
from infrastructure.agent_state import (
    AgentStateDatabase,
    AgentStateDatabaseSettings,
    ConversationRepository,
    LangChainHistoryFactory,
    TurnStreamRepository,
)
from infrastructure.agent_state.tool_call_repository import (
    ToolCallRepository,
)
from services.conversation_application_service import (
    ConversationApplicationService,
)
from tools.tool_contracts import (
    ToolDisplay,
    ToolResult,
    ToolStatus,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        self.calls.append((name, arguments))

        if name == "generate_explorer":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="Explorer generated.",
                data={
                    "explorer": {
                        "explorer_id": (
                            "explorer-ms84"
                        ),
                        "service_log_id": (
                            "log-ms84"
                        ),
                    }
                },
                display=ToolDisplay(
                    title="Generated Explorer",
                    markdown=(
                        "The RSI Explorer was generated."
                    ),
                    severity="success",
                ),
            )

        if name == "get_explorer":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="Explorer loaded.",
                data={
                    "explorer": {
                        "explorer_id": (
                            arguments["explorer_id"]
                        ),
                        "service_log_id": (
                            "log-ms84"
                        ),
                    }
                },
                display=ToolDisplay(
                    title="Current Explorer",
                    markdown=(
                        "Here is the current Explorer."
                    ),
                    severity="info",
                ),
            )

        raise ValueError(
            f"Unexpected fake tool: {name}"
        )


def main() -> int:
    conversation_id: UUID | None = None

    try:
        settings = (
            AgentStateDatabaseSettings
            .from_environment()
        )

        registry = FakeRegistry()

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
            tool_calls = ToolCallRepository(
                database.pool
            )

            service = ConversationApplicationService(
                conversations=conversations,
                history=history,
                streams=streams,
                tool_calls=tool_calls,
                registry=registry,
                controller_factory=(
                    lambda wrapped_registry:
                    ChatTurnController(
                        wrapped_registry
                    )
                ),
            )

            conversation = (
                service.create_conversation(
                    "MS8.4 application-service test"
                )
            )
            conversation_id = (
                conversation.conversation_id
            )

            first_client_turn_id = uuid4()

            first = (
                service.execute_conversation_turn(
                    conversation_id=conversation_id,
                    client_turn_id=(
                        first_client_turn_id
                    ),
                    user_content=(
                        "Find stocks where RSI "
                        "is below 30"
                    ),
                )
            )

            assert first.replayed is False
            assert (
                first.context.active_explorer_id
                == "explorer-ms84"
            )

            first_calls = (
                service.get_tool_calls_for_turn(
                    first.stream_id
                )
            )

            assert len(first_calls) == 1
            assert (
                first_calls[0].tool_name
                == "generate_explorer"
            )

            second = (
                service.execute_conversation_turn(
                    conversation_id=conversation_id,
                    user_content=(
                        "Show the current Explorer"
                    ),
                )
            )

            assert (
                registry.calls[-1]
                == (
                    "get_explorer",
                    {
                        "explorer_id":
                        "explorer-ms84"
                    },
                )
            )

            assert (
                second.context.active_explorer_id
                == "explorer-ms84"
            )

            turns = (
                service.get_conversation_turns(
                    conversation_id
                )
            )

            assert len(turns) == 2
            assert (
                turns[0].user_content
                == (
                    "Find stocks where RSI "
                    "is below 30"
                )
            )
            assert (
                turns[1].user_content
                == "Show the current Explorer"
            )

            call_count_before_replay = len(
                registry.calls
            )

            replayed = (
                service.execute_conversation_turn(
                    conversation_id=conversation_id,
                    client_turn_id=(
                        first_client_turn_id
                    ),
                    user_content=(
                        "Find stocks where RSI "
                        "is below 30"
                    ),
                )
            )

            assert replayed.replayed is True
            assert (
                len(registry.calls)
                == call_count_before_replay
            )

            service.clear_conversation(
                conversation_id
            )

            assert (
                service.get_conversation_turns(
                    conversation_id
                )
                == []
            )

            assert (
                service.list_conversations(
                    limit=20
                )
            )

            deleted = (
                service.delete_conversation(
                    conversation_id
                )
            )
            assert deleted is True

            conversation_id = None

        print(
            "[PASSED] MS8.4 conversation "
            "application service"
        )
        print(
            "[PASSED] Completed turn persisted"
        )
        print(
            "[PASSED] Context restored across turns"
        )
        print(
            "[PASSED] Tool calls recorded"
        )
        print(
            "[PASSED] Completed retry is idempotent"
        )
        print(
            "[PASSED] Conversation turns loaded"
        )
        print(
            "[PASSED] Conversation cleared"
        )
        print(
            "[PASSED] Conversation deleted"
        )

        return 0

    except Exception as exc:
        print(
            f"[FAILED] MS8.4 check: {exc}",
            file=sys.stderr,
        )

        if conversation_id is not None:
            cleanup(conversation_id)

        return 1


def cleanup(conversation_id: UUID) -> None:
    try:
        settings = (
            AgentStateDatabaseSettings
            .from_environment()
        )

        with AgentStateDatabase(settings) as database:
            ConversationRepository(
                database.pool
            ).delete(conversation_id)

    except Exception as exc:
        print(
            f"[WARNING] Cleanup failed: {exc}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())