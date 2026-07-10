from __future__ import annotations

from services.explorer_repository import ExplorerRepository
from services.rag_client import LocalRagClient
from tools.explorer_tools import ExplorerToolService
from tools.tool_registry import ToolRegistry
from workflows.explorer_review_workflow import ExplorerReviewWorkflow


RAG_REPO_PATH = r"C:\GitHub\metastock-RAG-LLM"


def build_registry() -> ToolRegistry:
    rag_client = LocalRagClient(rag_repo_path=RAG_REPO_PATH)
    repository = ExplorerRepository(rag_client=rag_client)

    workflow = ExplorerReviewWorkflow(
        rag_client=rag_client,
        explorer_repository=repository,
    )

    explorer_tools = ExplorerToolService(
        review_workflow=workflow,
        explorer_repository=repository,
    )

    return ToolRegistry(explorer_tool_service=explorer_tools)


def main() -> None:
    registry = build_registry()

    print("=== STEP 1: GENERATE EXPLORER ===")

    generate_result = registry.execute(
        "generate_explorer",
        {
            "user_query": (
                "Find stocks where RSI is below 30 and close is above "
                "50 day moving average"
            )
        },
    )

    print("generate_explorer ok:", generate_result.ok)
    print("generate_explorer status:", generate_result.status)
    print("generate_explorer message:", generate_result.message)

    if not generate_result.ok:
        print(generate_result.model_dump_json(indent=2))
        raise RuntimeError("generate_explorer failed.")

    explorer_data = generate_result.data["explorer"]

    explorer_id = explorer_data["explorer_id"]
    service_log_id = explorer_data["service_log_id"]

    print("explorer_id:", explorer_id)
    print("service_log_id:", service_log_id)

    if not explorer_id:
        raise RuntimeError("generate_explorer did not return explorer_id.")

    if not service_log_id:
        raise RuntimeError("generate_explorer did not return service_log_id.")

    print("\n=== STEP 2: GET EXPLORER BY ID ===")

    get_explorer_result = registry.execute(
        "get_explorer",
        {
            "explorer_id": explorer_id,
        },
    )

    print("get_explorer ok:", get_explorer_result.ok)
    print("get_explorer status:", get_explorer_result.status)
    print("get_explorer message:", get_explorer_result.message)

    if not get_explorer_result.ok:
        print(get_explorer_result.model_dump_json(indent=2))
        raise RuntimeError("get_explorer failed.")

    fetched_explorer = get_explorer_result.data["explorer"]

    print("fetched explorer name:", fetched_explorer["name"])
    print("fetched validation passed:", fetched_explorer["validation"]["passed"])
    print("fetched filter code:", fetched_explorer["filter_code"])

    if fetched_explorer["explorer_id"] != explorer_id:
        raise RuntimeError(
            "get_explorer returned a different explorer_id. "
            f"Expected {explorer_id}, got {fetched_explorer['explorer_id']}."
        )

    print("\n=== STEP 3: GET RAG LOG BY ID ===")

    get_log_result = registry.execute(
        "get_rag_log",
        {
            "log_id": service_log_id,
        },
    )

    print("get_rag_log ok:", get_log_result.ok)
    print("get_rag_log status:", get_log_result.status)
    print("get_rag_log message:", get_log_result.message)

    if not get_log_result.ok:
        print(get_log_result.model_dump_json(indent=2))
        raise RuntimeError("get_rag_log failed.")

    fetched_log = get_log_result.data

    print("log_id:", fetched_log["log_id"])
    print("event_type:", fetched_log["event_type"])
    print("created_at:", fetched_log["created_at"])
    print("stdout preview:")
    print((fetched_log["stdout_text"] or "")[:500])

    if fetched_log["log_id"] != service_log_id:
        raise RuntimeError(
            "get_rag_log returned a different log_id. "
            f"Expected {service_log_id}, got {fetched_log['log_id']}."
        )

    print("\n=== STEP 4: DISABLED TOOL SHOULD BE BLOCKED ===")

    run_result = registry.execute(
        "run_explorer_in_metastock",
        {
            "explorer_id": explorer_id,
            "instruments": "all",
        },
    )

    print("run_explorer_in_metastock ok:", run_result.ok)
    print("run_explorer_in_metastock status:", run_result.status)
    print("run_explorer_in_metastock message:", run_result.message)

    if run_result.ok:
        raise RuntimeError("Disabled run_explorer_in_metastock unexpectedly succeeded.")

    print("\n=== ALL READ PATH TESTS PASSED ===")


if __name__ == "__main__":
    main()