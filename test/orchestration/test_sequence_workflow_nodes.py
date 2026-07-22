from chat.models import ChatContext
from orchestration.context_resolver import DecisionResolution
from orchestration.sequence_workflow_nodes import (
    ExecuteExplorerSequenceStepNode,
    PrepareExplorerSequenceNode,
)
from tools.tool_contracts import ToolResult, ToolStatus


class _Executor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.capture_count = 0

    def execute(self, tool_name: str, arguments: dict) -> ToolResult:
        self.calls.append((tool_name, arguments))
        data = {}
        if tool_name == "read_metastock_explorer_results":
            self.capture_count += 1
            data = {
                "result_id": (
                    f"00000000-0000-0000-0000-00000000000{self.capture_count}"
                ),
                "persisted": True,
                "succeeded": True,
                "results": {
                    "outcome": "matches_found",
                    "matched_count": self.capture_count * 3,
                    "has_matches": True,
                    "rows": [],
                },
            }
        return ToolResult(
            tool_name=tool_name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message=f"{tool_name} completed",
            data=data,
        )


class _NonPersistingCaptureExecutor(_Executor):
    def execute(self, tool_name: str, arguments: dict) -> ToolResult:
        if tool_name != "read_metastock_explorer_results":
            return super().execute(tool_name, arguments)

        self.calls.append((tool_name, arguments))
        return ToolResult(
            tool_name=tool_name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="Rows were read but were not persisted.",
            data={
                "result_id": None,
                "persisted": False,
                "succeeded": True,
                "results": {
                    "outcome": "matches_found",
                    "matched_count": 2,
                    "has_matches": True,
                    "rows": [],
                },
            },
        )


def _prepared_state() -> dict:
    resolution = DecisionResolution(
        outcome="sequence",
        route="execute_explorer_sequence",
        workflow_name="execute_explorer_sequence",
        arguments={
            "sequence": {
                "stages": [
                    {
                        "stage_index": 0,
                        "explorer_id": (
                            "11111111-1111-1111-1111-111111111111"
                        ),
                        "explorer_reference": "Explorer A",
                        "instruments": "Singapore Exchange",
                        "create_in_metastock": True,
                    },
                    {
                        "stage_index": 1,
                        "explorer_id": (
                            "22222222-2222-2222-2222-222222222222"
                        ),
                        "explorer_reference": "Explorer B",
                        "instruments": "NASDAQ",
                        "create_in_metastock": False,
                    },
                ],
                "stop_on_failure": True,
            }
        },
        decision_reason="test",
    )
    state = {
        "turn_input": {
            "user_message": "run sequence",
            "context": ChatContext().model_dump(mode="json"),
        },
        "resolution": resolution.model_dump(mode="json"),
    }
    state.update(PrepareExplorerSequenceNode()(state))
    return state


def test_sequence_node_runs_all_stages_and_returns_aggregate_result():
    state = _prepared_state()
    executor = _Executor()
    node = ExecuteExplorerSequenceStepNode(executor)

    for _ in range(20):
        state.update(node(state))
        if state.get("sequence_complete"):
            break

    assert state["sequence_complete"] is True
    assert state["sequence_succeeded"] is True
    assert [name for name, _ in executor.calls] == [
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]
    assert executor.calls[1][1]["instruments"] == "Singapore Exchange"
    assert executor.calls[5][1]["instruments"] == "NASDAQ"

    aggregate = state["workflow_results"][0]
    sequence = aggregate["data"]["sequence"]
    assert sequence["completed_stage_count"] == 2
    assert sequence["stages"][0]["matched_count"] == 3
    assert sequence["stages"][1]["matched_count"] == 6
    assert sequence["stages"][0]["persisted"] is True
    assert sequence["stages"][1]["persisted"] is True
    assert sequence["stages"][0]["outcome"] == "matches_found"


def test_sequence_does_not_start_next_stage_after_unpersisted_capture():
    state = _prepared_state()
    executor = _NonPersistingCaptureExecutor()
    node = ExecuteExplorerSequenceStepNode(executor)

    for _ in range(20):
        state.update(node(state))
        if state.get("sequence_complete"):
            break

    assert state["sequence_complete"] is True
    assert state["sequence_succeeded"] is False
    assert state["sequence_failed_stage_index"] == 0
    assert (
        state["sequence_failed_tool"]
        == "read_metastock_explorer_results"
    )
    assert [name for name, _ in executor.calls] == [
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]
