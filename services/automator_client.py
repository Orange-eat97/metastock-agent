from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from pydantic import BaseModel, Field


class AutomatorExplorerColumn(BaseModel):
    col_letter: str = Field(
        min_length=1,
        max_length=1,
    )
    col_code: str = Field(min_length=1)


class AutomatorRunRequest(BaseModel):
    explorer_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    filter_code: str = Field(min_length=1)
    columns: list[
        AutomatorExplorerColumn
    ] = Field(default_factory=list)
    instruments: list[str] | None = None
    select_all_instruments: bool = True
    max_execution_wait_sec: int = Field(
        default=300,
        gt=0,
    )


class AutomatorRunResult(BaseModel):
    succeeded: bool
    message: str
    started_at: str | None = None
    finished_at: str | None = None
    result_available: bool = False
    diagnostics: dict[str, Any] = Field(
        default_factory=dict
    )


class AutomatorClipboardVerification(
    BaseModel
):
    passed: bool
    expected_count: int
    scraped_count: int
    clipboard_count: int
    missing_from_scrape: list[str] = Field(
        default_factory=list
    )
    unexpected_in_scrape: list[str] = Field(
        default_factory=list
    )
    clipboard_headers: list[str] = Field(
        default_factory=list
    )


class AutomatorResultRow(BaseModel):
    row_index: int
    instrument_name: str
    symbol: str | None = None
    column_values: dict[str, str] = Field(
        default_factory=dict
    )


class AutomatorExplorerResults(BaseModel):
    schema_version: str
    outcome: str
    expected_count: int
    matched_count: int
    has_matches: bool
    clipboard_verification: (
        AutomatorClipboardVerification | None
    ) = None
    rows: list[AutomatorResultRow] = Field(
        default_factory=list
    )


class AutomatorReadResultsRequest(BaseModel):
    explorer_id: str | None = None
    close_after_read: bool = True


class AutomatorReadResultsResult(BaseModel):
    succeeded: bool
    message: str
    started_at: str | None = None
    finished_at: str | None = None
    explorer_id: str | None = None
    results: (
        AutomatorExplorerResults | None
    ) = None
    diagnostics: dict[str, Any] = Field(
        default_factory=dict
    )


class AutomatorClient(Protocol):
    @property
    def configured(self) -> bool:
        ...

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        ...

    def read_results(
        self,
        request: AutomatorReadResultsRequest,
    ) -> AutomatorReadResultsResult:
        ...


class UnavailableAutomatorClient:
    @property
    def configured(self) -> bool:
        return False

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        raise RuntimeError(
            "Automator execution is not configured."
        )

    def read_results(
        self,
        request: AutomatorReadResultsRequest,
    ) -> AutomatorReadResultsResult:
        raise RuntimeError(
            "MetaStock result reading is not "
            "configured."
        )


