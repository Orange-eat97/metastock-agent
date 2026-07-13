from __future__ import annotations

from typing import Any

import pytest

from services.rag_client import LocalRagClient


class FakeResultService:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def save_explorer_results(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "save_explorer_results",
                kwargs,
            )
        )

        return {
            "result_id": "result-1",
            "explorer_id": kwargs[
                "explorer_id"
            ],
            "created_at": "created",
        }

    def get_result(
        self,
        result_id: str,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "get_result",
                {
                    "result_id": result_id,
                },
            )
        )

        return {
            "result_id": result_id,
            "explorer_id": "explorer-1",
            "schema_version": "1.0",
            "rows": [],
        }

    def get_latest_result(
        self,
        explorer_id: str,
    ) -> dict[str, Any] | None:
        self.calls.append(
            (
                "get_latest_result",
                {
                    "explorer_id": (
                        explorer_id
                    ),
                },
            )
        )

        if explorer_id == "empty":
            return None

        return {
            "result_id": "result-latest",
            "explorer_id": explorer_id,
            "schema_version": "1.0",
            "rows": [],
        }

    def list_results(
        self,
        explorer_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            (
                "list_results",
                {
                    "explorer_id": (
                        explorer_id
                    ),
                    "limit": limit,
                },
            )
        )

        return [
            {
                "result_id": "result-2",
                "explorer_id": explorer_id,
            },
            {
                "result_id": "result-1",
                "explorer_id": explorer_id,
            },
        ]


def build_client(
    result_service: FakeResultService,
) -> LocalRagClient:
    """
    Construct the adapter without loading the sibling RAG repository.
    """
    client = object.__new__(
        LocalRagClient
    )
    client._result_store_service = (
        result_service
    )
    return client


def build_payload() -> dict[str, Any]:
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
    }


def test_save_explorer_result_unpacks_payload() -> None:
    service = FakeResultService()
    client = build_client(service)

    stored = client.save_explorer_result(
        explorer_id="explorer-1",
        result_payload=build_payload(),
        capture_started_at="start",
        capture_finished_at="finish",
        diagnostics={
            "source": "test",
        },
    )

    assert stored["result_id"] == "result-1"

    assert service.calls == [
        (
            "save_explorer_results",
            {
                "explorer_id": "explorer-1",
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
                "capture_started_at": (
                    "start"
                ),
                "capture_finished_at": (
                    "finish"
                ),
                "diagnostics": {
                    "source": "test",
                },
            },
        )
    ]


def test_get_explorer_result_delegates() -> None:
    service = FakeResultService()
    client = build_client(service)

    result = client.get_explorer_result(
        "result-123"
    )

    assert (
        result["result_id"]
        == "result-123"
    )
    assert service.calls == [
        (
            "get_result",
            {
                "result_id": "result-123",
            },
        )
    ]


def test_get_latest_explorer_result_delegates() -> None:
    service = FakeResultService()
    client = build_client(service)

    result = (
        client.get_latest_explorer_result(
            "explorer-1"
        )
    )

    assert result is not None
    assert (
        result["result_id"]
        == "result-latest"
    )
    assert service.calls == [
        (
            "get_latest_result",
            {
                "explorer_id": (
                    "explorer-1"
                ),
            },
        )
    ]


def test_latest_result_preserves_none() -> None:
    service = FakeResultService()
    client = build_client(service)

    result = (
        client.get_latest_explorer_result(
            "empty"
        )
    )

    assert result is None


def test_list_explorer_results_forwards_limit() -> None:
    service = FakeResultService()
    client = build_client(service)

    results = client.list_explorer_results(
        "explorer-1",
        limit=5,
    )

    assert [
        row["result_id"]
        for row in results
    ] == [
        "result-2",
        "result-1",
    ]

    assert service.calls == [
        (
            "list_results",
            {
                "explorer_id": (
                    "explorer-1"
                ),
                "limit": 5,
            },
        )
    ]


@pytest.mark.parametrize(
    "invalid_payload",
    [
        None,
        [],
        "not-a-dictionary",
    ],
)
def test_save_rejects_non_dictionary_payload(
    invalid_payload: Any,
) -> None:
    service = FakeResultService()
    client = build_client(service)

    with pytest.raises(
        ValueError,
        match="result_payload must be",
    ):
        client.save_explorer_result(
            explorer_id="explorer-1",
            result_payload=invalid_payload,
            capture_started_at=None,
            capture_finished_at=None,
            diagnostics={},
        )

    assert service.calls == []


def test_legacy_plural_save_remains_compatible() -> None:
    service = FakeResultService()
    client = build_client(service)

    stored = client.save_explorer_results(
        explorer_id="explorer-1",
        schema_version="1.0",
        outcome="no_matches",
        expected_count=0,
        matched_count=0,
        has_matches=False,
        clipboard_verification=None,
        rows=[],
        capture_started_at="start",
        capture_finished_at="finish",
        diagnostics={},
    )

    assert stored["result_id"] == "result-1"

    call_name, arguments = service.calls[0]

    assert (
        call_name
        == "save_explorer_results"
    )
    assert arguments["outcome"] == "no_matches"
    assert arguments["rows"] == []