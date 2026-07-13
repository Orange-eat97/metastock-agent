from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agent_workflows.explorer_review_workflow import (
    ExplorerReviewWorkflow,
)
from services.rag_client import (
    LocalRagClient,
    RagGenerateResult,
)
from tools.explorer_tools import (
    ExplorerToolService,
)
from tools.tool_contracts import (
    GenerateExplorerInput,
    ToolStatus,
)


class FakeRetrievedRef:
    def model_dump(
        self,
        *,
        mode: str,
    ) -> dict[str, Any]:
        assert mode == "json"

        return {
            "key": "function.rsi",
            "table_title": "rag_cards",
            "rag_score": 0.91,
            "retrieval_reason": (
                "RSI is required by the query."
            ),
        }


class FakeGenerateService:
    def generate_explorer(
        self,
        user_message: str,
    ) -> Any:
        assert user_message == "RSI test"

        return SimpleNamespace(
            explorer="explorer-1",
            explorer_created_at="created",
            service_log="log-1",
            service_log_created_at=(
                "log-created"
            ),
            assumptions=[
                "RSI uses a 14-period lookback."
            ],
            retrieved_refs=[
                FakeRetrievedRef()
            ],
            validation=SimpleNamespace(
                passed=True,
                errors=[],
                warnings=[
                    "Threshold is configurable."
                ],
            ),
            source="generated",
        )


class FakeRepository:
    def get_explorer(
        self,
        explorer_id: str,
    ) -> dict[str, Any]:
        return {
            "id": explorer_id,
            "created_at": "created",
            "explorer_name": "RSI Test",
            "explorer_description": (
                "RSI test Explorer."
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
        }

    def get_service_log(
        self,
        log_id: str,
    ) -> dict[str, Any]:
        return {
            "log_id": log_id,
            "stdout_text": "",
            "stderr_text": "",
            "metadata": {},
        }


def test_local_rag_client_preserves_metadata() -> None:
    client = object.__new__(
        LocalRagClient
    )
    client._generate_service = (
        FakeGenerateService()
    )

    result = client.generate_explorer(
        "RSI test"
    )

    assert result.assumptions == [
        "RSI uses a 14-period lookback."
    ]
    assert result.validation_warnings == [
        "Threshold is configurable."
    ]
    assert result.retrieved_refs == [
        {
            "key": "function.rsi",
            "table_title": "rag_cards",
            "rag_score": 0.91,
            "retrieval_reason": (
                "RSI is required by the query."
            ),
        }
    ]


class StaticRagClient:
    def generate_explorer(
        self,
        user_query: str,
    ) -> RagGenerateResult:
        assert user_query == "RSI test"

        return RagGenerateResult(
            explorer="explorer-1",
            explorer_created_at="created",
            service_log="log-1",
            service_log_created_at=(
                "log-created"
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
                    "rag_score": 0.91,
                    "retrieval_reason": (
                        "RSI is required by the "
                        "query."
                    ),
                }
            ],
            validation_warnings=[
                "Threshold is configurable."
            ],
        )


def test_tool_result_preserves_metadata() -> None:
    repository = FakeRepository()

    workflow = ExplorerReviewWorkflow(
        rag_client=StaticRagClient(),
        explorer_repository=repository,
    )

    service = ExplorerToolService(
        review_workflow=workflow,
        explorer_repository=repository,
    )

    result = service.generate_explorer(
        GenerateExplorerInput(
            user_query="RSI test"
        )
    )

    assert result.ok is True
    assert result.status is ToolStatus.SUCCESS

    assert result.data["assumptions"] == [
        "RSI uses a 14-period lookback."
    ]

    assert (
        result.data["retrieved_refs"][0][
            "key"
        ]
        == "function.rsi"
    )

    explorer = result.data["explorer"]

    assert explorer["source"] == "generated"
    assert (
        explorer["service_log_id"]
        == "log-1"
    )
    assert explorer["validation"][
        "warnings"
    ] == [
        "Threshold is configurable."
    ]
