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

    def test_calibrator_records_approved_fallback_points(self) -> None:
        source = self.read("calibrate_coordinates.py")

        for expected in (
            '"explore_tab"',
            '"strategy_checkbox"',
            '"start_exploration"',
            '"result_first_row"',
            '"system_test_tab"',
            '"start_system_test"',
        ):
            self.assertIn(expected, source)

        for forbidden in (
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

    def test_strategy_selection_uses_calibrated_anchor_and_fallback(self) -> None:
        selector_source = self.read(
            "compartments/strategy_selector.py"
        )
        locator_source = self.read(
            "ui_interacter/explore_selectors.py"
        )

        self.assertIn(
            '"strategy_checkbox"',
            selector_source,
        )
        self.assertIn(
            "click_absolute_calibrated_point",
            selector_source,
        )
        self.assertIn(
            "STRATEGY_FILTER_MAX_UIA_ATTEMPTS = 2",
            selector_source,
        )
        self.assertIn(
            "last_row_count == 1",
            selector_source,
        )
        self.assertIn(
            "_find_strategy_list_from_calibrated_anchor",
            locator_source,
        )
        self.assertIn(
            "list_view: Optional[BaseWrapper] = None",
            locator_source,
        )

    def test_other_row_selectors_are_not_calibration_aware(self) -> None:
        for relative_path in (
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
            "compartments/result_capture.py",
        ):
            self.assertNotIn(
                "calibrat",
                self.read(relative_path).casefold(),
                relative_path,
            )

    def test_result_row_calibration_is_result_window_relative(self) -> None:
        calibrator = self.read(
            "calibrate_coordinates.py"
        )
        scraper_method = self.function_source(
            "compartments/result_scraper.py",
            "_click_result_window_relative_calibrated_first_row",
        )

        self.assertIn(
            "result_window.rectangle()",
            calibrator,
        )
        self.assertIn(
            "absolute_x - int(rectangle.left)",
            calibrator,
        )
        self.assertIn(
            "absolute_y - int(rectangle.top)",
            calibrator,
        )
        self.assertIn(
            "execution_window.rectangle()",
            scraper_method,
        )
        self.assertIn(
            "point.window_relative_x",
            scraper_method,
        )
        self.assertIn(
            "point.window_relative_y",
            scraper_method,
        )
        self.assertNotIn(
            "point.absolute_x",
            scraper_method,
        )
        self.assertNotIn(
            "point.absolute_y",
            scraper_method,
        )
        self.assertNotIn(
            ".resolve(",
            scraper_method,
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
