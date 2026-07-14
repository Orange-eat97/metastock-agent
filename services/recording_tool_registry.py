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

    def list_tools(self) -> list[Any]:
        ...

    def get_tool(self, name: str) -> Any:
        ...


class RecordingToolRegistry:
    """
    Per-turn decorator around the real ToolRegistry.

    execute() remains recorded exactly as before. Read-only catalog access is
    delegated without creating tool-call audit rows because planner discovery
    is not itself a business-tool execution.
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
        self._conversation_id = (
            conversation_id
        )
        self._stream_id = stream_id
        self._next_ordinal = 0

    def list_tools(self) -> list[Any]:
        method = getattr(
            self._delegate,
            "list_tools",
            None,
        )

        if not callable(method):
            raise RuntimeError(
                "The wrapped registry does not "
                "expose list_tools()."
            )

        return list(method())

    def get_tool(self, name: str) -> Any:
        method = getattr(
            self._delegate,
            "get_tool",
            None,
        )

        if not callable(method):
            raise RuntimeError(
                "The wrapped registry does not "
                "expose get_tool()."
            )

        return method(name)

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        ordinal = self._next_ordinal
        self._next_ordinal += 1

        call = self._repository.start(
            conversation_id=(
                self._conversation_id
            ),
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
                tool_call_id=(
                    call.tool_call_id
                ),
                exception=exc,
            )
            raise

        self._repository.finish(
            tool_call_id=call.tool_call_id,
            result=result,
        )

        return result
