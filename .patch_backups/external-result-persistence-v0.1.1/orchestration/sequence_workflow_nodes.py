from __future__ import annotations

from typing import Any

from chat.models import ChatContext
from chat.result_mapper import update_context_from_tool_result
from orchestration.context_resolver import DecisionResolution
from orchestration.registry_executor import RegistryToolExecutor
from orchestration.sequence_workflows import (
    ExplorerSequenceCatalog,
    ExplorerSequencePlan,
    ExplorerSequenceRunResult,
    ExplorerSequenceStagePlan,
    ExplorerSequenceStageResult,
    ResolvedExplorerSequenceRequest,
)
from orchestration.state import MetaStockGraphState
from tools.tool_contracts import (
    ToolDisplay,
    ToolError,
    ToolResult,
    ToolStatus,
)


RESULT_CAPTURE_TOOL_NAME = "read_metastock_explorer_results"


class PrepareExplorerSequenceNode:
    """Prepare all stages before the first MetaStock side effect occurs."""

    def __init__(
        self,
        catalog: ExplorerSequenceCatalog | None = None,
    ) -> None:
        self._catalog = catalog or ExplorerSequenceCatalog()

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        turn_input = state.get("turn_input") or {}
        resolution = DecisionResolution.model_validate(
            state.get("resolution")
        )

        if resolution.outcome != "sequence":
            raise RuntimeError(
                "PrepareExplorerSequenceNode received a non-sequence "
                "resolution."
            )

        raw_sequence = resolution.arguments.get("sequence")
        resolved = ResolvedExplorerSequenceRequest.model_validate(
            raw_sequence
        )
        plan = self._catalog.prepare(resolved)
        context = (
            turn_input.get("context")
            if isinstance(turn_input, dict)
            else {}
        ) or {}

        return {
            "sequence_plan": plan.model_dump(mode="json"),
            "sequence_stage_index": 0,
            "sequence_step_index": 0,
            "sequence_stage_results": [],
            "sequence_current_results": [],
            "sequence_context": dict(context),
            "sequence_complete": False,
            "sequence_succeeded": False,
            "sequence_failed_stage_index": None,
            "sequence_failed_tool": None,
            # Keep the established response-composition path active.
            "workflow_plan": {
                "workflow_name": "execute_explorer_sequence"
            },
            "workflow_results": [],
            "workflow_context": dict(context),
            "workflow_complete": False,
            "workflow_succeeded": False,
            "workflow_failed_tool": None,
        }


class ExecuteExplorerSequenceStepNode:
    """Execute one tool call in the current stage, then advance safely."""

    def __init__(
        self,
        executor: RegistryToolExecutor,
    ) -> None:
        self._executor = executor

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        plan = ExplorerSequencePlan.model_validate(
            state.get("sequence_plan")
        )
        stage_index = int(state.get("sequence_stage_index", 0))
        step_index = int(state.get("sequence_step_index", 0))

        if stage_index < 0 or stage_index >= len(plan.stages):
            raise RuntimeError("Explorer sequence stage index is out of bounds.")

        stage = plan.stages[stage_index]
        workflow = stage.workflow_plan

        if step_index < 0 or step_index >= len(workflow.steps):
            raise RuntimeError("Explorer sequence step index is out of bounds.")

        context = ChatContext.model_validate(
            state.get("sequence_context") or {}
        )
        prior_stage_results = [
            ExplorerSequenceStageResult.model_validate(value)
            for value in (state.get("sequence_stage_results") or [])
        ]
        current_results = [
            ToolResult.model_validate(value)
            for value in (state.get("sequence_current_results") or [])
        ]
        step = workflow.steps[step_index]
        arguments = _build_step_arguments(
            stage=stage,
            context=context,
            step=step,
        )

        result = self._executor.execute(step.tool_name, arguments)
        next_context = update_context_from_tool_result(
            context,
            result,
        )
        next_current_results = [*current_results, result]
        step_succeeded = _step_completed_successfully(
            tool_name=step.tool_name,
            result=result,
        )

        if not step_succeeded:
            stage_result = _summarize_stage(
                stage,
                next_current_results,
                succeeded=False,
                failed_tool=step.tool_name,
            )
            all_stage_results = [
                *prior_stage_results,
                stage_result,
            ]
            aggregate = _build_aggregate_result(
                plan,
                all_stage_results,
                succeeded=False,
                failed_stage_index=stage_index,
                failed_tool=step.tool_name,
            )
            return _complete_state(
                context=next_context,
                aggregate=aggregate,
                stage_results=all_stage_results,
                failed_stage_index=stage_index,
                failed_tool=step.tool_name,
            )

        next_step_index = step_index + 1
        stage_complete = next_step_index >= len(workflow.steps)

        if not stage_complete:
            return {
                "sequence_step_index": next_step_index,
                "sequence_current_results": [
                    item.model_dump(mode="json")
                    for item in next_current_results
                ],
                "sequence_context": next_context.model_dump(mode="json"),
                "workflow_context": next_context.model_dump(mode="json"),
            }

        stage_result = _summarize_stage(
            stage,
            next_current_results,
            succeeded=True,
            failed_tool=None,
        )
        all_stage_results = [
            *prior_stage_results,
            stage_result,
        ]
        next_stage_index = stage_index + 1
        sequence_complete = next_stage_index >= len(plan.stages)

        if sequence_complete:
            aggregate = _build_aggregate_result(
                plan,
                all_stage_results,
                succeeded=True,
                failed_stage_index=None,
                failed_tool=None,
            )
            return _complete_state(
                context=next_context,
                aggregate=aggregate,
                stage_results=all_stage_results,
                failed_stage_index=None,
                failed_tool=None,
            )

        return {
            "sequence_stage_index": next_stage_index,
            "sequence_step_index": 0,
            "sequence_stage_results": [
                item.model_dump(mode="json")
                for item in all_stage_results
            ],
            "sequence_current_results": [],
            "sequence_context": next_context.model_dump(mode="json"),
            "workflow_context": next_context.model_dump(mode="json"),
        }


