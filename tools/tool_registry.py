from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: Type[BaseModel]
    handler: Callable[[Any], ToolResult]
    enabled: bool = True

    def input_json_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


class ToolRegistry:
    """Registry of LLM-accessible tools."""

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

    def get_tool(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")

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
                message=f"Tool is disabled: {name}",
                error=ToolError(
                    code="TOOL_DISABLED",
                    message=f"The tool `{name}` is currently disabled.",
                ),
            )

        payload = tool.input_model.model_validate(arguments)
        return tool.handler(payload)

    def _build_tools(self) -> dict[str, ToolDefinition]:
        tools = [
            ToolDefinition(
                name="generate_explorer",
                description=(
                    "Generate a new MetaStock Explorer from a natural-language "
                    "trading condition."
                ),
                input_model=GenerateExplorerInput,
                handler=self.explorer_tool_service.generate_explorer,
                enabled=True,
            ),
            ToolDefinition(
                name="repair_explorer",
                description=(
                    "Repair an existing Explorer that has validation or syntax "
                    "issues."
                ),
                input_model=RepairExplorerInput,
                handler=self.explorer_tool_service.repair_explorer,
                enabled=True,
            ),
            ToolDefinition(
                name="revise_explorer",
                description=(
                    "Revise an existing Explorer according to a human strategy "
                    "change request."
                ),
                input_model=ReviseExplorerInput,
                handler=self.explorer_tool_service.revise_explorer,
                enabled=False,
            ),
            ToolDefinition(
                name="get_explorer",
                description=(
                    "Fetch and display a stored Explorer by explorer_outputs ID."
                ),
                input_model=GetExplorerInput,
                handler=self.explorer_tool_service.get_explorer,
                enabled=True,
            ),
            ToolDefinition(
                name="get_rag_log",
                description=(
                    "Fetch and display a stored RAG service log by "
                    "rag_service_logs log_id."
                ),
                input_model=GetRagLogInput,
                handler=self.explorer_tool_service.get_rag_log,
                enabled=True,
            ),
            ToolDefinition(
                name="create_explorer_in_metastock",
                description=(
                    "Create a stored Explorer in MetaStock only. "
                    "This does not select or run it."
                ),
                input_model=RunExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .create_explorer_in_metastock
                ),
                enabled=True,
            ),
            ToolDefinition(
                name="select_explorer_in_metastock",
                description=(
                    "Select an existing Explorer and instruments "
                    "in MetaStock only. This does not create or run it."
                ),
                input_model=RunExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .select_explorer_in_metastock
                ),
                enabled=True,
            ),
            ToolDefinition(
                name="run_selected_explorer_in_metastock",
                description=(
                    "Run the currently selected Explorer in MetaStock. "
                    "Selection must already have completed."
                ),
                input_model=RunExplorerInput,
                handler=(
                    self.explorer_tool_service
                    .run_selected_explorer_in_metastock
                ),
                enabled=True,
            ),
            ToolDefinition(
                name="read_metastock_explorer_results",
                description=(
                    "Read, normalize, clipboard-verify, and persist the currently "
                    "open completed MetaStock Explorer result window."
                ),
                input_model=ReadMetaStockResultsInput,
                handler=(
                    self.result_tool_service.read_metastock_explorer_results
                ),
                enabled=True,
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
                enabled=True,
            ),
            ToolDefinition(
                name="get_latest_explorer_result",
                description=(
                    "Fetch the newest stored MetaStock "
                    "result for an Explorer."
                ),
                input_model=GetLatestExplorerResultInput,
                handler=(
                    self.result_tool_service
                    .get_latest_explorer_result
                ),
                enabled=True,
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
                enabled=True,
            ),
        ]

        return {tool.name: tool for tool in tools}
