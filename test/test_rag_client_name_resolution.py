from __future__ import annotations

import pytest

from services.rag_client import LocalRagClient


class FakeReadService:
    def __init__(
        self,
        *,
        result: str = "explorer-id-1",
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.received_name: str | None = None

    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        self.received_name = explorer_name

        if self.error is not None:
            raise self.error

        return self.result


def build_client(
    read_service: FakeReadService,
) -> LocalRagClient:
    """
    Construct the client without running its real repository-loading
    constructor. This keeps this test isolated from Supabase, .env files,
    and the local RAG repository.
    """
    client = object.__new__(LocalRagClient)
    client._read_service = read_service
    return client


def test_name_resolution_delegates_to_read_service() -> None:
    read_service = FakeReadService(
        result="explorer-uuid-123"
    )
    client = build_client(read_service)

    resolved_id = (
        client.resolve_explorer_id_by_name(
            "  RSI Scanner  "
        )
    )

    assert resolved_id == "explorer-uuid-123"

    # LocalRagClient must not apply its own matching rules.
    assert (
        read_service.received_name
        == "  RSI Scanner  "
    )


def test_name_resolution_propagates_service_error() -> None:
    expected_error = LookupError(
        "No exact Explorer name match."
    )
    read_service = FakeReadService(
        error=expected_error
    )
    client = build_client(read_service)

    with pytest.raises(
        LookupError,
        match="No exact Explorer name match",
    ):
        client.resolve_explorer_id_by_name(
            "Unknown Explorer"
        )