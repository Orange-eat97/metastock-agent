from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID, uuid4

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
)

from chat.models import (
    ChatTurnInput,
    ChatTurnOutput,
)
from infrastructure.agent_state.conversation_repository import (
    ConversationRepository,
)
from infrastructure.agent_state.history_factory import (
    LangChainHistoryFactory,
)
from infrastructure.agent_state.models import (
    ConversationRecord,
    ToolCallRecord,
    TurnStreamRecord,
    TurnStreamStatus,
)
from infrastructure.agent_state.tool_call_repository import (
    ToolCallRepository,
)
from infrastructure.agent_state.turn_stream_repository import (
    TurnStreamRepository,
)
from services.conversation_context_resolver import (
    METASTOCK_METADATA_KEY,
    ConversationContextResolver,
)
from services.conversation_models import (
    ConversationTurn,
    ExecuteConversationTurnResult,
)
from services.recording_tool_registry import (
    RecordingToolRegistry,
    ToolRegistryProtocol,
)
from tools.tool_contracts import ToolResult


class ChatControllerProtocol(Protocol):
    def handle_turn(
        self,
        payload: ChatTurnInput,
    ) -> ChatTurnOutput:
        ...


ControllerFactory = Callable[
    [ToolRegistryProtocol],
    ChatControllerProtocol,
]


class TurnAlreadyInProgressError(RuntimeError):
    """
    Raised when the same client turn is already being processed.

    The service does not automatically rerun it because a prior
    attempt may already have caused an external side effect.
    """


class TurnCannotResumeError(RuntimeError):
    """Raised when a terminal non-completed turn is reused."""


