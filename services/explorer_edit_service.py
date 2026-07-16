from __future__ import annotations

from typing import Any, Protocol


class ExplorerEditValidationError(ValueError):
    """Raised when deterministic MetaStock validation rejects manual edits."""

    def __init__(self, errors: list[str]) -> None:
        cleaned = [str(error).strip() for error in errors if str(error).strip()]
        self.errors = cleaned or ["The Explorer failed deterministic validation."]
        super().__init__("\n".join(self.errors))


class ExplorerRepositoryProtocol(Protocol):
    def get_explorer(self, explorer_id: str) -> dict[str, Any]:
        ...

    def get_explorers_by_ids(
        self,
        explorer_ids: list[str],
    ) -> list[dict[str, Any]]:
        ...

    def update_explorer_full_json(
        self,
        *,
        explorer_id: str,
        expected_version: int,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class ExplorerEditService:
    """
    Deterministic application service for manual Explorer-card edits.

    This service never calls the conversation model, LangGraph, RAG retrieval,
    or an AI repair path. It validates the UI patch shape and delegates a
    controlled update of explorer_outputs.full_output_json through the RAG
    repository boundary.
    """

    def __init__(
        self,
        explorer_repository: ExplorerRepositoryProtocol,
    ) -> None:
        self._explorers = explorer_repository

    def get_explorer(self, explorer_id: str) -> dict[str, Any]:
        return self._explorers.get_explorer(explorer_id)

    def get_explorers(
        self,
        explorer_ids: list[str],
    ) -> list[dict[str, Any]]:
        cleaned_ids = [
            self._clean_required(value, "explorer_id")
            for value in explorer_ids
        ]
        return self._explorers.get_explorers_by_ids(cleaned_ids)

    def save_edits(
        self,
        *,
        explorer_id: str,
        expected_version: int,
        name: str,
        description: str,
        columns: list[dict[str, str]],
        filter_formula: str,
        assumptions: list[str],
    ) -> dict[str, Any]:
        cleaned_id = self._clean_required(explorer_id, "explorer_id")
        cleaned_name = self._clean_required(name, "name")
        cleaned_filter = self._clean_required(
            filter_formula,
            "filter_formula",
        )
        if expected_version < 0:
            raise ValueError("expected_version cannot be negative.")
        if not isinstance(columns, list) or not columns:
            raise ExplorerEditValidationError(
                ["At least one Explorer column is required."]
            )
        if len(columns) > 12:
            raise ExplorerEditValidationError(
                ["MetaStock Explorer supports at most 12 columns (A through L)."]
            )

        normalized_columns: list[dict[str, str]] = []
        for index, column in enumerate(columns):
            if not isinstance(column, dict):
                raise ExplorerEditValidationError(
                    [f"col_definitions[{index}] must be an object."]
                )
            expected_letter = chr(ord("A") + index)
            supplied_letter = self._clean_required(
                column.get("col_letter", ""),
                f"columns[{index}].col_letter",
            ).upper()
            if supplied_letter != expected_letter:
                raise ExplorerEditValidationError(
                    [
                        f"col_definitions[{index}].col_letter must be "
                        f"{expected_letter}, got {supplied_letter!r}."
                    ]
                )
            formula = str(column.get("col_code", "") or "").strip()
            if not formula:
                raise ExplorerEditValidationError(
                    [f"col_definitions[{index}].col_code is required."]
                )
            normalized_columns.append(
                {
                    "col_letter": expected_letter,
                    "col_code": formula,
                }
            )

        normalized_assumptions = [
            str(item).strip()
            for item in assumptions
            if str(item).strip()
        ]

        try:
            return self._explorers.update_explorer_full_json(
                explorer_id=cleaned_id,
                expected_version=expected_version,
                patch={
                    "explorer_name": cleaned_name,
                    "explorer_description": str(description or "").strip(),
                    "explorer_code_body": cleaned_filter,
                    "col_definitions": normalized_columns,
                    "assumptions": normalized_assumptions,
                },
            )
        except Exception as exc:
            validation_errors = getattr(exc, "errors", None)
            if isinstance(validation_errors, list) and validation_errors:
                raise ExplorerEditValidationError(
                    [str(error) for error in validation_errors]
                ) from exc
            raise

    @staticmethod
    def _clean_required(value: Any, field_name: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError(f"{field_name} is required.")
        return cleaned
