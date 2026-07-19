from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from system_test_automator import (
    create_system_test_request,
    run_existing_system_test_request,
    run_selected_system_test_request,
    select_system_test_request,
)
from system_test_definition import SystemTestCreationRequest
from system_test_request import SystemTestRequest


@dataclass(frozen=True)
class SystemTestCreateResult:
    succeeded: bool
    message: str
    started_at: str
    finished_at: str
    created: bool = False
    system_test_id: str | None = None
    source_explorer_id: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SystemTestRunResult:
    succeeded: bool
    message: str
    started_at: str
    finished_at: str
    execution_started: bool = False
    status: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class MetaStockSystemTestService:
    """
    System Tester service with the same boundaries as AutomatorService:

    - create_system_test(): create only;
    - select_system_test(): select test and instruments only;
    - run_selected_system_test(): start the current selection only;
    - run_system_test(): legacy CLI convenience wrapper, select then run.
    """

    def create_system_test(
        self,
        request: SystemTestCreationRequest | Mapping[str, Any],
    ) -> SystemTestCreateResult:
        started_at = self._utc_now()
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        normalized: SystemTestCreationRequest | None = None

        try:
            normalized = (
                request.normalized()
                if isinstance(request, SystemTestCreationRequest)
                else SystemTestCreationRequest.from_dict(request)
            )

            with (
                redirect_stdout(stdout_buffer),
                redirect_stderr(stderr_buffer),
            ):
                create_system_test_request(normalized)

            return SystemTestCreateResult(
                succeeded=True,
                message=(
                    f"System test {normalized.name!r} was created in "
                    "MetaStock. It was not selected or run."
                ),
                started_at=started_at,
                finished_at=self._utc_now(),
                created=True,
                system_test_id=normalized.system_test_id,
                source_explorer_id=normalized.source_explorer_id,
                diagnostics={
                    "boundary": "create_system_test",
                    "schema_version": normalized.schema_version,
                    "system_test_name": normalized.name,
                    "system_test_id": normalized.system_test_id,
                    "source_explorer_id": normalized.source_explorer_id,
                    "order_bias": normalized.general.order_bias,
                    "portfolio_bias": normalized.general.portfolio_bias,
                    "position_limit_enabled": (
                        normalized.general.position_limit_enabled
                    ),
                    "max_positions": normalized.general.max_positions,
                    "filled_order_tabs": ["Buy Order", "Sell Order"],
                    "stdout_text": stdout_buffer.getvalue(),
                    "stderr_text": stderr_buffer.getvalue(),
                },
            )

        except Exception as exc:
            return SystemTestCreateResult(
                succeeded=False,
                message=f"create_system_test failed: {exc}",
                started_at=started_at,
                finished_at=self._utc_now(),
                created=False,
                system_test_id=(
                    normalized.system_test_id
                    if normalized is not None
                    else None
                ),
                source_explorer_id=(
                    normalized.source_explorer_id
                    if normalized is not None
                    else None
                ),
                diagnostics={
                    "boundary": "create_system_test",
                    "system_test_name": (
                        normalized.name
                        if normalized is not None
                        else None
                    ),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                    "stdout_text": stdout_buffer.getvalue(),
                    "stderr_text": stderr_buffer.getvalue(),
                },
            )

    def select_system_test(
        self,
        request: SystemTestRequest,
    ) -> SystemTestRunResult:
        return self._call_run_boundary(
            request,
            boundary="select_system_test",
            runner=select_system_test_request,
            success_message=(
                "System test {system_test_name!r} and instruments were "
                "selected in MetaStock. Execution was not started."
            ),
            execution_started=False,
        )

    def run_selected_system_test(
        self,
        request: SystemTestRequest,
    ) -> SystemTestRunResult:
        return self._call_run_boundary(
            request,
            boundary="run_selected_system_test",
            runner=run_selected_system_test_request,
            success_message=(
                "The selected system test completed in MetaStock."
            ),
            execution_started=True,
        )

    def run_system_test(
        self,
        request: SystemTestRequest,
    ) -> SystemTestRunResult:
        """Backward-compatible CLI wrapper: select, then run selected."""
        return self._call_run_boundary(
            request,
            boundary="run_system_test",
            runner=run_existing_system_test_request,
            success_message=(
                "System test {system_test_name!r} was selected and "
                "completed in MetaStock."
            ),
            execution_started=True,
        )

    def _call_run_boundary(
        self,
        request: SystemTestRequest,
        *,
        boundary: str,
        runner: Callable[[SystemTestRequest], Any],
        success_message: str,
        execution_started: bool,
    ) -> SystemTestRunResult:
        started_at = self._utc_now()
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        normalized: SystemTestRequest | None = None

        try:
            normalized = self._normalize_run_request(request)

            with (
                redirect_stdout(stdout_buffer),
                redirect_stderr(stderr_buffer),
            ):
                result = runner(normalized)

            status_payload = None
            if result is not None and hasattr(result, "status"):
                status_payload = asdict(result.status)

            return SystemTestRunResult(
                succeeded=True,
                message=success_message.format(
                    system_test_name=normalized.system_test_name
                ),
                started_at=started_at,
                finished_at=self._utc_now(),
                execution_started=execution_started,
                status=status_payload,
                diagnostics={
                    "boundary": boundary,
                    "system_test_name": normalized.system_test_name,
                    "select_all_instruments": (
                        normalized.select_all_instruments
                    ),
                    "instruments": normalized.instrument_names,
                    "stdout_text": stdout_buffer.getvalue(),
                    "stderr_text": stderr_buffer.getvalue(),
                },
            )

        except Exception as exc:
            return SystemTestRunResult(
                succeeded=False,
                message=f"{boundary} failed: {exc}",
                started_at=started_at,
                finished_at=self._utc_now(),
                execution_started=False,
                status=None,
                diagnostics={
                    "boundary": boundary,
                    "system_test_name": (
                        normalized.system_test_name
                        if normalized is not None
                        else str(
                            getattr(request, "system_test_name", "")
                            or ""
                        )
                    ),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                    "stdout_text": stdout_buffer.getvalue(),
                    "stderr_text": stderr_buffer.getvalue(),
                },
            )

    @staticmethod
    def _normalize_run_request(
        request: SystemTestRequest,
    ) -> SystemTestRequest:
        name = str(request.system_test_name or "").strip()
        if not name:
            raise ValueError("system_test_name is required.")

        if request.max_execution_wait_sec <= 0:
            raise ValueError(
                "max_execution_wait_sec must be positive."
            )

        if request.select_all_instruments:
            instruments = None
            select_all = True
        else:
            instruments = [
                str(value or "").strip()
                for value in (request.instrument_names or [])
                if str(value or "").strip()
            ]
            if not instruments:
                raise ValueError(
                    "At least one instrument is required when "
                    "select_all_instruments is false."
                )
            select_all = False

        return SystemTestRequest(
            system_test_name=name,
            instrument_names=instruments,
            select_all_instruments=select_all,
            max_execution_wait_sec=request.max_execution_wait_sec,
            read_status_if_visible=request.read_status_if_visible,
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
