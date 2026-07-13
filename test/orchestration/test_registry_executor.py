from __future__ import annotations

from typing import Any

from orchestration.registry_executor import (
    RegistryToolExecutor,
)
from tools.tool_contracts import (
    ToolResult,
    ToolStatus,
)


class SuccessRegistry:
    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="passed",
            data={"arguments": arguments},
        )


class UnknownToolRegistry:
    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        del arguments
        raise ValueError(
            f"Unknown tool: {name}"
        )


class ExplodingRegistry:
    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        del name, arguments
        raise RuntimeError("boom")


def test_executor_returns_success_result() -> None:
    executor = RegistryToolExecutor(
        SuccessRegistry()
    )

    result = executor.execute(
        "generate_explorer",
        {"user_query": "RSI"},
    )

    assert result.ok is True
    assert result.status is ToolStatus.SUCCESS
    assert result.data["arguments"] == {
        "user_query": "RSI"
    }


def test_executor_translates_unknown_tool() -> None:
    executor = RegistryToolExecutor(
        UnknownToolRegistry()
    )

    result = executor.execute(
        "invented_tool",
        {},
    )

    assert result.ok is False
    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code == "UNKNOWN_TOOL"


def test_executor_translates_unexpected_error() -> None:
    executor = RegistryToolExecutor(
        ExplodingRegistry()
    )

    result = executor.execute(
        "generate_explorer",
        {},
    )

    assert result.ok is False
    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code == "RuntimeError"
    assert result.error.message == "boom"