def route_after_sequence_step(
    state: MetaStockGraphState,
) -> str:
    return (
        "compose"
        if bool(state.get("sequence_complete", False))
        else "continue"
    )


def _step_completed_successfully(
    *,
    tool_name: str,
    result: ToolResult,
) -> bool:
    if not (
        result.ok
        and result.status is ToolStatus.SUCCESS
    ):
        return False

    if tool_name != RESULT_CAPTURE_TOOL_NAME:
        return True

    # release-v0.1.1's result tool defines success as read + normalize +
    # clipboard verification + Supabase persistence. Keep that contract
    # explicit here so the next Explorer cannot start after a partial read.
    data = result.data
    result_id = str(data.get("result_id") or "").strip()
    return (
        data.get("succeeded") is True
        and data.get("persisted") is True
        and bool(result_id)
        and isinstance(data.get("results"), dict)
    )


def _build_step_arguments(
    *,
    stage: ExplorerSequenceStagePlan,
    context: ChatContext,
    step: Any,
) -> dict[str, object]:
    workflow = stage.workflow_plan
    arguments: dict[str, object] = {}

    if step.explorer_source == "active":
        explorer_id = context.active_explorer_id or workflow.explorer_id
        if not explorer_id:
            raise RuntimeError(
                "The sequence stage has no active Explorer ID for "
                f"step {step.tool_name}."
            )
        arguments["explorer_id"] = explorer_id
    elif step.explorer_source == "original":
        if not workflow.explorer_id:
            raise RuntimeError(
                "The sequence stage has no source Explorer ID for "
                f"step {step.tool_name}."
            )
        arguments["explorer_id"] = workflow.explorer_id

    for tool_argument, workflow_argument in (
        step.argument_bindings.items()
    ):
        if workflow_argument not in workflow.workflow_arguments:
            raise RuntimeError(
                "Sequence workflow argument is missing: "
                f"{workflow_argument}"
            )
        value = workflow.workflow_arguments[workflow_argument]
        if value is None:
            raise RuntimeError(
                "Sequence workflow argument cannot be null: "
                f"{workflow_argument}"
            )
        arguments[tool_argument] = value

    arguments.update(step.argument_overrides)
    return arguments


