from __future__ import annotations

from typing import Any

from services.automator_client import (
    AutomatorClipboardVerification,
    AutomatorExplorerResults,
    AutomatorReadResultsRequest,
    AutomatorReadResultsResult,
    AutomatorResultRow,
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
                            "A": "1.0",
                        },
                    )
                ],
            ),
            diagnostics={
                "capture": "verified",
            },
        )


class FakeResultClient:
    def __init__(
        self,
        *,
        fail: bool = False,
    ) -> None:
        self.fail = fail
        self.payload: (
            dict[str, Any] | None
        ) = None

    def save_explorer_result(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.payload = kwargs

        if self.fail:
            raise RuntimeError(
                "Supabase unavailable"
            )

        return {
            "result_id": "result-1",
            "explorer_id": kwargs[
                "explorer_id"
            ],
            "created_at": "created",
        }

    def get_explorer_result(
        self,
        result_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def get_latest_explorer_result(
        self,
        explorer_id: str,
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_explorer_results(
        self,
        explorer_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


def test_result_tool_persists_through_client() -> None:
    result_client = FakeResultClient()

    service = MetaStockResultToolService(
        automator_client=(
            FakeAutomatorClient()
        ),
        result_client=result_client,
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

    assert result_client.payload is not None

    assert (
        result_client.payload[
            "result_payload"
        ]["rows"][0]["symbol"]
        == "TEST.SI"
    )


def test_persistence_failure_keeps_rows() -> None:
    service = MetaStockResultToolService(
        automator_client=(
            FakeAutomatorClient()
        ),
        result_client=FakeResultClient(
            fail=True
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
    assert result.error is not None

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


def test_missing_result_client_blocks_before_read() -> None:
    service = MetaStockResultToolService(
        automator_client=(
            FakeAutomatorClient()
        ),
        result_client=None,
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
    assert result.status is ToolStatus.BLOCKED
    assert result.error is not None

    assert (
        result.error.code
        == "RESULT_PERSISTENCE_NOT_CONFIGURED"
    )