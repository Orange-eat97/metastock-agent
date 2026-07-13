from __future__ import annotations

from pathlib import Path

from services.automator_client import (
    AutomatorExplorerColumn,
    AutomatorReadResultsRequest,
    AutomatorRunRequest,
    LocalAutomatorClient,
)


CONSOLIDATED_SERVICE_SOURCE = """
from dataclasses import dataclass, field

@dataclass(frozen=True)
class AutomatorExecutionColumn:
    col_letter: str
    col_code: str

@dataclass(frozen=True)
class AutomatorExecutionRequest:
    explorer_id: str
    name: str
    description: str
    filter_code: str
    columns: list = field(default_factory=list)
    instruments: list | None = None
    select_all_instruments: bool = True
    max_execution_wait_sec: int = 300

@dataclass(frozen=True)
class AutomatorResultReadRequest:
    explorer_id: str | None = None
    close_after_read: bool = True

@dataclass(frozen=True)
class RunResult:
    succeeded: bool
    message: str
    started_at: str
    finished_at: str
    result_available: bool
    diagnostics: dict

class Results:
    def to_dict(self):
        return {
            "schema_version": "1.0",
            "outcome": "matches_found",
            "expected_count": 1,
            "matched_count": 1,
            "has_matches": True,
            "clipboard_verification": {
                "passed": True,
                "expected_count": 1,
                "scraped_count": 1,
                "clipboard_count": 1,
                "missing_from_scrape": [],
                "unexpected_in_scrape": [],
                "clipboard_headers": [],
            },
            "rows": [
                {
                    "row_index": 0,
                    "instrument_name": "Test Instrument",
                    "symbol": "TEST.SI",
                    "column_values": {"A": "1.0"},
                }
            ],
        }

@dataclass(frozen=True)
class ReadResult:
    succeeded: bool
    message: str
    started_at: str
    finished_at: str
    explorer_id: str | None
    results: object
    diagnostics: dict

class MetaStockAutomatorService:
    def _result(
        self,
        boundary,
        request,
        *,
        result_available,
    ):
        return RunResult(
            succeeded=True,
            message=boundary,
            started_at=f"{boundary}-start",
            finished_at=f"{boundary}-finish",
            result_available=result_available,
            diagnostics={
                "boundary": boundary,
                "explorer_id": request.explorer_id,
            },
        )

    def create_explorer(self, request):
        return self._result(
            "create_explorer",
            request,
            result_available=False,
        )

    def select_explorer(self, request):
        return self._result(
            "select_explorer",
            request,
            result_available=False,
        )

    def run_selected_explorer(self, request):
        return self._result(
            "run_selected_explorer",
            request,
            result_available=True,
        )

    def run_explorer(self, request):
        raise AssertionError(
            "Composite run_explorer must not be called."
        )

    def read_results(self, request):
        return ReadResult(
            succeeded=True,
            message="read",
            started_at="read-start",
            finished_at="read-finish",
            explorer_id=request.explorer_id,
            results=Results(),
            diagnostics={
                "close_after_read": (
                    request.close_after_read
                ),
            },
        )
"""


def build_request() -> AutomatorRunRequest:
    return AutomatorRunRequest(
        explorer_id="explorer-1",
        name="RSI Test",
        description="Test",
        filter_code="RSI(14) < 30",
        columns=[
            AutomatorExplorerColumn(
                col_letter="A",
                col_code="RSI(14)",
            )
        ],
    )


def test_client_loads_one_service_module(
    tmp_path: Path,
) -> None:
    (
        tmp_path / "automator_service.py"
    ).write_text(
        CONSOLIDATED_SERVICE_SOURCE,
        encoding="utf-8",
    )

    client = LocalAutomatorClient(
        str(tmp_path)
    )
    request = build_request()

    create_result = client.create_explorer(
        request
    )
    assert create_result.succeeded is True
    assert (
        create_result.result_available
        is False
    )
    assert (
        create_result.diagnostics[
            "boundary"
        ]
        == "create_explorer"
    )

    select_result = client.select_explorer(
        request
    )
    assert select_result.succeeded is True
    assert (
        select_result.result_available
        is False
    )
    assert (
        select_result.diagnostics[
            "boundary"
        ]
        == "select_explorer"
    )

    run_result = (
        client.run_selected_explorer(
            request
        )
    )
    assert run_result.succeeded is True
    assert (
        run_result.result_available
        is True
    )
    assert (
        run_result.diagnostics[
            "boundary"
        ]
        == "run_selected_explorer"
    )

    composite_result = (
        client.run_explorer(request)
    )
    assert (
        composite_result.succeeded
        is False
    )
    assert (
        composite_result.diagnostics[
            "boundary"
        ]
        == "run_explorer"
    )

    read_result = client.read_results(
        AutomatorReadResultsRequest(
            explorer_id="explorer-1",
            close_after_read=True,
        )
    )

    assert read_result.succeeded is True
    assert read_result.results is not None
    assert (
        read_result.results.matched_count
        == 1
    )
    assert (
        read_result.results.rows[0].symbol
        == "TEST.SI"
    )
