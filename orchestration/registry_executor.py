from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from tools.tool_contracts import (
    ToolError,
    ToolResult,
    ToolStatus,
)


class ToolRegistryProtocol(Protocol):
    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        ...


class RegistryToolExecutor:
    """
    Narrow execution adapter around ToolRegistry.execute(...).

    The deterministic parity graph still delegates complete turns to the
    existing ChatTurnController. This adapter is introduced now so the next
    MS10 stage can execute planner-selected tools without bypassing the
    existing registry boundary or duplicating exception translation.
    """

    def __init__(
        self,
        registry: ToolRegistryProtocol,
    ) -> None:
        self._registry = registry

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        try:
            return self._registry.execute(
                tool_name,
                arguments,
            )
        except ValidationError as exc:
            return ToolResult(
                tool_name=tool_name,
                ok=False,
                status=ToolStatus.FAILED,
                message=(
                    "Tool arguments failed validation."
                ),
                error=ToolError(
                    code=(
                        "TOOL_ARGUMENT_VALIDATION_FAILED"
                    ),
                    message=(
                        "Tool arguments failed validation."
                    ),
                    details={
                        "errors": exc.errors(
                            include_url=False
                        )
                    },
                ),
            )
        except ValueError as exc:
            return ToolResult(
                tool_name=tool_name,
                ok=False,
                status=ToolStatus.FAILED,
                message=str(exc),
                error=ToolError(
                    code="UNKNOWN_TOOL",
                    message=str(exc),
                ),
            )
        except Exception as exc:
            return ToolResult(
                tool_name=tool_name,
                ok=False,
                status=ToolStatus.FAILED,
                message=(
                    "The tool call failed unexpectedly."
                ),
                error=ToolError(
                    code=type(exc).__name__,
                    message=(
                        str(exc).strip()
                        or type(exc).__name__
                    ),
                ),
            )
