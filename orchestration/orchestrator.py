from __future__ import annotations

from typing import Any, Protocol

from chat.controller import ToolRegistryProtocol
from chat.models import (
    ChatTurnInput,
    ChatTurnOutput,
)
from chat.router import DeterministicChatRouter
from orchestration.graph import (
    build_deterministic_parity_graph,
)


class CompiledGraphProtocol(Protocol):
    def invoke(
        self,
        input: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class LangGraphOrchestrator:
    """
    ChatControllerProtocol-compatible LangGraph entry point.

    ConversationApplicationService can construct this class with the
    per-turn RecordingToolRegistry. Therefore all graph-triggered tool calls
    keep the current audit behavior and still pass through ToolRegistry.
    """

    def __init__(
        self,
        registry: ToolRegistryProtocol,
        router: (
            DeterministicChatRouter | None
        ) = None,
        *,
        graph: CompiledGraphProtocol | None = None,
    ) -> None:
        self._graph = (
            graph
            if graph is not None
            else build_deterministic_parity_graph(
                registry=registry,
                router=router,
            )
        )

    @property
    def graph(self) -> CompiledGraphProtocol:
        return self._graph

    def handle_turn(
        self,
        payload: ChatTurnInput,
    ) -> ChatTurnOutput:
        graph_result = self._graph.invoke(
            {
                "turn_input": payload.model_dump(
                    mode="json"
                )
            }
        )

        if not isinstance(graph_result, dict):
            raise RuntimeError(
                "LangGraph returned a non-dictionary "
                "turn result."
            )

        raw_output = graph_result.get(
            "turn_output"
        )

        if not isinstance(raw_output, dict):
            raise RuntimeError(
                "LangGraph did not return a "
                "'turn_output' dictionary."
            )

        return ChatTurnOutput.model_validate(
            raw_output
        )
