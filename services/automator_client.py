from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
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
    @property
    def configured(self) -> bool:
        return False

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        raise RuntimeError("Automator execution is not configured.")


class LocalAutomatorClient:
    """Loads only the workflow-level automator_service.py boundary."""

    def __init__(self, automator_repo_path: str) -> None:
        self.automator_repo_path = Path(automator_repo_path).expanduser().resolve()

        if not self.automator_repo_path.exists():
            raise FileNotFoundError(
                f"Automator repo path not found: {self.automator_repo_path}"
            )

        service_path = self.automator_repo_path / "automator_service.py"
        if not service_path.is_file():
            raise FileNotFoundError(
                f"Automator service file not found: {service_path}"
            )

        repo_path_str = str(self.automator_repo_path)
        if repo_path_str not in sys.path:
            sys.path.insert(0, repo_path_str)

        module = self._load_service_module(service_path)

        try:
            self._service_column_type = module.AutomatorExecutionColumn
            self._service_request_type = module.AutomatorExecutionRequest
            service_type = module.MetaStockAutomatorService
        except AttributeError as exc:
            raise RuntimeError(
                "automator_service.py does not expose the Milestone 6 contract."
            ) from exc

        self._service = service_type()

    @property
    def configured(self) -> bool:
        return True

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        service_request = self._service_request_type(
            explorer_id=request.explorer_id,
            name=request.name,
            description=request.description,
            filter_code=request.filter_code,
            columns=[
                self._service_column_type(
                    col_letter=column.col_letter,
                    col_code=column.col_code,
                )
                for column in request.columns
            ],
            instruments=request.instruments,
            select_all_instruments=request.select_all_instruments,
            max_execution_wait_sec=request.max_execution_wait_sec,
        )

        result = self._service.run_explorer(service_request)
        diagnostics = getattr(result, "diagnostics", {})
        if not isinstance(diagnostics, dict):
            diagnostics = {"raw_diagnostics": str(diagnostics)}

        return AutomatorRunResult(
            succeeded=bool(result.succeeded),
            message=str(result.message),
            started_at=self._optional_str(getattr(result, "started_at", None)),
            finished_at=self._optional_str(getattr(result, "finished_at", None)),
            diagnostics=diagnostics,
        )

    def _load_service_module(self, service_path: Path) -> ModuleType:
        path_hash = hashlib.sha1(
            str(service_path).encode("utf-8")
        ).hexdigest()[:12]
        module_name = f"_metastock_automator_service_{path_hash}"

        existing = sys.modules.get(module_name)
        if isinstance(existing, ModuleType):
            return existing

        spec = importlib.util.spec_from_file_location(module_name, service_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"Could not load Automator service module from {service_path}"
            )

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        return module

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)
