from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

from src.validator import validate_explorer_output


load_dotenv()


class ExplorerEditConflictError(RuntimeError):
    """Raised when an Explorer changed after the UI card was loaded."""


class ExplorerValidationError(ValueError):
    """Raised when deterministic MetaStock validation rejects a manual edit."""

    def __init__(self, errors: list[str]) -> None:
        cleaned = [str(error).strip() for error in errors if str(error).strip()]
        self.errors = cleaned or ["The Explorer failed deterministic validation."]
        super().__init__("\n".join(self.errors))


class RagExplorerUpdateService:
    """
    Controlled write service for manual Explorer-card edits.

    Only allowlisted fields inside explorer_outputs.full_output_json are
    replaced. The service re-runs the deterministic validator and updates the
    durable validation columns. It never calls an LLM or RAG retrieval.
    """

    _EDITABLE_FIELDS = {
        "explorer_name",
        "explorer_description",
        "explorer_code_body",
        "col_definitions",
        "assumptions",
    }

    def __init__(self, client: Client | None = None) -> None:
        self.client = client if client is not None else self._make_client()

    def update_explorer_full_json(
        self,
        *,
        explorer_id: str,
        expected_version: int,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        cleaned_id = self._required_text(explorer_id, "explorer_id")
        if expected_version < 0:
            raise ValueError("expected_version cannot be negative.")
        if not isinstance(patch, dict):
            raise ValueError("patch must be an object.")

        unexpected = sorted(set(patch) - self._EDITABLE_FIELDS)
        if unexpected:
            raise ValueError(
                "Unsupported Explorer edit field(s): " + ", ".join(unexpected)
            )

        current = self._get_row(cleaned_id)
        current_version = int(current.get("manual_edit_version") or 0)
        if current_version != expected_version:
            raise ExplorerEditConflictError(
                "This Explorer changed after the card was opened. Reload it before saving."
            )

        full_output = current.get("full_output_json")
        if not isinstance(full_output, dict):
            raise RuntimeError("Stored full_output_json is not a JSON object.")

        updated_output = dict(full_output)
        updated_output.update(patch)
        validation_messages = validate_explorer_output(updated_output)
        hard_errors = [
            str(message)
            for message in validation_messages
            if not str(message).startswith("Warning:")
        ]
        if hard_errors:
            raise ExplorerValidationError(hard_errors)

        updated_at = datetime.now(timezone.utc).isoformat()

        response = (
            self.client.table("explorer_outputs")
            .update(
                {
                    "full_output_json": updated_output,
                    "validation_passed": True,
                    "validation_errors": validation_messages,
                    "updated_at": updated_at,
                    "manual_edit_version": current_version + 1,
                }
            )
            .eq("id", cleaned_id)
            .eq("manual_edit_version", current_version)
            .execute()
        )

        if not response.data:
            raise ExplorerEditConflictError(
                "This Explorer changed while it was being saved. Reload it before retrying."
            )

        return self._flatten_row(self._get_row(cleaned_id))

    def get_explorer(self, explorer_id: str) -> dict[str, Any]:
        return self._flatten_row(
            self._get_row(self._required_text(explorer_id, "explorer_id"))
        )

    def _get_row(self, explorer_id: str) -> dict[str, Any]:
        response = (
            self.client.table("explorer_outputs")
            .select(
                "id, created_at, updated_at, manual_edit_version, backend, model, "
                "user_query, full_output_json, validation_passed, validation_errors, "
                "retrieved_refs, service_log_id, repaired_from_explorer_id, "
                "repair_instruction, revised_from_explorer_id, revision_instruction"
            )
            .eq("id", explorer_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise ValueError(f"No explorer_outputs row found for id={explorer_id}")
        row = response.data[0]
        if not isinstance(row, dict):
            raise RuntimeError("Supabase returned an invalid explorer_outputs row.")
        return row

    @staticmethod
    def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
        full_output = row.get("full_output_json")
        if not isinstance(full_output, dict):
            full_output = {}
        flattened = dict(row)
        flattened["explorer_name"] = str(full_output.get("explorer_name") or "")
        flattened["explorer_description"] = str(
            full_output.get("explorer_description") or ""
        )
        flattened["explorer_code_body"] = str(
            full_output.get("explorer_code_body") or ""
        )
        columns = full_output.get("col_definitions")
        flattened["col_definitions"] = columns if isinstance(columns, list) else []
        assumptions = full_output.get("assumptions")
        flattened["assumptions"] = assumptions if isinstance(assumptions, list) else []
        refs = row.get("retrieved_refs")
        flattened["retrieved_refs"] = refs if isinstance(refs, list) else []
        return flattened

    @staticmethod
    def _required_text(value: Any, field_name: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError(f"{field_name} is required.")
        return cleaned

    @staticmethod
    def _make_client() -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url:
            raise RuntimeError("Missing SUPABASE_URL in RAG service environment.")
        if not key:
            raise RuntimeError(
                "Missing SUPABASE_SERVICE_ROLE_KEY in RAG service environment."
            )
        return create_client(url, key)
