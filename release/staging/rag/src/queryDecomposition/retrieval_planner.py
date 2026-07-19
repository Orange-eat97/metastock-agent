from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from supabase import Client

from src.queryDecomposition.query_decomposer import (
    RetrievalIntent,
    decompose_query_for_retrieval,
    get_seed_canonical_ids,
)
from src.queryDecomposition.registry_resolver import (
    DEFAULT_ALLOWED_EDGE_TYPES,
    DEFAULT_MAX_DEPENDENCY_DEPTH,
    AliasMatch,
    RegistryCard,
    RegistryConcept,
    RegistryResolver,
)
from src.queryDecomposition.seed_coverage_verifier import (
    MissingSeedSuggestion,
    SeedCoverageDecision,
    SeedCoverageVerifier,
)


@dataclass(frozen=True)
class RetrievalPlan:
    original_query: str
    intents: list[RetrievalIntent]
    seed_canonical_ids: list[str]
    alias_matches: list[AliasMatch]
    resolved_cards: list[RegistryCard]
    missing_seed_canonical_ids: list[str]
    retrieval_queries_by_bucket: dict[str, list[str]] = field(default_factory=dict)
    raw_seed_canonical_ids: list[str] = field(default_factory=list)
    coverage_decisions: list[SeedCoverageDecision] = field(default_factory=list)
    missing_seed_suggestions: list[MissingSeedSuggestion] = field(default_factory=list)
    rejected_seed_canonical_ids: list[str] = field(default_factory=list)

    @property
    def forced_cards(self) -> list[RegistryCard]:
        return self.resolved_cards

    def print_summary(self) -> None:
        print("\n=== Retrieval Plan ===")
        print(f"Original query: {self.original_query}")

        print("\n--- Intents ---")
        for i, intent in enumerate(self.intents, start=1):
            print(f"{i}. [{intent.target_bucket}] {intent.query}")
            print(f"   reason: {intent.reason}")
            print(f"   seed canonical IDs: {list(intent.seed_canonical_ids)}")

            if intent.proposed_missing_seed_ids:
                print(f"   proposed missing seed IDs: {list(intent.proposed_missing_seed_ids)}")

            print(f"   rule: {intent.source_rule}")

        print("\n--- Alias matches from registry ---")
        if self.alias_matches:
            for match in self.alias_matches:
                print(
                    f"- {match.canonical_id} | alias={match.alias_text!r} "
                    f"| weight={match.weight:.2f}"
                )
        else:
            print("(none)")

        print("\n--- Raw seed canonical IDs before coverage gate ---")
        if self.raw_seed_canonical_ids:
            for canonical_id in self.raw_seed_canonical_ids:
                print(f"- {canonical_id}")
        else:
            print("(none)")

        print("\n--- Seed coverage decisions ---")
        if self.coverage_decisions:
            for decision in self.coverage_decisions:
                print(
                    f"- {decision.candidate_seed_id} | "
                    f"{decision.coverage_status} | "
                    f"score={decision.coverage_score:.2f} | "
                    f"{decision.reason}"
                )
        else:
            print("(none)")

        if self.rejected_seed_canonical_ids:
            print("\n--- Rejected seed canonical IDs ---")
            for canonical_id in self.rejected_seed_canonical_ids:
                print(f"- {canonical_id}")

        if self.missing_seed_suggestions:
            print("\n--- Missing-card suggestions ---")
            for suggestion in self.missing_seed_suggestions:
                print(f"- suggest adding {suggestion.suggested_seed_id} card")

        print("\n--- Accepted seed canonical IDs ---")
        if self.seed_canonical_ids:
            for canonical_id in self.seed_canonical_ids:
                print(f"- {canonical_id}")
        else:
            print("(none)")

        print("\n--- Registry-resolved forced cards ---")
        if self.resolved_cards:
            for card in self.resolved_cards:
                print(
                    f"- {card.canonical_id} -> {card.card_title} "
                    f"| {card.source_path} | depth={card.depth}"
                )
        else:
            print("(none)")

        if self.missing_seed_canonical_ids:
            print("\n--- Missing seed canonical IDs ---")
            for canonical_id in self.missing_seed_canonical_ids:
                print(f"- {canonical_id}")

        print("\n--- Retrieval queries by bucket ---")
        for bucket, queries in self.retrieval_queries_by_bucket.items():
            print(f"[{bucket}]")
            for query in queries:
                print(f"  - {query}")
                


