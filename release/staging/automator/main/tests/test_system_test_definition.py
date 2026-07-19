from __future__ import annotations

import unittest

from system_test_definition import SystemTestCreationRequest


VALID_PAYLOAD = {
    "schema_version": "1.0",
    "system_test_id": "11111111-1111-1111-1111-111111111111",
    "source_explorer_id": "22222222-2222-2222-2222-222222222222",
    "name": "RAG long-only smoke test",
    "description": "Created from a validated Explorer output.",
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
            "signal_formula": "Cross(C, Mov(C,20,S))",
        },
        "sell": {
            "enabled": True,
            "signal_formula": "Cross(Mov(C,20,S), C)",
        },
        "sell_short": {"enabled": False},
        "buy_to_cover": {"enabled": False},
    },
    "stops": {"enabled": False},
    "optimizations": {"enabled": False},
}


class SystemTestDefinitionTests(unittest.TestCase):
    def test_valid_long_only_payload(self) -> None:
        request = SystemTestCreationRequest.from_dict(VALID_PAYLOAD)
        self.assertEqual(request.name, "RAG long-only smoke test")
        self.assertEqual(request.general.order_bias, "long")
        self.assertTrue(request.orders.buy.enabled)
        self.assertFalse(request.orders.sell_short.enabled)

    def test_rejects_explorer_column_reference(self) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["orders"] = dict(VALID_PAYLOAD["orders"])
        payload["orders"]["buy"] = {
            "enabled": True,
            "signal_formula": "ColA > ColB",
        }

        with self.assertRaisesRegex(ValueError, "Explorer-only"):
            SystemTestCreationRequest.from_dict(payload)

    def test_rejects_uninspected_stops(self) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["stops"] = {"enabled": True}

        with self.assertRaisesRegex(ValueError, "Stops tab"):
            SystemTestCreationRequest.from_dict(payload)

    def test_rejects_uninspected_short_scope(self) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["general"] = {
            "order_bias": "short",
            "portfolio_bias": "single",
            "position_limit": {
                "enabled": True,
                "max_positions": 1,
            },
        }
        payload["orders"] = dict(VALID_PAYLOAD["orders"])
        payload["orders"]["buy"] = {"enabled": False}
        payload["orders"]["sell"] = {"enabled": False}
        payload["orders"]["sell_short"] = {
            "enabled": True,
            "signal_formula": "Cross(Mov(C,20,S), C)",
        }
        payload["orders"]["buy_to_cover"] = {
            "enabled": True,
            "signal_formula": "Cross(C, Mov(C,20,S))",
        }

        with self.assertRaisesRegex(ValueError, "order_bias must be 'long'"):
            SystemTestCreationRequest.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
