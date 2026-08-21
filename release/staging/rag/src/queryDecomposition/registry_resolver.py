from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from supabase import Client


DEFAULT_ALLOWED_EDGE_TYPES = ("requires", "suggests")
DEFAULT_MAX_DEPENDENCY_DEPTH = 5


@dataclass(frozen=True)
class RegistryConcept:
    canonical_id: str
    title: str
    concept_type: str
    card_bucket: str
    source_path: str
    aliases: tuple[str, ...]

    @classmethod
    def from_registry_row(
        cls,
        row: dict[str, Any],
        aliases: Sequence[str],
    ) -> "RegistryConcept":
        return cls(
            canonical_id=row.get("canonical_id", ""),
            title=row.get("title", ""),
            concept_type=row.get("concept_type", ""),
            card_bucket=row.get("card_bucket", ""),
            source_path=row.get("source_path", ""),
            aliases=tuple(aliases),
        )


@dataclass(frozen=True)
class RegistryCard:
    canonical_id: str
    source_path: str
    registry_title: str
    concept_type: str
    registry_bucket: str
    depth: int
    priority: int
    card_id: str
    card_title: str
    card_type: str
    card_bucket: str
    category: str | None
    body_markdown: str
    content_hash: str | None = None

    @classmethod
    def from_rpc_row(cls, row: dict[str, Any]) -> "RegistryCard":
        card_title = row.get("card_title") or row.get("registry_title") or ""
        card_bucket = row.get("card_bucket") or row.get("registry_bucket") or ""

        return cls(
            canonical_id=row.get("canonical_id", ""),
            source_path=row.get("source_path", ""),
            registry_title=row.get("registry_title", ""),
            concept_type=row.get("concept_type", ""),
            registry_bucket=row.get("registry_bucket", ""),
            depth=int(row.get("depth") or 0),
            priority=int(row.get("priority") or 100),
            card_id=str(row.get("card_id") or ""),
            card_title=card_title,
            card_type=row.get("card_type") or row.get("concept_type") or "",
            card_bucket=card_bucket,
            category=row.get("category"),
            body_markdown=row.get("body_markdown") or "",
            content_hash=row.get("content_hash"),
        )

    def to_rag_card_row(self) -> dict[str, Any]:
        """
        Convert the registry-resolved card into the same row shape used by
        context_builder.make_dynamic_item().
        """
        return {
            "card_id": self.card_id,
            "title": self.card_title or self.registry_title,
            "card_type": self.card_type,
            "card_bucket": self.card_bucket,
            "category": self.category,
            "source_path": self.source_path,
            "body_markdown": self.body_markdown,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class AliasMatch:
    canonical_id: str
    title: str
    concept_type: str
    card_bucket: str
    alias_text: str
    alias_type: str
    weight: float
    source_path: str

    @classmethod
    def from_rpc_row(cls, row: dict[str, Any]) -> "AliasMatch":
        return cls(
            canonical_id=row.get("canonical_id", ""),
            title=row.get("title", ""),
            concept_type=row.get("concept_type", ""),
            card_bucket=row.get("card_bucket", ""),
            alias_text=row.get("alias_text", ""),
            alias_type=row.get("alias_type", ""),
            weight=float(row.get("weight") or 0),
            source_path=row.get("source_path", ""),
        )


@dataclass(frozen=True)
class SemanticProfile:
    canonical_id: str
    source_path: str
    semantic_signature: dict[str, Any]
    compatible_condition_frames: list[dict[str, Any]]
    incompatible_condition_frames: list[dict[str, Any]]
    review_status: str
    profile_version: int
    evidence_text: str = ""

    @classmethod
    def from_card_row(
        cls,
        *,
        canonical_id: str,
        registry_row: dict[str, Any],
        card_row: dict[str, Any] | None,
    ) -> "SemanticProfile":
        card_row = card_row or {}

        title = (
            card_row.get("title")
            or registry_row.get("title")
            or canonical_id
        )

        semantic_signature = {
            "canonical_id": canonical_id,
            "title": title,
            "concept_type": registry_row.get("concept_type", ""),
            "card_bucket": registry_row.get("card_bucket", ""),
            "source_path": registry_row.get("source_path", ""),
            "card_type": card_row.get("card_type", ""),
            "category": card_row.get("category", ""),
            "frontmatter": _as_dict(card_row.get("frontmatter")),
            "structured_json": _as_dict(card_row.get("structured_json")),
        }

        evidence_text = _truncate_text(
            "\n\n".join(
                part
                for part in [
                    f"Title: {title}",
                    f"Canonical ID: {canonical_id}",
                    f"Source path: {registry_row.get('source_path', '')}",
                    f"Card type: {card_row.get('card_type', '')}",
                    f"Category: {card_row.get('category', '')}",
                    "Plain text:",
                    str(card_row.get("plain_text") or ""),
                    "Body markdown:",
                    str(card_row.get("body_markdown") or ""),
                ]
                if part
            ),
            max_chars=6000,
        )

        return cls(
            canonical_id=canonical_id,
            source_path=registry_row.get("source_path", ""),
            semantic_signature=semantic_signature,
            compatible_condition_frames=[],
            incompatible_condition_frames=[],
            review_status="runtime_card_evidence",
            profile_version=1,
            evidence_text=evidence_text,
        )

    @classmethod
    def from_table_row(cls, row: dict[str, Any]) -> "SemanticProfile":
        return cls(
            canonical_id=row.get("canonical_id", ""),
            source_path=row.get("source_path", ""),
            semantic_signature=_as_dict(row.get("semantic_signature")),
            compatible_condition_frames=_as_list_of_dicts(
                row.get("compatible_condition_frames")
            ),
            incompatible_condition_frames=_as_list_of_dicts(
                row.get("incompatible_condition_frames")
            ),
            review_status=row.get("review_status", ""),
            profile_version=int(row.get("profile_version") or 1),
            evidence_text=str(row.get("evidence_text") or ""),
        )

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "source_path": self.source_path,
            "review_status": self.review_status,
            "profile_version": self.profile_version,
            "semantic_signature": self.semantic_signature,
            "compatible_condition_frames": self.compatible_condition_frames,
            "incompatible_condition_frames": self.incompatible_condition_frames,
            "card_evidence": self.evidence_text,
        }


