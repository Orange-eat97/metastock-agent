from __future__ import annotations

from types import SimpleNamespace

from services.automator_client import (
    AutomatorExplorerColumn,
    AutomatorReadResultsRequest,
    AutomatorRunRequest,
    LocalAutomatorClient,
)


class FakeService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _execution_result(
        self,
        boundary: str,
    ) -> SimpleNamespace:
        self.calls.append(boundary)

        return SimpleNamespace(
            succeeded=True,
            message=f"{boundary} succeeded",
            started_at="start",
            finished_at="finish",
            result_available=(
                boundary
                == "run_selected_explorer"
            ),
            diagnostics={
                "boundary": boundary,
            },
        )

    def create_explorer(
        self,
        request,
    ) -> SimpleNamespace:
        return self._execution_result(
            "create_explorer"
        )

    def select_explorer(
        self,
        request,
    ) -> SimpleNamespace:
        return self._execution_result(
            "select_explorer"
        )

    def run_selected_explorer(
        self,
        request,
    ) -> SimpleNamespace:
        return self._execution_result(
            "run_selected_explorer"
        )

    def read_results(
        self,
        request,
    ) -> SimpleNamespace:
        self.calls.append("read_results")

        return SimpleNamespace(
            succeeded=True,
            message="read succeeded",
            started_at="start",
            finished_at="finish",
            explorer_id=request.explorer_id,
            results=None,
            diagnostics={},
        )


def build_client(
    service: FakeService,
) -> LocalAutomatorClient:
    client = object.__new__(
        LocalAutomatorClient
    )

    client._service = service
    client._execution_column_type = (
        lambda **kwargs: SimpleNamespace(
            **kwargs
        )
    )
    client._execution_request_type = (
        lambda **kwargs: SimpleNamespace(
            **kwargs
        )
    )
    client._result_request_type = (
        lambda **kwargs: SimpleNamespace(
            **kwargs
        )
    )

    return client


def build_run_request() -> AutomatorRunRequest:
    return AutomatorRunRequest(
        explorer_id="explorer-1",
        name="RSI Scanner",
        description="Test Explorer",
        filter_code="RSI(14) < 30",
        columns=[
            AutomatorExplorerColumn(
                col_letter="A",
                col_code="RSI(14)",
            )
        ],
        select_all_instruments=True,
    )


def test_create_calls_only_create() -> None:
    service = FakeService()
    client = build_client(service)

    result = client.create_explorer(
        build_run_request()
    )

    assert result.succeeded is True
    assert service.calls == [
        "create_explorer"
    ]


def test_select_calls_only_select() -> None:
    service = FakeService()
    client = build_client(service)

    result = client.select_explorer(
        build_run_request()
    )

    assert result.succeeded is True
    assert service.calls == [
        "select_explorer"
    ]


def test_run_selected_calls_only_run() -> None:
    service = FakeService()
    client = build_client(service)

    result = client.run_selected_explorer(
        build_run_request()
    )

    assert result.succeeded is True
    assert result.result_available is True
    assert service.calls == [
        "run_selected_explorer"
    ]


def test_read_results_calls_only_read() -> None:
    service = FakeService()
    client = build_client(service)

    result = client.read_results(
        AutomatorReadResultsRequest(
            explorer_id="explorer-1",
            close_after_read=True,
        )
    )

    assert result.succeeded is True
    assert service.calls == [
        "read_results"
    ]


def test_composite_run_remains_disabled() -> None:
    service = FakeService()
    client = build_client(service)

    result = client.run_explorer(
        build_run_request()
    )

    assert result.succeeded is False
    assert service.calls == []
    assert (
        result.diagnostics["boundary"]
        == "run_explorer"
    )