class RetrievalPlanner:
    """
    Tell-style retrieval planner.

    Context builder tells this object:
        build a retrieval plan for this query.

    This object owns:
    - loading active registry concepts;
    - LLM seed extraction;
    - registry alias hints;
    - semantic profile coverage verification;
    - canonical ID collection;
    - dependency expansion through Supabase;
    - grouping vector-retrieval subqueries by bucket.
    """

    def __init__(
        self,
        supabase: Client,
        *,
        include_alias_hints: bool = True,
        alias_min_weight: float = 0.7,
        verify_seed_coverage: bool = True,
        semantic_profile_review_statuses: Sequence[str] = ("pending", "approved"),
        allowed_edge_types: Sequence[str] = DEFAULT_ALLOWED_EDGE_TYPES,
        max_dependency_depth: int = DEFAULT_MAX_DEPENDENCY_DEPTH,
    ):
        self.resolver = RegistryResolver(supabase)
        self.include_alias_hints = include_alias_hints
        self.alias_min_weight = alias_min_weight
        self.verify_seed_coverage = verify_seed_coverage
        self.semantic_profile_review_statuses = tuple(semantic_profile_review_statuses)
        self.allowed_edge_types = tuple(allowed_edge_types)
        self.max_dependency_depth = max_dependency_depth
        self.seed_coverage_verifier = SeedCoverageVerifier()

    def build_plan(self, user_query: str) -> RetrievalPlan:
        active_concepts = self.resolver.fetch_active_concepts()

        intents = decompose_query_for_retrieval(
            user_query,
            available_concepts=active_concepts,
        )
        decomposer_missing_seed_suggestions = _missing_suggestions_from_intents(
            intents
        )

        raw_seed_canonical_ids = get_seed_canonical_ids(intents)

        alias_matches: list[AliasMatch] = []
        if self.include_alias_hints:
            alias_matches = self.resolver.match_aliases(
                query_text=user_query,
                min_weight=self.alias_min_weight,
            )

            for match in alias_matches:
                if match.canonical_id not in raw_seed_canonical_ids:
                    raw_seed_canonical_ids.append(match.canonical_id)

        seed_canonical_ids = list(raw_seed_canonical_ids)
        coverage_decisions: list[SeedCoverageDecision] = []
        missing_seed_suggestions: list[MissingSeedSuggestion] = list(
            decomposer_missing_seed_suggestions
        )
        rejected_seed_canonical_ids: list[str] = []

        if self.verify_seed_coverage and seed_canonical_ids:
            semantic_profiles = self.resolver.fetch_semantic_profiles(
                seed_canonical_ids,
                review_statuses=self.semantic_profile_review_statuses,
            )

            verification = self.seed_coverage_verifier.verify(
                user_query=user_query,
                candidate_seed_ids=seed_canonical_ids,
                semantic_profiles=semantic_profiles,
                active_concepts=active_concepts,
            )

            seed_canonical_ids = verification.accepted_seed_ids
            coverage_decisions = verification.decisions
            missing_seed_suggestions = _dedupe_missing_suggestions(
                [
                    *missing_seed_suggestions,
                    *verification.missing_seed_suggestions,
                ]
            )
            rejected_seed_canonical_ids = verification.rejected_seed_ids

        resolved_cards, missing_seed_canonical_ids = self.resolver.resolve_cards(
            seed_canonical_ids=seed_canonical_ids,
            allowed_edge_types=self.allowed_edge_types,
            max_depth=self.max_dependency_depth,
        )

        return RetrievalPlan(
            original_query=user_query,
            intents=intents,
            seed_canonical_ids=seed_canonical_ids,
            raw_seed_canonical_ids=raw_seed_canonical_ids,
            alias_matches=alias_matches,
            resolved_cards=resolved_cards,
            missing_seed_canonical_ids=missing_seed_canonical_ids,
            retrieval_queries_by_bucket=_group_queries_by_bucket(
                intents,
                active_concepts,
                accepted_seed_ids=set(seed_canonical_ids),
                coverage_decisions=coverage_decisions,
                missing_seed_suggestions=missing_seed_suggestions,
            ),
            coverage_decisions=coverage_decisions,
            missing_seed_suggestions=missing_seed_suggestions,
            rejected_seed_canonical_ids=rejected_seed_canonical_ids,
        )


