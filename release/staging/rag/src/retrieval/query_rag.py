from __future__ import annotations

from dotenv import load_dotenv

from src.retrieval.context_builder import (
    retrieve_tiered_dynamic_context,
    retrieve_unique_dynamic_context,
)


load_dotenv()


def print_titles(items: list[dict]) -> None:
    if not items:
        print("No dynamic cards retrieved.")
        return

    for i, item in enumerate(items, start=1):
        print(
            f"{i}. {item['title']} "
            f"({item['card_id']}, bucket={item['card_bucket']}, "
            f"score={item['score']:.4f}, path={item['file_path']})"
        )


def print_full(items: list[dict]) -> None:
    if not items:
        print("No dynamic cards retrieved.")
        return

    for i, item in enumerate(items, start=1):
        print(f"\n--- Result {i} ---")
        print(f"Title: {item['title']}")
        print(f"Card ID: {item['card_id']}")
        print(f"Bucket: {item['card_bucket']}")
        print(f"Score: {item['score']:.4f}")
        print(f"Path: {item['file_path']}")
        print("-" * 60)
        print(item["text"][:1200])


def main() -> None:
    print("[query_rag] Supabase RAG mode.")
    print("[query_rag] Type 'exit' to quit.")
    print("[query_rag] Prefix with 'full:' to print card text.")
    print("[query_rag] Prefix with 'global:' to use non-tiered global retrieval.")

    while True:
        query = input("\nUser query: ").strip()

        if query.lower() in {"exit", "quit"}:
            break

        if not query:
            continue

        show_full = False
        use_global = False

        if query.lower().startswith("full:"):
            show_full = True
            query = query[5:].strip()

        if query.lower().startswith("global:"):
            use_global = True
            query = query[7:].strip()

        if not query:
            continue

        if use_global:
            items = retrieve_unique_dynamic_context(query=query)
        else:
            items = retrieve_tiered_dynamic_context(query=query)

        print("\n=== Retrieved Cards ===")

        if show_full:
            print_full(items)
        else:
            print_titles(items)


if __name__ == "__main__":
    main()