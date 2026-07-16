from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from services.recording_tool_registry import (
    RecordingToolRegistry,
)


@dataclass
class Definition:
    name: str


class Delegate:
    def list_tools(self) -> list[Definition]:
        return [Definition("tool-a")]

    def get_tool(
        self,
        name: str,
    ) -> Definition:
        return Definition(name)

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ):
        raise AssertionError(
            "Execution is not used."
        )


class Repository:
    def start(self, **kwargs: Any):
        raise AssertionError(
            "Catalog reads must not "
            "create audit rows."
        )


def test_catalog_access_is_delegated_without_recording() -> None:
    registry = RecordingToolRegistry(
        delegate=Delegate(),
        repository=Repository(),
        conversation_id=uuid4(),
        stream_id=uuid4(),
    )

    assert [
        item.name
        for item in registry.list_tools()
    ] == ["tool-a"]
    assert registry.get_tool(
        "tool-b"
    ).name == "tool-b"
