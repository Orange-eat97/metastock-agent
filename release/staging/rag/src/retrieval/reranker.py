"""
Hybrid lexical/vector reranking helpers for MetaStock RAG retrieval.

This module is intentionally dependency-light. It implements a small BM25 scorer
locally so the retrieval layer can combine Supabase vector search with lexical
signals without adding rank-bm25 or another package.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|\d+(?:\.\d+)?")

# Very broad words that should not dominate BM25 scoring.
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "find",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "over",
    "price",
    "stock",
    "stocks",
    "the",
    "to",
    "where",
    "with",
}

# Exact syntax-like terms are highly valuable for MetaStock retrieval.
METASTOCK_SYNTAX_TERMS = {
    "mov",
    "rsi",
    "ref",
    "cross",
    "hhv",
    "llv",
    "sum",
    "if",
    "roc",
    "macd",
    "atr",
    "bbandtop",
    "bbandbot",
    "stoch",
    "valuewhen",
    "barssince",
    "prev",
    "colA".lower(),
    "colB".lower(),
    "colC".lower(),
}

# Cards that are useful only when explicitly requested should not win optional
# retrieval just because their aliases are generic.
GENERIC_CARD_PENALTY_MARKERS = {
    "logical_operators",
    "logical operators",
    "system_tester_vs_explorer",
    "commentary_writeif_writeval",
}

REFERENCE_QUERY_HINTS = {
    "lookahead",
    "future",
    "repaint",
    "zigzag",
    "explorer",
    "cola",
    "colb",
    "column",
    "columns",
    "system tester",
    "opt",
    "simulation",
    "writeif",
    "writeval",
    "limitation",
    "limitations",
}


@dataclass(frozen=True)
class RerankWeights:
    """Weights used to combine vector, BM25, and deterministic card signals."""

    vector: float = 0.55
    bm25: float = 0.35
    metadata: float = 0.10


@dataclass(frozen=True)
class RerankConfig:
    weights: RerankWeights = RerankWeights()
    k1: float = 1.5
    b: float = 0.75
    syntax_term_bonus: float = 0.10
    title_exact_bonus: float = 0.08
    bucket_match_bonus: float = 0.06
    pattern_bonus: float = 0.04
    generic_penalty: float = 0.14
    weak_reference_penalty: float = 0.06


def tokenize(text: str) -> list[str]:
    """Tokenize text for lexical scoring."""
    tokens = [match.group(0).lower() for match in TOKEN_RE.finditer(text or "")]
    return [token for token in tokens if token not in STOPWORDS]


def build_query_text(
    original_query: str,
    retrieval_queries_by_bucket: dict[str, list[str]] | None = None,
    *,
    bucket: str | None = None,
) -> str:
    """
    Create the lexical query used for BM25.

    For planned retrieval, include the original user query plus the safe/planned
    subqueries for the same bucket. This lets BM25 prefer cards that match the
    decomposed intent, without letting unsafe missing-concept spans dominate.
    """
    parts = [original_query]

    if retrieval_queries_by_bucket:
        if bucket:
            parts.extend(retrieval_queries_by_bucket.get(bucket, []))
        else:
            for queries in retrieval_queries_by_bucket.values():
                parts.extend(queries)

    return " ".join(part for part in parts if str(part or "").strip())


def card_text(item: dict[str, Any]) -> str:
    """Build a searchable text representation of a retrieved card item."""
    return "\n".join(
        str(part or "")
        for part in [
            item.get("title"),
            item.get("card_type"),
            item.get("card_bucket"),
            item.get("category"),
            item.get("file_path"),
            item.get("retrieval_reason"),
            item.get("text"),
        ]
    )


def compute_bm25_scores(
    query: str,
    items: list[dict[str, Any]],
    *,
    config: RerankConfig = RerankConfig(),
) -> dict[str, float]:
    """Return normalized BM25 scores keyed by each item's file path."""
    query_terms = tokenize(query)
    if not query_terms or not items:
        return {str(item.get("file_path", "")): 0.0 for item in items}

    documents = [tokenize(card_text(item)) for item in items]
    doc_count = len(documents)
    avg_doc_len = sum(len(doc) for doc in documents) / max(doc_count, 1)

    doc_freq: dict[str, int] = {}
    for doc in documents:
        for term in set(doc):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    raw_scores: dict[str, float] = {}

    for item, doc in zip(items, documents, strict=True):
        term_counts: dict[str, int] = {}
        for term in doc:
            term_counts[term] = term_counts.get(term, 0) + 1

        doc_len = len(doc) or 1
        score = 0.0

        for term in query_terms:
            freq = term_counts.get(term, 0)
            if freq == 0:
                continue

            df = doc_freq.get(term, 0)
            idf = math.log(1 + ((doc_count - df + 0.5) / (df + 0.5)))
            denominator = freq + config.k1 * (
                1 - config.b + config.b * (doc_len / max(avg_doc_len, 1e-9))
            )
            score += idf * ((freq * (config.k1 + 1)) / denominator)

        raw_scores[str(item.get("file_path", ""))] = score

    max_score = max(raw_scores.values(), default=0.0)
    if max_score <= 0:
        return {key: 0.0 for key in raw_scores}

    return {key: value / max_score for key, value in raw_scores.items()}


