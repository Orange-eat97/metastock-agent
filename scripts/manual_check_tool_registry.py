from __future__ import annotations

from services.automator_client import UnavailableAutomatorClient
from services.explorer_repository import ExplorerRepository
from services.rag_client import LocalRagClient
from tools.explorer_tools import ExplorerToolService
from tools.tool_registry import ToolRegistry
from agent_workflows.explorer_review_workflow import ExplorerReviewWorkflow
from tools.result_tools import (
    MetaStockResultToolService,
)

RAG_REPO_PATH = r"C:\GitHub\metastock-RAG-LLM"


def main() -> None:
    rag_client = LocalRagClient(
    rag_repo_path=RAG_REPO_PATH
    )
    automator_client = (
        UnavailableAutomatorClient()
    )

    repository = ExplorerRepository(
        rag_client=rag_client
    )

    workflow = ExplorerReviewWorkflow(
        rag_client=rag_client,
        explorer_repository=repository,
    )

    explorer_tools = ExplorerToolService(
        review_workflow=workflow,
        explorer_repository=repository,
        automator_client=automator_client,
    )

    result_tools = MetaStockResultToolService(
        automator_client=automator_client,
        result_client=rag_client,
    )

    registry = ToolRegistry(
        explorer_tool_service=explorer_tools,
        result_tool_service=result_tools,
    )
    print("=== AVAILABLE TOOLS ===")
    for tool in registry.list_tools():
        print("-", tool.name, "| enabled=", tool.enabled)

    print("\n=== GENERATE EXPLORER TOOL TEST ===")
    result = registry.execute(
        "generate_explorer",
        {
            "user_query": (
                "Find stocks where RSI is below 30 and close is above "
                "50 day moving average"
            )
        },
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
