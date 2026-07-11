from __future__ import annotations

from services.explorer_result_repository import (
    ExplorerResultRepository,
)


class FakeRagClient:
    def __init__(self):
        self.arguments = None

    def save_explorer_results(self, **kwargs):
        self.arguments = kwargs

        return {
            "result_id": "result-1",
            "explorer_id": (
                kwargs["explorer_id"]
            ),
            "created_at": "created",
        }


def test_repository_delegates_to_rag_service() -> None:
    rag_client = FakeRagClient()
    repository = ExplorerResultRepository(
        rag_client=rag_client
    )

    stored = repository.save_result(
        explorer_id="explorer-1",
        result_payload={
            "schema_version": "1.0",
            "outcome": "no_matches",
            "expected_count": 0,
            "matched_count": 0,
            "has_matches": False,
            "clipboard_verification": None,
            "rows": [],
        },
        capture_started_at="start",
        capture_finished_at="finish",
        diagnostics={"source": "test"},
    )

    assert stored.result_id == "result-1"
    assert stored.explorer_id == "explorer-1"
    assert (
        rag_client.arguments[
            "capture_started_at"
        ]
        == "start"
    )
