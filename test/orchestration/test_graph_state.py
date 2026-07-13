from __future__ import annotations

import json

from chat.models import ChatTurnInput
from orchestration.nodes import (
    DeterministicTurnNode,
)
from test.chat.fakes import FakeRegistry


def test_node_emits_json_serializable_output() -> None:
    node = DeterministicTurnNode(
        registry=FakeRegistry()
    )

    state = node(
        {
            "turn_input": (
                ChatTurnInput(
                    user_message=(
                        "Find stocks where RSI "
                        "is below 30"
                    )
                ).model_dump(mode="json")
            )
        }
    )

    assert "turn_output" in state

    encoded = json.dumps(
        state["turn_output"]
    )

    assert "generate_explorer" in encoded
    assert "explorer-new" in encoded


def test_node_rejects_missing_turn_input() -> None:
    node = DeterministicTurnNode(
        registry=FakeRegistry()
    )

    try:
        node({})  # type: ignore[arg-type]
    except ValueError as exc:
        assert "turn_input" in str(exc)
    else:
        raise AssertionError(
            "Expected missing graph input "
            "to raise ValueError."
        )
