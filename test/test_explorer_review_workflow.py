from services.explorer_repository import ExplorerRepository
from services.rag_client import LocalRagClient
from workflows.explorer_review_workflow import ExplorerReviewWorkflow


RAG_REPO_PATH = r"C:\GitHub\metastock-RAG-LLM"


def main() -> None:
    workflow = ExplorerReviewWorkflow(
        rag_client=LocalRagClient(rag_repo_path=RAG_REPO_PATH),
        explorer_repository=ExplorerRepository(),
    )

    state = workflow.generate_for_review(
        "Find stocks where RSI is below 30 and close is above 50 day moving average"
    )

    print("=== REVIEW STATE ===")
    print("explorer_id:", state.explorer_id)
    print("explorer_created_at:", state.explorer_created_at)
    print("service_log_id:", state.service_log_id)
    print("validation_passed:", state.validation_passed)
    print("can_run_in_metastock:", state.can_run_in_metastock)
    print("can_repair:", state.can_repair)

    print("\n=== EXPLORER PREVIEW ===")
    print("name:", state.explorer_row["explorer_name"])
    print("description:", state.explorer_row["explorer_description"])
    print("filter:", state.explorer_row["explorer_code_body"])
    print("columns:", state.explorer_row["col_definitions"])

    print("\n=== VALIDATION ===")
    print(state.validation_errors)

    if state.service_log_row:
        print("\n=== LOG PREVIEW ===")
        print(state.service_log_row["stdout_text"][:1500])


if __name__ == "__main__":
    main()