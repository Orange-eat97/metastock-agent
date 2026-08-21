"""
RAG retrieval service.

Supabase source tables:

rag_cards
  card_id
  card_type
  card_bucket
  title
  category
  source_path
  body_markdown
  content_hash

rag_card_embeddings
  card_id
  embedding
  embedding_model
  content_hash

Registry / knowledge-graph layer:

rag_card_registry
  canonical_id
  concept_type
  source_path
  title
  card_bucket

rag_card_aliases
  canonical_id
  alias_text
  alias_type
  weight

rag_card_dependencies
  from_canonical_id
  to_canonical_id
  edge_type

Context-builder boundary:
  Context builder does not decompose the query.
  It tells RetrievalPlanner to build a plan, then applies the returned plan.

External contract stays unchanged:
    build_context_for_query(...) -> tuple[str, list[dict[str, Any]]]
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Literal

from dotenv import load_dotenv
from openai import OpenAI
from supabase import Client, create_client

from src.queryDecomposition.retrieval_planner import RetrievalPlanner
from src.retrieval.reranker import rerank_items


load_dotenv()


EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

DEFAULT_TOP_K = 12
DEFAULT_MAX_DYNAMIC_FILES = 10

# Pull a wider optional pool, then rerank down to DEFAULT_MAX_DYNAMIC_FILES.
# Forced registry cards do not use this budget and are still preserved first.
DEFAULT_OPTIONAL_VECTOR_POOL_MULTIPLIER = 3
DEFAULT_OPTIONAL_LEXICAL_POOL_PER_BUCKET = 80

RETRIEVAL_BACKEND = "supabase"
BASE_CONTEXT_SOURCE = "supabase.rag_cards"
DYNAMIC_CONTEXT_SOURCE = "supabase.rpc.match_rag_cards"
LEXICAL_CONTEXT_SOURCE = "supabase.rag_cards.local_bm25"
HYBRID_CONTEXT_SOURCE = "hybrid.vector_bm25_rerank"
FORCED_CONTEXT_SOURCE = "supabase.registry.resolve_rag_registry_cards"


BASE_CONTEXT_SOURCE_PATHS = [
    "references/price_fields.md",
    "templates/explorer_basic.md",
    "templates/explorer_columns_filter.md",
]

Bucket = Literal["patterns", "functions", "references"]


# ============================================================
# Environment / clients
# ============================================================


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


def make_supabase_client() -> Client:
    return create_client(
        require_env("SUPABASE_URL"),
        require_env("SUPABASE_SERVICE_ROLE_KEY"),
    )


def make_openai_client() -> OpenAI:
    return OpenAI(api_key=require_env("OPENAI_API_KEY"))


def create_query_embedding(openai_client: OpenAI, query: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )

    return response.data[0].embedding


# ============================================================
# Shared card helpers
# ============================================================


def normalize_filename(name: str) -> str:
    return name.strip().lower().replace("\\", "/")


def get_file_name_from_source_path(source_path: str) -> str:
    normalized = source_path.replace("\\", "/")
    return normalized.split("/")[-1]


def should_exclude_from_dynamic(source_path: str, title: str = "") -> bool:
    """
    Avoid retrieving mandatory base cards again as dynamic context.

    This preserves the previous behavior:
    - base templates are always included manually;
    - templates are not retrieved again dynamically;
    - price_fields is not retrieved again dynamically.
    """
    path = source_path.replace("\\", "/").lower()
    file_name = normalize_filename(get_file_name_from_source_path(path))

    base_names = {
        "price_fields.md",
        "explorer_basic.md",
        "explorer_columns_filter.md",
    }

    if file_name in base_names:
        return True

    if path.startswith("templates/"):
        return True

    if path == "references/price_fields.md":
        return True

    return False


def make_dynamic_item(
    row: dict[str, Any],
    *,
    retrieval_source: str = DYNAMIC_CONTEXT_SOURCE,
    score: float | None = None,
    retrieval_reason: str = "",
) -> dict[str, Any]:
    source_path = row.get("source_path", "")

    return {
        "file_name": get_file_name_from_source_path(source_path),
        "file_path": source_path,
        "card_id": row["card_id"],
        "title": row.get("title", ""),
        "card_type": row.get("card_type", ""),
        "card_bucket": row.get("card_bucket", ""),
        "category": row.get("category"),
        "score": float(score if score is not None else (row.get("similarity") or 0)),
        "text": row.get("body_markdown", ""),
        "retrieval_backend": RETRIEVAL_BACKEND,
        "retrieval_source": retrieval_source,
        "retrieval_reason": retrieval_reason,
    }


def dedupe_best_by_path(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate candidate items by source path, keeping the highest score."""
    best_by_file: dict[str, dict[str, Any]] = {}

    for item in items:
        key = normalize_filename(item.get("file_path", ""))
        if not key:
            continue

        current = best_by_file.get(key)
        if current is None or float(item.get("score") or 0) > float(current.get("score") or 0):
            best_by_file[key] = item

    return list(best_by_file.values())


