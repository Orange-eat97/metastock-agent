from __future__ import annotations

from typing import Any, TypedDict


class GraphInputState(TypedDict):
    """JSON-serializable input accepted by the MS10 graph."""

    turn_input: dict[str, Any]


class MetaStockGraphState(GraphInputState, total=False):
    """
    Internal graph state for the MS10.1-10.2 parity stage.

    This stage deliberately stores the existing ChatTurnInput and
    ChatTurnOutput envelopes instead of introducing a second context model.
    Later MS10 stages can add planner and workflow fields without changing
    the current chat or tool contracts.
    """

    turn_output: dict[str, Any]


class GraphOutputState(TypedDict):
    """JSON-serializable output returned by the compiled graph."""

    turn_output: dict[str, Any]
