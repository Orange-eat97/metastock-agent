from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.query_identity import build_query_identity
from src.rag_service import ValidationResult, _RagServiceBase
from src.supabase_store import update_explorer_service_log_id
from src.validator import validate_explorer_output


UPLOAD_BACKEND = "user-upload"
UPLOAD_MODEL = "manual"
EXPLORER_TABLE = "explorer_outputs"
NAME_SCAN_PAGE_SIZE = 1000


class ExplorerUploadValidationError(ValueError):
    """Raised when a transient user-supplied Explorer fails validation."""

    def __init__(self, errors: list[str]) -> None:
        cleaned = [
            str(error).strip()
            for error in errors
            if str(error).strip()
        ]
        self.errors = cleaned or [
            "The uploaded Explorer failed deterministic validation."
        ]
        super().__init__("\n".join(self.errors))


class ExplorerDuplicateNameError(ValueError):
    """Raised when an uploaded Explorer name already exists."""

    def __init__(self, explorer_name: str) -> None:
        self.explorer_name = str(explorer_name).strip()
        super().__init__(
            "An Explorer with this name already exists "
            f"(case-insensitive): {self.explorer_name}"
        )


class ExplorerUploadResponse(BaseModel):
    explorer: str
    explorer_created_at: str | None = None
    service_log: str | None = None
    service_log_created_at: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    retrieved_refs: list[dict[str, Any]] = Field(default_factory=list)
    validation: ValidationResult
    source: str = "upload"