# ============================================================
# Base context
# ============================================================


def fetch_cards_by_source_paths(
    supabase: Client,
    source_paths: list[str],
) -> list[dict[str, Any]]:
    response = (
        supabase.table("rag_cards")
        .select(
            "card_id,title,card_type,card_bucket,category,source_path,body_markdown"
        )
        .in_("source_path", source_paths)
        .execute()
    )

    rows = response.data or []

    by_path = {
        row["source_path"]: row
        for row in rows
    }

    ordered_rows: list[dict[str, Any]] = []
    missing_paths: list[str] = []

    for source_path in source_paths:
        row = by_path.get(source_path)

        if row is None:
            missing_paths.append(source_path)
            continue

        ordered_rows.append(row)

    if missing_paths:
        raise RuntimeError(
            "Missing mandatory base context cards in Supabase: "
            + ", ".join(missing_paths)
        )

    return ordered_rows


def load_base_context() -> str:
    """
    Fetch mandatory base context from Supabase instead of local markdown files.
    """
    print(f"[context_builder] Loading base context from {BASE_CONTEXT_SOURCE}")

    supabase = make_supabase_client()

    rows = fetch_cards_by_source_paths(
        supabase=supabase,
        source_paths=BASE_CONTEXT_SOURCE_PATHS,
    )

    parts: list[str] = []

    for row in rows:
        parts.append(
            f"## BASE CONTEXT FILE: {row['source_path']}\n"
            f"Card ID: {row['card_id']}\n"
            f"Title: {row['title']}\n"
            f"Retrieved from: {BASE_CONTEXT_SOURCE}\n\n"
            f"{row['body_markdown']}"
        )

    return "\n\n" + ("=" * 80) + "\n\n".join(parts)


# ============================================================
# Supabase retrieval primitives
# ============================================================


def retrieve_cards_from_supabase(
    supabase: Client,
    query_embedding: list[float],
    top_k: int,
    filter_card_type: str | None = None,
    filter_card_bucket: str | None = None,
) -> list[dict[str, Any]]:
    print(
        "[context_builder] Retrieving dynamic context from "
        f"{DYNAMIC_CONTEXT_SOURCE} | "
        f"top_k={top_k} | "
        f"filter_card_type={filter_card_type} | "
        f"filter_card_bucket={filter_card_bucket}"
    )

    response = supabase.rpc(
        "match_rag_cards",
        {
            "query_embedding": query_embedding,
            "match_count": top_k,
            "filter_card_type": filter_card_type,
            "filter_card_bucket": filter_card_bucket,
        },
    ).execute()

    return response.data or []


