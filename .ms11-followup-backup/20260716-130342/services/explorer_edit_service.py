from __future__ import annotations

from typing import Any, Protocol


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
    or an AI repair path. It only validates the UI patch shape and delegates a
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
            raise ValueError("At least one Explorer column is required.")

        normalized_columns: list[dict[str, str]] = []
        for index, column in enumerate(columns):
            if not isinstance(column, dict):
                raise ValueError(f"columns[{index}] must be an object.")
            letter = self._clean_required(
                column.get("col_letter", ""),
                f"columns[{index}].col_letter",
            ).upper()
            formula = self._clean_required(
                column.get("col_code", ""),
                f"columns[{index}].col_code",
            )
            normalized_columns.append(
                {
                    "col_letter": letter,
                    "col_code": formula,
                }
            )

        normalized_assumptions = [
            str(item).strip()
            for item in assumptions
            if str(item).strip()
        ]

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

    @staticmethod
    def _clean_required(value: Any, field_name: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError(f"{field_name} is required.")
        return cleaned