def normalize_vector_scores(items: list[dict[str, Any]]) -> dict[str, float]:
    """Normalize the vector/retrieval score already present on items."""
    raw = {
        str(item.get("file_path", "")): float(item.get("score") or 0.0)
        for item in items
    }
    max_score = max(raw.values(), default=0.0)

    if max_score <= 0:
        return {key: 0.0 for key in raw}

    return {key: value / max_score for key, value in raw.items()}


def metadata_score(
    *,
    query_text: str,
    item: dict[str, Any],
    target_bucket: str | None = None,
    config: RerankConfig = RerankConfig(),
) -> float:
    """Deterministic boosts/penalties for MetaStock retrieval quality."""
    normalized_query = " ".join(query_text.lower().split())
    title = str(item.get("title") or "").lower()
    path = str(item.get("file_path") or "").lower()
    bucket = str(item.get("card_bucket") or "").lower()
    text = card_text(item).lower()

    score = 0.0

    if target_bucket and bucket == target_bucket:
        score += config.bucket_match_bonus

    if bucket == "patterns":
        score += config.pattern_bonus

    for term in METASTOCK_SYNTAX_TERMS:
        if term in normalized_query and term in text:
            score += config.syntax_term_bonus

    # If a meaningful title phrase appears in the query, boost it. Avoid
    # one-word generic title boosts such as "breakout" winning over a more
    # specific Bollinger breakout card when the latter also matches.
    title_tokens = [token for token in tokenize(title) if len(token) >= 3]
    if len(title_tokens) >= 2:
        title_phrase = " ".join(title_tokens)
        if title_phrase in normalized_query:
            score += config.title_exact_bonus

    if any(marker in path or marker in title for marker in GENERIC_CARD_PENALTY_MARKERS):
        score -= config.generic_penalty

    if bucket == "references" and not any(hint in normalized_query for hint in REFERENCE_QUERY_HINTS):
        score -= config.weak_reference_penalty

    return score


def rerank_items(
    *,
    original_query: str,
    items: Iterable[dict[str, Any]],
    retrieval_queries_by_bucket: dict[str, list[str]] | None = None,
    target_bucket: str | None = None,
    config: RerankConfig = RerankConfig(),
) -> list[dict[str, Any]]:
    """
    Rerank candidate items using vector score + local BM25 + metadata signals.

    The returned items keep the existing shape expected by context_builder, but
    include debug fields:
      - vector_score
      - bm25_score
      - metadata_score
      - rerank_score
    """
    candidates = list(items)
    if not candidates:
        return []

    query_text = build_query_text(
        original_query,
        retrieval_queries_by_bucket=retrieval_queries_by_bucket,
        bucket=target_bucket,
    )

    bm25_scores = compute_bm25_scores(query_text, candidates, config=config)
    vector_scores = normalize_vector_scores(candidates)

    reranked: list[dict[str, Any]] = []

    for item in candidates:
        key = str(item.get("file_path", ""))
        vector_score = vector_scores.get(key, 0.0)
        bm25_score = bm25_scores.get(key, 0.0)
        meta_score = metadata_score(
            query_text=query_text,
            item=item,
            target_bucket=target_bucket,
            config=config,
        )
        final_score = (
            config.weights.vector * vector_score
            + config.weights.bm25 * bm25_score
            + config.weights.metadata * meta_score
        )

        enriched = dict(item)
        enriched["vector_score"] = vector_score
        enriched["bm25_score"] = bm25_score
        enriched["metadata_score"] = meta_score
        enriched["rerank_score"] = final_score
        enriched["score"] = final_score

        reason = str(enriched.get("retrieval_reason") or "")
        if "hybrid_rerank" not in reason:
            reason = f"{reason}; hybrid_rerank=vector+bm25+metadata".strip("; ")
        enriched["retrieval_reason"] = reason

        reranked.append(enriched)

    reranked.sort(
        key=lambda x: (
            float(x.get("rerank_score") or 0.0),
            float(x.get("bm25_score") or 0.0),
            float(x.get("vector_score") or 0.0),
        ),
        reverse=True,
    )

    return reranked
