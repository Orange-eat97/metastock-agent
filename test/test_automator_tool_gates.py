from __future__ import annotations

from typing import Any

from services.automator_client import (
    UnavailableAutomatorClient,
)
from tools.explorer_tools import ExplorerToolService
from tools.tool_contracts import (
    RunExplorerInput,
    ToolStatus,
)


class FakeExplorerRepository:
    def __init__(
        self,
        row: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.row = row
        self.error = error

    def get_explorer(
        self,
        explorer_id: str,
    ) -> dict[str, Any]:
        if self.error is not None:
            raise self.error

        if self.row is None:
            raise ValueError(
                "No explorer_outputs row found "
                f"for id={explorer_id}"
            )

        return self.row

    def get_service_log(
        self,
        log_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError


def build_row(
    *,
    validation_passed: bool,
) -> dict[str, Any]:
    return {
        "id": "explorer-1",
        "created_at": (
            "2026-07-10T00:00:00+00:00"
        ),
        "explorer_name": "RSI Test",
        "explorer_description": (
            "Test Explorer"
        ),
        "explorer_code_body": (
            "RSI(14) < 30"
        ),
        "col_definitions": [
            {
                "col_letter": "A",
                "col_code": "RSI(14)",
            },
        ],
        "validation_passed": (
            validation_passed
        ),
        "validation_errors": (
            []
            if validation_passed
            else ["Invalid formula"]
        ),
        "service_log_id": "log-1",
    }


def build_service(
    repository: FakeExplorerRepository,
) -> ExplorerToolService:
    return ExplorerToolService(
        review_workflow=object(),
        explorer_repository=repository,
        automator_client=(
            UnavailableAutomatorClient()
        ),
    )


def test_unknown_explorer_returns_failed() -> None:
    service = build_service(
        FakeExplorerRepository(
            error=ValueError(
                "No explorer_outputs row found "
                "for id=missing"
            )
        )
    )

    result = (
        service.create_explorer_in_metastock(
            RunExplorerInput(
                explorer_id="missing"
            )
        )
    )

    assert result.ok is False
    assert result.status is ToolStatus.FAILED


def test_invalid_explorer_is_blocked_before_automator_gate() -> None:
    service = build_service(
        FakeExplorerRepository(
            row=build_row(
                validation_passed=False
            )
        )
    )

    result = (
        service.create_explorer_in_metastock(
            RunExplorerInput(
                explorer_id="explorer-1"
            )
        )
    )

    assert result.ok is False
    assert result.status is ToolStatus.BLOCKED
    assert result.error is not None
    assert (
        result.error.code
        == "EXPLORER_VALIDATION_FAILED"
    )


def test_valid_explorer_is_blocked_when_automator_is_unavailable() -> None:
    service = build_service(
        FakeExplorerRepository(
            row=build_row(
                validation_passed=True
            )
        )
    )

    result = (
        service.create_explorer_in_metastock(
            RunExplorerInput(
                explorer_id="explorer-1",
                instruments="all",
            )
        )
    )

    assert result.ok is False
    assert result.status is ToolStatus.BLOCKED
    assert result.error is not None
    assert (
        result.error.code
        == "AUTOMATOR_NOT_CONFIGURED"
    )
