from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class AutomatorExplorerColumn(BaseModel):
    col_letter: str = Field(min_length=1, max_length=1)
    col_code: str = Field(min_length=1)


class AutomatorRunRequest(BaseModel):
    explorer_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    filter_code: str = Field(min_length=1)
    columns: list[AutomatorExplorerColumn] = Field(default_factory=list)

    instruments: list[str] | None = None
    select_all_instruments: bool = True
    max_execution_wait_sec: int = Field(default=300, gt=0)


class AutomatorRunResult(BaseModel):
    succeeded: bool
    message: str
    started_at: str | None = None
    finished_at: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class AutomatorClient(Protocol):
    @property
    def configured(self) -> bool:
        ...

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        ...


class UnavailableAutomatorClient:
    """
    Milestone 5 placeholder.

    It establishes the agent-side execution boundary without importing or
    invoking MetaStock UI automation. Milestone 6 can replace this object with
    a concrete client that implements the same protocol.
    """

    @property
    def configured(self) -> bool:
        return False

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        raise RuntimeError("Automator execution is not configured.")
