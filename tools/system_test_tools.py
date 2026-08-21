from __future__ import annotations

import traceback
from typing import Any

from tools.tool_contracts import (
    ConvertExplorerToSystemTestInput,
    ConvertExplorerToSystemTestOutput,
    SystemTestSettingsDTO,
    ToolDisplay,
    ToolError,
    ToolResult,
    ToolStatus,
    ValidationDTO,
)


class SystemTestToolService:
    """Agent-side facade for deterministic RAG System Test conversion."""

    def __init__(self, rag_client: Any) -> None:
        self.rag_client = rag_client

    def convert_explorer_to_system_test(
        self,
        payload: ConvertExplorerToSystemTestInput,
    ) -> ToolResult:
        try:
            raw = (
                self.rag_client
                .convert_explorer_to_system_test(
                    payload.explorer_id
                )
            )
            definition = raw.get("system_test")
            if not isinstance(definition, dict):
                raise RuntimeError(
                    "RAG System Test response is missing "
                    "system_test."
                )

            orders = definition.get("orders")
            general = definition.get("general")
            validation = raw.get("validation")
            if not isinstance(orders, dict):
                orders = {}
            if not isinstance(general, dict):
                general = {}
            if not isinstance(validation, dict):
                validation = {}

            buy = orders.get("buy")
            sell = orders.get("sell")
            position_limit = general.get(
                "position_limit"
            )
            if not isinstance(buy, dict):
                buy = {}
            if not isinstance(sell, dict):
                sell = {}
            if not isinstance(position_limit, dict):
                position_limit = {}

            output = ConvertExplorerToSystemTestOutput(
                system_test_id=str(
                    raw.get("system_test_id") or ""
                ),
                explorer_id=str(
                    raw.get("source_explorer_id")
                    or payload.explorer_id
                ),
                name=str(
                    definition.get("name") or ""
                ),
                description=str(
                    definition.get("description") or ""
                ),
                buy_formula=str(
                    buy.get("signal_formula") or ""
                ),
                sell_formula=str(
                    sell.get("signal_formula") or ""
                ),
                settings=SystemTestSettingsDTO(
                    order_bias=str(
                        general.get("order_bias")
                        or "long"
                    ),
                    portfolio_bias=str(
                        general.get("portfolio_bias")
                        or "single"
                    ),
                    position_limit_enabled=bool(
                        position_limit.get(
                            "enabled",
                            True,
                        )
                    ),
                    max_positions=int(
                        position_limit.get(
                            "max_positions",
                            1,
                        )
                    ),
                    buy_enabled=bool(
                        buy.get("enabled", True)
                    ),
                    sell_enabled=bool(
                        sell.get("enabled", True)
                    ),
                    sell_short_enabled=bool(
                        (
                            orders.get("sell_short")
                            if isinstance(
                                orders.get("sell_short"),
                                dict,
                            )
                            else {}
                        ).get("enabled", False)
                    ),
                    buy_to_cover_enabled=bool(
                        (
                            orders.get("buy_to_cover")
                            if isinstance(
                                orders.get("buy_to_cover"),
                                dict,
                            )
                            else {}
                        ).get("enabled", False)
                    ),
                    stops_enabled=bool(
                        (
                            definition.get("stops")
                            if isinstance(
                                definition.get("stops"),
                                dict,
                            )
                            else {}
                        ).get("enabled", False)
                    ),
                    optimizations_enabled=bool(
                        (
                            definition.get(
                                "optimizations"
                            )
                            if isinstance(
                                definition.get(
                                    "optimizations"
                                ),
                                dict,
                            )
                            else {}
                        ).get("enabled", False)
                    ),
                ),
                validation=ValidationDTO(
                    passed=bool(
                        validation.get("passed", False)
                    ),
                    errors=[
                        str(item)
                        for item in validation.get(
                            "errors",
                            [],
                        )
                    ],
                    warnings=[
                        str(item)
                        for item in validation.get(
                            "warnings",
                            [],
                        )
                    ],
                ),
                service_log_id=(
                    str(raw.get("service_log"))
                    if raw.get("service_log")
                    else None
                ),
            )

            severity = (
                "success"
                if output.validation.passed
                else "warning"
            )
            return ToolResult(
                tool_name=(
                    "convert_explorer_to_system_test"
                ),
                ok=output.validation.passed,
                status=(
                    ToolStatus.SUCCESS
                    if output.validation.passed
                    else ToolStatus.BLOCKED
                ),
                message=(
                    "System Test generated for manual "
                    "entry in MetaStock."
                    if output.validation.passed
                    else "System Test validation failed."
                ),
                data=output.model_dump(mode="json"),
                display=ToolDisplay(
                    title=(
                        "System Test Manual Entry"
                    ),
                    markdown=self._manual_entry_markdown(
                        output
                    ),
                    severity=severity,
                ),
                error=(
                    None
                    if output.validation.passed
                    else ToolError(
                        code=(
                            "SYSTEM_TEST_VALIDATION_FAILED"
                        ),
                        message=(
                            "The generated System Test "
                            "failed validation."
                        ),
                        details={
                            "errors": (
                                output.validation.errors
                            ),
                        },
                    )
                ),
            )

        except Exception as exc:
            return ToolResult(
                tool_name=(
                    "convert_explorer_to_system_test"
                ),
                ok=False,
                status=ToolStatus.FAILED,
                message=str(exc),
                error=ToolError(
                    code=type(exc).__name__,
                    message=str(exc),
                    details={
                        "traceback": traceback.format_exc(),
                    },
                ),
                display=ToolDisplay(
                    title="System Test generation failed",
                    markdown=str(exc),
                    severity="error",
                ),
            )

    @staticmethod
    def _manual_entry_markdown(
        output: ConvertExplorerToSystemTestOutput,
    ) -> str:
        warnings = (
            "\n".join(
                f"- {item}"
                for item in output.validation.warnings
            )
            or "- None."
        )
        errors = (
            "\n".join(
                f"- {item}"
                for item in output.validation.errors
            )
            or "- None."
        )

        return "\n".join(
            [
                "Create a new MetaStock System Test named:",
                "",
                f"**{output.name}**",
                "",
                "## General tab",
                "",
                "- Order Bias: Long Orders",
                "- Portfolio Bias: Single",
                "- Limit Positions: Enabled",
                "- Maximum Simultaneous Positions: 1",
                "",
                "## Buy Order tab",
                "",
                (
                    "Enable **Buy**, then paste this into "
                    "the Buy Order formula editor:"
                ),
                "",
                "```metastock",
                output.buy_formula,
                "```",
                "",
                "## Sell Order tab",
                "",
                (
                    "Enable **Sell**, then paste this into "
                    "the Sell Order formula editor:"
                ),
                "",
                "```metastock",
                output.sell_formula,
                "```",
                "",
                "## Leave disabled",
                "",
                "- Sell Short",
                "- Buy to Cover",
                "- Stops",
                "- Optimizations",
                "",
                (
                    "**Validation:** "
                    + (
                        "PASSED"
                        if output.validation.passed
                        else "FAILED"
                    )
                ),
                "",
                "### Validation warnings",
                warnings,
                "",
                "### Validation errors",
                errors,
            ]
        )
