from __future__ import annotations

import traceback
from typing import Any, Protocol
from pydantic import ValidationError

from services.automator_client import (
    AutomatorClient,
    AutomatorReadResultsRequest,
    UnavailableAutomatorClient,
)

from tools.tool_contracts import (
    MetaStockExplorerResultsDTO,
    ReadMetaStockResultsInput,
    ReadMetaStockResultsOutput,
    ToolDisplay,
    ToolError,
    ToolResult,
    ToolStatus,
    GetExplorerResultInput,
    GetExplorerResultOutput,
    GetLatestExplorerResultInput,
    GetLatestExplorerResultOutput,
    ListExplorerResultsInput,
    ListExplorerResultsOutput,
    MetaStockExplorerResultSummaryDTO,
    StoredMetaStockExplorerResultDTO,
)


class ExplorerResultClientProtocol(Protocol):
    """
    Controlled result persistence and retrieval boundary.

    LocalRagClient implements this protocol. Tests may inject a fake
    without loading the sibling RAG repository.
    """

    def save_explorer_result(
        self,
        *,
        explorer_id: str,
        result_payload: dict[str, Any],
        capture_started_at: str | None,
        capture_finished_at: str | None,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def get_explorer_result(
        self,
        result_id: str,
    ) -> dict[str, Any]:
        ...

    def get_latest_explorer_result(
        self,
        explorer_id: str,
    ) -> dict[str, Any] | None:
        ...

    def list_explorer_results(
        self,
        explorer_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        ...

class MetaStockResultToolService:
    """
    LLM-facing result-reading and persistence facade.

    A successful tool call means:
    1. MetaStock rows were read;
    2. the result contract was validated;
    3. clipboard verification passed when matches exist;
    4. the normalized result artifact was stored in Supabase.

    The tool never receives a raw Supabase client.
    """

    def __init__(
        self,
        *,
        automator_client: (
            AutomatorClient | None
        ) = None,
        result_client: (
            ExplorerResultClientProtocol
            | None
        ) = None,
        display_row_limit: int = 50,
    ) -> None:
        self.automator_client = (
            automator_client
            or UnavailableAutomatorClient()
        )
        self.result_client = result_client
        self.display_row_limit = max(
            1,
            display_row_limit,
        )

    def read_metastock_explorer_results(
        self,
        payload: ReadMetaStockResultsInput,
    ) -> ToolResult:
        if not self.automator_client.configured:
            return self._blocked_result(
                code="AUTOMATOR_NOT_CONFIGURED",
                message=(
                    "MetaStock result reading is "
                    "not configured."
                ),
                title=(
                    "MetaStock Result Reader "
                    "Not Connected"
                ),
                markdown=(
                    "The result window was not read "
                    "because the local AutomatorClient "
                    "is unavailable."
                ),
            )

        if self.result_client is None:
            return self._blocked_result(
                code=(
                    "RESULT_PERSISTENCE_NOT_CONFIGURED"
                ),
                message=(
                    "Explorer result persistence is "
                    "not configured."
                ),
                title=(
                    "Result Persistence Not Connected"
                ),
                markdown=(
                    "The result window was not read "
                    "because no RAG result client was "
                    "supplied."
                ),
            )

        try:
            result = (
                self.automator_client
                .read_results(
                    AutomatorReadResultsRequest(
                        explorer_id=(
                            payload.explorer_id
                        ),
                        close_after_read=(
                            payload
                            .close_after_read
                        ),
                    )
                )
            )

            parsed_results = (
                MetaStockExplorerResultsDTO
                .model_validate(
                    result.results.model_dump(
                        mode="json"
                    )
                )
                if (
                    result.results
                    is not None
                )
                else None
            )

            if not result.succeeded:
                output = (
                    ReadMetaStockResultsOutput(
                        explorer_id=(
                            payload.explorer_id
                        ),
                        persisted=False,
                        succeeded=False,
                        message=result.message,
                        started_at=(
                            result.started_at
                        ),
                        finished_at=(
                            result.finished_at
                        ),
                        results=parsed_results,
                        diagnostics=(
                            result.diagnostics
                        ),
                    )
                )

                return ToolResult(
                    tool_name=(
                        "read_metastock_"
                        "explorer_results"
                    ),
                    ok=False,
                    status=ToolStatus.FAILED,
                    message=result.message,
                    data=output.model_dump(
                        mode="json"
                    ),
                    error=ToolError(
                        code=(
                            "METASTOCK_RESULT_"
                            "READ_FAILED"
                        ),
                        message=result.message,
                        details=(
                            result.diagnostics
                        ),
                    ),
                    display=ToolDisplay(
                        title=(
                            "MetaStock Result "
                            "Reading Failed"
                        ),
                        markdown=result.message,
                        severity="error",
                    ),
                )

            if parsed_results is None:
                raise RuntimeError(
                    "The Automator reported a "
                    "successful result read without "
                    "a result payload."
                )

            result_payload = (
                parsed_results.model_dump(
                    mode="json"
                )
            )

            try:
                stored = (
                    self.result_client
                    .save_explorer_result(
                        explorer_id=(
                            payload.explorer_id
                        ),
                        result_payload=(
                            result_payload
                        ),
                        capture_started_at=(
                            result.started_at
                        ),
                        capture_finished_at=(
                            result.finished_at
                        ),
                        diagnostics=(
                            result.diagnostics
                        ),
                    )
                )

                (
                    stored_result_id,
                    stored_explorer_id,
                    stored_at,
                ) = self._stored_result_metadata(
                    stored,
                    fallback_explorer_id=(
                        payload.explorer_id
                    ),
                )

            except Exception as exc:
                output = (
                    ReadMetaStockResultsOutput(
                        explorer_id=(
                            payload.explorer_id
                        ),
                        result_id=None,
                        stored_at=None,
                        persisted=False,
                        succeeded=True,
                        message=(
                            "MetaStock results were "
                            "read, but Supabase "
                            "persistence failed."
                        ),
                        started_at=(
                            result.started_at
                        ),
                        finished_at=(
                            result.finished_at
                        ),
                        results=parsed_results,
                        diagnostics=(
                            result.diagnostics
                        ),
                    )
                )

                return ToolResult(
                    tool_name=(
                        "read_metastock_"
                        "explorer_results"
                    ),
                    ok=False,
                    status=ToolStatus.FAILED,
                    message=(
                        "MetaStock results were read "
                        "but could not be stored in "
                        "Supabase."
                    ),
                    data=output.model_dump(
                        mode="json"
                    ),
                    error=ToolError(
                        code=(
                            "RESULT_PERSISTENCE_FAILED"
                        ),
                        message=str(exc),
                        details={
                            "explorer_id": (
                                payload.explorer_id
                            ),
                            "traceback": (
                                traceback.format_exc()
                            ),
                        },
                    ),
                    display=ToolDisplay(
                        title=(
                            "Result Persistence Failed"
                        ),
                        markdown=(
                            "MetaStock returned valid "
                            "results, but they were not "
                            "stored in Supabase. The "
                            "structured rows remain in "
                            "this failed tool response."
                        ),
                        severity="error",
                    ),
                )

            message = (
                f"{result.message} Stored result "
                f"artifact {stored_result_id}."
            )

            output = ReadMetaStockResultsOutput(
                explorer_id=stored_explorer_id,
                result_id=stored_result_id,
                stored_at=stored_at,
                persisted=True,
                succeeded=True,
                message=message,
                started_at=result.started_at,
                finished_at=result.finished_at,
                results=parsed_results,
                diagnostics=result.diagnostics,
            )

            return ToolResult(
                tool_name=(
                    "read_metastock_explorer_results"
                ),
                ok=True,
                status=ToolStatus.SUCCESS,
                message=message,
                data=output.model_dump(
                    mode="json"
                ),
                display=self._result_display(
                    results=parsed_results,
                    result_id=stored_result_id,
                ),
            )

        except Exception as exc:
            return ToolResult(
                tool_name=(
                    "read_metastock_explorer_results"
                ),
                ok=False,
                status=ToolStatus.FAILED,
                message=str(exc),
                error=ToolError(
                    code=type(exc).__name__,
                    message=str(exc),
                    details={
                        "traceback": (
                            traceback.format_exc()
                        )
                    },
                ),
                display=ToolDisplay(
                    title=(
                        "MetaStock Result "
                        "Reading Failed"
                    ),
                    markdown=str(exc),
                    severity="error",
                ),
            )
        
    def get_explorer_result(
        self,
        payload: GetExplorerResultInput,
    ) -> ToolResult:
        tool_name = "get_explorer_result"

        if self.result_client is None:
            return self._blocked_result(
                tool_name=tool_name,
                code=(
                    "RESULT_PERSISTENCE_NOT_CONFIGURED"
                ),
                message=(
                    "Stored Explorer result retrieval "
                    "is not configured."
                ),
                title="Result Storage Not Connected",
                markdown=(
                    "The stored result could not be "
                    "loaded because no RAG result "
                    "client was supplied."
                ),
            )

        try:
            raw_result = (
                self.result_client
                .get_explorer_result(
                    payload.result_id
                )
            )

            stored_result = (
                StoredMetaStockExplorerResultDTO
                .model_validate(raw_result)
            )

            output = GetExplorerResultOutput(
                result=stored_result
            )

            message = (
                "Loaded stored Explorer result "
                f"{stored_result.result_id}."
            )

            return ToolResult(
                tool_name=tool_name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message=message,
                data=output.model_dump(
                    mode="json"
                ),
                display=(
                    self._stored_result_display(
                        stored_result
                    )
                ),
            )

        except ValidationError as exc:
            return self._retrieval_failure(
                tool_name=tool_name,
                code=(
                    "STORED_RESULT_SCHEMA_INVALID"
                ),
                message=(
                    "The stored Explorer result did "
                    "not conform to schema version 1.0."
                ),
                exc=exc,
            )

        except ValueError as exc:
            return self._retrieval_failure(
                tool_name=tool_name,
                code="RESULT_NOT_FOUND",
                message=str(exc),
                exc=exc,
            )

        except Exception as exc:
            return self._retrieval_failure(
                tool_name=tool_name,
                code=type(exc).__name__,
                message=str(exc),
                exc=exc,
            )


    def get_latest_explorer_result(
        self,
        payload: GetLatestExplorerResultInput,
    ) -> ToolResult:
        tool_name = "get_latest_explorer_result"

        if self.result_client is None:
            return self._blocked_result(
                tool_name=tool_name,
                code=(
                    "RESULT_PERSISTENCE_NOT_CONFIGURED"
                ),
                message=(
                    "Stored Explorer result retrieval "
                    "is not configured."
                ),
                title="Result Storage Not Connected",
                markdown=(
                    "The latest result could not be "
                    "loaded because no RAG result "
                    "client was supplied."
                ),
            )

        try:
            raw_result = (
                self.result_client
                .get_latest_explorer_result(
                    payload.explorer_id
                )
            )

            if raw_result is None:
                output = (
                    GetLatestExplorerResultOutput(
                        explorer_id=(
                            payload.explorer_id
                        ),
                        found=False,
                        result=None,
                    )
                )

                message = (
                    "No stored results were found for "
                    f"Explorer {payload.explorer_id}."
                )

                return ToolResult(
                    tool_name=tool_name,
                    ok=True,
                    status=ToolStatus.SUCCESS,
                    message=message,
                    data=output.model_dump(
                        mode="json"
                    ),
                    display=ToolDisplay(
                        title=(
                            "Latest MetaStock "
                            "Explorer Result"
                        ),
                        markdown=message,
                        severity="info",
                    ),
                )

            stored_result = (
                StoredMetaStockExplorerResultDTO
                .model_validate(raw_result)
            )

            output = GetLatestExplorerResultOutput(
                explorer_id=payload.explorer_id,
                found=True,
                result=stored_result,
            )

            message = (
                "Loaded the latest stored result "
                f"{stored_result.result_id} for "
                f"Explorer {payload.explorer_id}."
            )

            return ToolResult(
                tool_name=tool_name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message=message,
                data=output.model_dump(
                    mode="json"
                ),
                display=(
                    self._stored_result_display(
                        stored_result
                    )
                ),
            )

        except ValidationError as exc:
            return self._retrieval_failure(
                tool_name=tool_name,
                code=(
                    "STORED_RESULT_SCHEMA_INVALID"
                ),
                message=(
                    "The latest stored result did not "
                    "conform to schema version 1.0."
                ),
                exc=exc,
            )

        except Exception as exc:
            return self._retrieval_failure(
                tool_name=tool_name,
                code=type(exc).__name__,
                message=str(exc),
                exc=exc,
            )


    def list_explorer_results(
        self,
        payload: ListExplorerResultsInput,
    ) -> ToolResult:
        tool_name = "list_explorer_results"

        if self.result_client is None:
            return self._blocked_result(
                tool_name=tool_name,
                code=(
                    "RESULT_PERSISTENCE_NOT_CONFIGURED"
                ),
                message=(
                    "Stored Explorer result listing "
                    "is not configured."
                ),
                title="Result Storage Not Connected",
                markdown=(
                    "Result history could not be listed "
                    "because no RAG result client was "
                    "supplied."
                ),
            )

        try:
            raw_results = (
                self.result_client
                .list_explorer_results(
                    payload.explorer_id,
                    limit=payload.limit,
                )
            )

            results = [
                MetaStockExplorerResultSummaryDTO
                .model_validate(item)
                for item in raw_results
            ]

            output = ListExplorerResultsOutput(
                explorer_id=payload.explorer_id,
                count=len(results),
                results=results,
            )

            message = (
                f"Loaded {len(results)} stored "
                "result summaries for Explorer "
                f"{payload.explorer_id}."
            )

            return ToolResult(
                tool_name=tool_name,
                ok=True,
                status=ToolStatus.SUCCESS,
                message=message,
                data=output.model_dump(
                    mode="json"
                ),
                display=(
                    self._result_list_display(
                        output
                    )
                ),
            )

        except ValidationError as exc:
            return self._retrieval_failure(
                tool_name=tool_name,
                code=(
                    "STORED_RESULT_SCHEMA_INVALID"
                ),
                message=(
                    "A stored result summary did not "
                    "conform to schema version 1.0."
                ),
                exc=exc,
            )

        except Exception as exc:
            return self._retrieval_failure(
                tool_name=tool_name,
                code=type(exc).__name__,
                message=str(exc),
                exc=exc,
            )

    @staticmethod
    def _stored_result_metadata(
        stored: Any,
        *,
        fallback_explorer_id: str,
    ) -> tuple[str, str, str | None]:
        """
        Validate the narrow response returned by LocalRagClient.
        """
        if not isinstance(stored, dict):
            raise TypeError(
                "The RAG result client returned an "
                "unsupported persistence response: "
                f"{type(stored).__name__}."
            )

        result_id = str(
            stored.get("result_id")
            or ""
        ).strip()

        if not result_id:
            raise RuntimeError(
                "The RAG result client returned no "
                "result_id."
            )

        explorer_id = str(
            stored.get("explorer_id")
            or fallback_explorer_id
            or ""
        ).strip()

        if not explorer_id:
            raise RuntimeError(
                "The RAG result client returned no "
                "explorer_id."
            )

        raw_created_at = stored.get(
            "created_at"
        )

        created_at = (
            str(raw_created_at).strip()
            if raw_created_at is not None
            else None
        )

        if created_at == "":
            created_at = None

        return (
            result_id,
            explorer_id,
            created_at,
        )

    def _stored_result_display(
        self,
        result: StoredMetaStockExplorerResultDTO,
    ) -> ToolDisplay:
        current_result = (
            MetaStockExplorerResultsDTO(
                schema_version=(
                    result.schema_version
                ),
                outcome=result.outcome,
                expected_count=(
                    result.expected_count
                ),
                matched_count=(
                    result.matched_count
                ),
                has_matches=result.has_matches,
                clipboard_verification=(
                    result.clipboard_verification
                ),
                rows=result.rows,
            )
        )

        return self._result_display(
            results=current_result,
            result_id=result.result_id,
        )


    @staticmethod
    def _result_list_display(
        output: ListExplorerResultsOutput,
    ) -> ToolDisplay:
        lines = [
            (
                "**Explorer ID:** "
                f"`{output.explorer_id}`"
            ),
            (
                "**Stored result count:** "
                f"{output.count}"
            ),
        ]

        if output.results:
            lines.extend(
                [
                    "",
                    "## Stored results",
                    "",
                ]
            )

            for result in output.results:
                created_at = (
                    result.created_at
                    or "<unknown time>"
                )

                lines.append(
                    f"- `{result.result_id}` — "
                    f"{created_at} — "
                    f"{result.outcome} — "
                    f"{result.matched_count} matches"
                )
        else:
            lines.extend(
                [
                    "",
                    "No stored results were found.",
                ]
            )

        return ToolDisplay(
            title="MetaStock Explorer Result History",
            markdown="\n".join(lines),
            severity="info",
        )


    @staticmethod
    def _retrieval_failure(
        *,
        tool_name: str,
        code: str,
        message: str,
        exc: Exception,
    ) -> ToolResult:
        return ToolResult(
            tool_name=tool_name,
            ok=False,
            status=ToolStatus.FAILED,
            message=message,
            error=ToolError(
                code=code,
                message=message,
                details={
                    "error_type": (
                        type(exc).__name__
                    ),
                    "traceback": (
                        traceback.format_exc()
                    ),
                },
            ),
            display=ToolDisplay(
                title=(
                    "Stored MetaStock Result "
                    "Retrieval Failed"
                ),
                markdown=message,
                severity="error",
            ),
        )

    def _result_display(
        self,
        *,
        results: MetaStockExplorerResultsDTO,
        result_id: str,
    ) -> ToolDisplay:
        if results.outcome == "no_matches":
            return ToolDisplay(
                title=(
                    "MetaStock Explorer Results"
                ),
                markdown=(
                    f"**Result ID:** `{result_id}`\n\n"
                    "**Outcome:** No matches\n\n"
                    "The Explorer completed "
                    "successfully and the zero-match "
                    "result was stored in Supabase."
                ),
                severity="info",
            )

        verification = (
            results.clipboard_verification
        )
        verified = (
            verification.passed
            if verification is not None
            else False
        )

        lines = [
            f"**Result ID:** `{result_id}`",
            f"**Outcome:** {results.outcome}",
            (
                "**Matched instruments:** "
                f"{results.matched_count}"
            ),
            (
                "**Clipboard verified:** "
                f"{verified}"
            ),
            "",
            "## Result rows",
            "",
        ]

        for row in results.rows[
            : self.display_row_limit
        ]:
            symbol = (
                row.symbol
                or "<no symbol>"
            )
            values = "; ".join(
                f"{letter}={value}"
                for letter, value in sorted(
                    row.column_values.items()
                )
            )

            lines.append(
                f"- `{symbol}` — "
                f"{row.instrument_name}"
                + (
                    f" — {values}"
                    if values
                    else ""
                )
            )

        hidden_count = (
            len(results.rows)
            - self.display_row_limit
        )

        if hidden_count > 0:
            lines.extend(
                [
                    "",
                    (
                        f"{hidden_count} additional "
                        "rows are available in the "
                        "stored artifact and structured "
                        "tool data."
                    ),
                ]
            )

        return ToolDisplay(
            title="MetaStock Explorer Results",
            markdown="\n".join(lines),
            severity="success",
        )

    @staticmethod
    def _blocked_result(
        *,
        tool_name: str = (
            "read_metastock_explorer_results"
        ),
        code: str,
        message: str,
        title: str,
        markdown: str,
    ) -> ToolResult:
        return ToolResult(
            tool_name=tool_name,
            ok=False,
            status=ToolStatus.BLOCKED,
            message=message,
            error=ToolError(
                code=code,
                message=message,
            ),
            display=ToolDisplay(
                title=title,
                markdown=markdown,
                severity="warning",
            ),
        )