class ConversationApplicationService:
    """
    Coordinates durable conversation turns.

    This service owns persistence sequencing but does not contain
    routing, Explorer logic, RAG logic, or MetaStock automation.
    """

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        history: LangChainHistoryFactory,
        streams: TurnStreamRepository,
        tool_calls: ToolCallRepository,
        registry: ToolRegistryProtocol,
        controller_factory: ControllerFactory,
        context_resolver: (
            ConversationContextResolver | None
        ) = None,
    ) -> None:
        self._conversations = conversations
        self._history = history
        self._streams = streams
        self._tool_calls = tool_calls
        self._registry = registry
        self._controller_factory = controller_factory
        self._context_resolver = (
            context_resolver
            or ConversationContextResolver()
        )

    # --------------------------------------------------------
    # Conversation registry operations
    # --------------------------------------------------------

    def create_conversation(
        self,
        title: str | None = None,
    ) -> ConversationRecord:
        return self._conversations.create(title)
    
    def get_conversation(
        self,
        conversation_id: UUID,
    ) -> ConversationRecord:
        return self._conversations.require(
            conversation_id
        )

    def list_conversations(
        self,
        *,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[ConversationRecord]:
        return self._conversations.list_recent(
            limit=limit,
            include_archived=include_archived,
        )

    def rename_conversation(
        self,
        conversation_id: UUID,
        title: str | None,
    ) -> ConversationRecord:
        return self._conversations.rename(
            conversation_id,
            title,
        )

    def clear_conversation(
        self,
        conversation_id: UUID,
    ) -> ConversationRecord:
        return self._conversations.clear_content(
            conversation_id
        )

    def delete_conversation(
        self,
        conversation_id: UUID,
    ) -> bool:
        return self._conversations.delete(
            conversation_id
        )

    # --------------------------------------------------------
    # Conversation reads
    # --------------------------------------------------------

    def get_conversation_turns(
        self,
        conversation_id: UUID,
    ) -> list[ConversationTurn]:
        self._conversations.require(conversation_id)

        messages = self._history.get_messages(
            conversation_id
        )

        return self._context_resolver.to_turns(
            messages
        )

    def get_tool_calls_for_turn(
        self,
        stream_id: UUID,
    ) -> list[ToolCallRecord]:
        return self._tool_calls.list_for_stream(
            stream_id
        )

    def get_active_partial_turn(
        self,
        conversation_id: UUID,
    ) -> TurnStreamRecord | None:
        self._conversations.require(conversation_id)

        return (
            self._streams
            .get_active_for_conversation(
                conversation_id
            )
        )

    # --------------------------------------------------------
    # Real stream checkpoint boundary
    # --------------------------------------------------------

    def checkpoint_assistant_delta(
        self,
        *,
        stream_id: UUID,
        sequence: int,
        content_delta: str,
    ) -> TurnStreamRecord:
        """
        Persist a genuine chunk emitted by a future streaming model.

        The current deterministic controller returns one completed
        response, so execute_conversation_turn() persists that final
        response as one checkpoint. It does not artificially split it
        into fake tokens.
        """
        result = self._streams.append_delta(
            stream_id=stream_id,
            sequence=sequence,
            content_delta=content_delta,
        )

        return result.stream

    # --------------------------------------------------------
    # Turn execution
    # --------------------------------------------------------

    def execute_conversation_turn(
        self,
        *,
        conversation_id: UUID,
        user_content: str,
        client_turn_id: UUID | None = None,
    ) -> ExecuteConversationTurnResult:
        conversation = self._conversations.require(
            conversation_id
        )

        del conversation  # Existence is the required check.

        normalised_user_content = user_content.strip()

        if not normalised_user_content:
            raise ValueError(
                "User content cannot be blank."
            )

        resolved_client_turn_id = (
            client_turn_id or uuid4()
        )

        start_result = self._streams.start_or_get(
            conversation_id=conversation_id,
            client_turn_id=resolved_client_turn_id,
            user_content=normalised_user_content,
        )

        stream = start_result.stream

        if not start_result.created:
            return self._handle_existing_turn(
                stream
            )

        previous_messages = (
            self._history.get_messages(
                conversation_id
            )
        )

        current_context = (
            self._context_resolver.resolve(
                previous_messages
            )
        )

        recording_registry = RecordingToolRegistry(
            delegate=self._registry,
            repository=self._tool_calls,
            conversation_id=conversation_id,
            stream_id=stream.stream_id,
        )

        controller = self._controller_factory(
            recording_registry
        )

        try:
            output = controller.handle_turn(
                ChatTurnInput(
                    user_message=normalised_user_content,
                    context=current_context,
                )
            )

            assistant_message = (
                output.assistant_message.strip()
            )

            if not assistant_message:
                raise RuntimeError(
                    "The controller returned an empty "
                    "assistant message."
                )

            # Current controller is synchronous. Persist its real
            # final output as one checkpoint; do not simulate tokens.
            self._streams.append_delta(
                stream_id=stream.stream_id,
                sequence=1,
                content_delta=assistant_message,
            )

            persisted_tool_calls = (
                self._tool_calls.list_for_stream(
                    stream.stream_id
                )
            )

            tool_call_ids = [
                str(call.tool_call_id)
                for call in persisted_tool_calls
            ]

            self._history.add_messages(
                conversation_id,
                [
                    HumanMessage(
                        content=normalised_user_content,
                        additional_kwargs={
                            METASTOCK_METADATA_KEY: {
                                "stream_id": str(
                                    stream.stream_id
                                ),
                                "client_turn_id": str(
                                    resolved_client_turn_id
                                ),
                            }
                        },
                    ),
                    AIMessage(
                        content=assistant_message,
                        additional_kwargs={
                            METASTOCK_METADATA_KEY: {
                                "stream_id": str(
                                    stream.stream_id
                                ),
                                "client_turn_id": str(
                                    resolved_client_turn_id
                                ),
                                "route": output.route.value,
                                "context": (
                                    output.context.model_dump(
                                        mode="json"
                                    )
                                ),
                                "tool_call_ids": (
                                    tool_call_ids
                                ),
                            }
                        },
                    ),
                ],
            )

            completed_stream = self._streams.complete(
                stream_id=stream.stream_id,
                final_content=assistant_message,
            )

            return ExecuteConversationTurnResult(
                conversation_id=conversation_id,
                stream_id=completed_stream.stream_id,
                client_turn_id=(
                    resolved_client_turn_id
                ),
                assistant_message=assistant_message,
                route=output.route,
                context=output.context,
                tool_result=output.tool_result,
                replayed=False,
            )

        except Exception as exc:
            self._best_effort_fail_stream(
                stream_id=stream.stream_id,
                exception=exc,
            )
            raise

    def _handle_existing_turn(
        self,
        stream: TurnStreamRecord,
    ) -> ExecuteConversationTurnResult:
        if stream.status == TurnStreamStatus.STREAMING:
            raise TurnAlreadyInProgressError(
                "This client turn is already in progress. "
                "It will not be executed a second time."
            )

        if stream.status in {
            TurnStreamStatus.FAILED,
            TurnStreamStatus.CANCELLED,
        }:
            raise TurnCannotResumeError(
                "This client turn is already terminal with "
                f"status {stream.status.value!r}. Submit a "
                "new client_turn_id to try again."
            )

        messages = self._history.get_messages(
            stream.conversation_id
        )

        turn = (
            self._context_resolver
            .find_turn_by_stream(
                messages,
                stream.stream_id,
            )
        )

        if turn is None or turn.route is None:
            raise TurnCannotResumeError(
                "The completed stream exists, but its "
                "completed conversation turn could not "
                "be reconstructed."
            )

        tool_calls = self._tool_calls.list_for_stream(
            stream.stream_id
        )

        tool_result = self._recover_tool_result(
            tool_calls
        )

        return ExecuteConversationTurnResult(
            conversation_id=stream.conversation_id,
            stream_id=stream.stream_id,
            client_turn_id=stream.client_turn_id,
            assistant_message=(
                turn.assistant_content
            ),
            route=turn.route,
            context=turn.context,
            tool_result=tool_result,
            replayed=True,
        )

    @staticmethod
    def _recover_tool_result(
        tool_calls: list[ToolCallRecord],
    ) -> ToolResult | None:
        for call in reversed(tool_calls):
            if call.result_json is None:
                continue

            try:
                return ToolResult.model_validate(
                    call.result_json
                )
            except Exception:
                continue

        return None

    def _best_effort_fail_stream(
        self,
        *,
        stream_id: UUID,
        exception: Exception,
    ) -> None:
        try:
            current = self._streams.get(stream_id)

            if (
                current is not None
                and current.status
                == TurnStreamStatus.STREAMING
            ):
                self._streams.fail(
                    stream_id=stream_id,
                    error_code=(
                        type(exception).__name__
                    ),
                    error_message=(
                        str(exception).strip()
                        or type(exception).__name__
                    ),
                )
        except Exception:
            # Preserve the original application exception.
            pass