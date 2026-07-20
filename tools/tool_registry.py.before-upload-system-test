from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Type

from pydantic import BaseModel

from tools.explorer_tools import ExplorerToolService
from tools.result_tools import MetaStockResultToolService
from tools.tool_contracts import (
    GenerateExplorerInput,
    GetExplorerInput,
    GetExplorerResultInput,
    GetLatestExplorerResultInput,
    GetRagLogInput,
    ListExplorerResultsInput,
    ReadMetaStockResultsInput,
    RepairExplorerInput,
    ReviseExplorerInput,
    RunExplorerInput,
    ToolError,
    ToolResult,
    ToolStatus,
)


class ToolExposure(str, Enum):
    """
    Which orchestration layer may choose the tool.

    Conversation tools may be selected directly by the model.
    Workflow-internal tools are selected only by approved deterministic
    workflow definitions.
    """

    CONVERSATION = "conversation"
    WORKFLOW_INTERNAL = "workflow_internal"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: Type[BaseModel]
    handler: Callable[[Any], ToolResult]
    enabled: bool = True
    exposure: ToolExposure = (
        ToolExposure.CONVERSATION
    )

    def input_json_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


class ToolRegistry:
    """Validated execution boundary for LLM-accessible capabilities."""

    def __init__(
        self,
        explorer_tool_service: ExplorerToolService,
        result_tool_service: MetaStockResultToolService,
    ) -> None:
        self.explorer_tool_service = (
            explorer_tool_service
        )
        self.result_tool_service = (
            result_tool_service
        )
        self._tools = self._build_tools()

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def list_conversation_tools(
        self,
    ) -> list[ToolDefinition]:
        return [
            tool
            for tool in self._tools.values()
            if (
                tool.exposure
                is ToolExposure.CONVERSATION
            )
        ]

    def get_tool(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise ValueError(
                f"Unknown tool: {name}"
            )

        return self._tools[name]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        tool = self.get_tool(name)

        if not tool.enabled:
            return ToolResult(
                tool_name=name,
                ok=False,
                status=ToolStatus.BLOCKED,
                message=(
                    f"Tool is disabled: {name}"
                ),
                error=ToolError(
                    code="TOOL_DISABLED",
                    message=(
                        f"The tool `{name}` is "
                        "currently disabled."
                    ),
                ),
            )

        payload = tool.input_model.model_validate(
            arguments
        )
        return tool.handler(payload)

    def _build_tools(
        self,
    ) -> dict[str, ToolDefinition]:
        tools = [
            ToolDefinition(
                name="generate_explorer",
                description=(
                    "Generate a new MetaStock Explorer "
                    "from a natural-language trading "
                    "condition."
                ),
                input_model=GenerateExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .generate_explorer
                ),
            ),
            ToolDefinition(
                name="repair_explorer",
                description=(
                    "Repair syntax or validation issues "
                    "in an existing Explorer without "
                    "changing its trading intent."
                ),
                input_model=RepairExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .repair_explorer
                ),
            ),
            ToolDefinition(
                name="revise_explorer",
                description=(
                    "Revise strategy logic or parameters "
                    "in an existing Explorer."
                ),
                input_model=ReviseExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .revise_explorer
                ),
                enabled=True,
            ),
            ToolDefinition(
                name="get_explorer",
                description=(
                    "Fetch and display a stored Explorer."
                ),
                input_model=GetExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .get_explorer
                ),
            ),
            ToolDefinition(
                name="get_rag_log",
                description=(
                    "Fetch and display a stored RAG "
                    "service log."
                ),
                input_model=GetRagLogInput,
                handler=(
                    self.explorer_tool_service
                    .get_rag_log
                ),
            ),
            ToolDefinition(
                name="create_explorer_in_metastock",
                description=(
                    "Create a stored Explorer in "
                    "MetaStock only."
                ),
                input_model=RunExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .create_explorer_in_metastock
                ),
                exposure=(
                    ToolExposure.WORKFLOW_INTERNAL
                ),
            ),
            ToolDefinition(
                name="select_explorer_in_metastock",
                description=(
                    "Select an existing Explorer and "
                    "instruments in MetaStock only."
                ),
                input_model=RunExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .select_explorer_in_metastock
                ),
                exposure=(
                    ToolExposure.WORKFLOW_INTERNAL
                ),
            ),
            ToolDefinition(
                name=(
                    "run_selected_explorer_in_metastock"
                ),
                description=(
                    "Run the currently selected Explorer "
                    "in MetaStock."
                ),
                input_model=RunExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .run_selected_explorer_in_metastock
                ),
                exposure=(
                    ToolExposure.WORKFLOW_INTERNAL
                ),
            ),
            ToolDefinition(
                name=(
                    "read_metastock_explorer_results"
                ),
                description=(
                    "Read, normalize, verify, and persist "
                    "the open MetaStock result window."
                ),
                input_model=ReadMetaStockResultsInput,
                handler=(
                    self.result_tool_service
                    .read_metastock_explorer_results
                ),
                exposure=(
                    ToolExposure.WORKFLOW_INTERNAL
                ),
            ),
            ToolDefinition(
                name="get_explorer_result",
                description=(
                    "Fetch one complete stored MetaStock "
                    "Explorer result by result ID."
                ),
                input_model=GetExplorerResultInput,
                handler=(
                    self.result_tool_service
                    .get_explorer_result
                ),
            ),
            ToolDefinition(
                name="get_latest_explorer_result",
                description=(
                    "Fetch the newest stored MetaStock "
                    "result for an Explorer."
                ),
                input_model=(
                    GetLatestExplorerResultInput
                ),
                handler=(
                    self.result_tool_service
                    .get_latest_explorer_result
                ),
            ),
            ToolDefinition(
                name="list_explorer_results",
                description=(
                    "List newest-first stored MetaStock "
                    "result summaries for an Explorer."
                ),
                input_model=ListExplorerResultsInput,
                handler=(
                    self.result_tool_service
                    .list_explorer_results
                ),
            ),
        ]

        return {
            tool.name: tool
            for tool in tools
        }
