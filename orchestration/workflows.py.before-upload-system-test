from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from chat.routes import ChatRoute
from orchestration.command_resolution import (
    ArtifactAction,
    MetaStockAction,
    NormalizedExplorerCommand,
    ResultAction,
)


MAX_WORKFLOW_STEPS = 5
ExplorerSource = Literal[
    "none",
    "original",
    "active",
]


class WorkflowStep(BaseModel):
    tool_name: str
    explorer_source: ExplorerSource = "original"
    argument_overrides: dict[str, Any] = Field(
        default_factory=dict
    )

    # tool_argument -> workflow_argument
    argument_bindings: dict[str, str] = Field(
        default_factory=dict
    )


class WorkflowPlan(BaseModel):
    workflow_name: str
    route: ChatRoute
    explorer_id: str | None = None
    steps: list[WorkflowStep] = Field(
        min_length=1,
        max_length=MAX_WORKFLOW_STEPS,
    )
    workflow_arguments: dict[str, Any] = Field(
        default_factory=dict
    )


class UnknownWorkflowError(ValueError):
    pass


class StaticWorkflowCatalog:
    """
    Compile normalized semantic commands into bounded static tool sequences.

    The conversation model never supplies tool names or step ordering. It emits
    independent intent dimensions, and this compiler chooses the only approved
    sequence for that combination.
    """

    LEGACY_WORKFLOWS = {
        "run_explorer",
        "run_and_capture",
        "create_run_and_capture",
        "revise_and_run",
    }

    def list_workflows(self) -> list[str]:
        # Retained for legacy tests and deterministic fallback compatibility.
        # The production conversation model receives one semantic command
        # function instead of this overlapping workflow list.
        return sorted(self.LEGACY_WORKFLOWS)

    def prepare(
        self,
        *,
        workflow_name: str,
        explorer_id: str | None = None,
        workflow_arguments: dict[str, Any] | None = None,
    ) -> WorkflowPlan:
        arguments = dict(
            workflow_arguments or {}
        )
        raw_command = arguments.get("command")

        if raw_command is not None:
            command = (
                NormalizedExplorerCommand
                .model_validate(raw_command)
            )
            return self._compile(
                command=command,
                explorer_id=explorer_id,
            )

        command = self._legacy_command(
            workflow_name=workflow_name,
            arguments=arguments,
        )

        return self._compile(
            command=command,
            explorer_id=explorer_id,
        )

    def _compile(
        self,
        *,
        command: NormalizedExplorerCommand,
        explorer_id: str | None,
    ) -> WorkflowPlan:
        if command.needs_source_explorer and not explorer_id:
            raise ValueError(
                "This workflow requires a source Explorer ID."
            )

        steps: list[WorkflowStep] = []
        downstream_source: ExplorerSource = "original"

        if command.artifact_action is ArtifactAction.GENERATE:
            steps.append(
                WorkflowStep(
                    tool_name="generate_explorer",
                    explorer_source="none",
                    argument_bindings={
                        "user_query": (
                            "resolved_instruction"
                        )
                    },
                )
            )
            downstream_source = "active"

        elif command.artifact_action is ArtifactAction.REVISE:
            steps.append(
                WorkflowStep(
                    tool_name="revise_explorer",
                    explorer_source="original",
                    argument_bindings={
                        "revision_instruction": (
                            "resolved_instruction"
                        )
                    },
                )
            )
            downstream_source = "active"

        elif command.artifact_action is ArtifactAction.REPAIR:
            steps.append(
                WorkflowStep(
                    tool_name="repair_explorer",
                    explorer_source="original",
                    argument_bindings={
                        "repair_instruction": (
                            "resolved_instruction"
                        )
                    },
                )
            )
            downstream_source = "active"

        if command.metastock_action in {
            MetaStockAction.CREATE,
            MetaStockAction.CREATE_AND_RUN,
        }:
            steps.append(
                self._metastock_step(
                    "create_explorer_in_metastock",
                    explorer_source=downstream_source,
                )
            )

        if command.metastock_action in {
            MetaStockAction.RUN,
            MetaStockAction.CREATE_AND_RUN,
        }:
            steps.extend(
                [
                    self._metastock_step(
                        "select_explorer_in_metastock",
                        explorer_source=downstream_source,
                    ),
                    self._metastock_step(
                        "run_selected_explorer_in_metastock",
                        explorer_source=downstream_source,
                    ),
                ]
            )

        if command.result_action is ResultAction.CAPTURE_NEW:
            steps.append(
                WorkflowStep(
                    tool_name=(
                        "read_metastock_explorer_results"
                    ),
                    explorer_source=downstream_source,
                    argument_overrides={
                        "close_after_read": True
                    },
                )
            )

        if not steps:
            raise ValueError(
                "The normalized command compiled to no steps."
            )

        if len(steps) > MAX_WORKFLOW_STEPS:
            raise ValueError(
                f"Workflow {command.workflow_name!r} exceeds "
                f"{MAX_WORKFLOW_STEPS} steps."
            )

        return WorkflowPlan(
            workflow_name=command.workflow_name,
            route=command.route,
            explorer_id=explorer_id,
            steps=steps,
            workflow_arguments={
                "resolved_instruction": (
                    command.resolved_instruction
                ),
                "instruments": command.instruments,
            },
        )

    @staticmethod
    def _metastock_step(
        tool_name: str,
        *,
        explorer_source: ExplorerSource,
    ) -> WorkflowStep:
        return WorkflowStep(
            tool_name=tool_name,
            explorer_source=explorer_source,
            argument_bindings={
                "instruments": "instruments"
            },
        )

    @staticmethod
    def _legacy_command(
        *,
        workflow_name: str,
        arguments: dict[str, Any],
    ) -> NormalizedExplorerCommand:
        instruction = arguments.get(
            "revision_instruction"
        )

        mapping = {
            "run_explorer": NormalizedExplorerCommand(
                artifact_action="none",
                metastock_action="run",
                result_action="none",
                instruments=str(
                    arguments.get("instruments")
                    or "all"
                ),
            ),
            "run_and_capture": NormalizedExplorerCommand(
                artifact_action="none",
                metastock_action="run",
                result_action="capture_new",
                instruments=str(
                    arguments.get("instruments")
                    or "all"
                ),
            ),
            "create_run_and_capture": (
                NormalizedExplorerCommand(
                    artifact_action="none",
                    metastock_action=(
                        "create_and_run"
                    ),
                    result_action="capture_new",
                    instruments=str(
                        arguments.get("instruments")
                        or "all"
                    ),
                )
            ),
            "revise_and_run": NormalizedExplorerCommand(
                artifact_action="revise",
                resolved_instruction=(
                    str(instruction).strip()
                    if instruction
                    else "Revise the current Explorer."
                ),
                metastock_action="create_and_run",
                result_action="none",
                instruments=str(
                    arguments.get("instruments")
                    or "all"
                ),
            ),
        }

        try:
            return mapping[workflow_name]
        except KeyError as exc:
            raise UnknownWorkflowError(
                f"Unknown workflow: {workflow_name}"
            ) from exc
