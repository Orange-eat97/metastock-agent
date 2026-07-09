from services.rag_client import LocalRagClient


RAG_REPO_PATH = r"C:\GitHub\metastock-RAG-LLM"


def main() -> None:
    client = LocalRagClient(rag_repo_path=RAG_REPO_PATH)

    result = client.generate_explorer(
        "Find stocks where RSI is below 30 and close is above 50 day moving average"
    )

    print("=== RAG RESULT ===")
    print(result)

    explorer_row = client.get_explorer(result.explorer)

    print("\n=== EXPLORER ROW ===")
    print("id:", explorer_row["id"])
    print("created_at:", explorer_row["created_at"])
    print("name:", explorer_row["explorer_name"])
    print("filter:", explorer_row["explorer_code_body"])
    print("validation_passed:", explorer_row["validation_passed"])
    print("validation_errors:", explorer_row["validation_errors"])

    if result.service_log:
        log_row = client.get_service_log(result.service_log)

        print("\n=== SERVICE LOG ===")
        print("log_id:", log_row["log_id"])
        print("created_at:", log_row["created_at"])
        print("event_type:", log_row["event_type"])
        print("stdout preview:")
        print(log_row["stdout_text"][:1000])


if __name__ == "__main__":
    main()