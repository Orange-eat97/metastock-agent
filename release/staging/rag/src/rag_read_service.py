from __future__ import annotations

import os
from typing import Any, Iterator

from dotenv import load_dotenv
from supabase import Client, create_client


load_dotenv()

EXPLORER_NAME_LOOKUP_PAGE_SIZE = 1000


class ExplorerNameResolutionError(LookupError):
    """Base error for exact Explorer-name resolution failures."""


class ExplorerNotFoundError(ExplorerNameResolutionError):
    """Raised when no stored Explorer has the requested exact name."""


class ExplorerNameAmbiguousError(ExplorerNameResolutionError):
    """Raised when multiple stored Explorers have the requested exact name."""


class RagExplorerReadService:
    """
    Controlled read-only service for stored RAG artifacts.

    This service is intentionally narrow:
    - read one explorer_outputs row by id;
    - read one rag_service_logs row by log_id;
    - no arbitrary table access;
    - no write operations;
    - no Supabase URL/key returned to callers.
    """

    def __init__(
        self,
        client: Client | None = None,
    ) -> None:
        self.client = (
            client
            if client is not None
            else self._make_supabase_client()
        )

    def get_explorer(self, explorer: str) -> dict[str, Any]:
        explorer_id = self._clean_required_text(explorer, "explorer")

        response = (
            self.client.table("explorer_outputs")
            .select(
                "id, created_at, updated_at, manual_edit_version, backend, "
                "model, user_query, full_output_json, validation_passed, "
                "validation_errors, "
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

        return self._flatten_explorer_row(response.data[0])

    def get_explorers_by_ids(
        self,
        explorer_ids: list[str],
    ) -> list[dict[str, Any]]:
        cleaned_ids = list(
            dict.fromkeys(
                self._clean_required_text(
                    explorer_id,
                    "explorer_id",
                )
                for explorer_id in explorer_ids
            )
        )
        if not cleaned_ids:
            return []

        response = (
            self.client.table("explorer_outputs")
            .select(
                "id, created_at, updated_at, manual_edit_version, backend, "
                "model, user_query, full_output_json, validation_passed, "
                "validation_errors, retrieved_refs, service_log_id, "
                "repaired_from_explorer_id, repair_instruction, "
                "revised_from_explorer_id, revision_instruction"
            )
            .in_("id", cleaned_ids)
            .execute()
        )
        rows = response.data or []
        if not isinstance(rows, list):
            raise RuntimeError(
                "Supabase returned an invalid explorer_outputs response."
            )
        flattened_by_id = {
            str(row.get("id")): self._flatten_explorer_row(row)
            for row in rows
            if isinstance(row, dict) and row.get("id")
        }
        return [
            flattened_by_id[explorer_id]
            for explorer_id in cleaned_ids
            if explorer_id in flattened_by_id
        ]

    def get_service_log(self, log_id: str) -> dict[str, Any]:
        cleaned_log_id = self._clean_required_text(log_id, "log_id")

        response = (
            self.client.table("rag_service_logs")
            .select(
                "log_id, event_type, service_name, user_query, "
                "explorer_output_id, explorer_output_created_at, "
                "stdout_text, stderr_text, metadata, created_at"
            )
            .eq("log_id", cleaned_log_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise ValueError(f"No rag_service_logs row found for log_id={cleaned_log_id}")

        return response.data[0]

    def _make_supabase_client(self) -> Client:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url:
            raise RuntimeError("Missing SUPABASE_URL in RAG service environment.")

        if not key:
            raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY in RAG service environment.")

        return create_client(url, key)

    def _flatten_explorer_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """
        explorer_outputs stores the generated Explorer JSON in full_output_json.

        The agent/tool layer expects convenient top-level fields, so this returns
        both:
        - original row fields;
        - flattened explorer_name / explorer_description / explorer_code_body /
          col_definitions.
        """
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

        col_definitions = full_output.get("col_definitions")
        if isinstance(col_definitions, list):
            flattened["col_definitions"] = col_definitions
        else:
            flattened["col_definitions"] = []

        assumptions = full_output.get("assumptions")
        if isinstance(assumptions, list):
            flattened["assumptions"] = assumptions
        else:
            flattened["assumptions"] = []

        retrieved_refs = row.get("retrieved_refs")
        if isinstance(retrieved_refs, list):
            flattened["retrieved_refs"] = retrieved_refs
        else:
            flattened["retrieved_refs"] = []

        return flattened

    def _clean_required_text(self, value: str, field_name: str) -> str:
        cleaned = str(value or "").strip()

        if not cleaned:
            raise ValueError(f"{field_name} is required.")

        return cleaned
    
    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        """
        Resolve an exact Explorer name to one explorer_outputs UUID.

        Matching rules:
        - leading and trailing whitespace are ignored;
        - matching is case-insensitive;
        - the complete Explorer name must match;
        - prefix, substring, fuzzy, and semantic matches are rejected.

        Raises:
            ExplorerNotFoundError:
                No exact match exists.

            ExplorerNameAmbiguousError:
                More than one exact match exists.
        """
        cleaned_name = self._clean_required_text(
            explorer_name,
            "explorer_name",
        )
        normalized_name = cleaned_name.casefold()

        matched_ids: list[str] = []

        for row in self._iter_explorer_identity_rows():
            full_output = row.get("full_output_json")

            if not isinstance(full_output, dict):
                continue

            stored_name = str(
                full_output.get("explorer_name") or ""
            ).strip()

            if stored_name.casefold() != normalized_name:
                continue

            explorer_id = str(row.get("id") or "").strip()

            if not explorer_id:
                raise RuntimeError(
                    "An explorer_outputs row matched the requested "
                    "name but did not contain an id."
                )

            matched_ids.append(explorer_id)

            if len(matched_ids) > 1:
                raise ExplorerNameAmbiguousError(
                    "More than one explorer_outputs row has the "
                    f"exact Explorer name {cleaned_name!r}."
                )

        if not matched_ids:
            raise ExplorerNotFoundError(
                "No explorer_outputs row has the exact Explorer "
                f"name {cleaned_name!r}."
            )

        return matched_ids[0]
    
    def _iter_explorer_identity_rows(
        self,
    ) -> Iterator[dict[str, Any]]:
        """
        Read only the fields required for exact-name resolution.

        Explorer names currently live inside full_output_json, so comparison
        is performed in Python. Explicit pagination avoids silently depending
        on the PostgREST result limit.
        """
        start = 0

        while True:
            end = (
                start
                + EXPLORER_NAME_LOOKUP_PAGE_SIZE
                - 1
            )

            response = (
                self.client.table("explorer_outputs")
                .select("id, full_output_json")
                .order("id")
                .range(start, end)
                .execute()
            )

            batch = response.data or []

            if not isinstance(batch, list):
                raise RuntimeError(
                    "Supabase returned an invalid "
                    "explorer_outputs response."
                )

            for row in batch:
                if isinstance(row, dict):
                    yield row

            if (
                len(batch)
                < EXPLORER_NAME_LOOKUP_PAGE_SIZE
            ):
                return

            start += EXPLORER_NAME_LOOKUP_PAGE_SIZE