def _summarize_stage(
    stage: ExplorerSequenceStagePlan,
    results: list[ToolResult],
    *,
    succeeded: bool,
    failed_tool: str | None,
) -> ExplorerSequenceStageResult:
    payloads = [result.data for result in results]
    result_id = _find_first_key(payloads, "result_id")
    persisted = _find_first_key(payloads, "persisted") is True
    outcome = _find_first_key(payloads, "outcome")
    has_matches = _find_first_key(payloads, "has_matches")
    matched_count = _find_first_key(payloads, "matched_count")
    last_message = (
        results[-1].message
        if results
        else "No tool result was produced."
    )

    return ExplorerSequenceStageResult(
        stage_index=stage.stage_index,
        explorer_id=stage.explorer_id,
        explorer_reference=stage.explorer_reference,
        instruments=stage.instruments,
        create_in_metastock=stage.create_in_metastock,
        succeeded=succeeded,
        failed_tool=failed_tool,
        result_id=(str(result_id) if result_id else None),
        persisted=persisted,
        outcome=(
            str(outcome)
            if outcome in {"matches_found", "no_matches"}
            else None
        ),
        has_matches=(
            has_matches
            if isinstance(has_matches, bool)
            else None
        ),
        matched_count=(
            int(matched_count)
            if isinstance(matched_count, (int, float, str))
            and str(matched_count).strip().isdigit()
            else None
        ),
        message=last_message,
    )


def _find_first_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value and value[key] is not None:
            return value[key]
        for nested in value.values():
            found = _find_first_key(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_first_key(nested, key)
            if found is not None:
                return found
    return None


def _build_aggregate_result(
    plan: ExplorerSequencePlan,
    stage_results: list[ExplorerSequenceStageResult],
    *,
    succeeded: bool,
    failed_stage_index: int | None,
    failed_tool: str | None,
) -> ToolResult:
    completed = sum(1 for item in stage_results if item.succeeded)
    run_result = ExplorerSequenceRunResult(
        succeeded=succeeded,
        total_stage_count=len(plan.stages),
        attempted_stage_count=len(stage_results),
        completed_stage_count=completed,
        failed_stage_index=failed_stage_index,
        failed_tool=failed_tool,
        stages=stage_results,
    )
    message = (
        f"Explorer sequence completed {completed}/{len(plan.stages)} stages."
        if succeeded
        else (
            "Explorer sequence stopped at stage "
            f"{(failed_stage_index or 0) + 1} during {failed_tool}."
        )
    )
    markdown_lines = [message, ""]
    for item in stage_results:
        status = "completed" if item.succeeded else "failed"
        detail = (
            f"result `{item.result_id}`"
            if item.result_id
            else "no stored result ID"
        )
        if item.matched_count is not None:
            detail += f", {item.matched_count} matches"
        detail += ", persisted" if item.persisted else ", not persisted"
        markdown_lines.append(
            f"- Stage {item.stage_index + 1}: "
            f"**{item.explorer_reference}** on "
            f"`{item.instruments}` — {status}; {detail}."
        )

    return ToolResult(
        tool_name="execute_explorer_sequence",
        ok=succeeded,
        status=(ToolStatus.SUCCESS if succeeded else ToolStatus.FAILED),
        message=message,
        data={
            "sequence": run_result.model_dump(mode="json"),
        },
        display=ToolDisplay(
            title=(
                "Explorer sequence complete"
                if succeeded
                else "Explorer sequence failed"
            ),
            markdown="\n".join(markdown_lines),
            severity=("success" if succeeded else "error"),
        ),
        error=(
            None
            if succeeded
            else ToolError(
                code="EXPLORER_SEQUENCE_FAILED",
                message=message,
                details={
                    "failed_stage_index": failed_stage_index,
                    "failed_tool": failed_tool,
                },
            )
        ),
    )


def _complete_state(
    *,
    context: ChatContext,
    aggregate: ToolResult,
    stage_results: list[ExplorerSequenceStageResult],
    failed_stage_index: int | None,
    failed_tool: str | None,
) -> MetaStockGraphState:
    succeeded = aggregate.ok and aggregate.status is ToolStatus.SUCCESS
    return {
        "sequence_stage_results": [
            item.model_dump(mode="json")
            for item in stage_results
        ],
        "sequence_current_results": [],
        "sequence_context": context.model_dump(mode="json"),
        "sequence_complete": True,
        "sequence_succeeded": succeeded,
        "sequence_failed_stage_index": failed_stage_index,
        "sequence_failed_tool": failed_tool,
        "workflow_results": [aggregate.model_dump(mode="json")],
        "workflow_context": context.model_dump(mode="json"),
        "workflow_complete": True,
        "workflow_succeeded": succeeded,
        "workflow_failed_tool": failed_tool,
    }
