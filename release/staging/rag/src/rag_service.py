from __future__ import annotations

import argparse
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from supabase import Client, create_client

from src.generate_explorer import MODEL, build_prompt, generate_with_openai
from src.query_duplicate_guard import (
    DuplicateExplorerMatch,
    ExplorerQueryDuplicateGuard,
)
from src.query_identity import build_query_identity
from src.retrieval.context_builder import build_context_for_query
from src.supabase_store import (
    save_explorer_output_to_supabase,
    update_explorer_service_log_id,
)

from src.validator import validate_explorer_output



load_dotenv()


RetrievalTableTitle = Literal[
    "explorer_outputs",
    "rag_card_aliases",
    "rag_card_dependencies",
    "rag_card_embeddings",
    "rag_card_registry",
    "rag_cards",
]

ResponseSource = Literal[
    "cache",
    "generated",
    "repair",
    "revision",
]


class RetrievedCardRef(BaseModel):
    """
    Compact pointer to a retrieved RAG source.

    Current context_builder dynamic_items expose card_id, title, score, and
    retrieval_reason, but not rag_cards.id. For now, key uses card_id as the
    stable RAG card key.
    """

    key: str = Field(description="Primary/key column value from the referenced table.")
    table_title: RetrievalTableTitle = Field(description="Source table name.")
    rag_score: float | None = Field(default=None)
    retrieval_reason: str = Field(description="One-line retrieval reason.")


