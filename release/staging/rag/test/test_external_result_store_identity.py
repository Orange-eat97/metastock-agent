from types import SimpleNamespace

from src.rag_result_store_service import (
    RagExplorerResultStoreService,
)


class _InsertQuery:
    def __init__(self, table_name: str, captured: dict):
        self._table_name = table_name
        self._captured = captured

    def insert(self, row: dict):
        self._captured["table"] = self._table_name
        self._captured["row"] = dict(row)
        return self

    def execute(self):
        stored = {
            "id": "11111111-1111-1111-1111-111111111111",
            "created_at": "2026-07-22T04:01:00+00:00",
            **self._captured["row"],
        }
        return SimpleNamespace(data=[stored])


class _FakeClient:
    def __init__(self):
        self.captured: dict = {}

    def table(self, table_name: str):
        return _InsertQuery(table_name, self.captured)


def test_external_result_is_stored_without_explorer_foreign_key():
    client = _FakeClient()
    service = RagExplorerResultStoreService(client=client)

    stored = service.save_explorer_results(
        explorer_id=None,
        explorer_name="#External Explorer",
        run_started_at="2026-07-22T04:00:00+00:00",
        schema_version="1.0",
        outcome="no_matches",
        expected_count=0,
        matched_count=0,
        has_matches=False,
        clipboard_verification=None,
        rows=[],
        diagnostics={},
    )

    assert client.captured["table"] == "explorer_result_sets"
    assert client.captured["row"]["explorer_id"] is None
    assert (
        client.captured["row"]["explorer_name"]
        == "#External Explorer"
    )
    assert (
        client.captured["row"]["run_started_at"]
        == "2026-07-22T04:00:00+00:00"
    )
    assert stored["explorer_id"] is None
    assert stored["explorer_name"] == "#External Explorer"
