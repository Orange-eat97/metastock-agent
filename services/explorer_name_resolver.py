from __future__ import annotations

from typing import Protocol


class ExplorerNameLookupClient(Protocol):
    """
    Minimal client contract required by ExplorerNameResolver.

    LocalRagClient satisfies this protocol without needing to inherit
    from it explicitly.
    """

    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        ...


class ExplorerNameResolutionError(LookupError):
    """Base error for agent-side Explorer-name resolution."""


class ExplorerNotFoundError(
    ExplorerNameResolutionError
):
    """No stored Explorer has the requested exact name."""


class ExplorerNameAmbiguousError(
    ExplorerNameResolutionError
):
    """More than one stored Explorer has the requested exact name."""


class ExplorerNameResolver:
    """
    Application-level boundary for resolving Explorer names.

    Responsibilities:
    - reject missing or blank user input;
    - delegate exact-name lookup to the RAG client;
    - translate RAG-side lookup errors into agent-side domain errors;
    - return a non-empty explorer_outputs UUID.

    This class does not perform its own fuzzy, semantic, prefix, or
    substring matching. Exact matching remains owned by the RAG read
    service.
    """

    def __init__(
        self,
        rag_client: ExplorerNameLookupClient,
    ) -> None:
        self._rag_client = rag_client

    def resolve_explorer_id(
        self,
        explorer_name: str,
    ) -> str:
        """
        Resolve an exact Explorer name to an explorer_outputs UUID.

        Raises:
            ValueError:
                The supplied name is blank.

            ExplorerNotFoundError:
                No exact stored name matches.

            ExplorerNameAmbiguousError:
                More than one exact stored name matches.

            ExplorerNameResolutionError:
                The lookup failed with another lookup-related error.

            RuntimeError:
                The lookup service returned an empty Explorer ID.
        """
        cleaned_name = self._clean_required_text(
            explorer_name,
            "explorer_name",
        )

        try:
            explorer_id = (
                self._rag_client
                .resolve_explorer_id_by_name(
                    cleaned_name
                )
            )

        except LookupError as exc:
            self._raise_domain_lookup_error(exc)

        cleaned_explorer_id = str(
            explorer_id or ""
        ).strip()

        if not cleaned_explorer_id:
            raise RuntimeError(
                "Explorer-name lookup returned an empty "
                "explorer ID."
            )

        return cleaned_explorer_id

    @staticmethod
    def _raise_domain_lookup_error(
        error: LookupError,
    ) -> None:
        """
        Convert dynamically imported RAG exceptions into stable
        agent-side exception types.

        The RAG repository is loaded at runtime, so importing its
        exception classes directly into this module would recreate the
        sibling-repository import problem. The service-side exceptions
        are LookupError subclasses with stable class names.
        """
        error_type_name = type(error).__name__
        message = str(error)

        if (
            error_type_name
            == "ExplorerNotFoundError"
        ):
            raise ExplorerNotFoundError(
                message
            ) from error

        if (
            error_type_name
            == "ExplorerNameAmbiguousError"
        ):
            raise ExplorerNameAmbiguousError(
                message
            ) from error

        raise ExplorerNameResolutionError(
            message
        ) from error

    @staticmethod
    def _clean_required_text(
        value: str,
        field_name: str,
    ) -> str:
        cleaned = str(value or "").strip()

        if not cleaned:
            raise ValueError(
                f"{field_name} is required."
            )

        return cleaned