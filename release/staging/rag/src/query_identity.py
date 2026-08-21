from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from openai import OpenAI


DEFAULT_QUERY_EMBEDDING_MODEL = (
    "text-embedding-3-small"
)


@dataclass(frozen=True)
class QueryIdentity:
    original: str
    normalized: str
    query_hash: str

    embedding_model: str | None = None
    embedding: list[float] | None = None


def normalize_user_query(value: str) -> str:
    """
    Normalize superficial textual differences without changing strategy
    meaning.

    This intentionally preserves:
    - numbers;
    - operators;
    - AND / OR;
    - technical terms;
    - direction words;
    - periods and thresholds inside the query.
    """
    text = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    )

    text = text.casefold().strip()

    # Normalize spacing around comparison operators.
    text = re.sub(
        r"\s*(<=|>=|<>|=|<|>)\s*",
        r"\1",
        text,
    )

    # Terminal punctuation does not alter strategy semantics.
    text = re.sub(
        r"[.!?。！？]+$",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def hash_normalized_query(
    normalized_query: str,
) -> str:
    return hashlib.sha256(
        normalized_query.encode("utf-8")
    ).hexdigest()


def build_query_identity(
    user_query: str,
    *,
    include_embedding: bool,
    embedding_model: str = (
        DEFAULT_QUERY_EMBEDDING_MODEL
    ),
    client: OpenAI | None = None,
) -> QueryIdentity:
    original = str(user_query or "").strip()

    if not original:
        raise ValueError(
            "user_query is required."
        )

    normalized = normalize_user_query(
        original
    )

    query_hash = hash_normalized_query(
        normalized
    )

    if not include_embedding:
        return QueryIdentity(
            original=original,
            normalized=normalized,
            query_hash=query_hash,
        )

    openai_client = client or OpenAI()

    response = (
        openai_client.embeddings.create(
            model=embedding_model,
            input=normalized,
        )
    )

    if not response.data:
        raise RuntimeError(
            "Query embedding returned no data."
        )

    embedding = list(
        response.data[0].embedding
    )

    return QueryIdentity(
        original=original,
        normalized=normalized,
        query_hash=query_hash,
        embedding_model=embedding_model,
        embedding=embedding,
    )