def _group_queries_by_bucket(
    intents: list[RetrievalIntent],
    active_concepts: list[RegistryConcept],
    *,
    accepted_seed_ids: set[str] | None = None,
    coverage_decisions: list[SeedCoverageDecision] | None = None,
    missing_seed_suggestions: list[MissingSeedSuggestion] | None = None,
) -> dict[str, list[str]]:
    """
    Build safe vector-retrieval queries by bucket.

    Important rule:
    If a query span is known to be missing/uncovered, do not use an intent query
    containing that span for vector retrieval. Otherwise vector retrieval will
    search for the missing concept and retrieve semantically-near wrong cards.
    """
    grouped: dict[str, list[str]] = {
        "patterns": [],
        "functions": [],
        "references": [],
    }

    concept_lookup = {
        concept.canonical_id: concept
        for concept in active_concepts
    }

    accepted_seed_ids = accepted_seed_ids or set()
    coverage_decisions = coverage_decisions or []
    missing_seed_suggestions = missing_seed_suggestions or []

    unsafe_spans = _collect_unsafe_spans(
        coverage_decisions=coverage_decisions,
        missing_seed_suggestions=missing_seed_suggestions,
    )

    for intent in intents:
        accepted_intent_seed_ids = [
            canonical_id
            for canonical_id in intent.seed_canonical_ids
            if canonical_id in accepted_seed_ids
        ]

        # Do not route raw fallback/original-query intents when there are
        # missing concepts. These are the noisiest retrieval queries.
        if not intent.seed_canonical_ids:
            if unsafe_spans:
                continue

            bucket = _safe_bucket(intent.target_bucket)
            _append_unique(grouped.setdefault(bucket, []), intent.query)
            continue

        # If none of this intent's seeds survived the coverage gate, do not use
        # the original intent query.
        if not accepted_intent_seed_ids:
            continue

        # If the intent query mentions a missing span, do not use the raw query.
        # Instead, add safe seed-based queries below.
        intent_query_is_safe = not _contains_any_span(intent.query, unsafe_spans)

        if intent_query_is_safe:
            bucket = _safe_bucket(intent.target_bucket)
            _append_unique(grouped.setdefault(bucket, []), intent.query)

        # Always add seed-based safe queries for accepted seeds. These queries
        # are based on existing concepts, not missing concepts like MACD/ATR.
        for canonical_id in accepted_intent_seed_ids:
            concept = concept_lookup.get(canonical_id)
            if concept is None:
                continue

            concept_bucket = _safe_bucket(concept.card_bucket)
            safe_query = _safe_query_for_concept(concept)

            _append_unique(grouped.setdefault(concept_bucket, []), safe_query)

    return grouped

def _collect_unsafe_spans(
    *,
    coverage_decisions: list[SeedCoverageDecision],
    missing_seed_suggestions: list[MissingSeedSuggestion],
) -> list[str]:
    spans: list[str] = []

    for decision in coverage_decisions:
        if decision.uncovered_span:
            _append_unique(spans, decision.uncovered_span)

        if decision.suggested_missing_seed_id:
            for token in _tokens_from_seed_id(decision.suggested_missing_seed_id):
                _append_unique(spans, token)

    for suggestion in missing_seed_suggestions:
        if suggestion.uncovered_span:
            _append_unique(spans, suggestion.uncovered_span)

        for token in _tokens_from_seed_id(suggestion.suggested_seed_id):
            _append_unique(spans, token)

    return [
        span
        for span in spans
        if len(span.strip()) >= 3
    ]