def fetch_lexical_candidate_rows(
    supabase: Client,
    *,
    filter_card_bucket: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch a small local BM25 candidate corpus from rag_cards.

    This is deliberately simple because the current knowledge base is card-sized
    rather than document-sized. It gives BM25 the chance to recover exact syntax
    terms such as Mov, RSI, Ref, HHV, LLV, Cross, ColA, and Bollinger function
    names even when dense vector retrieval misses them.
    """
    query = supabase.table("rag_cards").select(
        "card_id,title,card_type,card_bucket,category,source_path,body_markdown"
    )

    if filter_card_bucket:
        query = query.eq("card_bucket", filter_card_bucket)

    response = query.execute()
    return response.data or []


def retrieve_lexical_candidates(
    supabase: Client,
    *,
    filter_card_bucket: str | None = None,
    limit: int = DEFAULT_OPTIONAL_LEXICAL_POOL_PER_BUCKET,
) -> list[dict[str, Any]]:
    """
    Return lexical/BM25 candidate items before final hybrid reranking.

    The actual BM25 score is assigned in rerank_items(), where vector and lexical
    candidates are combined into one pool.
    """
    print(
        "[context_builder] Loading lexical candidate pool from "
        f"{LEXICAL_CONTEXT_SOURCE} | "
        f"filter_card_bucket={filter_card_bucket}"
    )

    rows = fetch_lexical_candidate_rows(
        supabase,
        filter_card_bucket=filter_card_bucket,
    )

    items: list[dict[str, Any]] = []
    for row in rows[:limit]:
        source_path = row.get("source_path", "")
        title = row.get("title", "")

        if should_exclude_from_dynamic(source_path=source_path, title=title):
            continue

        items.append(
            make_dynamic_item(
                row,
                retrieval_source=LEXICAL_CONTEXT_SOURCE,
                score=0.0,
                retrieval_reason=f"lexical_candidate; bucket={filter_card_bucket or 'all'}",
            )
        )

    return items


# ============================================================
# Hybrid optional retrieval
# ============================================================


def retrieve_unique_dynamic_context(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    max_dynamic_files: int = DEFAULT_MAX_DYNAMIC_FILES,
) -> list[dict[str, Any]]:
    """
    Non-planned fallback path.

    Before this change, this path used vector retrieval only. It now retrieves a
    wider vector pool, adds a lexical card pool, deduplicates, then reranks with
    vector + BM25 + metadata signals.
    """
    supabase = make_supabase_client()
    openai_client = make_openai_client()

    query_embedding = create_query_embedding(openai_client, query)

    vector_rows = retrieve_cards_from_supabase(
        supabase=supabase,
        query_embedding=query_embedding,
        top_k=max(top_k, max_dynamic_files * DEFAULT_OPTIONAL_VECTOR_POOL_MULTIPLIER),
        filter_card_type=None,
        filter_card_bucket=None,
    )

    candidates: list[dict[str, Any]] = []

    for row in vector_rows:
        source_path = row.get("source_path", "")
        title = row.get("title", "")

        if should_exclude_from_dynamic(source_path=source_path, title=title):
            continue

        candidates.append(
            make_dynamic_item(
                row,
                retrieval_source=DYNAMIC_CONTEXT_SOURCE,
                retrieval_reason="fallback_vector_candidate",
            )
        )

    candidates.extend(retrieve_lexical_candidates(supabase, filter_card_bucket=None))

    reranked = rerank_items(
        original_query=query,
        items=dedupe_best_by_path(candidates),
    )

    return reranked[:max_dynamic_files]


# ============================================================
# Planned dynamic retrieval
# ============================================================


def retrieve_planned_dynamic_context(
    query: str,
    max_dynamic_files: int = DEFAULT_MAX_DYNAMIC_FILES,
    debug_plan: bool = True,
) -> list[dict[str, Any]]:
    """
    Tell-style planned retrieval.

    Context builder tells RetrievalPlanner to build a plan.
    RetrievalPlanner owns decomposition, alias matching, canonical-ID collection,
    and registry dependency resolution.

    This function only applies the returned plan:
    1. force-include registry-resolved cards;
    2. run bucketed vector retrieval using planned subqueries;
    3. add lexical/BM25 candidates for optional retrieval;
    4. rerank optional candidates with vector + BM25 + metadata signals;
    5. return forced cards first, then reranked optional results.
    """
    supabase = make_supabase_client()
    openai_client = make_openai_client()

    plan = RetrievalPlanner(supabase=supabase).build_plan(query)

    if debug_plan:
        plan.print_summary()

    bucket_plan = {
        "patterns": {
            "top_k": 10,
            "min_keep": 1,
        },
        "functions": {
            "top_k": 10,
            "min_keep": 1,
        },
        "references": {
            "top_k": 6,
            "min_keep": 0,
        },
    }

    selected: list[dict[str, Any]] = []
    selected_paths: set[str] = set()

    # First: force-include registry-resolved cards.
    if plan.forced_cards:
        print("\n=== Forced Cards Matched From Supabase Registry ===")

    for card in plan.forced_cards:
        item = make_dynamic_item(
            card.to_rag_card_row(),
            retrieval_source=FORCED_CONTEXT_SOURCE,
            score=1.0,
            retrieval_reason=(
                f"forced_by_registry_plan; canonical_id={card.canonical_id}; "
                f"depth={card.depth}"
            ),
        )

        path = normalize_filename(item["file_path"])
        if path in selected_paths:
            continue

        print(f"- {item['title']} | {item['file_path']} | {card.canonical_id}")
        selected.append(item)
        selected_paths.add(path)

    if plan.missing_seed_canonical_ids:
        print("\n=== Registry Seed IDs Missing/Unresolved ===")
        for canonical_id in plan.missing_seed_canonical_ids:
            print(f"- {canonical_id}")

    # If forced cards already fill the allowed dynamic slots, stop here.
    # This prevents optional retrieval from displacing required cards.
    if len(selected) >= max_dynamic_files:
        return selected[:max_dynamic_files]

    # Second: build optional candidate pools by bucket.
    bucket_candidates: dict[str, list[dict[str, Any]]] = {
        bucket: []
        for bucket in bucket_plan
    }

    for bucket, plan_config in bucket_plan.items():
        queries = plan.retrieval_queries_by_bucket.get(bucket, [])

        for subquery in queries:
            query_embedding = create_query_embedding(openai_client, subquery)

            rows = retrieve_cards_from_supabase(
                supabase=supabase,
                query_embedding=query_embedding,
                top_k=plan_config["top_k"],
                filter_card_type=None,
                filter_card_bucket=bucket,
            )

            for row in rows:
                source_path = row.get("source_path", "")
                title = row.get("title", "")

                if should_exclude_from_dynamic(source_path=source_path, title=title):
                    continue

                key = normalize_filename(source_path)
                if key in selected_paths:
                    continue

                bucket_candidates[bucket].append(
                    make_dynamic_item(
                        row,
                        retrieval_source=DYNAMIC_CONTEXT_SOURCE,
                        retrieval_reason=f"vector_candidate; bucket={bucket}; subquery={subquery}",
                    )
                )

        # BM25 side of hybrid retrieval. This intentionally does not apply a
        # lexical score yet; rerank_items() scores the combined candidate pool.
        for item in retrieve_lexical_candidates(
            supabase,
            filter_card_bucket=bucket,
            limit=DEFAULT_OPTIONAL_LEXICAL_POOL_PER_BUCKET,
        ):
            key = normalize_filename(item.get("file_path", ""))
            if key in selected_paths:
                continue
            bucket_candidates[bucket].append(item)

    # Third: rerank within each bucket, then keep a small minimum from each
    # bucket so functions/patterns are not erased by one dominant bucket.
    bucket_results: dict[str, list[dict[str, Any]]] = {}
    for bucket, candidates in bucket_candidates.items():
        bucket_results[bucket] = rerank_items(
            original_query=query,
            items=dedupe_best_by_path(candidates),
            retrieval_queries_by_bucket=plan.retrieval_queries_by_bucket,
            target_bucket=bucket,
        )

    for bucket, plan_config in bucket_plan.items():
        for item in bucket_results[bucket][: plan_config["min_keep"]]:
            if len(selected) >= max_dynamic_files:
                break

            path = normalize_filename(item["file_path"])

            if path in selected_paths:
                continue

            selected.append(item)
            selected_paths.add(path)

    # Fourth: fill remaining slots by global hybrid rerank score.
    remaining: list[dict[str, Any]] = []

    for items in bucket_results.values():
        for item in items:
            path = normalize_filename(item["file_path"])

            if path not in selected_paths:
                remaining.append(item)

    remaining.sort(
        key=lambda x: (
            float(x.get("rerank_score") or x.get("score") or 0.0),
            float(x.get("bm25_score") or 0.0),
            float(x.get("vector_score") or 0.0),
        ),
        reverse=True,
    )

    for item in remaining:
        if len(selected) >= max_dynamic_files:
            break

        path = normalize_filename(item["file_path"])

        if path in selected_paths:
            continue

        selected.append(item)
        selected_paths.add(path)

    return selected[:max_dynamic_files]


def retrieve_tiered_dynamic_context(
    query: str,
    max_dynamic_files: int = DEFAULT_MAX_DYNAMIC_FILES,
) -> list[dict[str, Any]]:
    """
    Backward-compatible public function name.

    The old implementation retrieved the same query once per bucket. The current
    implementation keeps tiered retrieval but routes planning through
    RetrievalPlanner, so required cards can be resolved through the registry
    before optional hybrid vector/BM25 retrieval is added.
    """
    return retrieve_planned_dynamic_context(
        query=query,
        max_dynamic_files=max_dynamic_files,
        debug_plan=True,
    )


# ============================================================
# Context formatting / public API
# ============================================================


def format_dynamic_context(items: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []

    for i, item in enumerate(items, start=1):
        rerank_debug = ""
        if "rerank_score" in item:
            rerank_debug = (
                f"Rerank score: {float(item.get('rerank_score') or 0):.4f}\n"
                f"Vector score: {float(item.get('vector_score') or 0):.4f}\n"
                f"BM25 score: {float(item.get('bm25_score') or 0):.4f}\n"
                f"Metadata score: {float(item.get('metadata_score') or 0):.4f}\n"
            )

        parts.append(
            f"## RETRIEVED CONTEXT {i}: {item['file_name']}\n"
            f"Card ID: {item['card_id']}\n"
            f"Title: {item['title']}\n"
            f"Source path: {item['file_path']}\n"
            f"Card bucket: {item['card_bucket']}\n"
            f"Retrieval backend: {item.get('retrieval_backend', 'unknown')}\n"
            f"Retrieval source: {item.get('retrieval_source', 'unknown')}\n"
            f"Retrieval reason: {item.get('retrieval_reason', '')}\n"
            f"Retrieval score: {item['score']:.4f}\n"
            f"{rerank_debug}\n"
            f"{item['text']}"
        )

    if not parts:
        return "## RETRIEVED CONTEXT\n\nNo dynamic context retrieved."

    return "\n\n" + ("=" * 80) + "\n\n".join(parts)


def build_context_for_query(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    max_dynamic_files: int = DEFAULT_MAX_DYNAMIC_FILES,
    use_tiered_dynamic: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Returns:
      final_context: base context + dynamic retrieved context
      dynamic_items: retrieved unique files, useful for logging/debugging

    This function keeps the old external contract used by generate_explorer.py.
    """
    base_context = load_base_context()

    if use_tiered_dynamic:
        dynamic_items = retrieve_tiered_dynamic_context(
            query=query,
            max_dynamic_files=max_dynamic_files,
        )
    else:
        dynamic_items = retrieve_unique_dynamic_context(
            query=query,
            top_k=top_k,
            max_dynamic_files=max_dynamic_files,
        )

    dynamic_context = format_dynamic_context(dynamic_items)

    final_context = (
        "# Mandatory Base Context\n"
        f"{base_context}\n\n"
        "# Dynamic Retrieved Context\n"
        f"{dynamic_context}"
    )

    return final_context, dynamic_items
