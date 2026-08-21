from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from numpy import identity
from supabase import create_client, Client

from src.query_identity import (
    QueryIdentity,
    build_query_identity,
)

load_dotenv()


TABLE_NAME = "explorer_outputs"

EXPLORER_CACHE_SELECT = (
    "id, created_at, backend, model, user_query, "
    "user_query_normalized, user_query_hash, "
    "user_query_embedding_model, "
    "full_output_json, validation_passed, "
    "validation_errors, retrieved_refs, "
    "service_log_id, repaired_from_explorer_id, "
    "repair_instruction, revised_from_explorer_id, "
    "revision_instruction"
)

def _get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url:
        raise RuntimeError("Missing SUPABASE_URL in .env")

    if not key:
        raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY in .env")

    return create_client(url, key)


def save_explorer_output_to_supabase(
    *,
    output: dict[str, Any],
    user_query: str,
    backend: str,
    model: str,
    validation_errors: list[str] | None = None,
    retrieved_refs: list[dict[str, Any]] | None = None,
    repaired_from_explorer_id: str | None = None,
    repair_instruction: str | None = None,
    revised_from_explorer_id: str | None = None,
    revision_instruction: str | None = None,
    query_identity: QueryIdentity | None = None,
) -> str:
    
    """
    Insert one generated Explorer object into Supabase.

    Returns:
        explorer_outputs.id
    """
    validation_errors = validation_errors or []
    retrieved_refs = retrieved_refs or []

    explorer_name = str(output.get("explorer_name", "")).strip()
    explorer_description = str(output.get("explorer_description", "")).strip()
    explorer_code_body = str(output.get("explorer_code_body", "")).strip()
    col_definitions = output.get("col_definitions", [])

    if not explorer_name:
        raise ValueError("Cannot save to Supabase: explorer_name is empty.")

    if not explorer_code_body:
        raise ValueError("Cannot save to Supabase: explorer_code_body is empty.")

    if not isinstance(col_definitions, list):
        raise ValueError("Cannot save to Supabase: col_definitions must be a list.")

    if not isinstance(retrieved_refs, list):
        raise ValueError("Cannot save to Supabase: retrieved_refs must be a list.")

    repaired_from_explorer_id = (
        str(repaired_from_explorer_id).strip()
        if repaired_from_explorer_id
        else None
    )
    repair_instruction = (
        str(repair_instruction).strip()
        if repair_instruction and str(repair_instruction).strip()
        else None
    )
    revised_from_explorer_id = (
        str(revised_from_explorer_id).strip()
        if revised_from_explorer_id
        else None
    )
    revision_instruction = (
        str(revision_instruction).strip()
        if revision_instruction
        and str(revision_instruction).strip()
        else None
    )

    if bool(repaired_from_explorer_id) and bool(revised_from_explorer_id):
        raise ValueError(
            "An Explorer row cannot be both a repair and a revision."
        )

    validation_passed = len(validation_errors) == 0

    identity = (
        query_identity
        or build_query_identity(
            user_query,
            include_embedding=False,
        )
    )

    if not identity.original.strip():
        raise ValueError(
            "query_identity.original is required."
        )

    row = {
        "backend": backend,
        "model": model,
        "user_query": user_query,
        "user_query_normalized": (
            identity.normalized
        ),
        "user_query_hash": (
            identity.query_hash
        ),
        "user_query_embedding": (
            identity.embedding
        ),
        "user_query_embedding_model": (
            identity.embedding_model
        ),

        "explorer_name": explorer_name,
        "explorer_description": explorer_description,
        "explorer_code_body": explorer_code_body,

        "col_definitions": col_definitions,
        "full_output_json": output,

        "validation_passed": validation_passed,
        "validation_errors": validation_errors,

        "retrieved_refs": retrieved_refs,
        "repaired_from_explorer_id": repaired_from_explorer_id,
        "repair_instruction": repair_instruction,
        "revised_from_explorer_id": revised_from_explorer_id,
        "revision_instruction": revision_instruction,

        "status": "generated",
    }

    client = _get_supabase_client()

    response = (
        client
        .table(TABLE_NAME)
        .insert(row)
        .execute()
    )

    if not response.data:
        raise RuntimeError(f"Supabase insert returned no data: {response}")

    inserted = response.data[0]
    explorer_id = inserted.get("id")

    if not explorer_id:
        raise RuntimeError(f"Supabase insert did not return id: {inserted}")

    return explorer_id