class RegistryResolver:
    """
    Resolves canonical concept IDs through the Supabase registry graph.

    Tell-style API:
        resolver.fetch_active_concepts()
        resolver.fetch_semantic_profiles(seed_canonical_ids)
        resolver.resolve_cards(seed_canonical_ids)

    The caller does not manually fetch registry tables, expand dependencies, or
    match source paths. That logic stays behind this object.
    """

    def __init__(self, supabase: Client):
        self.supabase = supabase

    def fetch_active_concepts(self) -> list[RegistryConcept]:
        """
        Load active registry concepts and their aliases for the LLM seed planner.
        """
        concept_response = (
            self.supabase.table("rag_card_registry")
            .select("canonical_id,title,concept_type,card_bucket,source_path")
            .eq("is_active", True)
            .execute()
        )
        concept_rows = concept_response.data or []

        alias_response = (
            self.supabase.table("rag_card_aliases")
            .select("canonical_id,alias_text,weight")
            .eq("is_active", True)
            .execute()
        )
        alias_rows = alias_response.data or []

        aliases_by_concept: dict[str, list[tuple[float, str]]] = {}
        for row in alias_rows:
            canonical_id = row.get("canonical_id")
            alias_text = row.get("alias_text")
            if not canonical_id or not alias_text:
                continue

            aliases_by_concept.setdefault(canonical_id, []).append(
                (float(row.get("weight") or 0), str(alias_text))
            )

        concepts: list[RegistryConcept] = []
        for row in concept_rows:
            canonical_id = row.get("canonical_id", "")
            weighted_aliases = aliases_by_concept.get(canonical_id, [])
            weighted_aliases.sort(key=lambda item: item[0], reverse=True)
            aliases = [alias for _, alias in weighted_aliases]
            concepts.append(RegistryConcept.from_registry_row(row, aliases))

        concepts.sort(key=lambda c: (c.concept_type, c.canonical_id))
        return concepts

    def fetch_semantic_profiles(
        self,
        canonical_ids: Sequence[str] | None = None,
        *,
        review_statuses: Sequence[str] = ("pending", "approved"),
    ) -> list[SemanticProfile]:
        """
        Build runtime semantic profiles from existing registry + card content.

        This intentionally does NOT require a separate rag_card_semantic_profiles
        table. The coverage verifier uses the actual knowledge card text as
        semantic evidence.
        """
        ordered_ids = _dedupe_preserve_order(canonical_ids or [])

        if not ordered_ids:
            return []

        registry_response = (
            self.supabase.table("rag_card_registry")
            .select("canonical_id,title,concept_type,card_bucket,source_path")
            .in_("canonical_id", ordered_ids)
            .eq("is_active", True)
            .execute()
        )

        registry_rows = registry_response.data or []

        registry_by_id = {
            row.get("canonical_id"): row
            for row in registry_rows
            if row.get("canonical_id")
        }

        source_paths = _dedupe_preserve_order(
            [
                row.get("source_path", "")
                for row in registry_rows
                if row.get("source_path")
            ]
        )

        cards_by_source_path: dict[str, dict[str, Any]] = {}

        if source_paths:
            card_response = (
                self.supabase.table("rag_cards")
                .select(
                    "source_path,title,card_type,card_bucket,category,"
                    "frontmatter,structured_json,plain_text,body_markdown,content_hash"
                )
                .in_("source_path", source_paths)
                .execute()
            )

            for row in card_response.data or []:
                source_path = row.get("source_path")
                if source_path and source_path not in cards_by_source_path:
                    cards_by_source_path[source_path] = row

        profiles: list[SemanticProfile] = []

        for canonical_id in ordered_ids:
            registry_row = registry_by_id.get(canonical_id)

            if not registry_row:
                print(
                    "[seed_coverage] No registry row found for seed; "
                    f"keeping seed without coverage verification: {canonical_id}"
                )
                continue

            source_path = registry_row.get("source_path", "")
            card_row = cards_by_source_path.get(source_path)

            if not card_row:
                print(
                    "[seed_coverage] No rag_cards row found for seed source_path; "
                    f"keeping seed without coverage verification: {canonical_id} "
                    f"| source_path={source_path}"
                )
                continue

            profiles.append(
                SemanticProfile.from_card_row(
                    canonical_id=canonical_id,
                    registry_row=registry_row,
                    card_row=card_row,
                )
            )

        return profiles

    def match_aliases(
        self,
        query_text: str,
        min_weight: float = 0.7,
    ) -> list[AliasMatch]:
        response = self.supabase.rpc(
            "match_rag_card_aliases",
            {
                "query_text": query_text,
                "min_weight": min_weight,
            },
        ).execute()

        return [AliasMatch.from_rpc_row(row) for row in (response.data or [])]

    def resolve_cards(
        self,
        seed_canonical_ids: Sequence[str],
        allowed_edge_types: Sequence[str] = DEFAULT_ALLOWED_EDGE_TYPES,
        max_depth: int = DEFAULT_MAX_DEPENDENCY_DEPTH,
    ) -> tuple[list[RegistryCard], list[str]]:
        """
        Expand seed concepts through registry dependencies and return actual
        rag_cards rows.

        Returns:
        - resolved registry cards
        - missing seed canonical IDs
        """
        ordered_seed_ids = _dedupe_preserve_order(seed_canonical_ids)

        if not ordered_seed_ids:
            return [], []

        response = self.supabase.rpc(
            "resolve_rag_registry_cards",
            {
                "seed_canonical_ids": ordered_seed_ids,
                "allowed_edge_types": list(allowed_edge_types),
                "max_depth": max_depth,
            },
        ).execute()

        rows = response.data or []
        cards = [RegistryCard.from_rpc_row(row) for row in rows]

        # Keep only cards that actually resolve to a rag_cards row with body.
        # The missing list below still reports unresolved seed IDs.
        cards = [card for card in cards if card.card_id and card.body_markdown]

        resolved_ids = {card.canonical_id for card in cards}
        missing_seed_ids = [
            canonical_id
            for canonical_id in ordered_seed_ids
            if canonical_id not in resolved_ids
        ]

        return cards, missing_seed_ids


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


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]

def _truncate_text(value: str, *, max_chars: int) -> str:
    text = str(value or "")

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n[TRUNCATED]"