class RagExplorerUploadService(_RagServiceBase):
    """
    Validate and persist one user-supplied Explorer.

    Invalid submissions are never inserted. The caller may keep the submitted
    object transiently and resubmit it after the user edits the fields.
    """

    def upload_explorer(
        self,
        explorer_output: dict[str, Any],
        *,
        source_text: str | None = None,
    ) -> ExplorerUploadResponse:
        normalized = self._normalize_output(explorer_output)
        validation_messages = validate_explorer_output(normalized)
        hard_errors, warnings = self._split_validation_messages(
            validation_messages
        )

        if hard_errors:
            raise ExplorerUploadValidationError(hard_errors)

        explorer_name = str(
            normalized.get("explorer_name") or ""
        ).strip()
        self._ensure_unique_name(explorer_name)

        assumptions = [
            str(item).strip()
            for item in normalized.get("assumptions") or []
            if str(item).strip()
        ]
        normalized["assumptions"] = assumptions
        normalized["source"] = "user-upload"

        user_query = f"Uploaded Explorer: {explorer_name}"
        identity = build_query_identity(
            user_query,
            include_embedding=False,
        )

        row = {
            "backend": UPLOAD_BACKEND,
            "model": UPLOAD_MODEL,
            "user_query": user_query,
            "user_query_normalized": identity.normalized,
            "user_query_hash": identity.query_hash,
            "user_query_embedding": identity.embedding,
            "user_query_embedding_model": identity.embedding_model,
            "explorer_name": explorer_name,
            "explorer_description": str(
                normalized.get("explorer_description") or ""
            ).strip(),
            "explorer_code_body": str(
                normalized.get("explorer_code_body") or ""
            ).strip(),
            "col_definitions": normalized.get("col_definitions") or [],
            "full_output_json": normalized,
            "validation_passed": True,
            "validation_errors": [
                f"Warning: {warning}"
                for warning in warnings
            ],
            "retrieved_refs": [],
            "repaired_from_explorer_id": None,
            "repair_instruction": None,
            "revised_from_explorer_id": None,
            "revision_instruction": None,
            "status": "uploaded",
        }

        response = (
            self._make_supabase_client()
            .table(EXPLORER_TABLE)
            .insert(row)
            .execute()
        )
        if not response.data:
            raise RuntimeError(
                "Supabase inserted no explorer_outputs row."
            )

        inserted = response.data[0]
        explorer_id = str(inserted.get("id") or "").strip()
        if not explorer_id:
            raise RuntimeError(
                "Supabase did not return the uploaded Explorer ID."
            )

        created_at = self._as_optional_str(
            inserted.get("created_at")
        )
        log_row = self._save_rag_service_log(
            event_type="rag_service.explorer_upload",
            user_query=user_query,
            explorer_output_id=explorer_id,
            explorer_output_created_at=created_at,
            metadata={
                "source": "user-upload",
                "validation_passed": True,
                "validation_warning_count": len(warnings),
                "source_text_supplied": bool(
                    str(source_text or "").strip()
                ),
            },
        )

        service_log_id = str(
            log_row.get("log_id") or ""
        ).strip()
        if service_log_id:
            update_explorer_service_log_id(
                explorer_id=explorer_id,
                service_log_id=service_log_id,
            )

        return ExplorerUploadResponse(
            explorer=explorer_id,
            explorer_created_at=created_at,
            service_log=service_log_id or None,
            service_log_created_at=self._as_optional_str(
                log_row.get("created_at")
            ),
            assumptions=assumptions,
            validation=ValidationResult(
                passed=True,
                errors=[],
                warnings=warnings,
            ),
        )

    def _normalize_output(
        self,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ExplorerUploadValidationError(
                ["Explorer upload must be a JSON object."]
            )

        name = str(
            value.get("explorer_name")
            or value.get("name")
            or ""
        ).strip()
        description = str(
            value.get("explorer_description")
            or value.get("description")
            or ""
        ).strip()
        filter_code = str(
            value.get("explorer_code_body")
            or value.get("filter_code")
            or value.get("filter_formula")
            or ""
        ).strip()

        raw_columns = (
            value.get("col_definitions")
            if isinstance(value.get("col_definitions"), list)
            else value.get("columns")
        )
        if not isinstance(raw_columns, list):
            raw_columns = []

        columns: list[dict[str, str]] = []
        for item in raw_columns:
            if not isinstance(item, dict):
                columns.append(
                    {
                        "col_letter": "",
                        "col_code": "",
                    }
                )
                continue

            columns.append(
                {
                    "col_letter": str(
                        item.get("col_letter")
                        or item.get("label")
                        or ""
                    ).strip().upper(),
                    "col_code": str(
                        item.get("col_code")
                        or item.get("formula")
                        or ""
                    ).strip(),
                }
            )

        assumptions = value.get("assumptions")
        if not isinstance(assumptions, list):
            assumptions = []

        structural_errors: list[str] = []
        if not columns:
            structural_errors.append(
                "At least one Explorer column is required."
            )
        if len(columns) > 12:
            structural_errors.append(
                "MetaStock Explorer supports at most 12 "
                "columns (A through L)."
            )

        if structural_errors:
            raise ExplorerUploadValidationError(
                structural_errors
            )

        return {
            "explorer_name": name,
            "explorer_description": description,
            "explorer_code_body": filter_code,
            "col_definitions": columns,
            "assumptions": [
                str(item).strip()
                for item in assumptions
                if str(item).strip()
            ],
        }

    def _ensure_unique_name(
        self,
        explorer_name: str,
    ) -> None:
        normalized_name = explorer_name.casefold()
        start = 0

        while True:
            response = (
                self._make_supabase_client()
                .table(EXPLORER_TABLE)
                .select("id, full_output_json")
                .range(
                    start,
                    start + NAME_SCAN_PAGE_SIZE - 1,
                )
                .execute()
            )
            rows = response.data or []
            if not isinstance(rows, list):
                raise RuntimeError(
                    "Supabase returned an invalid Explorer-name scan."
                )

            for row in rows:
                if not isinstance(row, dict):
                    continue
                output = row.get("full_output_json")
                if not isinstance(output, dict):
                    continue
                stored_name = str(
                    output.get("explorer_name") or ""
                ).strip()
                if (
                    stored_name
                    and stored_name.casefold()
                    == normalized_name
                ):
                    raise ExplorerDuplicateNameError(
                        explorer_name
                    )

            if len(rows) < NAME_SCAN_PAGE_SIZE:
                return
            start += NAME_SCAN_PAGE_SIZE

    @staticmethod
    def _split_validation_messages(
        messages: list[str],
    ) -> tuple[list[str], list[str]]:
        hard_errors: list[str] = []
        warnings: list[str] = []

        for raw in messages:
            message = str(raw).strip()
            if not message:
                continue
            if message.startswith("Warning:"):
                warnings.append(
                    message[len("Warning:"):].strip()
                )
            else:
                hard_errors.append(message)

        return hard_errors, warnings
