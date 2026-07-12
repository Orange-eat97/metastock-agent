from __future__ import annotations

from uuid import UUID

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
)

from chat.models import ChatContext
from chat.routes import ChatRoute
from services.conversation_models import ConversationTurn


METASTOCK_METADATA_KEY = "metastock_agent"


class ConversationHistoryIntegrityError(RuntimeError):
    """Raised when completed history is not stored as turns."""


class ConversationContextResolver:
    """
    Recovers the deterministic ChatContext from completed assistant
    message metadata.

    LangGraph will eventually own active workflow state. Until then,
    this avoids adding active_explorer_id columns to conversations.
    """

    def resolve(
        self,
        messages: list[BaseMessage],
    ) -> ChatContext:
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue

            metadata = message.additional_kwargs.get(
                METASTOCK_METADATA_KEY
            )

            if not isinstance(metadata, dict):
                continue

            raw_context = metadata.get("context")

            if not isinstance(raw_context, dict):
                continue

            try:
                return ChatContext.model_validate(
                    raw_context
                )
            except Exception:
                continue

        return ChatContext()

    def to_turns(
        self,
        messages: list[BaseMessage],
    ) -> list[ConversationTurn]:
        if len(messages) % 2 != 0:
            raise ConversationHistoryIntegrityError(
                "Completed conversation history contains "
                "an incomplete turn."
            )

        turns: list[ConversationTurn] = []

        for index in range(0, len(messages), 2):
            human = messages[index]
            assistant = messages[index + 1]

            if not isinstance(human, HumanMessage):
                raise ConversationHistoryIntegrityError(
                    f"Expected HumanMessage at index {index}."
                )

            if not isinstance(assistant, AIMessage):
                raise ConversationHistoryIntegrityError(
                    f"Expected AIMessage at index {index + 1}."
                )

            metadata = assistant.additional_kwargs.get(
                METASTOCK_METADATA_KEY,
                {},
            )

            if not isinstance(metadata, dict):
                metadata = {}

            route = self._parse_route(
                metadata.get("route")
            )
            context = self._parse_context(
                metadata.get("context")
            )
            stream_id = self._parse_uuid(
                metadata.get("stream_id")
            )
            tool_call_ids = self._parse_uuid_list(
                metadata.get("tool_call_ids")
            )

            turns.append(
                ConversationTurn(
                    user_content=self._as_text(
                        human.content
                    ),
                    assistant_content=self._as_text(
                        assistant.content
                    ),
                    route=route,
                    context=context,
                    stream_id=stream_id,
                    tool_call_ids=tool_call_ids,
                )
            )

        return turns

    def find_turn_by_stream(
        self,
        messages: list[BaseMessage],
        stream_id: UUID,
    ) -> ConversationTurn | None:
        for turn in reversed(self.to_turns(messages)):
            if turn.stream_id == stream_id:
                return turn

        return None

    @staticmethod
    def _parse_route(value: object) -> ChatRoute | None:
        if not isinstance(value, str):
            return None

        try:
            return ChatRoute(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_context(value: object) -> ChatContext:
        if not isinstance(value, dict):
            return ChatContext()

        try:
            return ChatContext.model_validate(value)
        except Exception:
            return ChatContext()

    @staticmethod
    def _parse_uuid(value: object) -> UUID | None:
        if not isinstance(value, str):
            return None

        try:
            return UUID(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_uuid_list(
        value: object,
    ) -> list[UUID]:
        if not isinstance(value, list):
            return []

        values: list[UUID] = []

        for item in value:
            parsed = (
                ConversationContextResolver
                ._parse_uuid(item)
            )

            if parsed is not None:
                values.append(parsed)

        return values

    @staticmethod
    def _as_text(content: object) -> str:
        if isinstance(content, str):
            return content

        return str(content)