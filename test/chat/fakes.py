from __future__ import annotations

from typing import Any

from tools.tool_contracts import (
    ToolDisplay,
    ToolResult,
    ToolStatus,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        self.calls.append(
            (name, arguments)
        )

        if name == "generate_explorer":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="generated",
                data={
                    "explorer": {
                        "explorer_id": (
                            "explorer-new"
                        ),
                        "service_log_id": (
                            "log-new"
                        ),
                    },
                    "retrieved_refs": [],
                },
                display=ToolDisplay(
                    title=(
                        "Generated Explorer"
                    ),
                    markdown=(
                        "Generated explorer "
                        "markdown"
                    ),
                    severity="success",
                ),
            )

        if name == "repair_explorer":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="repaired",
                data={
                    "explorer": {
                        "explorer_id": (
                            "explorer-repaired"
                        ),
                        "service_log_id": (
                            "log-repaired"
                        ),
                    },
                    "repaired_from_explorer_id": (
                        arguments["explorer_id"]
                    ),
                },
            )

        if name == "get_explorer":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="fetched",
                data={
                    "explorer": {
                        "explorer_id": (
                            arguments[
                                "explorer_id"
                            ]
                        ),
                        "service_log_id": (
                            "log-existing"
                        ),
                    }
                },
            )

        if name == "get_rag_log":
            return ToolResult(
                tool_name=name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message="log fetched",
                data={
                    "log_id": arguments[
                        "log_id"
                    ]
                },
            )

        if name in {
            "create_explorer_in_metastock",
            "select_explorer_in_metastock",
            (
                "run_selected_explorer_"
                "in_metastock"
            ),
        }:
            return ToolResult(
                tool_name=name,
                ok=False,
                status=ToolStatus.BLOCKED,
                message=(
                    "MetaStock automation is "
                    "not configured."
                ),
            )

        raise ValueError(
            f"Unknown tool: {name}"
        )
