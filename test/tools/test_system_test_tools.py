from __future__ import annotations

from tools.system_test_tools import SystemTestToolService
from tools.tool_contracts import ConvertExplorerToSystemTestInput


class FakeRagClient:
    def convert_explorer_to_system_test(self, explorer_id: str):
        return {
            "system_test_id": "00000000-0000-4000-8000-000000000001",
            "source_explorer_id": explorer_id,
            "service_log": None,
            "validation": {
                "passed": True,
                "errors": [],
                "warnings": [],
            },
            "system_test": {
                "name": "AI - RSI Explorer - System Test",
                "description": "Fixed target",
                "general": {
                    "order_bias": "long",
                    "portfolio_bias": "single",
                    "position_limit": {
                        "enabled": True,
                        "max_positions": 1,
                    },
                },
                "orders": {
                    "buy": {
                        "enabled": True,
                        "signal_formula": (
                            "BuySignal := RSI(14) < 30;\n"
                            "BuySignal AND "
                            "Simulation.LongPositionCount = 0"
                        ),
                    },
                    "sell": {
                        "enabled": True,
                        "signal_formula": (
                            "EntryPrice := C - "
                            "Simulation.CurrentPositionPointDifference;\n"
                            "H >= EntryPrice * 1.20"
                        ),
                    },
                    "sell_short": {"enabled": False},
                    "buy_to_cover": {"enabled": False},
                },
                "stops": {"enabled": False},
                "optimizations": {"enabled": False},
            },
        }


def test_manual_system_test_response_preserves_formulas() -> None:
    service = SystemTestToolService(FakeRagClient())
    result = service.convert_explorer_to_system_test(
        ConvertExplorerToSystemTestInput(
            explorer_id="00000000-0000-4000-8000-000000000002"
        )
    )

    assert result.ok is True
    assert result.display is not None
    assert "Buy Order formula editor" in result.display.markdown
    assert "Sell Order formula editor" in result.display.markdown
    assert "H >= EntryPrice * 1.20" in result.display.markdown
    assert "Sell Short" in result.display.markdown
