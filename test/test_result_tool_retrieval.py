from __future__ import annotations

from typing import Any

from tools.result_tools import (
    MetaStockResultToolService,
)
from tools.tool_contracts import (
    GetExplorerResultInput,
    GetLatestExplorerResultInput,
    ListExplorerResultsInput,
    ToolStatus,
)


def full_result(
    result_id: str = "result-1",
) -> dict[str, Any]:
    return {
        "result_id": result_id,
        "explorer_id": "explorer-1",
        "created_at": "created",
        "schema_version": "1.0",
        "outcome": "matches_found",
        "expected_count": 1,
        "matched_count": 1,
        "has_matches": True,
        "clipboard_verified": True,
        "clipboard_verification": {
            "passed": True,
            "expected_count": 1,
            "scraped_count": 1,
            "clipboard_count": 1,
            "missing_from_scrape": [],
            "unexpected_in_scrape": [],
            "clipboard_headers": [
                "Instrument",
                "A",
            ],
        },
        "rows": [
            {
                "row_index": 0,
                "instrument_name": (
                    "Test Instrument"
                ),
                "symbol": "TEST.SI",
                "column_values": {
                    "A": "1.0",
                },
            }
        ],
        "capture_started_at": "start",
        "capture_finished_at": "finish",
        "diagnostics": {
            "source": "test",
        },
    }


def result_summary(
    result_id: str,
) -> dict[str, Any]:
    result = full_result(result_id)

    return {
        key: result[key]
        for key in (
            "result_id",
            "explorer_id",
            "created_at",
            "schema_version",
            "outcome",
            "expected_count",
            "matched_count",
            "has_matches",
            "clipboard_verified",
            "capture_started_at",
            "capture_finished_at",
        )
    }


class FakeResultClient:
    def __init__(self) -> None:
        self.list_limit: int | None = None

    def save_explorer_result(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def get_explorer_result(
        self,
        result_id: str,
    ) -> dict[str, Any]:
        if result_id == "missing":
            raise ValueError(
                "No explorer_result_sets row found "
                "for id=missing"
            )

        return full_result(result_id)

    def get_latest_explorer_result(
        self,
        explorer_id: str,
    ) -> dict[str, Any] | None:
        if explorer_id == "empty":
            return None

        return full_result("latest-result")

    def list_explorer_results(
        self,
        explorer_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self.list_limit = limit

        return [
            result_summary("result-2"),
            result_summary("result-1"),
        ]


def build_service() -> MetaStockResultToolService:
    return MetaStockResultToolService(
        result_client=FakeResultClient()
    )


def test_get_result_returns_full_artifact() -> None:
    result = build_service().get_explorer_result(
        GetExplorerResultInput(
            result_id="result-1"
        )
    )

    assert result.ok is True
    assert result.status is ToolStatus.SUCCESS
    assert (
        result.data["result"]["result_id"]
        == "result-1"
    )
    assert (
        result.data["result"]["rows"][0][
            "symbol"
        ]
        == "TEST.SI"
    )


def test_unknown_result_fails_cleanly() -> None:
    result = build_service().get_explorer_result(
        GetExplorerResultInput(
            result_id="missing"
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert (
        result.error.code
        == "RESULT_NOT_FOUND"
    )


def test_latest_result_returns_found_result() -> None:
    result = (
        build_service()
        .get_latest_explorer_result(
            GetLatestExplorerResultInput(
                explorer_id="explorer-1"
            )
        )
    )

    assert result.ok is True
    assert result.data["found"] is True
    assert (
        result.data["result"]["result_id"]
        == "latest-result"
    )


def test_latest_result_preserves_empty_state() -> None:
    result = (
        build_service()
        .get_latest_explorer_result(
            GetLatestExplorerResultInput(
                explorer_id="empty"
            )
        )
    )

    assert result.ok is True
    assert result.data["found"] is False
    assert result.data["result"] is None


def test_list_results_forwards_limit() -> None:
    client = FakeResultClient()

    service = MetaStockResultToolService(
        result_client=client
    )

    result = service.list_explorer_results(
        ListExplorerResultsInput(
            explorer_id="explorer-1",
            limit=5,
        )
    )

    assert result.ok is True
    assert result.data["count"] == 2
    assert client.list_limit == 5
    assert [
        item["result_id"]
        for item in result.data["results"]
    ] == [
        "result-2",
        "result-1",
    ]