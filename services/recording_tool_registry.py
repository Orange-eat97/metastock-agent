from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from infrastructure.agent_state.tool_call_repository import (
    ToolCallRepository,
)
from tools.tool_contracts import ToolResult


class ToolRegistryProtocol(Protocol):
    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        ...


class RecordingToolRegistry:
    """
    Per-turn decorator around the real ToolRegistry.

    Every execute() call is persisted before dispatch and finalized
    after dispatch. This supports both one-tool turns and controller
    flows that intentionally call several separate tools.
    """

    def __init__(
        self,
        *,
        delegate: ToolRegistryProtocol,
        repository: ToolCallRepository,
        conversation_id: UUID,
        stream_id: UUID,
    ) -> None:
        self._delegate = delegate
        self._repository = repository
        self._conversation_id = conversation_id
        self._stream_id = stream_id
        self._next_ordinal = 0

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        ordinal = self._next_ordinal
        self._next_ordinal += 1

        call = self._repository.start(
            conversation_id=self._conversation_id,
            stream_id=self._stream_id,
            ordinal=ordinal,
            tool_name=name,
            arguments=arguments,
        )

        try:
            result = self._delegate.execute(
                name,
                arguments,
            )
        except Exception as exc:
            self._repository.fail_exception(
                tool_call_id=call.tool_call_id,
                exception=exc,
            )
            raise

        self._repository.finish(
            tool_call_id=call.tool_call_id,
            result=result,
        )

        return result