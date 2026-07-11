from __future__ import annotations

from services.automator_client import (
    AutomatorClipboardVerification,
    AutomatorExplorerResults,
    AutomatorReadResultsRequest,
    AutomatorReadResultsResult,
    AutomatorResultRow,
)
from services.explorer_result_repository import (
    StoredExplorerResult,
)
from tools.result_tools import (
    MetaStockResultToolService,
)
from tools.tool_contracts import (
    ReadMetaStockResultsInput,
    ToolStatus,
)


class FakeAutomatorClient:
    @property
    def configured(self) -> bool:
        return True

    def read_results(
        self,
        request: AutomatorReadResultsRequest,
    ) -> AutomatorReadResultsResult:
        return AutomatorReadResultsResult(
            succeeded=True,
            message="Results read.",
            started_at="start",
            finished_at="finish",
            explorer_id=request.explorer_id,
            results=AutomatorExplorerResults(
                schema_version="1.0",
                outcome="matches_found",
                expected_count=1,
                matched_count=1,
                has_matches=True,
                clipboard_verification=(
                    AutomatorClipboardVerification(
                        passed=True,
                        expected_count=1,
                        scraped_count=1,
                        clipboard_count=1,
                    )
                ),
                rows=[
                    AutomatorResultRow(
                        row_index=0,
                        instrument_name=(
                            "Test Instrument"
                        ),
                        symbol="TEST.SI",
                        column_values={
                            "A": "1.0"
                        },
                    )
                ],
            ),
            diagnostics={
                "capture": "verified"
            },
        )


class FakeRepository:
    def __init__(self, fail=False):
        self.fail = fail
        self.payload = None

    @property
    def configured(self) -> bool:
        return True

    def save_result(self, **kwargs):
        self.payload = kwargs

        if self.fail:
            raise RuntimeError(
                "Supabase unavailable"
            )

        return StoredExplorerResult(
            result_id="result-1",
            explorer_id=(
                kwargs["explorer_id"]
            ),
            created_at="created",
        )


def test_result_tool_persists_before_success() -> None:
    repository = FakeRepository()
    service = MetaStockResultToolService(
        automator_client=(
            FakeAutomatorClient()
        ),
        result_repository=repository,
    )

    result = (
        service
        .read_metastock_explorer_results(
            ReadMetaStockResultsInput(
                explorer_id="explorer-1"
            )
        )
    )

    assert result.ok is True
    assert result.status is ToolStatus.SUCCESS
    assert result.data["persisted"] is True
    assert (
        result.data["result_id"]
        == "result-1"
    )
    assert (
        repository.payload[
            "result_payload"
        ]["rows"][0]["symbol"]
        == "TEST.SI"
    )


def test_persistence_failure_keeps_rows_in_data() -> None:
    service = MetaStockResultToolService(
        automator_client=(
            FakeAutomatorClient()
        ),
        result_repository=(
            FakeRepository(fail=True)
        ),
    )

    result = (
        service
        .read_metastock_explorer_results(
            ReadMetaStockResultsInput(
                explorer_id="explorer-1"
            )
        )
    )

    assert result.ok is False
    assert result.status is ToolStatus.FAILED
    assert (
        result.error.code
        == "RESULT_PERSISTENCE_FAILED"
    )
    assert result.data["persisted"] is False
    assert (
        result.data["results"]["rows"][0][
            "symbol"
        ]
        == "TEST.SI"
    )