def _tokens_from_seed_id(seed_id: str) -> list[str]:
    """
    Convert a missing canonical ID into unsafe lexical spans.

    Example:
        function.macd -> ["macd"]
        pattern.atr_trailing_stop -> ["atr trailing stop", "atr", "trailing", "stop"]
    """
    raw = str(seed_id or "").strip().lower()

    if "." in raw:
        raw = raw.split(".", 1)[1]

    phrase = raw.replace("_", " ").replace("-", " ").strip()
    tokens = [token for token in phrase.split() if len(token) >= 3]

    result: list[str] = []

    if phrase:
        result.append(phrase)

    for token in tokens:
        if token not in result:
            result.append(token)

    return result


def _contains_any_span(text: str, spans: list[str]) -> bool:
    normalized_text = _normalize_text(text)

    for span in spans:
        normalized_span = _normalize_text(span)

        if not normalized_span:
            continue

        if normalized_span in normalized_text:
            return True

    return False


def _safe_query_for_concept(concept: RegistryConcept) -> str:
    """
    Generate a safe retrieval query using only an existing registry concept.

    This avoids queries like:
        "MACD crosses above signal line"

    and replaces them with:
        "Cross function crossover crossing event"
        "Mov moving average"
    """
    parts = [
        concept.title,
        concept.concept_type,
        concept.card_bucket,
        concept.source_path.replace("/", " ").replace(".md", ""),
    ]

    for alias in concept.aliases[:5]:
        parts.append(alias)

    return " ".join(
        part.strip()
        for part in parts
        if str(part).strip()
    )


def _normalize_text(value: str) -> str:
    return " ".join(
        str(value or "")
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


def _append_unique(values: list[str], value: str) -> None:
    cleaned = str(value or "").strip()

    if not cleaned:
        return

    if cleaned not in values:
        values.append(cleaned)


def _safe_bucket(value: str) -> str:
    normalized = str(value or "references").lower().strip()

    if normalized in {"pattern", "patterns"}:
        return "patterns"
    if normalized in {"function", "functions"}:
        return "functions"

    return "references"

def _missing_suggestions_from_intents(
    intents: list[RetrievalIntent],
) -> list[MissingSeedSuggestion]:
    suggestions: list[MissingSeedSuggestion] = []
    seen: set[str] = set()

    for intent in intents:
        for seed_id in intent.proposed_missing_seed_ids:
            cleaned = str(seed_id or "").strip().lower()

            if not cleaned:
                continue

            if cleaned in seen:
                continue

            seen.add(cleaned)

            suggestions.append(
                MissingSeedSuggestion(
                    suggested_seed_id=cleaned,
                    reason=(
                        "LLM seed planner proposed this concept, but it does "
                        "not exist in the active Supabase registry."
                    ),
                    uncovered_span=_span_from_seed_id(cleaned),
                )
            )

    return suggestions


def _span_from_seed_id(seed_id: str) -> str:
    raw = str(seed_id or "").strip().lower()

    if "." in raw:
        raw = raw.split(".", 1)[1]

    return raw.replace("_", " ").replace("-", " ").strip()

def _dedupe_missing_suggestions(
    suggestions: list[MissingSeedSuggestion],
) -> list[MissingSeedSuggestion]:
    result: list[MissingSeedSuggestion] = []
    seen: set[str] = set()

    for suggestion in suggestions:
        seed_id = str(suggestion.suggested_seed_id or "").strip().lower()

        if not seed_id:
            continue

        if seed_id in seen:
            continue

        seen.add(seed_id)
        result.append(suggestion)

    return result