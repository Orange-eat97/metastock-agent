from __future__ import annotations

from typing import Any

from chat.controller import (
    ChatTurnController,
    ToolRegistryProtocol,
)
from chat.models import (
    ChatTurnInput,
    ChatTurnOutput,
)
from chat.router import DeterministicChatRouter
from orchestration.state import (
    GraphInputState,
    MetaStockGraphState,
)


class DeterministicTurnNode:
    """
    Transitional parity node for merged MS10.1-10.2.

    It executes the existing deterministic controller inside a LangGraph
    node. This preserves current routing, context checks, registry calls,
    ToolResult rendering, and existing multi-tool behavior exactly.

    MS10.3-10.4 will replace this node's routing responsibility with the
    structured LLM planner and explicit context resolution.
    """

    def __init__(
        self,
        *,
        registry: ToolRegistryProtocol,
        router: (
            DeterministicChatRouter | None
        ) = None,
    ) -> None:
        self._controller = ChatTurnController(
            registry=registry,
            router=router,
        )

    def __call__(
        self,
        state: GraphInputState,
    ) -> MetaStockGraphState:
        raw_input = state.get("turn_input")

        if not isinstance(raw_input, dict):
            raise ValueError(
                "Graph state must contain a "
                "dictionary at 'turn_input'."
            )

        payload = ChatTurnInput.model_validate(
            raw_input
        )
        output = self._controller.handle_turn(
            payload
        )

        return {
            "turn_output": _dump_turn_output(
                output
            )
        }


def _dump_turn_output(
    output: ChatTurnOutput,
) -> dict[str, Any]:
    return output.model_dump(mode="json")
