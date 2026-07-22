from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client


load_dotenv()


TABLE_NAME = "explorer_result_sets"
SUPPORTED_SCHEMA_VERSION = "1.0"
SUPPORTED_OUTCOMES = {
    "matches_found",
    "no_matches",
}
FULL_RESULT_SELECT = (
    "id, explorer_id, created_at, "
    "schema_version, outcome, "
    "expected_count, matched_count, "
    "has_matches, clipboard_verified, "
    "clipboard_verification, rows, "
    "capture_started_at, "
    "capture_finished_at, diagnostics"
)

RESULT_SUMMARY_SELECT = (
    "id, explorer_id, created_at, "
    "schema_version, outcome, "
    "expected_count, matched_count, "
    "has_matches, clipboard_verified, "
    "capture_started_at, "
    "capture_finished_at"
)

DEFAULT_RESULT_LIST_LIMIT = 20
MAX_RESULT_LIST_LIMIT = 100


class RagExplorerResultStoreService:
    """
    Controlled write service for normalized MetaStock result artifacts.

    This service is intentionally narrow:
    - insert one explorer_result_sets row;
    - require an explorer_outputs foreign key;
    - validate the result contract before writing;
    - return only the stored result ID and timestamps;
    - never expose Supabase credentials or the raw client.
    """

    def __init__(
        self,
        client: Any | None = None,
    ) -> None:
        self.client = (
            client
            if client is not None
            else self._make_supabase_client()
        )

    def save_explorer_results(
        self,
        *,
        explorer_id: str,
        schema_version: str,
        outcome: str,
        expected_count: int,
        matched_count: int,
        has_matches: bool,
        clipboard_verification: (
            dict[str, Any] | None
        ),
        rows: list[dict[str, Any]],
        capture_started_at: str | None = None,
        capture_finished_at: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cleaned_explorer_id = self._required_text(
            explorer_id,
            "explorer_id",
        )
        cleaned_schema_version = self._required_text(
            schema_version,
            "schema_version",
        )
        cleaned_outcome = self._required_text(
            outcome,
            "outcome",
        )

        if (
            cleaned_schema_version
            != SUPPORTED_SCHEMA_VERSION
        ):
            raise ValueError(
                "Unsupported result schema version: "
                f"{cleaned_schema_version!r}."
            )

        if cleaned_outcome not in SUPPORTED_OUTCOMES:
            raise ValueError(
                "Unsupported result outcome: "
                f"{cleaned_outcome!r}."
            )

        expected_count = int(expected_count)
        matched_count = int(matched_count)
        has_matches = bool(has_matches)

        if expected_count < 0 or matched_count < 0:
            raise ValueError(
                "Result counts cannot be negative."
            )

        if not isinstance(rows, list):
            raise ValueError(
                "rows must be a list."
            )

        normalized_rows = [
            self._normalize_row(row)
            for row in rows
        ]

        normalized_verification = (
            self._normalize_verification(
                clipboard_verification
            )
            if clipboard_verification
            is not None
            else None
        )

        if cleaned_outcome == "no_matches":
            if (
                expected_count != 0
                or matched_count != 0
                or has_matches
                or normalized_rows
            ):
                raise ValueError(
                    "A no_matches result must contain "
                    "zero rows and zero counts."
                )

            clipboard_verified = None

        else:
            if (
                expected_count <= 0
                or matched_count != expected_count
                or len(normalized_rows)
                != matched_count
                or not has_matches
            ):
                raise ValueError(
                    "A matches_found result must have "
                    "equal positive expected, matched, "
                    "and row counts."
                )

            if (
                normalized_verification is None
                or normalized_verification.get(
                    "passed"
                )
                is not True
            ):
                raise ValueError(
                    "A matches_found result must include "
                    "passed clipboard verification."
                )

            clipboard_verified = True

        if diagnostics is None:
            diagnostics = {}

        if not isinstance(diagnostics, dict):
            raise ValueError(
                "diagnostics must be a dictionary."
            )

        row = {
            "explorer_id": cleaned_explorer_id,
            "schema_version": (
                cleaned_schema_version
            ),
            "outcome": cleaned_outcome,
            "expected_count": expected_count,
            "matched_count": matched_count,
            "has_matches": has_matches,
            "clipboard_verified": (
                clipboard_verified
            ),
            "clipboard_verification": (
                normalized_verification
            ),
            "rows": normalized_rows,
            "capture_started_at": (
                self._optional_text(
                    capture_started_at
                )
            ),
            "capture_finished_at": (
                self._optional_text(
                    capture_finished_at
                )
            ),
            "diagnostics": diagnostics,
        }

        response = (
            self.client.table(TABLE_NAME)
            .insert(row)
            .execute()
        )

        if not response.data:
            raise RuntimeError(
                "Supabase inserted no "
                "explorer_result_sets row."
            )

        stored = response.data[0]

        return {
            "result_id": str(stored["id"]),
            "explorer_id": str(
                stored.get("explorer_id")
                or cleaned_explorer_id
            ),
            "created_at": self._optional_text(
                stored.get("created_at")
            ),
        }
    
    def get_result(
        self,
        result_id: str,
    ) -> dict[str, Any]:
        """
        Return one complete stored result artifact.
        """
        cleaned_result_id = self._required_text(
            result_id,
            "result_id",
        )

        response = (
            self.client.table(TABLE_NAME)
            .select(FULL_RESULT_SELECT)
            .eq("id", cleaned_result_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise ValueError(
                "No explorer_result_sets row found "
                f"for id={cleaned_result_id}"
            )

        return self._normalize_stored_result(
            response.data[0]
        )


    def get_latest_result(
        self,
        explorer_id: str,
    ) -> dict[str, Any] | None:
        """
        Return the newest complete result for an Explorer.

        None means that the Explorer has no stored results.
        """
        cleaned_explorer_id = self._required_text(
            explorer_id,
            "explorer_id",
        )

        response = (
            self.client.table(TABLE_NAME)
            .select(FULL_RESULT_SELECT)
            .eq(
                "explorer_id",
                cleaned_explorer_id,
            )
            .order(
                "created_at",
                desc=True,
            )
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        return self._normalize_stored_result(
            response.data[0]
        )


    def list_results(
        self,
        explorer_id: str,
        *,
        limit: int = DEFAULT_RESULT_LIST_LIMIT,
    ) -> list[dict[str, Any]]:
        """
        Return newest-first summaries for an Explorer.

        Full rows and diagnostics are excluded. Call get_result()
        when the complete result artifact is needed.
        """
        cleaned_explorer_id = self._required_text(
            explorer_id,
            "explorer_id",
        )
        cleaned_limit = int(limit)

        if cleaned_limit <= 0:
            raise ValueError(
                "limit must be greater than zero."
            )

        if cleaned_limit > MAX_RESULT_LIST_LIMIT:
            raise ValueError(
                "limit cannot exceed "
                f"{MAX_RESULT_LIST_LIMIT}."
            )

        response = (
            self.client.table(TABLE_NAME)
            .select(RESULT_SUMMARY_SELECT)
            .eq(
                "explorer_id",
                cleaned_explorer_id,
            )
            .order(
                "created_at",
                desc=True,
            )
            .limit(cleaned_limit)
            .execute()
        )

        return [
            self._normalize_result_summary(row)
            for row in (response.data or [])
        ]


    def _normalize_stored_result(
        self,
        row: Any,
    ) -> dict[str, Any]:
        """
        Convert one database row into the stable full-result contract.
        """
        if not isinstance(row, dict):
            raise RuntimeError(
                "Stored result row must be a dictionary."
            )

        schema_version = self._required_text(
            row.get("schema_version"),
            "stored schema_version",
        )

        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise RuntimeError(
                "Stored result uses unsupported schema "
                f"version {schema_version!r}."
            )

        outcome = self._required_text(
            row.get("outcome"),
            "stored outcome",
        )

        if outcome not in SUPPORTED_OUTCOMES:
            raise RuntimeError(
                "Stored result uses unsupported outcome "
                f"{outcome!r}."
            )

        raw_rows = row.get("rows") or []

        if not isinstance(raw_rows, list):
            raise RuntimeError(
                "Stored result rows must be a list."
            )

        normalized_rows = [
            self._normalize_row(item)
            for item in raw_rows
        ]

        raw_verification = row.get(
            "clipboard_verification"
        )

        clipboard_verification = (
            self._normalize_verification(
                raw_verification
            )
            if raw_verification is not None
            else None
        )

        diagnostics = row.get("diagnostics") or {}

        if not isinstance(diagnostics, dict):
            raise RuntimeError(
                "Stored result diagnostics must be "
                "a dictionary."
            )

        raw_clipboard_verified = row.get(
            "clipboard_verified"
        )

        clipboard_verified = (
            None
            if raw_clipboard_verified is None
            else bool(raw_clipboard_verified)
        )

        return {
            "result_id": self._required_text(
                row.get("id"),
                "stored result id",
            ),
            "explorer_id": self._required_text(
                row.get("explorer_id"),
                "stored explorer id",
            ),
            "created_at": self._optional_text(
                row.get("created_at")
            ),
            "schema_version": schema_version,
            "outcome": outcome,
            "expected_count": int(
                row.get("expected_count", 0)
            ),
            "matched_count": int(
                row.get("matched_count", 0)
            ),
            "has_matches": bool(
                row.get("has_matches", False)
            ),
            "clipboard_verified": (
                clipboard_verified
            ),
            "clipboard_verification": (
                clipboard_verification
            ),
            "rows": normalized_rows,
            "capture_started_at": (
                self._optional_text(
                    row.get("capture_started_at")
                )
            ),
            "capture_finished_at": (
                self._optional_text(
                    row.get("capture_finished_at")
                )
            ),
            "diagnostics": dict(diagnostics),
        }


    def _normalize_result_summary(
        self,
        row: Any,
    ) -> dict[str, Any]:
        """
        Convert one database row into the bounded list contract.
        """
        if not isinstance(row, dict):
            raise RuntimeError(
                "Stored result summary must be a dictionary."
            )

        schema_version = self._required_text(
            row.get("schema_version"),
            "stored schema_version",
        )

        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise RuntimeError(
                "Stored result summary uses unsupported "
                f"schema version {schema_version!r}."
            )

        outcome = self._required_text(
            row.get("outcome"),
            "stored outcome",
        )

        if outcome not in SUPPORTED_OUTCOMES:
            raise RuntimeError(
                "Stored result summary uses unsupported "
                f"outcome {outcome!r}."
            )

        return {
            "result_id": self._required_text(
                row.get("id"),
                "stored result id",
            ),
            "explorer_id": self._required_text(
                row.get("explorer_id"),
                "stored explorer id",
            ),
            "created_at": self._optional_text(
                row.get("created_at")
            ),
            "schema_version": schema_version,
            "outcome": outcome,
            "expected_count": int(
                row.get("expected_count", 0)
            ),
            "matched_count": int(
                row.get("matched_count", 0)
            ),
            "has_matches": bool(
                row.get("has_matches", False)
            ),
            "clipboard_verified": (
                None
                if row.get("clipboard_verified") is None
                else bool(
                    row.get("clipboard_verified")
                )
            ),
            "capture_started_at": (
                self._optional_text(
                    row.get("capture_started_at")
                )
            ),
            "capture_finished_at": (
                self._optional_text(
                    row.get("capture_finished_at")
                )
            ),
        }

    @staticmethod
    def _normalize_row(
        row: Any,
    ) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise ValueError(
                "Each result row must be a dictionary."
            )

        column_values = row.get(
            "column_values"
        ) or {}

        if not isinstance(
            column_values,
            dict,
        ):
            raise ValueError(
                "row.column_values must be "
                "a dictionary."
            )

        return {
            "row_index": int(
                row.get("row_index", 0)
            ),
            "instrument_name": str(
                row.get("instrument_name")
                or ""
            ),
            "symbol": (
                str(row["symbol"])
                if row.get("symbol")
                is not None
                else None
            ),
            "column_values": {
                str(letter): str(value)
                for letter, value in (
                    column_values.items()
                )
            },
        }

    @staticmethod
    def _normalize_verification(
        value: Any,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(
                "clipboard_verification must be "
                "a dictionary."
            )

        return {
            "passed": bool(
                value.get("passed", False)
            ),
            "expected_count": int(
                value.get("expected_count", 0)
            ),
            "scraped_count": int(
                value.get("scraped_count", 0)
            ),
            "clipboard_count": int(
                value.get("clipboard_count", 0)
            ),
            "missing_from_scrape": [
                str(item)
                for item in (
                    value.get(
                        "missing_from_scrape"
                    )
                    or []
                )
            ],
            "unexpected_in_scrape": [
                str(item)
                for item in (
                    value.get(
                        "unexpected_in_scrape"
                    )
                    or []
                )
            ],
            "clipboard_headers": [
                str(item)
                for item in (
                    value.get(
                        "clipboard_headers"
                    )
                    or []
                )
            ],
        }

    @staticmethod
    def _make_supabase_client() -> Any:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv(
            "SUPABASE_SERVICE_ROLE_KEY"
        )

        if not url:
            raise RuntimeError(
                "Missing SUPABASE_URL in "
                "RAG service environment."
            )

        if not key:
            raise RuntimeError(
                "Missing SUPABASE_SERVICE_ROLE_KEY "
                "in RAG service environment."
            )

        return create_client(url, key)

    @staticmethod
    def _required_text(
        value: Any,
        field_name: str,
    ) -> str:
        cleaned = str(value or "").strip()

        if not cleaned:
            raise ValueError(
                f"{field_name} is required."
            )

        return cleaned

    @staticmethod
    def _optional_text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        cleaned = str(value).strip()
        return cleaned or None
