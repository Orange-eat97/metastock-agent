from __future__ import annotations

import difflib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


Bucket = Literal["patterns", "functions", "references"]

DEFAULT_SEED_PLANNER_MODEL = os.getenv(
    "SEED_PLANNER_MODEL",
    os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
)


@dataclass(frozen=True)
class RetrievalIntent:
    """
    A retrieval intent is not a MetaStock formula fragment.

    It is a planning object that says:
    - which semantic subquery should be used for vector retrieval;
    - which bucket should receive that subquery;
    - which canonical registry concepts should be used as seed nodes;
    - which proposed seed nodes were missing from the registry.

    Dependencies are intentionally NOT stored here. Dependencies belong to the
    Supabase registry graph: rag_card_registry + rag_card_dependencies.
    """

    query: str
    target_bucket: Bucket
    reason: str
    seed_canonical_ids: tuple[str, ...] = field(default_factory=tuple)
    proposed_missing_seed_ids: tuple[str, ...] = field(default_factory=tuple)
    source_rule: str = ""

    @property
    def force_card_names(self) -> tuple[str, ...]:
        """
        Backward-compatible alias for older debug/test code.

        The values are now canonical IDs, not human card titles.
        """
        return self.seed_canonical_ids


@dataclass(frozen=True)
class PlannerConcept:
    canonical_id: str
    title: str
    concept_type: str
    card_bucket: str
    source_path: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


def decompose_query_for_retrieval(
    user_query: str,
    available_concepts: Sequence[Any] | None = None,
    *,
    model: str | None = None,
) -> list[RetrievalIntent]:
    """
    LLM seed extractor.

    This function replaces the old string/regex seed matching. It asks an LLM
    to map the user query to seed canonical IDs, then validates every returned
    seed against the active Supabase registry concept list supplied by the
    retrieval planner.

    Important boundary:
    - This function extracts seed canonical IDs only.
    - It does NOT expand dependencies.
    - Registry dependency expansion remains in RegistryResolver/Supabase.

    If the LLM proposes a seed that is not in Supabase, this function prints a
    message, suggests the nearest existing concept, prints:
        suggest adding <seed> card
    and skips the invalid seed.
    """
    concepts = _coerce_concepts(available_concepts or [])

    if not concepts:
        print(
            "[query_decomposer] No active registry concepts were supplied; "
            "falling back to original-query retrieval only."
        )
        return _fallback_intents(user_query)

    raw_plan = _call_llm_seed_planner(
        user_query=user_query,
        concepts=concepts,
        model=model or DEFAULT_SEED_PLANNER_MODEL,
    )

    intents = _build_intents_from_llm_plan(
        user_query=user_query,
        concepts=concepts,
        raw_plan=raw_plan,
    )

    # Always keep original-query fallback for vector retrieval.
    intents.append(
        RetrievalIntent(
            query=user_query,
            target_bucket="references",
            reason="Fallback retrieval using original query.",
            seed_canonical_ids=(),
            source_rule="original_query_fallback",
        )
    )

    return _dedupe_intents(intents)


def get_seed_canonical_ids(intents: list[RetrievalIntent]) -> list[str]:
    seed_ids: list[str] = []

    for intent in intents:
        for canonical_id in intent.seed_canonical_ids:
            if canonical_id not in seed_ids:
                seed_ids.append(canonical_id)

    return seed_ids


def get_forced_card_names(intents: list[RetrievalIntent]) -> list[str]:
    """
    Backward-compatible helper for old tests.

    It now returns canonical IDs, not card titles.
    Prefer get_seed_canonical_ids() in new code.
    """
    return get_seed_canonical_ids(intents)


# ============================================================
# LLM planner
# ============================================================


