from __future__ import annotations

import pytest

from services.explorer_name_resolver import (
    ExplorerNameAmbiguousError as AgentExplorerNameAmbiguousError,
    ExplorerNameResolutionError,
    ExplorerNameResolver,
    ExplorerNotFoundError as AgentExplorerNotFoundError,
)


# Simulate the exception classes raised by the dynamically loaded
# RAG repository. ExplorerNameResolver translates them according
# to their stable class names.
RagExplorerNotFoundError = type(
    "ExplorerNotFoundError",
    (LookupError,),
    {},
)

RagExplorerNameAmbiguousError = type(
    "ExplorerNameAmbiguousError",
    (LookupError,),
    {},
)


class FakeExactNameLookupClient:
    """
    Small in-memory substitute for the RAG exact-name lookup.

    Rows use:
        (explorer_id, explorer_name)

    This fake follows the RAG-side contract:
    - trimmed;
    - case-insensitive;
    - exact equality only.
    """

    def __init__(
        self,
        rows: list[tuple[str, str]],
    ) -> None:
        self.rows = rows
        self.received_names: list[str] = []

    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        self.received_names.append(explorer_name)

        normalized_name = (
            str(explorer_name)
            .strip()
            .casefold()
        )

        matches = [
            explorer_id
            for explorer_id, stored_name
            in self.rows
            if (
                str(stored_name)
                .strip()
                .casefold()
                == normalized_name
            )
        ]

        if not matches:
            raise RagExplorerNotFoundError(
                "No explorer_outputs row has the exact "
                f"Explorer name {explorer_name!r}."
            )

        if len(matches) > 1:
            raise RagExplorerNameAmbiguousError(
                "More than one explorer_outputs row has "
                "the requested exact Explorer name."
            )

        return matches[0]


class FixedResultClient:
    def __init__(
        self,
        result: str,
    ) -> None:
        self.result = result
        self.calls = 0

    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        self.calls += 1
        return self.result


class FixedErrorClient:
    def __init__(
        self,
        error: LookupError,
    ) -> None:
        self.error = error
        self.calls = 0

    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        self.calls += 1
        raise self.error


def test_exact_unique_match_returns_uuid() -> None:
    client = FakeExactNameLookupClient(
        [
            (
                "explorer-uuid-1",
                "RSI Scanner",
            ),
            (
                "explorer-uuid-2",
                "Breakout Scanner",
            ),
        ]
    )
    resolver = ExplorerNameResolver(client)

    result = resolver.resolve_explorer_id(
        "RSI Scanner"
    )

    assert result == "explorer-uuid-1"
    assert client.received_names == [
        "RSI Scanner"
    ]


def test_case_insensitive_exact_match_works() -> None:
    client = FakeExactNameLookupClient(
        [
            (
                "explorer-uuid-1",
                "RSI Scanner",
            )
        ]
    )
    resolver = ExplorerNameResolver(client)

    result = resolver.resolve_explorer_id(
        "rsi scanner"
    )

    assert result == "explorer-uuid-1"


def test_surrounding_whitespace_is_ignored() -> None:
    client = FakeExactNameLookupClient(
        [
            (
                "explorer-uuid-1",
                "RSI Scanner",
            )
        ]
    )
    resolver = ExplorerNameResolver(client)

    result = resolver.resolve_explorer_id(
        "   RSI Scanner   "
    )

    assert result == "explorer-uuid-1"

    # The application resolver cleans user-facing input before
    # passing it to LocalRagClient.
    assert client.received_names == [
        "RSI Scanner"
    ]


def test_unknown_name_raises_agent_not_found() -> None:
    client = FakeExactNameLookupClient(
        [
            (
                "explorer-uuid-1",
                "RSI Scanner",
            )
        ]
    )
    resolver = ExplorerNameResolver(client)

    with pytest.raises(
        AgentExplorerNotFoundError,
        match="exact Explorer name",
    ):
        resolver.resolve_explorer_id(
            "MACD Scanner"
        )


def test_duplicate_exact_names_raise_agent_ambiguous() -> None:
    client = FakeExactNameLookupClient(
        [
            (
                "explorer-uuid-1",
                "RSI Scanner",
            ),
            (
                "explorer-uuid-2",
                "rsi scanner",
            ),
        ]
    )
    resolver = ExplorerNameResolver(client)

    with pytest.raises(
        AgentExplorerNameAmbiguousError,
        match="More than one",
    ):
        resolver.resolve_explorer_id(
            "RSI Scanner"
        )


def test_partial_match_is_rejected() -> None:
    client = FakeExactNameLookupClient(
        [
            (
                "explorer-uuid-1",
                "RSI Scanner",
            )
        ]
    )
    resolver = ExplorerNameResolver(client)

    with pytest.raises(
        AgentExplorerNotFoundError
    ):
        resolver.resolve_explorer_id("RSI")


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "   ",
        "\t",
        "\n",
    ],
)
def test_blank_name_is_rejected_before_lookup(
    invalid_name: str,
) -> None:
    client = FixedResultClient(
        "explorer-uuid-1"
    )
    resolver = ExplorerNameResolver(client)

    with pytest.raises(
        ValueError,
        match="explorer_name is required",
    ):
        resolver.resolve_explorer_id(
            invalid_name
        )

    assert client.calls == 0


@pytest.mark.parametrize(
    "invalid_id",
    [
        "",
        "   ",
        "\t",
    ],
)
def test_empty_uuid_from_client_is_rejected(
    invalid_id: str,
) -> None:
    client = FixedResultClient(invalid_id)
    resolver = ExplorerNameResolver(client)

    with pytest.raises(
        RuntimeError,
        match="empty explorer ID",
    ):
        resolver.resolve_explorer_id(
            "RSI Scanner"
        )


def test_unknown_lookup_error_becomes_base_domain_error() -> None:
    client = FixedErrorClient(
        LookupError(
            "Unexpected lookup failure."
        )
    )
    resolver = ExplorerNameResolver(client)

    with pytest.raises(
        ExplorerNameResolutionError,
        match="Unexpected lookup failure",
    ):
        resolver.resolve_explorer_id(
            "RSI Scanner"
        )