from __future__ import annotations

from chat.models import ChatContext
from chat.result_mapper import (
    update_context_from_tool_result,
)
from orchestration.context_resolver import (
    DecisionResolution,
)
from orchestration.registry_executor import (
    RegistryToolExecutor,
)
from orchestration.state import MetaStockGraphState
from orchestration.workflows import (
    StaticWorkflowCatalog,
    WorkflowPlan,
)
from tools.tool_contracts import ToolStatus


class PrepareConversationWorkflowNode:
    """Prepare a normalized command workflow and retain validated arguments."""

    def __init__(
        self,
        catalog: StaticWorkflowCatalog,
    ) -> None:
        self._catalog = catalog

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        turn_input = state.get("turn_input") or {}
        resolution = DecisionResolution.model_validate(
            state.get("resolution")
        )

        if (
            resolution.outcome != "workflow"
            or not resolution.workflow_name
        ):
            raise RuntimeError(
                "PrepareConversationWorkflowNode received "
                "a non-workflow resolution."
            )

        explorer_id_value = resolution.arguments.get(
            "explorer_id"
        )
        explorer_id = (
            str(explorer_id_value).strip()
            if explorer_id_value
            else None
        )
        workflow_arguments = {
            key: value
            for key, value
            in resolution.arguments.items()
            if key != "explorer_id"
        }
        plan = self._catalog.prepare(
            workflow_name=resolution.workflow_name,
            explorer_id=explorer_id,
            workflow_arguments=workflow_arguments,
        )
        context = (
            turn_input.get("context")
            if isinstance(turn_input, dict)
            else {}
        ) or {}

        return {
            "workflow_plan": plan.model_dump(
                mode="json"
            ),
            "workflow_index": 0,
            "workflow_results": [],
            "workflow_context": dict(context),
            "workflow_complete": False,
            "workflow_succeeded": False,
            "workflow_failed_tool": None,
        }


class ExecuteConversationWorkflowStepNode:
    """
    Execute one compiled step through ToolRegistry.

    `active` Explorer sourcing carries a newly generated, revised, or repaired
    Explorer ID into every later MetaStock step.
    """

    def __init__(
        self,
        executor: RegistryToolExecutor,
    ) -> None:
        self._executor = executor

    def __call__(
        self,
        state: MetaStockGraphState,
    ) -> MetaStockGraphState:
        plan = WorkflowPlan.model_validate(
            state.get("workflow_plan")
        )
        index = int(
            state.get("workflow_index", 0)
        )

        if index < 0 or index >= len(plan.steps):
            raise RuntimeError(
                "Workflow step index is out of bounds."
            )

        context = ChatContext.model_validate(
            state.get("workflow_context") or {}
        )
        previous_results = list(
            state.get("workflow_results") or []
        )
        step = plan.steps[index]
        arguments: dict[str, object] = {}

        if step.explorer_source == "active":
            explorer_id = (
                context.active_explorer_id
                or plan.explorer_id
            )

            if not explorer_id:
                raise RuntimeError(
                    "The workflow has no active Explorer ID for "
                    f"step {step.tool_name}."
                )

            arguments["explorer_id"] = explorer_id

        elif step.explorer_source == "original":
            if not plan.explorer_id:
                raise RuntimeError(
                    "The workflow has no source Explorer ID for "
                    f"step {step.tool_name}."
                )

            arguments["explorer_id"] = plan.explorer_id

        for (
            tool_argument,
            workflow_argument,
        ) in step.argument_bindings.items():
            if workflow_argument not in plan.workflow_arguments:
                raise RuntimeError(
                    "Workflow argument is missing: "
                    f"{workflow_argument}"
                )

            value = plan.workflow_arguments[
                workflow_argument
            ]

            if value is None:
                raise RuntimeError(
                    "Workflow argument cannot be null: "
                    f"{workflow_argument}"
                )

            arguments[tool_argument] = value

        arguments.update(step.argument_overrides)

        if step.tool_name == "read_metastock_explorer_results":
            run_started_at = _find_prior_run_started_at(
                previous_results
            )
            if run_started_at:
                arguments["run_started_at"] = run_started_at

            external_name = _external_name_from_reference(
                arguments.get("explorer_id")
            )
            if external_name:
                arguments["explorer_name"] = external_name

        result = self._executor.execute(
            step.tool_name,
            arguments,
        )
        next_context = update_context_from_tool_result(
            context,
            result,
        )
        next_results = [
            *previous_results,
            result.model_dump(mode="json"),
        ]
        next_index = index + 1
        step_succeeded = (
            result.ok
            and result.status is ToolStatus.SUCCESS
        )
        workflow_complete = (
            not step_succeeded
            or next_index >= len(plan.steps)
        )

        return {
            "workflow_index": next_index,
            "workflow_results": next_results,
            "workflow_context": (
                next_context.model_dump(mode="json")
            ),
            "workflow_complete": workflow_complete,
            "workflow_succeeded": (
                step_succeeded
                and next_index >= len(plan.steps)
            ),
            "workflow_failed_tool": (
                None
                if step_succeeded
                else step.tool_name
            ),
        }


def _find_prior_run_started_at(
    previous_results: list[dict[str, object]],
) -> str | None:
    for raw_result in reversed(previous_results):
        if not isinstance(raw_result, dict):
            continue
        if raw_result.get("tool_name") != (
            "run_selected_explorer_in_metastock"
        ):
            continue
        data = raw_result.get("data")
        if not isinstance(data, dict):
            continue
        started_at = str(data.get("started_at") or "").strip()
        if started_at:
            return started_at
    return None


def _external_name_from_reference(
    value: object,
) -> str | None:
    reference = str(value or "").strip()
    prefix = "metastock-name:"
    if not reference.startswith(prefix):
        return None
    name = reference[len(prefix):].strip()
    return name or None
