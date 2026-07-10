from __future__ import annotations

from typing import Any

from services.automator_client import AutomatorRunRequest, AutomatorRunResult
from tools.explorer_tools import ExplorerToolService
from tools.tool_contracts import RunExplorerInput, ToolStatus


class FakeExplorerRepository:
    def get_explorer(self, explorer_id: str) -> dict[str, Any]:
        return {
            "id": explorer_id,
            "created_at": "2026-07-10T00:00:00+00:00",
            "explorer_name": "RSI Test",
            "explorer_description": "Test Explorer",
            "explorer_code_body": "RSI(14) < 30",
            "col_definitions": [
                {"col_letter": "A", "col_code": "RSI(14)"},
            ],
            "validation_passed": True,
            "validation_errors": [],
            "service_log_id": "log-1",
        }


class FakeConfiguredAutomatorClient:
    def __init__(self, succeeded: bool) -> None:
        self.succeeded = succeeded
        self.requests: list[AutomatorRunRequest] = []

    @property
    def configured(self) -> bool:
        return True

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        self.requests.append(request)
        return AutomatorRunResult(
            succeeded=self.succeeded,
            message="Explorer executed." if self.succeeded else "Execution failed.",
            started_at="start",
            finished_at="finish",
            diagnostics={"fake": True},
        )


def test_valid_explorer_dispatches_to_configured_client() -> None:
    client = FakeConfiguredAutomatorClient(succeeded=True)
    service = ExplorerToolService(
        review_workflow=object(),
        explorer_repository=FakeExplorerRepository(),
        automator_client=client,
    )

    result = service.run_explorer_in_metastock(
        RunExplorerInput(
            explorer_id="explorer-1",
            instruments="SGX, NASDAQ",
            max_execution_wait_sec=180,
        )
    )

    assert result.ok is True
    assert result.status is ToolStatus.SUCCESS
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.instruments == ["SGX", "NASDAQ"]
    assert request.select_all_instruments is False
    assert request.max_execution_wait_sec == 180


def test_configured_client_failure_returns_failed_result() -> None:
    client = FakeConfiguredAutomatorClient(succeeded=False)
    service = ExplorerToolService(
        review_workflow=object(),
        explorer_repository=FakeExplorerRepository(),
        automator_client=client,
    )

    result = service.run_explorer_in_metastock(
        RunExplorerInput(explorer_id="explorer-1")
    )

    assert result.ok is False
    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code == "AUTOMATOR_EXECUTION_FAILED"