def _call_llm_seed_planner(
    user_query: str,
    concepts: list[PlannerConcept],
    model: str,
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print(
            "[query_decomposer] Missing OPENAI_API_KEY; "
            "falling back to original-query retrieval only."
        )
        return {"intents": [], "proposed_missing_seed_ids": [], "unknown_terms": []}

    client = OpenAI(api_key=api_key)

    messages = [
        {
            "role": "system",
            "content": _build_system_prompt(),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "user_query": user_query,
                    "available_concepts": _concepts_for_prompt(concepts),
                },
                ensure_ascii=False,
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        if not isinstance(parsed, dict):
            raise ValueError("LLM planner response was not a JSON object.")

        return parsed

    except Exception as exc:
        print(
            "[query_decomposer] LLM seed planner failed; "
            f"falling back to original-query retrieval only. Error: {exc}"
        )
        return {"intents": [], "proposed_missing_seed_ids": [], "unknown_terms": []}


def _build_system_prompt() -> str:
    return """
You are a retrieval seed planner for a MetaStock Explorer RAG system.

Your job is NOT to write a MetaStock formula.
Your job is to identify which canonical knowledge-card concepts are needed for retrieval.

You receive:
- a user query;
- a list of active registry concepts from Supabase.

Return JSON only with this shape:
{
  "intents": [
    {
      "seed_canonical_ids": ["one or more canonical IDs"],
      "target_bucket": "patterns" | "functions" | "references",
      "retrieval_query": "short semantic retrieval query",
      "reason": "brief reason"
    }
  ],
  "proposed_missing_seed_ids": ["canonical IDs that would be useful but are not available"],
  "unknown_terms": ["terms you could not map"]
}

Rules:
1. Prefer available concepts. Use only canonical_id values from available_concepts when possible.
2. Do not invent a concept if an available concept reasonably covers the request.
3. If a useful pattern concept is missing, put its proposed canonical ID in proposed_missing_seed_ids.
4. Examples:
   - "volume above average" should use pattern.volume_above_average if available.
   - "break above previous high" should use pattern.breakout if available.
   - "new low" should use pattern.new_low if available; otherwise use function.llv and function.ref if available, and optionally propose pattern.new_low.
   - "MA crossover" should use function.cross and function.mov unless a pattern.crossover card exists.
5. Choose seed concepts only. Do not manually expand dependencies that the graph should expand from pattern cards.
6. But if no pattern card exists and only function cards cover the request, choose the function cards.
7. Keep retrieval_query concise and useful for vector retrieval.
""".strip()


def _concepts_for_prompt(concepts: list[PlannerConcept]) -> list[dict[str, Any]]:
    return [
        {
            "canonical_id": concept.canonical_id,
            "title": concept.title,
            "concept_type": concept.concept_type,
            "card_bucket": concept.card_bucket,
            "source_path": concept.source_path,
            "aliases": list(concept.aliases[:12]),
        }
        for concept in concepts
    ]


# ============================================================
# Plan validation / conversion
# ============================================================


def _build_intents_from_llm_plan(
    user_query: str,
    concepts: list[PlannerConcept],
    raw_plan: dict[str, Any],
) -> list[RetrievalIntent]:
    concept_lookup = {concept.canonical_id: concept for concept in concepts}

    intents: list[RetrievalIntent] = []

    raw_intents = raw_plan.get("intents") or []
    if not isinstance(raw_intents, list):
        raw_intents = []

    for raw_intent in raw_intents:
        if not isinstance(raw_intent, Mapping):
            continue

        raw_seed_ids = raw_intent.get("seed_canonical_ids") or []
        if isinstance(raw_seed_ids, str):
            raw_seed_ids = [raw_seed_ids]
        if not isinstance(raw_seed_ids, list):
            continue

        valid_seed_ids: list[str] = []
        missing_seed_ids: list[str] = []

        for raw_seed_id in raw_seed_ids:
            seed_id = str(raw_seed_id).strip()
            if not seed_id:
                continue

            if seed_id not in concept_lookup:
                _print_missing_seed_message(seed_id, concepts)

                if seed_id not in missing_seed_ids:
                    missing_seed_ids.append(seed_id)

                continue

            if seed_id not in valid_seed_ids:
                valid_seed_ids.append(seed_id)

        if not valid_seed_ids and not missing_seed_ids:
            continue

        if valid_seed_ids:
            target_bucket = _safe_bucket(
                raw_intent.get("target_bucket"),
                default=concept_lookup[valid_seed_ids[0]].card_bucket,
            )
        else:
            target_bucket = _safe_bucket(
                raw_intent.get("target_bucket"),
                default="references",
            )

        retrieval_query = str(raw_intent.get("retrieval_query") or user_query).strip()
        reason = str(raw_intent.get("reason") or "LLM selected registry seed concepts.").strip()

        intents.append(
            RetrievalIntent(
                query=retrieval_query,
                target_bucket=target_bucket,
                reason=reason,
                seed_canonical_ids=tuple(valid_seed_ids),
                proposed_missing_seed_ids=tuple(missing_seed_ids),
                source_rule="llm_seed_planner",
            )
        )

        proposed_missing = raw_plan.get("proposed_missing_seed_ids") or []
    if isinstance(proposed_missing, str):
        proposed_missing = [proposed_missing]

    global_missing_seed_ids: list[str] = []

    if isinstance(proposed_missing, list):
        for raw_seed_id in proposed_missing:
            seed_id = str(raw_seed_id).strip()
            if seed_id and seed_id not in concept_lookup:
                _print_missing_seed_message(seed_id, concepts)

                if seed_id not in global_missing_seed_ids:
                    global_missing_seed_ids.append(seed_id)

    if global_missing_seed_ids:
        intents.append(
            RetrievalIntent(
                query=user_query,
                target_bucket="references",
                reason="Missing concepts proposed by LLM seed planner.",
                seed_canonical_ids=(),
                proposed_missing_seed_ids=tuple(global_missing_seed_ids),
                source_rule="llm_missing_seed_proposal",
            )
        )

    return intents


def _safe_bucket(value: Any, default: str) -> Bucket:
    normalized = str(value or default or "references").strip().lower()

    if normalized in {"pattern", "patterns"}:
        return "patterns"
    if normalized in {"function", "functions"}:
        return "functions"
    if normalized in {"reference", "references", "template", "templates", "examples", "example"}:
        return "references"

    return "references"


def _print_missing_seed_message(seed_id: str, concepts: list[PlannerConcept]) -> None:
    similar = _find_most_similar_concept(seed_id, concepts)

    print(f"[query_decomposer] Skipping seed not found in Supabase registry: {seed_id}")

    if similar is not None:
        print(
            "[query_decomposer] Most similar existing concept: "
            f"{similar.canonical_id} | {similar.title} | {similar.source_path}"
        )

    print(f"suggest adding {seed_id} card")


def _find_most_similar_concept(
    seed_id: str,
    concepts: list[PlannerConcept],
) -> PlannerConcept | None:
    if not concepts:
        return None

    def score(concept: PlannerConcept) -> float:
        candidates = [
            concept.canonical_id,
            concept.title,
            concept.source_path,
            *concept.aliases,
        ]
        return max(
            difflib.SequenceMatcher(None, seed_id.lower(), str(candidate).lower()).ratio()
            for candidate in candidates
            if str(candidate).strip()
        )

    return max(concepts, key=score)


# ============================================================
# Concept coercion
# ============================================================


def _coerce_concepts(values: Sequence[Any]) -> list[PlannerConcept]:
    concepts: list[PlannerConcept] = []

    for value in values:
        concept = _coerce_one_concept(value)
        if concept is not None:
            concepts.append(concept)

    concepts.sort(key=lambda c: (c.concept_type, c.canonical_id))
    return concepts


def _coerce_one_concept(value: Any) -> PlannerConcept | None:
    def get(name: str, default: Any = "") -> Any:
        if isinstance(value, Mapping):
            return value.get(name, default)
        return getattr(value, name, default)

    canonical_id = str(get("canonical_id", "")).strip()
    if not canonical_id:
        return None

    aliases_raw = get("aliases", ())
    if aliases_raw is None:
        aliases: tuple[str, ...] = ()
    elif isinstance(aliases_raw, str):
        aliases = (aliases_raw,)
    else:
        aliases = tuple(str(alias) for alias in aliases_raw if str(alias).strip())

    return PlannerConcept(
        canonical_id=canonical_id,
        title=str(get("title", get("registry_title", canonical_id)) or canonical_id),
        concept_type=str(get("concept_type", "") or ""),
        card_bucket=str(get("card_bucket", get("registry_bucket", "references")) or "references"),
        source_path=str(get("source_path", "") or ""),
        aliases=aliases,
    )


def _fallback_intents(user_query: str) -> list[RetrievalIntent]:
    return [
        RetrievalIntent(
            query=user_query,
            target_bucket="references",
            reason="Fallback retrieval using original query.",
            seed_canonical_ids=(),
            source_rule="original_query_fallback",
        )
    ]


def _dedupe_intents(intents: list[RetrievalIntent]) -> list[RetrievalIntent]:
    seen: set[tuple[str, Bucket, tuple[str, ...]]] = set()
    result: list[RetrievalIntent] = []

    for intent in intents:
        key = (
            intent.query.lower(),
            intent.target_bucket,
            intent.seed_canonical_ids,
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(intent)

    return result
