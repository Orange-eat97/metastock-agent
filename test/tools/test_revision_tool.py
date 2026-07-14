from __future__ import annotations

from agent_workflows.explorer_review_workflow import (
    ExplorerReviewState,
)
from tools.explorer_tools import (
    ExplorerToolService,
)
from tools.tool_contracts import (
    ReviseExplorerInput,
    ToolStatus,
)


ORIGINAL_ID = (
    "11111111-1111-4111-8111-"
    "111111111111"
)
REVISED_ID = (
    "22222222-2222-4222-8222-"
    "222222222222"
)


class FakeWorkflow:
    def __init__(self) -> None:
        self.calls = []

    def revise_for_review(
        self,
        explorer_id: str,
        revision_instruction: str,
    ) -> ExplorerReviewState:
        self.calls.append(
            (
                explorer_id,
                revision_instruction,
            )
        )
        return ExplorerReviewState(
            explorer_id=REVISED_ID,
            explorer_created_at="created",
            service_log_id="log-1",
            service_log_created_at="logged",
            explorer_row={
                "id": REVISED_ID,
                "created_at": "created",
                "explorer_name": "RSI Below 25 Above SMA50",
                "explorer_description": "Revised threshold only.",
                "explorer_code_body": (
                    "ColB < 25 AND ColA > ColC"
                ),
                "col_definitions": [
                    {
                        "col_letter": "A",
                        "col_code": "C",
                    },
                    {
                        "col_letter": "B",
                        "col_code": "RSI(14)",
                    },
                    {
                        "col_letter": "C",
                        "col_code": "Mov(C,50,S)",
                    },
                ],
                "validation_passed": True,
                "validation_errors": [],
            },
            service_log_row=None,
            validation_passed=True,
            validation_errors=[],
            can_run_in_metastock=True,
            can_repair=False,
            source="revision",
        )


class FakeRepository:
    pass


def test_revision_tool_returns_new_explorer() -> None:
    workflow = FakeWorkflow()
    service = ExplorerToolService(
        review_workflow=workflow,
        explorer_repository=FakeRepository(),
    )

    result = service.revise_explorer(
        ReviseExplorerInput(
            explorer_id=ORIGINAL_ID,
            revision_instruction=(
                "Use 25 instead of 30."
            ),
        )
    )

    assert result.ok is True
    assert result.status is ToolStatus.SUCCESS
    assert workflow.calls == [
        (
            ORIGINAL_ID,
            "Use 25 instead of 30.",
        )
    ]
    assert result.data[
        "revised_from_explorer_id"
    ] == ORIGINAL_ID
    explorer = result.data["explorer"]
    assert explorer["explorer_id"] == REVISED_ID
    assert (
        explorer["filter_code"]
        == "ColB < 25 AND ColA > ColC"
    )
    assert any(
        column["col_code"] == "Mov(C,50,S)"
        for column in explorer["columns"]
    )
