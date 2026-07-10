from __future__ import annotations

from pathlib import Path

from services.automator_client import (
    AutomatorExplorerColumn,
    AutomatorRunRequest,
    LocalAutomatorClient,
)


FAKE_SERVICE_SOURCE = '''
from dataclasses import dataclass, field

@dataclass(frozen=True)
class AutomatorExecutionColumn:
    col_letter: str
    col_code: str

@dataclass(frozen=True)
class AutomatorExecutionRequest:
    explorer_id: str
    name: str
    description: str
    filter_code: str
    columns: list = field(default_factory=list)
    instruments: list | None = None
    select_all_instruments: bool = True
    max_execution_wait_sec: int = 300

@dataclass(frozen=True)
class Result:
    succeeded: bool
    message: str
    started_at: str
    finished_at: str
    diagnostics: dict

class MetaStockAutomatorService:
    def run_explorer(self, request):
        return Result(
            succeeded=True,
            message=request.name,
            started_at="start",
            finished_at="finish",
            diagnostics={
                "explorer_id": request.explorer_id,
                "column_count": len(request.columns),
                "instruments": request.instruments,
            },
        )
'''


def test_local_client_loads_service_and_maps_contract(tmp_path: Path) -> None:
    (tmp_path / "automator_service.py").write_text(
        FAKE_SERVICE_SOURCE,
        encoding="utf-8",
    )

    client = LocalAutomatorClient(str(tmp_path))
    result = client.run_explorer(
        AutomatorRunRequest(
            explorer_id="explorer-1",
            name="RSI Test",
            description="Test",
            filter_code="RSI(14) < 30",
            columns=[
                AutomatorExplorerColumn(
                    col_letter="A",
                    col_code="RSI(14)",
                )
            ],
            instruments=["SGX"],
            select_all_instruments=False,
        )
    )

    assert client.configured is True
    assert result.succeeded is True
    assert result.message == "RSI Test"
    assert result.started_at == "start"
    assert result.finished_at == "finish"
    assert result.diagnostics["explorer_id"] == "explorer-1"
    assert result.diagnostics["column_count"] == 1
    assert result.diagnostics["instruments"] == ["SGX"]
