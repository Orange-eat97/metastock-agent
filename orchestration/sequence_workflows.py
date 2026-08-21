from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from orchestration.workflows import StaticWorkflowCatalog, WorkflowPlan


MAX_EXPLORER_SEQUENCE_STAGES = 10


class ExplorerSequenceStageRequest(BaseModel):
    """One user-requested Explorer run inside a deterministic sequence."""

    explorer_reference: str = Field(min_length=1)
    instruments: str = "all"
    create_in_metastock: bool = False

    @field_validator("explorer_reference", mode="before")
    @classmethod
    def clean_reference(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("instruments", mode="before")
    @classmethod
    def clean_instruments(cls, value: object) -> str:
        cleaned = str(value or "all").strip()
        return cleaned or "all"


class ExplorerSequenceRequest(BaseModel):
    stages: list[ExplorerSequenceStageRequest] = Field(
        min_length=1,
        max_length=MAX_EXPLORER_SEQUENCE_STAGES,
    )
    stop_on_failure: bool = True

    @model_validator(mode="after")
    def require_stop_on_failure(self) -> "ExplorerSequenceRequest":
        if not self.stop_on_failure:
            raise ValueError(
                "Explorer sequences currently require stop_on_failure=true."
            )
        return self


class ResolvedExplorerSequenceStage(BaseModel):
    stage_index: int = Field(ge=0)
    explorer_id: str = Field(min_length=1)
    explorer_reference: str = Field(min_length=1)
    instruments: str = "all"
    create_in_metastock: bool = False


class ResolvedExplorerSequenceRequest(BaseModel):
    stages: list[ResolvedExplorerSequenceStage] = Field(
        min_length=1,
        max_length=MAX_EXPLORER_SEQUENCE_STAGES,
    )
    stop_on_failure: Literal[True] = True


class ExplorerSequenceStagePlan(BaseModel):
    stage_index: int = Field(ge=0)
    explorer_id: str = Field(min_length=1)
    explorer_reference: str = Field(min_length=1)
    instruments: str = "all"
    create_in_metastock: bool = False
    workflow_plan: WorkflowPlan


class ExplorerSequencePlan(BaseModel):
    workflow_name: Literal["execute_explorer_sequence"] = (
        "execute_explorer_sequence"
    )
    stages: list[ExplorerSequenceStagePlan] = Field(
        min_length=1,
        max_length=MAX_EXPLORER_SEQUENCE_STAGES,
    )
    stop_on_failure: Literal[True] = True


class ExplorerSequenceStageResult(BaseModel):
    stage_index: int
    explorer_id: str
    explorer_reference: str
    instruments: str
    create_in_metastock: bool
    succeeded: bool
    failed_tool: str | None = None
    result_id: str | None = None
    persisted: bool = False
    outcome: Literal["matches_found", "no_matches"] | None = None
    has_matches: bool | None = None
    matched_count: int | None = None
    message: str


class ExplorerSequenceRunResult(BaseModel):
    succeeded: bool
    total_stage_count: int
    attempted_stage_count: int
    completed_stage_count: int
    failed_stage_index: int | None = None
    failed_tool: str | None = None
    stages: list[ExplorerSequenceStageResult] = Field(default_factory=list)


class ExplorerSequenceCatalog:
    """Compile resolved stages into existing single-Explorer workflows."""

    def __init__(
        self,
        workflow_catalog: StaticWorkflowCatalog | None = None,
    ) -> None:
        self._workflow_catalog = (
            workflow_catalog or StaticWorkflowCatalog()
        )

    def prepare(
        self,
        request: ResolvedExplorerSequenceRequest,
    ) -> ExplorerSequencePlan:
        stages: list[ExplorerSequenceStagePlan] = []

        for stage in request.stages:
            workflow_name = (
                "create_run_and_capture"
                if stage.create_in_metastock
                else "run_and_capture"
            )
            workflow_plan = self._workflow_catalog.prepare(
                workflow_name=workflow_name,
                explorer_id=stage.explorer_id,
                workflow_arguments={
                    "instruments": stage.instruments,
                },
            )
            stages.append(
                ExplorerSequenceStagePlan(
                    stage_index=stage.stage_index,
                    explorer_id=stage.explorer_id,
                    explorer_reference=stage.explorer_reference,
                    instruments=stage.instruments,
                    create_in_metastock=stage.create_in_metastock,
                    workflow_plan=workflow_plan,
                )
            )

        return ExplorerSequencePlan(
            stages=stages,
            stop_on_failure=True,
        )
