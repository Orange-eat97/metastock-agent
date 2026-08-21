from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from dotenv import load_dotenv
from openai import OpenAI

from src.queryDecomposition.registry_resolver import (
    RegistryConcept,
    SemanticProfile,
)


load_dotenv()


CoverageStatus = Literal["full_coverage", "support_only", "not_covered"]

DEFAULT_SEED_COVERAGE_MODEL = os.getenv(
    "SEED_COVERAGE_MODEL",
    os.getenv("SEED_PLANNER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
)

DEFAULT_FULL_COVERAGE_THRESHOLD = float(
    os.getenv("SEED_FULL_COVERAGE_THRESHOLD", "0.82")
)
DEFAULT_SUPPORT_COVERAGE_THRESHOLD = float(
    os.getenv("SEED_SUPPORT_COVERAGE_THRESHOLD", "0.60")
)


@dataclass(frozen=True)
class SeedCoverageDecision:
    candidate_seed_id: str
    coverage_status: CoverageStatus
    coverage_score: float
    reason: str
    suggested_missing_seed_id: str | None = None
    uncovered_span: str | None = None

    @property
    def is_full_coverage(self) -> bool:
        return self.coverage_status == "full_coverage"

    @property
    def is_support_only(self) -> bool:
        return self.coverage_status == "support_only"

    @property
    def is_not_covered(self) -> bool:
        return self.coverage_status == "not_covered"


@dataclass(frozen=True)
class MissingSeedSuggestion:
    suggested_seed_id: str
    reason: str
    uncovered_span: str | None = None


@dataclass(frozen=True)
class SeedCoverageResult:
    accepted_seed_ids: list[str]
    rejected_seed_ids: list[str]
    unverified_seed_ids: list[str]
    decisions: list[SeedCoverageDecision] = field(default_factory=list)
    missing_seed_suggestions: list[MissingSeedSuggestion] = field(default_factory=list)


class SeedCoverageVerifier:
    """
    Generic semantic coverage gate for query decomposition.

    This is intentionally NOT a new table/function workflow.
    It uses the existing rag_card_semantic_profiles rows to decide whether
    candidate seed concepts actually cover the user's requested mechanism.

    Key rule:
        semantic closeness is not enough; the semantic profile must cover the
        requested mechanism/object/direction/operation.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        full_coverage_threshold: float = DEFAULT_FULL_COVERAGE_THRESHOLD,
        support_coverage_threshold: float = DEFAULT_SUPPORT_COVERAGE_THRESHOLD,
    ):
        self.model = model or DEFAULT_SEED_COVERAGE_MODEL
        self.full_coverage_threshold = full_coverage_threshold
        self.support_coverage_threshold = support_coverage_threshold

    def verify(
        self,
        *,
        user_query: str,
        candidate_seed_ids: Sequence[str],
        semantic_profiles: Sequence[SemanticProfile],
        active_concepts: Sequence[RegistryConcept],
    ) -> SeedCoverageResult:
        ordered_candidate_ids = _dedupe_preserve_order(candidate_seed_ids)

        if not ordered_candidate_ids:
            return SeedCoverageResult(
                accepted_seed_ids=[],
                rejected_seed_ids=[],
                unverified_seed_ids=[],
            )

        profile_lookup = {
            profile.canonical_id: profile for profile in semantic_profiles
        }

        profiled_candidate_ids = [
            canonical_id
            for canonical_id in ordered_candidate_ids
            if canonical_id in profile_lookup
        ]
        unverified_seed_ids = [
            canonical_id
            for canonical_id in ordered_candidate_ids
            if canonical_id not in profile_lookup
        ]

        if unverified_seed_ids:
            for canonical_id in unverified_seed_ids:
                print(
                    "[seed_coverage] No semantic profile found for seed; "
                    f"keeping seed without coverage verification: {canonical_id}"
                )

        if not profiled_candidate_ids:
            return SeedCoverageResult(
                accepted_seed_ids=ordered_candidate_ids,
                rejected_seed_ids=[],
                unverified_seed_ids=unverified_seed_ids,
            )

        raw_result = self._call_llm_verifier(
            user_query=user_query,
            candidate_profiles=[profile_lookup[x] for x in profiled_candidate_ids],
            active_concepts=active_concepts,
        )

        decisions = _parse_decisions(raw_result, allowed_ids=set(profiled_candidate_ids))
        missing_seed_suggestions = _parse_missing_seed_suggestions(raw_result)

        decided_ids = {decision.candidate_seed_id for decision in decisions}
        undecided_profiled_ids = [
            canonical_id
            for canonical_id in profiled_candidate_ids
            if canonical_id not in decided_ids
        ]

        for canonical_id in undecided_profiled_ids:
            print(
                "[seed_coverage] LLM verifier did not return a decision for seed; "
                f"keeping seed without coverage verification: {canonical_id}"
            )

        accepted_seed_ids: list[str] = []
        rejected_seed_ids: list[str] = []

        for canonical_id in ordered_candidate_ids:
            matching_decision = next(
                (
                    decision
                    for decision in decisions
                    if decision.candidate_seed_id == canonical_id
                ),
                None,
            )

            if matching_decision is None:
                # Fail-open for seeds that have no semantic profile or no decision.
                if canonical_id not in accepted_seed_ids:
                    accepted_seed_ids.append(canonical_id)
                continue

            if self._decision_is_accepted(matching_decision):
                if canonical_id not in accepted_seed_ids:
                    accepted_seed_ids.append(canonical_id)
            else:
                rejected_seed_ids.append(canonical_id)
                print(
                    "[seed_coverage] Rejected seed after semantic coverage check: "
                    f"{canonical_id} | status={matching_decision.coverage_status} "
                    f"| score={matching_decision.coverage_score:.2f} "
                    f"| reason={matching_decision.reason}"
                )

                suggestion = matching_decision.suggested_missing_seed_id
                if suggestion:
                    missing_seed_suggestions.append(
                        MissingSeedSuggestion(
                            suggested_seed_id=suggestion,
                            reason=matching_decision.reason,
                            uncovered_span=matching_decision.uncovered_span,
                        )
                    )

        active_concept_ids = {concept.canonical_id for concept in active_concepts}
        missing_seed_suggestions = _dedupe_missing_suggestions(
            suggestion
            for suggestion in missing_seed_suggestions
            if suggestion.suggested_seed_id not in active_concept_ids
        )

        for suggestion in missing_seed_suggestions:
            if suggestion.uncovered_span:
                print(
                    "[seed_coverage] Uncovered query span: "
                    f"{suggestion.uncovered_span}"
                )
            if suggestion.reason:
                print(f"[seed_coverage] Missing-card reason: {suggestion.reason}")
            print(f"suggest adding {suggestion.suggested_seed_id} card")

        return SeedCoverageResult(
            accepted_seed_ids=accepted_seed_ids,
            rejected_seed_ids=rejected_seed_ids,
            unverified_seed_ids=unverified_seed_ids,
            decisions=decisions,
            missing_seed_suggestions=missing_seed_suggestions,
        )

    def _decision_is_accepted(self, decision: SeedCoverageDecision) -> bool:
        if decision.coverage_status == "full_coverage":
            return decision.coverage_score >= self.full_coverage_threshold

        if decision.coverage_status == "support_only":
            return decision.coverage_score >= self.support_coverage_threshold

        return False

    def _call_llm_verifier(
        self,
        *,
        user_query: str,
        candidate_profiles: Sequence[SemanticProfile],
        active_concepts: Sequence[RegistryConcept],
    ) -> dict[str, Any]:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            print(
                "[seed_coverage] Missing OPENAI_API_KEY; "
                "accepting seed candidates without semantic coverage verification."
            )
            return {"decisions": [], "missing_seed_suggestions": []}

        client = OpenAI(api_key=api_key)

        payload = {
            "user_query": user_query,
            "candidate_profiles": [
                profile.to_prompt_dict() for profile in candidate_profiles
            ],
            "available_canonical_ids": [
                concept.canonical_id for concept in active_concepts
            ],
        }

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _build_verifier_prompt()},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)

            if not isinstance(parsed, dict):
                raise ValueError("Seed coverage verifier response was not a JSON object.")

            return parsed

        except Exception as exc:
            print(
                "[seed_coverage] LLM verifier failed; "
                f"accepting seed candidates without semantic coverage verification. Error: {exc}"
            )
            return {"decisions": [], "missing_seed_suggestions": []}


def _build_verifier_prompt() -> str:
    return """
You are a semantic coverage verifier for a MetaStock Explorer RAG query planner.

You are given:
- the original user query;
- candidate seed concepts selected by an earlier planner;
- each candidate's semantic profile or card evidence from the existing knowledge cards;
- the active canonical IDs that currently exist in the registry.

Your job is not to write formulas.
Your job is to decide whether each candidate seed actually covers the user's requested trading concept.

Return JSON only with this shape:
{
  "decisions": [
    {
      "candidate_seed_id": "canonical ID from candidate_profiles",
      "coverage_status": "full_coverage" | "support_only" | "not_covered",
      "coverage_score": 0.0,
      "reason": "brief reason",
      "suggested_missing_seed_id": null,
      "uncovered_span": null
    }
  ],
  "missing_seed_suggestions": [
    {
      "suggested_seed_id": "pattern.example_missing_card or function.example_missing_function",
      "reason": "brief reason",
      "uncovered_span": "exact or short span from the user query"
    }
  ]
}

Coverage definitions:
- full_coverage: the candidate profile directly satisfies a requested trading concept.
- support_only: the candidate profile is a useful helper for a requested concept, but a core concept is still missing.
- not_covered: the candidate is merely related or semantically nearby, but its profile does not cover the requested mechanism.

Generic acceptance rules:
1. Use the candidate semantic profile or card evidence as the source of truth.
2. Compare the user's requested mechanism, market object, direction, operation, and field requirements against the candidate profile.
3. Semantic similarity alone is insufficient.
4. A card must not be accepted as full_coverage if it does not cover the mechanism requested by the user.
5. A helper function can be support_only when it is useful but cannot represent the core requested concept by itself.
6. For every distinct requested concept in the user query, ensure it is either covered by a candidate or listed in missing_seed_suggestions.
7. If a distinct requested concept is missing, suggest a canonical ID using one of these prefixes: pattern., function., reference.
8. Do not suggest a missing seed ID if that canonical ID already exists in available_canonical_ids.
9. Do not manually expand graph dependencies. Only verify candidate coverage and missing concepts.
10. Keep reasons short and specific.
""".strip()


def _parse_decisions(
    raw_result: dict[str, Any],
    *,
    allowed_ids: set[str],
) -> list[SeedCoverageDecision]:
    raw_decisions = raw_result.get("decisions") or []

    if not isinstance(raw_decisions, list):
        return []

    decisions: list[SeedCoverageDecision] = []

    for item in raw_decisions:
        if not isinstance(item, dict):
            continue

        candidate_seed_id = str(item.get("candidate_seed_id") or "").strip()
        if candidate_seed_id not in allowed_ids:
            continue

        coverage_status = _safe_coverage_status(item.get("coverage_status"))
        coverage_score = _safe_float(item.get("coverage_score"), default=0.0)
        reason = str(item.get("reason") or "").strip()
        suggested_missing_seed_id = _clean_optional_seed_id(
            item.get("suggested_missing_seed_id")
        )
        uncovered_span = _clean_optional_text(item.get("uncovered_span"))

        decisions.append(
            SeedCoverageDecision(
                candidate_seed_id=candidate_seed_id,
                coverage_status=coverage_status,
                coverage_score=coverage_score,
                reason=reason,
                suggested_missing_seed_id=suggested_missing_seed_id,
                uncovered_span=uncovered_span,
            )
        )

    return decisions


def _parse_missing_seed_suggestions(
    raw_result: dict[str, Any],
) -> list[MissingSeedSuggestion]:
    raw_suggestions = raw_result.get("missing_seed_suggestions") or []

    if not isinstance(raw_suggestions, list):
        return []

    suggestions: list[MissingSeedSuggestion] = []

    for item in raw_suggestions:
        if not isinstance(item, dict):
            continue

        suggested_seed_id = _clean_optional_seed_id(item.get("suggested_seed_id"))
        if not suggested_seed_id:
            continue

        suggestions.append(
            MissingSeedSuggestion(
                suggested_seed_id=suggested_seed_id,
                reason=str(item.get("reason") or "").strip(),
                uncovered_span=_clean_optional_text(item.get("uncovered_span")),
            )
        )

    return suggestions


def _safe_coverage_status(value: Any) -> CoverageStatus:
    normalized = str(value or "not_covered").strip().lower()

    if normalized == "full_coverage":
        return "full_coverage"

    if normalized == "support_only":
        return "support_only"

    return "not_covered"


def _safe_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default

    if parsed < 0:
        return 0.0

    if parsed > 1:
        return 1.0

    return parsed


def _clean_optional_seed_id(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()
    if not text or text in {"none", "null", "n/a"}:
        return None

    # Keep canonical IDs simple and safe for display/storage.
    text = text.replace(" ", "_").replace("-", "_")
    return "".join(ch for ch in text if ch.isalnum() or ch in {".", "_"}) or None


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not value:
            continue

        if value in seen:
            continue

        result.append(value)
        seen.add(value)

    return result


def _dedupe_missing_suggestions(
    suggestions: Sequence[MissingSeedSuggestion],
) -> list[MissingSeedSuggestion]:
    result: list[MissingSeedSuggestion] = []
    seen: set[str] = set()

    for suggestion in suggestions:
        if suggestion.suggested_seed_id in seen:
            continue

        seen.add(suggestion.suggested_seed_id)
        result.append(suggestion)

    return result