class ValidationResult(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExplorerDraftResponse(BaseModel):
    """
    Stable RAG response contract for the desktop agent.

    explorer is only the primary key of the stored explorer_outputs row.
    """

    explorer: str = Field(description="Primary key of the explorer_outputs row.")
    explorer_created_at: str | None = Field(default=None)

    service_log: str | None = Field(
        default=None,
        description="Primary key of the rag_service_logs row.",
    )
    service_log_created_at: str | None = Field(default=None)

    assumptions: list[str] = Field(default_factory=list)
    retrieved_refs: list[RetrievedCardRef] = Field(default_factory=list)
    validation: ValidationResult
    model: str = MODEL
    source: ResponseSource = "generated"


class RagServiceConfig(BaseModel):
    backend: str = "openai"
    model: str = MODEL

    use_cache: bool = True
    use_semantic_cache: bool = True

    query_embedding_model: str = (
        "text-embedding-3-small"
    )

    query_equivalence_model: str = "gpt-5-mini"

    semantic_cache_min_similarity: (
        float
    ) = 0.75

    semantic_cache_min_confidence: (
        float
    ) = 0.97

    semantic_cache_max_candidates: (
        int
    ) = 5

    top_k: int = 12
    max_dynamic_files: int = 5
    use_tiered_dynamic: bool = True


class _RagServiceBase:
    def __init__(self, config: RagServiceConfig | None = None):
        self.config = config or RagServiceConfig()

    def _make_supabase_client(self) -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url:
            raise RuntimeError("Missing SUPABASE_URL in .env")

        if not key:
            raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY in .env")

        return create_client(url, key)

    def _fetch_explorer_output(self, explorer_id: str) -> dict[str, Any]:
        client = self._make_supabase_client()

        response = (
            client.table("explorer_outputs")
            .select(
                "id, created_at, backend, model, user_query, "
                "full_output_json, validation_passed, validation_errors, "
                "retrieved_refs, service_log_id, repaired_from_explorer_id, "
                "repair_instruction, revised_from_explorer_id, "
                "revision_instruction"
            )
            .eq("id", explorer_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise ValueError(f"No explorer_outputs row found for id={explorer_id}")

        return response.data[0]

    def _save_rag_service_log(
        self,
        *,
        event_type: str,
        user_query: str | None = None,
        explorer_output_id: str | None = None,
        explorer_output_created_at: str | None = None,
        stdout_text: str = "",
        stderr_text: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Save captured terminal-style output into Supabase.

        Expected table:
            public.rag_service_logs

        Expected primary key:
            log_id
        """
        client = self._make_supabase_client()

        row = {
            "event_type": event_type,
            "service_name": "rag_service",
            "user_query": user_query,
            "explorer_output_id": explorer_output_id,
            "explorer_output_created_at": explorer_output_created_at,
            "stdout_text": stdout_text or "",
            "stderr_text": stderr_text or "",
            "metadata": metadata or {},
        }

        response = client.table("rag_service_logs").insert(row).execute()

        if not response.data:
            raise RuntimeError(f"Supabase log insert returned no data: {response}")

        inserted = response.data[0]

        if not inserted.get("log_id"):
            raise RuntimeError(f"Supabase log insert did not return log_id: {inserted}")

        return inserted

    def _dynamic_items_to_refs(
        self,
        dynamic_items: list[dict[str, Any]],
    ) -> list[RetrievedCardRef]:
        refs: list[RetrievedCardRef] = []

        for item in dynamic_items:
            key = str(
                item.get("card_id")
                or item.get("file_path")
                or item.get("title")
                or ""
            ).strip()

            if not key:
                continue

            score = item.get("score")
            try:
                rag_score = float(score) if score is not None else None
            except (TypeError, ValueError):
                rag_score = None

            reason = str(item.get("retrieval_reason") or "").strip()
            if not reason:
                reason = f"Retrieved for {item.get('title', 'RAG context')}."

            refs.append(
                RetrievedCardRef(
                    key=key,
                    table_title="rag_cards",
                    rag_score=rag_score,
                    retrieval_reason=self._one_line(reason),
                )
            )

        return refs

    def _stored_refs_to_models(self, value: Any) -> list[RetrievedCardRef]:
        if not isinstance(value, list):
            return []

        refs: list[RetrievedCardRef] = []

        for item in value:
            if not isinstance(item, dict):
                continue

            try:
                refs.append(RetrievedCardRef.model_validate(item))
            except Exception:
                continue

        return refs

    def _extract_assumptions(self, explorer_output: dict[str, Any]) -> list[str]:
        description = str(explorer_output.get("explorer_description") or "")
        candidates: list[str] = []

        for sentence in description.replace("\n", " ").split("."):
            sentence = sentence.strip()
            if not sentence:
                continue

            lowered = sentence.lower()
            if any(
                token in lowered
                for token in [
                    "assume",
                    "assumes",
                    "assumption",
                    "default",
                    "defaults",
                    "interpreted",
                    "uses",
                ]
            ):
                candidates.append(sentence)

        return candidates

    def _clean_required_text(self, value: str, field_name: str) -> str:
        cleaned = str(value or "").strip()

        if not cleaned:
            raise ValueError(f"{field_name} is required.")

        return cleaned

    def _one_line(self, value: str) -> str:
        return " ".join(str(value or "").split())

    def _as_optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


class RagExplorerService(_RagServiceBase):
    """
    Local Python service boundary for Explorer generation.

    Important behavior:
    - generation checks exact-query cache by default;
    - generation validates and stores exactly one generated row;
    - generation never triggers repair automatically;
    - terminal output emitted during generation is captured and saved to
      rag_service_logs.
    """

    def generate_explorer(
        self,
        user_message: str,
        conversation_id: str | None = None,
    ) -> ExplorerDraftResponse:
        user_query = self._clean_required_text(
            user_message,
            "user_message",
        )

        # Always create at least the normalized/hash identity. If semantic cache
        # checking succeeds, cache_check.identity will also contain the embedding.
        query_identity = build_query_identity(
            user_query,
            include_embedding=False,
        )

        semantic_cache_error: str | None = None

        if self.config.use_cache:
            duplicate_guard = ExplorerQueryDuplicateGuard(
                embedding_model=(
                    self.config.query_embedding_model
                ),
                equivalence_model=(
                    self.config.query_equivalence_model
                ),
                min_similarity=(
                    self.config.semantic_cache_min_similarity
                ),
                min_equivalence_confidence=(
                    self.config.semantic_cache_min_confidence
                ),
                max_candidates=(
                    self.config.semantic_cache_max_candidates
                ),
            )

            cache_check = duplicate_guard.check(
                user_query=user_query,
                generation_model=self.config.model,
                semantic_enabled=(
                    self.config.use_semantic_cache
                ),
            )

            query_identity = cache_check.identity
            semantic_cache_error = (
                cache_check.semantic_error
            )

            if cache_check.match is not None:
                return self._response_from_cache(
                    cache_check.match.row,
                    user_query=user_query,
                    conversation_id=conversation_id,
                    cache_match=cache_check.match,
                )

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        generated_output: dict[str, Any] | None = None
        explorer_row: dict[str, Any] | None = None
        retrieved_refs: list[RetrievedCardRef] = []
        validation_errors: list[str] = []

        try:
            with (
                redirect_stdout(stdout_buffer),
                redirect_stderr(stderr_buffer),
            ):
                print(
                    "[rag_service] Starting Explorer generation"
                )
                print(
                    f"[rag_service] model={self.config.model}"
                )
                print(
                    f"[rag_service] backend={self.config.backend}"
                )
                print(
                    "[rag_service] "
                    f"use_cache={self.config.use_cache}"
                )
                print(
                    "[rag_service] "
                    "use_semantic_cache="
                    f"{self.config.use_semantic_cache}"
                )

                if semantic_cache_error:
                    print(
                        "[rag_service] Semantic cache check "
                        "failed open: "
                        f"{semantic_cache_error}"
                    )

                context, dynamic_items = (
                    build_context_for_query(
                        query=user_query,
                        top_k=self.config.top_k,
                        max_dynamic_files=(
                            self.config.max_dynamic_files
                        ),
                        use_tiered_dynamic=(
                            self.config.use_tiered_dynamic
                        ),
                    )
                )

                retrieved_refs = (
                    self._dynamic_items_to_refs(
                        dynamic_items
                    )
                )

                prompt = build_prompt(
                    user_query=user_query,
                    context=context,
                )

                generated_output = generate_with_openai(
                    prompt
                )

                validation_errors = (
                    validate_explorer_output(
                        generated_output
                    )
                )

                explorer_id = (
                    save_explorer_output_to_supabase(
                        output=generated_output,
                        user_query=user_query,
                        backend=self.config.backend,
                        model=self.config.model,
                        validation_errors=(
                            validation_errors
                        ),
                        retrieved_refs=[
                            ref.model_dump(mode="json")
                            for ref in retrieved_refs
                        ],
                        query_identity=query_identity,
                    )
                )

                explorer_row = (
                    self._fetch_explorer_output(
                        explorer_id
                    )
                )

                print(
                    "[rag_service] Saved "
                    "explorer_outputs row "
                    f"id={explorer_row.get('id')} "
                    f"created_at="
                    f"{explorer_row.get('created_at')}"
                )
                print(
                    "[rag_service] validation_passed="
                    f"{len(validation_errors) == 0}"
                )

        except Exception as exc:
            stdout_text = stdout_buffer.getvalue()
            stderr_text = stderr_buffer.getvalue()

            try:
                self._save_rag_service_log(
                    event_type=(
                        "rag_service.generate.error"
                    ),
                    user_query=user_query,
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                    metadata={
                        "conversation_id": (
                            conversation_id
                        ),
                        "model": self.config.model,
                        "backend": self.config.backend,
                        "semantic_cache_error": (
                            semantic_cache_error
                        ),
                        "error_type": (
                            type(exc).__name__
                        ),
                        "error_message": str(exc),
                    },
                )
            except Exception:
                # Preserve the original generation error.
                pass

            raise

        if (
            generated_output is None
            or explorer_row is None
        ):
            raise RuntimeError(
                "Generation completed without "
                "explorer output/row."
            )

        stdout_text = stdout_buffer.getvalue()
        stderr_text = stderr_buffer.getvalue()

        log_row = self._save_rag_service_log(
            event_type="rag_service.generate",
            user_query=user_query,
            explorer_output_id=(
                self._as_optional_str(
                    explorer_row.get("id")
                )
            ),
            explorer_output_created_at=(
                self._as_optional_str(
                    explorer_row.get("created_at")
                )
            ),
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            metadata={
                "conversation_id": conversation_id,
                "model": self.config.model,
                "backend": self.config.backend,
                "validation_passed": (
                    len(validation_errors) == 0
                ),
                "validation_error_count": (
                    len(validation_errors)
                ),
                "retrieved_ref_count": (
                    len(retrieved_refs)
                ),
                "uses_generate_explorer_module": True,
                "semantic_cache_error": (
                    semantic_cache_error
                ),
                "query_embedding_stored": (
                    query_identity.embedding is not None
                ),
                "query_embedding_model": (
                    query_identity.embedding_model
                ),
            },
        )

        update_explorer_service_log_id(
            explorer_id=str(explorer_row["id"]),
            service_log_id=str(log_row["log_id"]),
        )

        explorer_row["service_log_id"] = str(
            log_row["log_id"]
        )

        return ExplorerDraftResponse(
            explorer=str(explorer_row["id"]),
            explorer_created_at=(
                self._as_optional_str(
                    explorer_row.get("created_at")
                )
            ),
            service_log=(
                self._as_optional_str(
                    log_row.get("log_id")
                )
            ),
            service_log_created_at=(
                self._as_optional_str(
                    log_row.get("created_at")
                )
            ),
            assumptions=(
                self._extract_assumptions(
                    generated_output
                )
            ),
            retrieved_refs=retrieved_refs,
            validation=ValidationResult(
                passed=(
                    len(validation_errors) == 0
                ),
                errors=validation_errors,
            ),
            model=self.config.model,
            source="generated",
        )

   
    def _response_from_cache(
        self,
        cached: dict[str, Any],
        *,
        user_query: str,
        conversation_id: str | None,
        cache_match: DuplicateExplorerMatch | None = None,
    ) -> ExplorerDraftResponse:
        output = cached.get("full_output_json")

        if not isinstance(output, dict):
            raise ValueError(
                "Cached row "
                f"{cached.get('id')} has invalid "
                "full_output_json."
            )

        validation_errors = (
            cached.get("validation_errors")
            or []
        )

        if not isinstance(validation_errors, list):
            validation_errors = [
                str(validation_errors)
            ]

        match_type = str(
            (
                cache_match.match_type
                if cache_match is not None
                else cached.get(
                    "_cache_match_type"
                )
            )
            or "cache"
        )

        matched_query = (
            cached.get("_cache_matched_query")
            or cached.get("user_query")
        )

        similarity = (
            cache_match.similarity
            if cache_match is not None
            else cached.get(
                "_cache_similarity"
            )
        )

        equivalence_confidence = (
            cache_match.equivalence_confidence
            if cache_match is not None
            else cached.get(
                "_cache_equivalence_confidence"
            )
        )

        equivalence_reason = (
            cache_match.equivalence_reason
            if cache_match is not None
            else cached.get(
                "_cache_equivalence_reason"
            )
        )

        stdout_text = (
            "[rag_service] Query cache hit.\n"
            "[rag_service] "
            f"match_type={match_type}\n"
            "[rag_service] Reusing "
            "explorer_outputs row "
            f"id={cached.get('id')} "
            f"created_at={cached.get('created_at')}\n"
        )

        log_row = self._save_rag_service_log(
            event_type=(
                "rag_service.generate.cache_hit"
            ),
            user_query=user_query,
            explorer_output_id=(
                self._as_optional_str(
                    cached.get("id")
                )
            ),
            explorer_output_created_at=(
                self._as_optional_str(
                    cached.get("created_at")
                )
            ),
            stdout_text=stdout_text,
            stderr_text="",
            metadata={
                "conversation_id": (
                    conversation_id
                ),
                "model": str(
                    cached.get("model")
                    or self.config.model
                ),
                "backend": str(
                    cached.get("backend")
                    or self.config.backend
                ),
                "validation_passed": bool(
                    cached.get(
                        "validation_passed"
                    )
                ),
                "cache_match_type": match_type,
                "matched_query": matched_query,
                "similarity": similarity,
                "equivalence_confidence": (
                    equivalence_confidence
                ),
                "equivalence_reason": (
                    equivalence_reason
                ),
            },
        )

        return ExplorerDraftResponse(
            explorer=str(cached.get("id")),
            explorer_created_at=(
                self._as_optional_str(
                    cached.get("created_at")
                )
            ),
            service_log=(
                self._as_optional_str(
                    log_row.get("log_id")
                )
            ),
            service_log_created_at=(
                self._as_optional_str(
                    log_row.get("created_at")
                )
            ),
            assumptions=(
                self._extract_assumptions(
                    output
                )
            ),
            retrieved_refs=(
                self._stored_refs_to_models(
                    cached.get("retrieved_refs")
                )
            ),
            validation=ValidationResult(
                passed=bool(
                    cached.get(
                        "validation_passed"
                    )
                ),
                errors=[
                    str(error)
                    for error
                    in validation_errors
                ],
            ),
            model=str(
                cached.get("model")
                or self.config.model
            ),
            source="cache",
        )


class RagExplorerRepairService(_RagServiceBase):
    """
    Explicit repair trigger for generated Explorer rows.

    Normal generation never calls this service. The desktop app/orchestrator calls
    repair_explorer(...) only after a user action or explicit workflow trigger.
    """

    def repair_explorer(
        self,
        explorer: str,
        repair_instruction: str | None = None,
        conversation_id: str | None = None,
    ) -> ExplorerDraftResponse:
        explorer_id = self._clean_required_text(explorer, "explorer")
        existing = self._fetch_explorer_output(explorer_id)
        existing_output = existing.get("full_output_json")

        if not isinstance(existing_output, dict):
            raise ValueError(
                f"Stored explorer {explorer_id} has invalid full_output_json."
            )

        original_query = str(existing.get("user_query") or "").strip()
        if not original_query:
            original_query = "Repair this stored MetaStock Explorer."

        existing_errors = existing.get("validation_errors") or []
        if not isinstance(existing_errors, list):
            existing_errors = [str(existing_errors)]

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        repaired_output: dict[str, Any] | None = None
        repaired_row: dict[str, Any] | None = None
        retrieved_refs: list[RetrievedCardRef] = []
        validation_errors: list[str] = []

        try:
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                print("[rag_service] Starting explicit Explorer repair")
                print(f"[rag_service] repair_of={explorer_id}")
                print(f"[rag_service] model={self.config.model}")
                print(f"[rag_service] backend={self.config.backend}")

                context, dynamic_items = build_context_for_query(
                    query=original_query,
                    top_k=self.config.top_k,
                    max_dynamic_files=self.config.max_dynamic_files,
                    use_tiered_dynamic=self.config.use_tiered_dynamic,
                )

                retrieved_refs = self._dynamic_items_to_refs(dynamic_items)

                prompt = self._build_repair_prompt(
                    original_query=original_query,
                    context=context,
                    failed_explorer=existing_output,
                    validation_errors=[str(error) for error in existing_errors],
                    repair_instruction=repair_instruction,
                )

                repaired_output = generate_with_openai(prompt)
                validation_errors = validate_explorer_output(repaired_output)

                repair_query = (
                    self._build_repair_user_query(
                        original_explorer_id=explorer_id,
                        original_query=original_query,
                        repair_instruction=(
                            repair_instruction
                        ),
                    )
                )

                # The persisted user_query keeps repair lineage, but the cache identity points
                # to the original strategy request. This allows a valid repaired Explorer to
                # replace the invalid original as the preferred cache result.
                try:
                    repair_query_identity = (
                        build_query_identity(
                            original_query,
                            include_embedding=(
                                self.config.use_semantic_cache
                            ),
                            embedding_model=(
                                self.config
                                .query_embedding_model
                            ),
                        )
                    )
                except Exception as identity_exc:
                    # Embedding is a cache optimization. Failure to create it must not prevent
                    # the actual Explorer repair from completing.
                    print(
                        "[rag_service] Repair query "
                        "embedding failed open: "
                        f"{type(identity_exc).__name__}: "
                        f"{identity_exc}"
                    )

                    repair_query_identity = (
                        build_query_identity(
                            original_query,
                            include_embedding=False,
                        )
                    )

                repaired_id = (
                    save_explorer_output_to_supabase(
                        output=repaired_output,
                        user_query=repair_query,
                        backend=(
                            f"{self.config.backend}_repair"
                        ),
                        model=self.config.model,
                        validation_errors=(
                            validation_errors
                        ),
                        retrieved_refs=[
                            ref.model_dump(mode="json")
                            for ref in retrieved_refs
                        ],
                        repaired_from_explorer_id=(
                            explorer_id
                        ),
                        repair_instruction=(
                            repair_instruction
                        ),
                        query_identity=(
                            repair_query_identity
                        ),
                    )
                )

                repaired_row = self._fetch_explorer_output(repaired_id)

                print(
                    "[rag_service] Saved repaired explorer_outputs row "
                    f"id={repaired_row.get('id')} "
                    f"created_at={repaired_row.get('created_at')}"
                )
                print(
                    "[rag_service] validation_passed="
                    f"{len(validation_errors) == 0}"
                )

        except Exception as exc:
            stdout_text = stdout_buffer.getvalue()
            stderr_text = stderr_buffer.getvalue()

            try:
                self._save_rag_service_log(
                    event_type="rag_service.repair.error",
                    user_query=original_query,
                    explorer_output_id=explorer_id,
                    explorer_output_created_at=self._as_optional_str(
                        existing.get("created_at")
                    ),
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                    metadata={
                        "conversation_id": conversation_id,
                        "repair_of": explorer_id,
                        "model": self.config.model,
                        "backend": self.config.backend,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
            except Exception:
                pass

            raise

        if repaired_output is None or repaired_row is None:
            raise RuntimeError("Repair completed without repaired output/row.")

        log_row = self._save_rag_service_log(
            event_type="rag_service.repair",
            user_query=original_query,
            explorer_output_id=self._as_optional_str(repaired_row.get("id")),
            explorer_output_created_at=self._as_optional_str(
                repaired_row.get("created_at")
            ),
            stdout_text=stdout_buffer.getvalue(),
            stderr_text=stderr_buffer.getvalue(),
            metadata={
                "conversation_id": conversation_id,
                "repair_of": explorer_id,
                "model": self.config.model,
                "backend": self.config.backend,
                "validation_passed": len(validation_errors) == 0,
                "validation_error_count": len(validation_errors),
                "retrieved_ref_count": len(retrieved_refs),
            },
        )

        update_explorer_service_log_id(
            explorer_id=str(repaired_row["id"]),
            service_log_id=str(log_row["log_id"]),
        )
        repaired_row["service_log_id"] = str(log_row["log_id"])

        return ExplorerDraftResponse(
            explorer=str(repaired_row["id"]),
            explorer_created_at=self._as_optional_str(repaired_row.get("created_at")),
            service_log=self._as_optional_str(log_row.get("log_id")),
            service_log_created_at=self._as_optional_str(log_row.get("created_at")),
            assumptions=self._extract_assumptions(repaired_output),
            retrieved_refs=retrieved_refs,
            validation=ValidationResult(
                passed=len(validation_errors) == 0,
                errors=validation_errors,
            ),
            model=self.config.model,
            source="repair",
        )

    def _build_repair_prompt(
        self,
        *,
        original_query: str,
        context: str,
        failed_explorer: dict[str, Any],
        validation_errors: list[str],
        repair_instruction: str | None,
    ) -> str:
        optional_instruction = ""
        if repair_instruction and repair_instruction.strip():
            optional_instruction = (
                "\nAdditional repair instruction from caller:\n"
                f"{repair_instruction.strip()}\n"
            )

        return f"""
You are repairing a MetaStock Explorer JSON object.

The previous output failed validation or was selected for explicit repair.
Fix only the syntax/contract problems unless the caller gives an additional
repair instruction. Preserve the original trading intent as much as possible.
Use the provided context only.
Return valid JSON only.

Validation errors from the stored row:
{json.dumps(validation_errors, indent=2)}

Previous Explorer JSON:
{json.dumps(failed_explorer, indent=2)}
{optional_instruction}
Required JSON schema:
{{
  "explorer_name": "string",
  "explorer_description": "string",
  "explorer_code_body": "string",
  "col_definitions": [
    {{
      "col_letter": "A",
      "col_code": "string"
    }}
  ]
}}

Rules:
- explorer_code_body must be the Filter formula body only.
- Do not include "Filter:" inside explorer_code_body.
- col_code must be the formula body only.
- Do not include "col A =" inside col_code.
- Use AND and OR, not && or ||.
- Use = for equality, not ==.
- Do not invent unsupported MetaStock functions.
- Do not use natural language inside formulas.

Context:
{context}

Original user request:
{original_query}

Return repaired JSON only.
""".strip()

    def _build_repair_user_query(
        self,
        *,
        original_explorer_id: str,
        original_query: str,
        repair_instruction: str | None,
    ) -> str:
        parts = [
            f"[repair_of:{original_explorer_id}]",
            original_query,
        ]

        if repair_instruction and repair_instruction.strip():
            parts.append(f"Repair instruction: {repair_instruction.strip()}")

        return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local RAG service CLI for MetaStock Explorer generation/repair."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("query", help="Natural-language Explorer request")
    generate_parser.add_argument("--no-cache", action="store_true")
    generate_parser.add_argument("--max-dynamic-files", type=int, default=5)
    generate_parser.add_argument("--no-tiered-dynamic", action="store_true")

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("explorer", help="explorer_outputs.id to repair")
    repair_parser.add_argument("--instruction", default=None)
    repair_parser.add_argument("--max-dynamic-files", type=int, default=5)
    repair_parser.add_argument("--no-tiered-dynamic", action="store_true")

    args = parser.parse_args()

    config = RagServiceConfig(
        use_cache=not getattr(args, "no_cache", False),
        max_dynamic_files=args.max_dynamic_files,
        use_tiered_dynamic=not args.no_tiered_dynamic,
    )

    if args.command == "generate":
        response = RagExplorerService(config).generate_explorer(args.query)
    elif args.command == "repair":
        response = RagExplorerRepairService(config).repair_explorer(
            explorer=args.explorer,
            repair_instruction=args.instruction,
        )
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(
        json.dumps(
            response.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()