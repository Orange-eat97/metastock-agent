from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type

from pydantic import BaseModel

from tools.explorer_tools import ExplorerToolService
from tools.tool_contracts import (
    GenerateExplorerInput,
    GetExplorerInput,
    GetRagLogInput,
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
    """
    Registry of LLM-accessible tools.

    The future orchestrator will use this registry to:
    - present tool schemas to the LLM;
    - validate tool arguments;
    - dispatch the selected tool call.
    """

    def __init__(self, explorer_tool_service: ExplorerToolService):
        self.explorer_tool_service = explorer_tool_service
        self._tools = self._build_tools()

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")

        return self._tools[name]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
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
                    "trading condition. Use this when the user asks to create, "
                    "generate, build, or draft a stock screening Explorer."
                ),
                input_model=GenerateExplorerInput,
                handler=self.explorer_tool_service.generate_explorer,
                enabled=True,
            ),
            ToolDefinition(
                name="repair_explorer",
                description=(
                    "Repair an existing Explorer that has validation or syntax "
                    "issues. Use this mainly when validation failed or the user "
                    "asks to fix formula errors."
                ),
                input_model=RepairExplorerInput,
                handler=self.explorer_tool_service.repair_explorer,
                enabled=True,
            ),
            ToolDefinition(
                name="revise_explorer",
                description=(
                    "Revise an existing Explorer according to a human strategy "
                    "change request. Reserved for future MITL correction."
                ),
                input_model=ReviseExplorerInput,
                handler=self.explorer_tool_service.revise_explorer,
                enabled=False,
            ),
            ToolDefinition(
                name="get_explorer",
                description=(
                    "Fetch and display a stored Explorer by explorer_outputs id."
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
                name="run_explorer_in_metastock",
                description=(
                    "Run a validated Explorer in MetaStock. Disabled until "
                    "AutomatorClient is standardized."
                ),
                input_model=RunExplorerInput,
                handler=self.explorer_tool_service.run_explorer_in_metastock,
                enabled=False,
            ),
        ]

        return {tool.name: tool for tool in tools}