class LocalAutomatorClient:
    """
    Local adapter for one workflow-level module:

        automator_service.py

    The same MetaStockAutomatorService instance handles both
    execution and result reading.
    """

    def __init__(
        self,
        automator_repo_path: str,
    ) -> None:
        self.automator_repo_path = (
            Path(automator_repo_path)
            .expanduser()
            .resolve()
        )

        if not self.automator_repo_path.exists():
            raise FileNotFoundError(
                "Automator repo path not found: "
                f"{self.automator_repo_path}"
            )

        repo_path_str = str(
            self.automator_repo_path
        )

        if repo_path_str not in sys.path:
            sys.path.insert(
                0,
                repo_path_str,
            )

        module = self._load_service_module(
            self.automator_repo_path
            / "automator_service.py"
        )

        try:
            self._execution_column_type = (
                module.AutomatorExecutionColumn
            )
            self._execution_request_type = (
                module.AutomatorExecutionRequest
            )
            self._result_request_type = (
                module.AutomatorResultReadRequest
            )
            service_type = (
                module.MetaStockAutomatorService
            )

        except AttributeError as exc:
            raise RuntimeError(
                "automator_service.py does not "
                "expose the consolidated "
                "Milestone 7 contract."
            ) from exc

        self._service = service_type()

    @property
    def configured(self) -> bool:
        return True

    def run_explorer(
        self,
        request: AutomatorRunRequest,
    ) -> AutomatorRunResult:
        service_request = (
            self._execution_request_type(
                explorer_id=(
                    request.explorer_id
                ),
                name=request.name,
                description=(
                    request.description
                ),
                filter_code=(
                    request.filter_code
                ),
                columns=[
                    self._execution_column_type(
                        col_letter=(
                            column.col_letter
                        ),
                        col_code=(
                            column.col_code
                        ),
                    )
                    for column in (
                        request.columns
                    )
                ],
                instruments=(
                    request.instruments
                ),
                select_all_instruments=(
                    request
                    .select_all_instruments
                ),
                max_execution_wait_sec=(
                    request
                    .max_execution_wait_sec
                ),
            )
        )

        result = self._service.run_explorer(
            service_request
        )

        diagnostics = self._dict_or_wrapped(
            getattr(
                result,
                "diagnostics",
                {},
            )
        )
        result_available = bool(
            getattr(
                result,
                "result_available",
                False,
            )
        )
        diagnostics.setdefault(
            "result_available",
            result_available,
        )

        return AutomatorRunResult(
            succeeded=bool(result.succeeded),
            message=str(result.message),
            started_at=self._optional_str(
                getattr(
                    result,
                    "started_at",
                    None,
                )
            ),
            finished_at=self._optional_str(
                getattr(
                    result,
                    "finished_at",
                    None,
                )
            ),
            result_available=(
                result_available
            ),
            diagnostics=diagnostics,
        )

    def read_results(
        self,
        request: AutomatorReadResultsRequest,
    ) -> AutomatorReadResultsResult:
        service_request = (
            self._result_request_type(
                explorer_id=(
                    request.explorer_id
                ),
                close_after_read=(
                    request.close_after_read
                ),
            )
        )

        result = self._service.read_results(
            service_request
        )

        raw_results = getattr(
            result,
            "results",
            None,
        )

        parsed_results = (
            AutomatorExplorerResults
            .model_validate(
                self._model_payload(
                    raw_results
                )
            )
            if raw_results is not None
            else None
        )

        return AutomatorReadResultsResult(
            succeeded=bool(result.succeeded),
            message=str(result.message),
            started_at=self._optional_str(
                getattr(
                    result,
                    "started_at",
                    None,
                )
            ),
            finished_at=self._optional_str(
                getattr(
                    result,
                    "finished_at",
                    None,
                )
            ),
            explorer_id=self._optional_str(
                getattr(
                    result,
                    "explorer_id",
                    None,
                )
            ),
            results=parsed_results,
            diagnostics=self._dict_or_wrapped(
                getattr(
                    result,
                    "diagnostics",
                    {},
                )
            ),
        )

    def _load_service_module(
        self,
        service_path: Path,
    ) -> ModuleType:
        if not service_path.is_file():
            raise FileNotFoundError(
                "Automator service file not found: "
                f"{service_path}"
            )

        path_hash = hashlib.sha1(
            str(service_path).encode(
                "utf-8"
            )
        ).hexdigest()[:12]
        module_name = (
            "_metastock_automator_service_"
            f"{path_hash}"
        )

        existing = sys.modules.get(
            module_name
        )

        if isinstance(
            existing,
            ModuleType,
        ):
            return existing

        spec = (
            importlib.util
            .spec_from_file_location(
                module_name,
                service_path,
            )
        )

        if (
            spec is None
            or spec.loader is None
        ):
            raise RuntimeError(
                "Could not load Automator "
                f"service from {service_path}"
            )

        module = (
            importlib.util
            .module_from_spec(spec)
        )
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(
                module_name,
                None,
            )
            raise

        return module

    @staticmethod
    def _model_payload(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        if hasattr(value, "to_dict"):
            payload = value.to_dict()

            if isinstance(payload, dict):
                return payload

        if hasattr(value, "__dict__"):
            return {
                key: item
                for key, item in (
                    vars(value).items()
                )
                if not key.startswith("_")
            }

        raise TypeError(
            "Could not convert Automator "
            f"result model "
            f"{type(value).__name__} "
            "into a dictionary."
        )

    @staticmethod
    def _dict_or_wrapped(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        return {
            "raw_diagnostics": str(value)
        }

    @staticmethod
    def _optional_str(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        return str(value)
