from __future__ import annotations

import ast
import unittest
from pathlib import Path


MAIN = Path(__file__).resolve().parents[1]


class CoordinateOnlyBoundaryTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (MAIN / relative_path).read_text(encoding="utf-8")

    def function_source(self, relative_path: str, function_name: str) -> str:
        source = self.read(relative_path)
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    return ast.get_source_segment(source, node) or ""

        self.fail(f"Function {function_name!r} was not found")

    def test_calibrator_records_console_points_only(self) -> None:
        source = self.read("calibrate_coordinates.py")

        for expected in (
            '"explore_tab"',
            '"start_exploration"',
            '"system_test_tab"',
            '"start_system_test"',
        ):
            self.assertIn(expected, source)

        for forbidden in (
            "strategy_checkbox",
            "instruments_checkbox",
            "system_test_checkbox",
        ):
            self.assertNotIn(forbidden, source)

    def test_row_checkbox_fallback_has_no_calibration_logic(self) -> None:
        source = self.function_source(
            "ui_interacter/ui_actions.py",
            "click_checkbox_in_row",
        )
        self.assertNotIn("calibrat", source.casefold())
        self.assertIn("rectangle.left + x_offset", source)

    def test_strategy_and_instrument_selectors_are_not_calibration_aware(self) -> None:
        for relative_path in (
            "compartments/strategy_selector.py",
            "compartments/instrument_selector.py",
            "compartments/system_test_selector.py",
        ):
            self.assertNotIn(
                "calibrat",
                self.read(relative_path).casefold(),
                relative_path,
            )

    def test_workflows_are_not_calibration_aware(self) -> None:
        for relative_path in (
            "compartments/explore_workflow.py",
            "compartments/system_test_workflow.py",
            "compartments/result_scraper.py",
            "compartments/result_capture.py",
        ):
            self.assertNotIn(
                "calibrat",
                self.read(relative_path).casefold(),
                relative_path,
            )

    def test_console_fallbacks_name_their_calibrated_points(self) -> None:
        explorer = self.read("compartments/explore_console.py")
        system_test = self.read("compartments/system_test_console.py")

        self.assertIn('calibration_point_name="explore_tab"', explorer)
        self.assertIn(
            'calibration_point_name="start_exploration"',
            explorer,
        )
        self.assertIn(
            'calibration_point_name="system_test_tab"',
            system_test,
        )
        self.assertIn(
            'calibration_point_name="start_system_test"',
            system_test,
        )


if __name__ == "__main__":
    unittest.main()
