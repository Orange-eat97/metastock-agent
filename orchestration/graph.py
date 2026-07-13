from __future__ import annotations

from typing import Any

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from chat.controller import ToolRegistryProtocol
from chat.router import DeterministicChatRouter
from orchestration.nodes import (
    DeterministicTurnNode,
)
from orchestration.state import (
    GraphInputState,
    GraphOutputState,
    MetaStockGraphState,
)


DETERMINISTIC_TURN_NODE = (
    "execute_deterministic_turn"
)


def build_deterministic_parity_graph(
    *,
    registry: ToolRegistryProtocol,
    router: (
        DeterministicChatRouter | None
    ) = None,
) -> Any:
    """
    Build the MS10.1-10.2 graph.

    The graph has one transitional node so the first LangGraph integration
    remains behaviorally identical to the existing ChatTurnController.
    ToolRegistry remains the sole execution boundary.
    """

    builder = StateGraph(
        MetaStockGraphState,
        input_schema=GraphInputState,
        output_schema=GraphOutputState,
    )

    builder.add_node(
        DETERMINISTIC_TURN_NODE,
        DeterministicTurnNode(
            registry=registry,
            router=router,
        ),
    )

    builder.add_edge(
        START,
        DETERMINISTIC_TURN_NODE,
    )
    builder.add_edge(
        DETERMINISTIC_TURN_NODE,
        END,
    )

    return builder.compile()
