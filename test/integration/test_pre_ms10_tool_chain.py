from __future__ import annotations

from typing import Any

from agent_workflows.explorer_review_workflow import (
    ExplorerReviewWorkflow,
)
from services.automator_client import (
    AutomatorClipboardVerification,
    AutomatorExplorerResults,
    AutomatorReadResultsRequest,
    AutomatorReadResultsResult,
    AutomatorResultRow,
    AutomatorRunRequest,
    AutomatorRunResult,
)
from services.explorer_name_resolver import (
    ExplorerNameResolver,
)
from services.explorer_repository import (
    ExplorerRepository,
)
from services.rag_client import RagGenerateResult
from tools.explorer_tools import ExplorerToolService
from tools.result_tools import (
    MetaStockResultToolService,
)
from tools.tool_registry import ToolRegistry


EXPLORER_ID = "explorer-1"
RESULT_ID = "result-1"


class FakeRagClient:
    def __init__(self) -> None:
        self.stored_result: (
            dict[str, Any] | None
        ) = None

    def resolve_explorer_id_by_name(
        self,
        explorer_name: str,
    ) -> str:
        if (
            explorer_name.strip().casefold()
            != "rsi scanner"
        ):
            raise LookupError(
                "Explorer was not found."
            )

        return EXPLORER_ID

    def generate_explorer(
        self,
        user_message: str,
    ) -> RagGenerateResult:
        assert "RSI" in user_message

        return RagGenerateResult(
            explorer=EXPLORER_ID,
            explorer_created_at=(
                "2026-07-13T01:00:00+00:00"
            ),
            service_log="log-1",
            service_log_created_at=(
                "2026-07-13T01:00:01+00:00"
            ),
            validation_passed=True,
            validation_errors=[],
            source="generated",
            assumptions=[
                "RSI uses a 14-period lookback."
            ],
            retrieved_refs=[
                {
                    "key": "function.rsi",
                    "table_title": "rag_cards",
                    "rag_score": 0.95,
                    "retrieval_reason": (
                        "RSI is required by the query."
                    ),
                }
            ],
            validation_warnings=[
                "The threshold can be revised."
            ],
        )

    def repair_explorer(
        self,
        explorer_id: str,
        repair_instruction: str | None = None,
    ) -> RagGenerateResult:
        raise AssertionError(
            "Repair is not used in this test."
        )

    def get_explorer(
        self,
        explorer_id: str,
    ) -> dict[str, Any]:
        assert explorer_id == EXPLORER_ID

        return {
            "id": EXPLORER_ID,
            "created_at": (
                "2026-07-13T01:00:00+00:00"
            ),
            "explorer_name": "RSI Scanner",
            "explorer_description": (
                "Find oversold instruments."
            ),
            "explorer_code_body": (
                "RSI(14) < 30"
            ),
            "col_definitions": [
                {
                    "col_letter": "A",
                    "col_code": "RSI(14)",
                }
            ],
            "validation_passed": True,
            "validation_errors": [],
            "validation_warnings": [],
            "service_log_id": "log-1",
        }

    def get_service_log(
        self,
        log_id: str,
    ) -> dict[str, Any]:
        assert log_id == "log-1"

        return {
            "log_id": log_id,
            "created_at": (
                "2026-07-13T01:00:01+00:00"
            ),
            "event_type": "rag_service.generate",
            "stdout_text": "",
            "stderr_text": "",
            "metadata": {},
        }

    def save_explorer_result(
        self,
        *,
        explorer_id: str,
        result_payload: dict[str, Any],
        capture_started_at: str | None,
        capture_finished_at: str | None,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        verification = result_payload.get(
            "clipboard_verification"
        )

        self.stored_result = {
            "result_id": RESULT_ID,
            "explorer_id": explorer_id,
            "created_at": (
                "2026-07-13T01:05:00+00:00"
            ),
            "schema_version": (
                result_payload["schema_version"]
            ),
            "outcome": result_payload["outcome"],
            "expected_count": (
                result_payload["expected_count"]
            ),
            "matched_count": (
                result_payload["matched_count"]
            ),
            "has_matches": (
                result_payload["has_matches"]
            ),
            "clipboard_verified": bool(
                verification
                and verification.get("passed")
            ),
            "clipboard_verification": (
                verification
            ),
            "rows": result_payload["rows"],
            "capture_started_at": (
                capture_started_at
            ),
            "capture_finished_at": (
                capture_finished_at
            ),
            "diagnostics": dict(diagnostics),
        }

        return {
            "result_id": RESULT_ID,
            "explorer_id": explorer_id,
            "created_at": self.stored_result[
                "created_at"
            ],
        }

    def get_explorer_result(
        self,
        result_id: str,
    ) -> dict[str, Any]:
        if (
            result_id != RESULT_ID
            or self.stored_result is None
        ):
            raise ValueError(
                "Stored result was not found."
            )

        return dict(self.stored_result)

    def get_latest_explorer_result(
        self,
        explorer_id: str,
    ) -> dict[str, Any] | None:
        if (
            explorer_id != EXPLORER_ID
            or self.stored_result is None
        ):
            return None

        return dict(self.stored_result)

    def list_explorer_results(
        self,
        explorer_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if (
            explorer_id != EXPLORER_ID
            or self.stored_result is None
        ):
            return []

        keys = (
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

        return [
            {
                key: self.stored_result[key]
                for key in keys
            }
        ][:limit]


class FakeAutomatorClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def configured(self) -> bool:
        return True

    def create_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        self.calls.append("create")

        return self._run_result(
            "create_explorer",
            result_available=False,
        )

    def select_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        self.calls.append("select")

        return self._run_result(
            "select_explorer",
            result_available=False,
        )

    def run_selected_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        self.calls.append("run")

        return self._run_result(
            "run_selected_explorer",
            result_available=True,
        )

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        raise AssertionError(
            "Composite execution must not be used."
        )

    def read_results(
        self,
        request: AutomatorReadResultsRequest,
    ) -> AutomatorReadResultsResult:
        self.calls.append("read")

        verification = (
            AutomatorClipboardVerification(
                passed=True,
                expected_count=1,
                scraped_count=1,
                clipboard_count=1,
                missing_from_scrape=[],
                unexpected_in_scrape=[],
                clipboard_headers=[
                    "Instrument",
                    "A",
                ],
            )
        )

        results = AutomatorExplorerResults(
            schema_version="1.0",
            outcome="matches_found",
            expected_count=1,
            matched_count=1,
            has_matches=True,
            clipboard_verification=(
                verification
            ),
            rows=[
                AutomatorResultRow(
                    row_index=0,
                    instrument_name=(
                        "Test Instrument"
                    ),
                    symbol="TEST.SI",
                    column_values={
                        "A": "25.0",
                    },
                )
            ],
        )

        return AutomatorReadResultsResult(
            succeeded=True,
            message="Results read.",
            started_at="capture-start",
            finished_at="capture-finish",
            explorer_id=request.explorer_id,
            results=results,
            diagnostics={
                "boundary": "read_results",
            },
        )

    @staticmethod
    def _run_result(
        boundary: str,
        *,
        result_available: bool,
    ) -> AutomatorRunResult:
        return AutomatorRunResult(
            succeeded=True,
            message=f"{boundary} passed.",
            started_at="start",
            finished_at="finish",
            result_available=result_available,
            diagnostics={
                "boundary": boundary,
                "result_available": (
                    result_available
                ),
            },
        )


def test_complete_pre_ms10_tool_chain() -> None:
    rag_client = FakeRagClient()
    automator_client = FakeAutomatorClient()

    repository = ExplorerRepository(
        rag_client=rag_client
    )

    workflow = ExplorerReviewWorkflow(
        rag_client=rag_client,
        explorer_repository=repository,
    )

    registry = ToolRegistry(
        explorer_tool_service=(
            ExplorerToolService(
                review_workflow=workflow,
                explorer_repository=repository,
                automator_client=(
                    automator_client
                ),
            )
        ),
        result_tool_service=(
            MetaStockResultToolService(
                automator_client=(
                    automator_client
                ),
                result_client=rag_client,
            )
        ),
    )

    resolver = ExplorerNameResolver(
        rag_client
    )

    generated = registry.execute(
        "generate_explorer",
        {
            "user_query": (
                "Create an RSI Explorer."
            )
        },
    )

    assert generated.ok is True
    assert generated.data["assumptions"]
    assert generated.data["retrieved_refs"]
    assert generated.data["explorer"][
        "validation"
    ]["warnings"]

    explorer_id = (
        resolver.resolve_explorer_id(
            "  RSI Scanner  "
        )
    )

    run_arguments = {
        "explorer_id": explorer_id,
        "instruments": "all",
    }

    for tool_name in (
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
    ):
        result = registry.execute(
            tool_name,
            run_arguments,
        )
        assert result.ok is True

    captured = registry.execute(
        "read_metastock_explorer_results",
        {
            "explorer_id": explorer_id,
            "close_after_read": True,
        },
    )

    assert captured.ok is True
    assert captured.data["persisted"] is True
    assert captured.data["result_id"] == RESULT_ID

    exact = registry.execute(
        "get_explorer_result",
        {
            "result_id": RESULT_ID,
        },
    )

    latest = registry.execute(
        "get_latest_explorer_result",
        {
            "explorer_id": explorer_id,
        },
    )

    history = registry.execute(
        "list_explorer_results",
        {
            "explorer_id": explorer_id,
            "limit": 20,
        },
    )

    assert exact.ok is True
    assert exact.data["result"][
        "result_id"
    ] == RESULT_ID

    assert latest.ok is True
    assert latest.data["found"] is True

    assert history.ok is True
    assert history.data["count"] == 1

    assert automator_client.calls == [
        "create",
        "select",
        "run",
        "read",
    ]

    registered = {
        tool.name
        for tool in registry.list_tools()
    }

    assert {
        "read_metastock_explorer_results",
        "get_explorer_result",
        "get_latest_explorer_result",
        "list_explorer_results",
    } <= registered