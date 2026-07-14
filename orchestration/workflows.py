from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from chat.routes import ChatRoute


MAX_WORKFLOW_STEPS = 4


class WorkflowStep(BaseModel):
    tool_name: str
    argument_overrides: dict[str, Any] = Field(
        default_factory=dict
    )


class WorkflowPlan(BaseModel):
    workflow_name: str
    route: ChatRoute
    explorer_id: str
    steps: list[WorkflowStep] = Field(
        min_length=1,
        max_length=MAX_WORKFLOW_STEPS,
    )


class UnknownWorkflowError(ValueError):
    pass


class StaticWorkflowCatalog:
    """
    Approved sequential workflows for MS10.5.

    These definitions contain no planner-generated tool names. Every step is
    static, bounded, and executed through ToolRegistry.
    """

    def __init__(self) -> None:
        self._definitions: dict[
            str,
            tuple[ChatRoute, list[WorkflowStep]],
        ] = {
            "run_explorer": (
                ChatRoute.RUN_EXPLORER,
                [
                    WorkflowStep(
                        tool_name=(
                            "select_explorer_in_metastock"
                        ),
                        argument_overrides={
                            "instruments": "all"
                        },
                    ),
                    WorkflowStep(
                        tool_name=(
                            "run_selected_explorer_in_metastock"
                        ),
                        argument_overrides={
                            "instruments": "all"
                        },
                    ),
                ],
            ),
            "run_and_capture": (
                ChatRoute.RUN_AND_READ_EXPLORER,
                [
                    WorkflowStep(
                        tool_name=(
                            "select_explorer_in_metastock"
                        ),
                        argument_overrides={
                            "instruments": "all"
                        },
                    ),
                    WorkflowStep(
                        tool_name=(
                            "run_selected_explorer_in_metastock"
                        ),
                        argument_overrides={
                            "instruments": "all"
                        },
                    ),
                    WorkflowStep(
                        tool_name=(
                            "read_metastock_explorer_results"
                        ),
                        argument_overrides={
                            "close_after_read": True
                        },
                    ),
                ],
            ),
            "create_run_and_capture": (
                (
                    ChatRoute
                    .CREATE_RUN_AND_READ_EXPLORER
                ),
                [
                    WorkflowStep(
                        tool_name=(
                            "create_explorer_in_metastock"
                        ),
                        argument_overrides={
                            "instruments": "all"
                        },
                    ),
                    WorkflowStep(
                        tool_name=(
                            "select_explorer_in_metastock"
                        ),
                        argument_overrides={
                            "instruments": "all"
                        },
                    ),
                    WorkflowStep(
                        tool_name=(
                            "run_selected_explorer_in_metastock"
                        ),
                        argument_overrides={
                            "instruments": "all"
                        },
                    ),
                    WorkflowStep(
                        tool_name=(
                            "read_metastock_explorer_results"
                        ),
                        argument_overrides={
                            "close_after_read": True
                        },
                    ),
                ],
            ),
        }

        for name, (_, steps) in (
            self._definitions.items()
        ):
            if len(steps) > MAX_WORKFLOW_STEPS:
                raise ValueError(
                    f"Workflow {name!r} exceeds "
                    f"{MAX_WORKFLOW_STEPS} steps."
                )

    def list_workflows(self) -> list[str]:
        return sorted(self._definitions)

    def prepare(
        self,
        *,
        workflow_name: str,
        explorer_id: str,
    ) -> WorkflowPlan:
        definition = self._definitions.get(
            workflow_name
        )

        if definition is None:
            raise UnknownWorkflowError(
                f"Unknown workflow: {workflow_name}"
            )

        route, steps = definition

        return WorkflowPlan(
            workflow_name=workflow_name,
            route=route,
            explorer_id=explorer_id,
            steps=[
                step.model_copy(deep=True)
                for step in steps
            ],
        )