def update_explorer_service_log_id(
    *,
    explorer_id: str,
    service_log_id: str,
) -> None:
    """Attach the creation/repair RAG log to an existing Explorer row."""
    cleaned_explorer_id = str(explorer_id or "").strip()
    cleaned_service_log_id = str(service_log_id or "").strip()

    if not cleaned_explorer_id:
        raise ValueError("explorer_id is required.")

    if not cleaned_service_log_id:
        raise ValueError("service_log_id is required.")

    client = _get_supabase_client()

    response = (
        client
        .table(TABLE_NAME)
        .update({"service_log_id": cleaned_service_log_id})
        .eq("id", cleaned_explorer_id)
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Supabase update did not return an explorer_outputs row for "
            f"id={cleaned_explorer_id}"
        )

def find_cached_explorer_output_by_query(
    *,
    user_query: str,
    require_validation_passed: bool = True,
    model: str | None = None,
) -> dict[str, Any] | None:
    """
    Find the newest stored Explorer with the same normalized query.

    A legacy raw exact-match fallback remains so deployment can be performed
    before every existing row has been backfilled.
    """
    identity = build_query_identity(
        user_query,
        include_embedding=False,
    )

    client = _get_supabase_client()

    request = (
        client
        .table(TABLE_NAME)
        .select(EXPLORER_CACHE_SELECT)
        .eq(
            "user_query_hash",
            identity.query_hash,
        )
        .order(
            "created_at",
            desc=True,
        )
        .limit(1)
    )

    if require_validation_passed:
        request = request.eq(
            "validation_passed",
            True,
        )

    if model:
        request = request.eq(
            "model",
            model,
        )

    response = request.execute()

    if response.data:
        row = response.data[0]

        # Verify the normalized text as well as the hash.
        if (
            str(
                row.get(
                    "user_query_normalized"
                )
                or ""
            )
            == identity.normalized
        ):
            row["_cache_match_type"] = (
                "normalized_exact"
            )
            row["_cache_matched_query"] = (
                row.get("user_query")
            )
            return _validate_cached_row(row)

    legacy_request = (
        client
        .table(TABLE_NAME)
        .select(EXPLORER_CACHE_SELECT)
        .eq(
            "user_query",
            identity.original,
        )
        .order(
            "created_at",
            desc=True,
        )
        .limit(1)
    )

    if require_validation_passed:
        legacy_request = (
            legacy_request.eq(
                "validation_passed",
                True,
            )
        )

    if model:
        legacy_request = (
            legacy_request.eq(
                "model",
                model,
            )
        )

    legacy_response = (
        legacy_request.execute()
    )

    if not legacy_response.data:
        return None

    row = legacy_response.data[0]
    row["_cache_match_type"] = (
        "legacy_exact"
    )
    row["_cache_matched_query"] = (
        row.get("user_query")
    )

    return _validate_cached_row(row)


def _validate_cached_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    full_output = row.get(
        "full_output_json"
    )

    if not isinstance(
        full_output,
        dict,
    ):
        raise ValueError(
            "Cached row "
            f"{row.get('id')} has invalid "
            "full_output_json."
        )

    return row


def find_explorer_cache_row_by_id(
    explorer_id: str,
) -> dict[str, Any] | None:
    cleaned_id = str(
        explorer_id or ""
    ).strip()

    if not cleaned_id:
        raise ValueError(
            "explorer_id is required."
        )

    response = (
        _get_supabase_client()
        .table(TABLE_NAME)
        .select(EXPLORER_CACHE_SELECT)
        .eq("id", cleaned_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return _validate_cached_row(
        response.data[0]
    )


def find_semantic_explorer_candidates(
    *,
    query_embedding: list[float],
    embedding_model: str,
    generation_model: str,
    min_similarity: float,
    match_count: int,
) -> list[dict[str, Any]]:
    if not query_embedding:
        return []

    response = (
        _get_supabase_client()
        .rpc(
            "match_explorer_query_cache",
            {
                "p_query_embedding": (
                    query_embedding
                ),
                "p_embedding_model": (
                    embedding_model
                ),
                "p_generation_model": (
                    generation_model
                ),
                "p_min_similarity": (
                    min_similarity
                ),
                "p_match_count": (
                    match_count
                ),
            },
        )
        .execute()
    )

    candidates: list[
        dict[str, Any]
    ] = []

    for item in response.data or []:
        if not isinstance(item, dict):
            continue

        explorer_id = str(
            item.get("explorer_id")
            or ""
        ).strip()

        if not explorer_id:
            continue

        try:
            similarity = float(
                item.get("similarity")
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        candidates.append(
            {
                "explorer_id": (
                    explorer_id
                ),
                "similarity": (
                    similarity
                ),
            }
        )

    return candidates