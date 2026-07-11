from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from services.rag_client import (
    LocalRagClient,
)


@dataclass(frozen=True)
class StoredExplorerResult:
    result_id: str
    explorer_id: str
    created_at: str | None


class ExplorerResultRepositoryProtocol(
    Protocol
):
    @property
    def configured(self) -> bool:
        ...

    def save_result(
        self,
        *,
        explorer_id: str,
        result_payload: dict[str, Any],
        capture_started_at: str | None,
        capture_finished_at: str | None,
        diagnostics: dict[str, Any],
    ) -> StoredExplorerResult:
        ...


class UnavailableExplorerResultRepository:
    @property
    def configured(self) -> bool:
        return False

    def save_result(
        self,
        *,
        explorer_id: str,
        result_payload: dict[str, Any],
        capture_started_at: str | None,
        capture_finished_at: str | None,
        diagnostics: dict[str, Any],
    ) -> StoredExplorerResult:
        raise RuntimeError(
            "Explorer result persistence is "
            "not configured."
        )


class ExplorerResultRepository:
    """
    Agent-side repository for durable Explorer result artifacts.

    The repository does not create a Supabase client. It delegates
    through LocalRagClient to the RAG repository's narrow
    RagExplorerResultStoreService.
    """

    def __init__(
        self,
        rag_client: LocalRagClient,
    ) -> None:
        self.rag_client = rag_client

    @property
    def configured(self) -> bool:
        return True

    def save_result(
        self,
        *,
        explorer_id: str,
        result_payload: dict[str, Any],
        capture_started_at: str | None,
        capture_finished_at: str | None,
        diagnostics: dict[str, Any],
    ) -> StoredExplorerResult:
        cleaned_explorer_id = (
            self._required_text(
                explorer_id,
                "explorer_id",
            )
        )

        if not isinstance(
            result_payload,
            dict,
        ):
            raise ValueError(
                "result_payload must be "
                "a dictionary."
            )

        rows = result_payload.get(
            "rows"
        ) or []

        if not isinstance(rows, list):
            raise ValueError(
                "result_payload.rows must "
                "be a list."
            )

        response = (
            self.rag_client
            .save_explorer_results(
                explorer_id=(
                    cleaned_explorer_id
                ),
                schema_version=str(
                    result_payload.get(
                        "schema_version"
                    )
                    or ""
                ),
                outcome=str(
                    result_payload.get(
                        "outcome"
                    )
                    or ""
                ),
                expected_count=int(
                    result_payload.get(
                        "expected_count",
                        0,
                    )
                ),
                matched_count=int(
                    result_payload.get(
                        "matched_count",
                        0,
                    )
                ),
                has_matches=bool(
                    result_payload.get(
                        "has_matches",
                        False,
                    )
                ),
                clipboard_verification=(
                    result_payload.get(
                        "clipboard_verification"
                    )
                ),
                rows=rows,
                capture_started_at=(
                    capture_started_at
                ),
                capture_finished_at=(
                    capture_finished_at
                ),
                diagnostics=diagnostics,
            )
        )

        return StoredExplorerResult(
            result_id=self._required_text(
                response.get("result_id"),
                "result_id",
            ),
            explorer_id=self._required_text(
                response.get("explorer_id"),
                "stored explorer_id",
            ),
            created_at=self._optional_text(
                response.get("created_at")
            ),
        )

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
