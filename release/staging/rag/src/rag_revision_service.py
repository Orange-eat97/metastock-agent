from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from src.generate_explorer import generate_with_openai
from src.query_identity import build_query_identity
from src.rag_service import (
    ExplorerDraftResponse,
    RetrievedCardRef,
    ValidationResult,
    _RagServiceBase,
)
from src.retrieval.context_builder import (
    build_context_for_query,
)
from src.supabase_store import (
    save_explorer_output_to_supabase,
    update_explorer_service_log_id,
)
from src.validator import validate_explorer_output


class RagExplorerRevisionService(_RagServiceBase):
    """
    Explicit strategy-logic revision service.

    Revision is separate from repair. It intentionally changes strategy logic
    or parameters, stores a new Explorer row, and never mutates the original.

    Revised rows receive normalized query identity fields for traceability, but
    they do not receive semantic-cache embeddings. A revision represents
    deliberately changed strategy logic and must not be reused as a semantic
    duplicate of the original request.
    """

    def revise_explorer(
        self,
        explorer: str,
        revision_instruction: str,
        conversation_id: str | None = None,
    ) -> ExplorerDraftResponse:
        explorer_id = self._clean_required_text(
            explorer,
            "explorer",
        )
        instruction = self._clean_required_text(
            revision_instruction,
            "revision_instruction",
        )

        existing = self._fetch_explorer_output(
            explorer_id
        )
        existing_output = existing.get(
            "full_output_json"
        )

        if not isinstance(existing_output, dict):
            raise ValueError(
                "Stored Explorer has invalid "
                f"full_output_json: {explorer_id}"
            )

        original_query = str(
            existing.get("user_query") or ""
        ).strip()

        if not original_query:
            original_query = (
                "Revise this stored MetaStock Explorer."
            )

        retrieval_query = (
            f"{original_query}\n"
            f"Revision instruction: {instruction}"
        )

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        revised_output: dict[str, Any] | None = None
        revised_row: dict[str, Any] | None = None
        retrieved_refs: list[RetrievedCardRef] = []
        validation_errors: list[str] = []

        try:
            with (
                redirect_stdout(stdout_buffer),
                redirect_stderr(stderr_buffer),
            ):
                print(
                    "[rag_revision_service] "
                    "Starting Explorer revision"
                )
                print(
                    "[rag_revision_service] "
                    f"revision_of={explorer_id}"
                )
                print(
                    "[rag_revision_service] "
                    f"model={self.config.model}"
                )
                print(
                    "[rag_revision_service] "
                    f"backend={self.config.backend}"
                )

                context, dynamic_items = (
                    build_context_for_query(
                        query=retrieval_query,
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

                prompt = self._build_revision_prompt(
                    original_query=original_query,
                    context=context,
                    existing_explorer=existing_output,
                    revision_instruction=instruction,
                )

                revised_output = generate_with_openai(
                    prompt
                )

                if revised_output == existing_output:
                    raise ValueError(
                        "Revision produced no change to "
                        "the stored Explorer."
                    )

                validation_errors = (
                    validate_explorer_output(
                        revised_output
                    )
                )

                revision_query = (
                    self._build_revision_user_query(
                        original_explorer_id=explorer_id,
                        original_query=original_query,
                        revision_instruction=instruction,
                    )
                )

                # Revisions intentionally change strategy meaning. Store the
                # normalized query and hash for traceability, but do not create
                # an embedding that could make the revision eligible for
                # semantic duplicate matching.
                revision_query_identity = (
                    build_query_identity(
                        revision_query,
                        include_embedding=False,
                    )
                )

                revised_id = (
                    save_explorer_output_to_supabase(
                        output=revised_output,
                        user_query=revision_query,
                        backend=(
                            f"{self.config.backend}_revision"
                        ),
                        model=self.config.model,
                        validation_errors=(
                            validation_errors
                        ),
                        retrieved_refs=[
                            ref.model_dump(mode="json")
                            for ref in retrieved_refs
                        ],
                        revised_from_explorer_id=(
                            explorer_id
                        ),
                        revision_instruction=instruction,
                        query_identity=(
                            revision_query_identity
                        ),
                    )
                )

                revised_row = (
                    self._fetch_explorer_output(
                        revised_id
                    )
                )

                print(
                    "[rag_revision_service] Saved "
                    "revised explorer_outputs row "
                    f"id={revised_id}"
                )
                print(
                    "[rag_revision_service] "
                    "validation_passed="
                    f"{len(validation_errors) == 0}"
                )
                print(
                    "[rag_revision_service] "
                    "semantic_cache_embedding_stored=False"
                )

        except Exception as exc:
            try:
                self._save_rag_service_log(
                    event_type=(
                        "rag_service.revision.error"
                    ),
                    user_query=original_query,
                    explorer_output_id=explorer_id,
                    explorer_output_created_at=(
                        self._as_optional_str(
                            existing.get("created_at")
                        )
                    ),
                    stdout_text=(
                        stdout_buffer.getvalue()
                    ),
                    stderr_text=(
                        stderr_buffer.getvalue()
                    ),
                    metadata={
                        "conversation_id": (
                            conversation_id
                        ),
                        "revision_of": explorer_id,
                        "revision_instruction": (
                            instruction
                        ),
                        "model": self.config.model,
                        "backend": self.config.backend,
                        "semantic_cache_eligible": False,
                        "error_type": (
                            type(exc).__name__
                        ),
                        "error_message": str(exc),
                    },
                )
            except Exception:
                # Preserve the original revision error if service-log storage
                # also fails.
                pass

            raise

        if (
            revised_output is None
            or revised_row is None
        ):
            raise RuntimeError(
                "Revision completed without a "
                "revised output row."
            )

        log_row = self._save_rag_service_log(
            event_type="rag_service.revision",
            user_query=original_query,
            explorer_output_id=(
                self._as_optional_str(
                    revised_row.get("id")
                )
            ),
            explorer_output_created_at=(
                self._as_optional_str(
                    revised_row.get("created_at")
                )
            ),
            stdout_text=(
                stdout_buffer.getvalue()
            ),
            stderr_text=(
                stderr_buffer.getvalue()
            ),
            metadata={
                "conversation_id": conversation_id,
                "revision_of": explorer_id,
                "revision_instruction": instruction,
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
                "semantic_cache_eligible": False,
                "query_identity_stored": True,
                "query_embedding_stored": False,
            },
        )

        update_explorer_service_log_id(
            explorer_id=str(
                revised_row["id"]
            ),
            service_log_id=str(
                log_row["log_id"]
            ),
        )

        revised_row["service_log_id"] = str(
            log_row["log_id"]
        )

        return ExplorerDraftResponse(
            explorer=str(
                revised_row["id"]
            ),
            explorer_created_at=(
                self._as_optional_str(
                    revised_row.get(
                        "created_at"
                    )
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
                    revised_output
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
            source="revision",
        )

    def _build_revision_prompt(
        self,
        *,
        original_query: str,
        context: str,
        existing_explorer: dict[str, Any],
        revision_instruction: str,
    ) -> str:
        return f"""
You are revising one stored MetaStock Explorer JSON object.

Apply the user's revision instruction as a minimal change to the existing
Explorer. Preserve every condition, column, parameter, and assumption that the
instruction does not explicitly change. Do not simplify the strategy, remove
unmentioned conditions, or create a different scan.

Examples of the preservation rule:
- If the old filter is `RSI(14) < 30 AND C > Mov(C,50,S)` and the instruction
  says `use 25 instead of 30`, the revised filter must preserve the moving
  average condition and become `RSI(14) < 25 AND C > Mov(C,50,S)` or its
  equivalent column-reference form.
- Keep existing column letters and formulas unchanged unless the requested
  change requires modifying them.
- Repair incidental syntax errors only when necessary for the revised output to
  validate.

Explorer naming and version rules:
- A revision always creates a whole new Explorer.
- Preserve the existing Explorer's descriptive base name; do not rename it
  according to the changed formula.
- The AI-managed base name must begin with the exact prefix `AI_`.
- If the existing name does not begin with `AI_`, treat it as a legacy
  AI-generated name and add the `AI_` prefix.
- The initial Explorer is version 1 but does not display a version suffix.
- The first revised Explorer must append `_2`.
- Each later revision must increment only the final revision suffix:
  `_2` becomes `_3`, `_3` becomes `_4`, and so on.
- Revised-name format:
  `AI_<original generated explorer name>_<version number>`.
- Do not add `AI_` more than once.
- Do not omit the numeric suffix from a revised Explorer.

Examples:
- `RSI Below 30` revised for the first time becomes
  `AI_RSI Below 30_2`.
- `AI_RSI Below 30` revised for the first time becomes
  `AI_RSI Below 30_2`.
- `AI_RSI Below 30_2` revised again becomes
  `AI_RSI Below 30_3`.

Return valid JSON only with this schema:
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
- explorer_code_body is the Filter formula body only.
- Do not include `Filter:` in explorer_code_body.
- col_code is a formula body only.
- Use AND and OR, not && or ||.
- Use = for equality, not ==.
- Do not invent unsupported MetaStock functions.
- Do not use natural language inside formulas.
- Return no commentary outside the JSON object.

Original user request:
{original_query}

Existing Explorer JSON:
{json.dumps(existing_explorer, indent=2)}

Revision instruction:
{revision_instruction}

Retrieved MetaStock context:
{context}

Return the minimally revised JSON only.
""".strip()

    def _build_revision_user_query(
        self,
        *,
        original_explorer_id: str,
        original_query: str,
        revision_instruction: str,
    ) -> str:
        return "\n".join(
            [
                (
                    "[revision_of:"
                    f"{original_explorer_id}]"
                ),
                original_query,
                (
                    "Revision instruction: "
                    f"{revision_instruction}"
                ),
            ]
        )