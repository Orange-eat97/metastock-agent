from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, Field

from src.query_identity import (
    QueryIdentity,
    build_query_identity,
)
from src.supabase_store import (
    find_cached_explorer_output_by_query,
    find_explorer_cache_row_by_id,
    find_semantic_explorer_candidates,
)


class QueryEquivalenceDecision(
    BaseModel
):
    equivalent: bool

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    material_differences: list[str] = (
        Field(default_factory=list)
    )

    reason: str


@dataclass(frozen=True)
class DuplicateExplorerMatch:
    row: dict
    match_type: str

    similarity: float | None = None
    equivalence_confidence: (
        float | None
    ) = None
    equivalence_reason: (
        str | None
    ) = None


@dataclass(frozen=True)
class DuplicateCheckResult:
    identity: QueryIdentity
    match: (
        DuplicateExplorerMatch | None
    )
    semantic_error: str | None = None


class ExplorerQueryDuplicateGuard:
    """
    Stops a new generation only when:

    1. the normalized query is identical; or
    2. vector retrieval finds a strong candidate and the strict equivalence
       verifier confirms there are no material strategy differences.
    """

    def __init__(
        self,
        *,
        embedding_model: str,
        equivalence_model: str,
        min_similarity: float = 0.75,
        min_equivalence_confidence: (
            float
        ) = 0.97,
        max_candidates: int = 5,
        openai_client: OpenAI | None = None,
    ) -> None:
        self.embedding_model = (
            embedding_model
        )
        self.equivalence_model = (
            equivalence_model
        )
        self.min_similarity = (
            min_similarity
        )
        self.min_equivalence_confidence = (
            min_equivalence_confidence
        )
        self.max_candidates = (
            max_candidates
        )
        self._openai_client = (
            openai_client
        )

    def check(
        self,
        *,
        user_query: str,
        generation_model: str,
        semantic_enabled: bool,
    ) -> DuplicateCheckResult:
        identity = build_query_identity(
            user_query,
            include_embedding=False,
        )

        exact = (
            find_cached_explorer_output_by_query(
                user_query=user_query,
                require_validation_passed=True,
                model=generation_model,
            )
        )

        if exact is not None:
            return DuplicateCheckResult(
                identity=identity,
                match=DuplicateExplorerMatch(
                    row=exact,
                    match_type=str(
                        exact.get(
                            "_cache_match_type"
                        )
                        or "normalized_exact"
                    ),
                ),
            )

        if not semantic_enabled:
            return DuplicateCheckResult(
                identity=identity,
                match=None,
            )

        try:
            identity = (
                build_query_identity(
                    user_query,
                    include_embedding=True,
                    embedding_model=(
                        self.embedding_model
                    ),
                    client=(
                        self._openai_client
                    ),
                )
            )

            candidates = (
                find_semantic_explorer_candidates(
                    query_embedding=(
                        identity.embedding
                        or []
                    ),
                    embedding_model=(
                        self.embedding_model
                    ),
                    generation_model=(
                        generation_model
                    ),
                    min_similarity=(
                        self.min_similarity
                    ),
                    match_count=(
                        self.max_candidates
                    ),
                )
            )

            for candidate in candidates:
                row = (
                    find_explorer_cache_row_by_id(
                        candidate[
                            "explorer_id"
                        ]
                    )
                )

                if row is None:
                    continue

                decision = (
                    self._verify_equivalence(
                        new_query=user_query,
                        existing_row=row,
                    )
                )

                if not decision.equivalent:
                    continue

                if (
                    decision.material_differences
                ):
                    continue

                if (
                    decision.confidence
                    < self
                    .min_equivalence_confidence
                ):
                    continue

                row[
                    "_cache_match_type"
                ] = "semantic_equivalent"

                row[
                    "_cache_matched_query"
                ] = row.get("user_query")

                row[
                    "_cache_similarity"
                ] = candidate[
                    "similarity"
                ]

                row[
                    "_cache_equivalence_confidence"
                ] = decision.confidence

                row[
                    "_cache_equivalence_reason"
                ] = decision.reason

                return DuplicateCheckResult(
                    identity=identity,
                    match=(
                        DuplicateExplorerMatch(
                            row=row,
                            match_type=(
                                "semantic_equivalent"
                            ),
                            similarity=(
                                candidate[
                                    "similarity"
                                ]
                            ),
                            equivalence_confidence=(
                                decision.confidence
                            ),
                            equivalence_reason=(
                                decision.reason
                            ),
                        )
                    ),
                )

            return DuplicateCheckResult(
                identity=identity,
                match=None,
            )

        except Exception as exc:
            # Semantic matching is an optimization. A failure must not replace
            # normal generation with an unrelated cached Explorer.
            return DuplicateCheckResult(
                identity=identity,
                match=None,
                semantic_error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

    def _verify_equivalence(
        self,
        *,
        new_query: str,
        existing_row: dict,
    ) -> QueryEquivalenceDecision:
        client = (
            self._openai_client
            or OpenAI()
        )

        existing_query = str(
            existing_row.get(
                "user_query"
            )
            or ""
        ).strip()

        existing_explorer = (
            existing_row.get(
                "full_output_json"
            )
        )

        prompt_payload = {
            "new_query": new_query,
            "existing_query": (
                existing_query
            ),
            "existing_explorer": (
                existing_explorer
            ),
        }

        response = client.responses.parse(
            model=self.equivalence_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Determine whether the new "
                        "MetaStock Explorer request "
                        "requires exactly the same "
                        "strategy logic as the stored "
                        "request and Explorer. "
                        "Be conservative. Return "
                        "equivalent=false whenever "
                        "there is ambiguity or any "
                        "material difference. "
                        "Material differences include "
                        "indicators, functions, price "
                        "fields, periods, thresholds, "
                        "moving-average methods, "
                        "above/below direction, "
                        "bullish/bearish direction, "
                        "crossing events versus "
                        "continuing states, AND versus "
                        "OR, current versus previous "
                        "bar logic, lookback windows, "
                        "confirmations, and exclusions. "
                        "Different wording alone is "
                        "not a material difference."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        prompt_payload,
                        ensure_ascii=False,
                        indent=2,
                    ),
                },
            ],
            text_format=(
                QueryEquivalenceDecision
            ),
        )

        decision = (
            response.output_parsed
        )

        if decision is None:
            raise RuntimeError(
                "Query equivalence verifier "
                "returned no parsed decision."
            )

        return decision