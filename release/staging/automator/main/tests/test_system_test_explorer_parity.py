from __future__ import annotations

import unittest
from pathlib import Path


MAIN = Path(__file__).resolve().parents[1]


class SystemTestExplorerParityTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (MAIN / relative_path).read_text(
            encoding="utf-8"
        )

    def test_console_preserves_explorer_open_sequence(self) -> None:
        source = self.read(
            "compartments/system_test_console.py"
        )
        self.assertIn(
            "find_system_test_caption",
            source,
        )
        self.assertIn(
            "rectangle.left + 31",
            source,
        )
        self.assertIn(
            "rectangle.top + 533",
            source,
        )
        self.assertIn(
            "Could not verify SystemTest Console by text",
            source,
        )

    def test_selector_preserves_clean_state_machine(self) -> None:
        source = self.read(
            "compartments/system_test_selector.py"
        )
        self.assertIn(
            "clear_all_selected_system_tests",
            source,
        )
        self.assertIn(
            "find_system_test_select_all_checkbox",
            source,
        )
        self.assertIn(
            "get_selected_count(main) == 1",
            source,
        )

    def test_creator_preserves_explorer_creator_and_column_flow(self) -> None:
        source = self.read(
            "compartments/system_test_creator.py"
        )
        self.assertIn(
            "_open_new_system_test_editor",
            source,
        )
        self.assertIn(
            "self.actions.invoke_or_click(\n                tab",
            source,
        )
        self.assertIn(
            "_wait_for_order_formula_editor",
            source,
        )
        self.assertIn(
            "self._save_editor(editor)",
            source,
        )

    def test_workflow_waits_like_explorer(self) -> None:
        source = self.read(
            "compartments/system_test_workflow.py"
        )
        self.assertIn(
            "self.execution_monitor.wait_for_window(main)",
            source,
        )
        self.assertIn(
            "self.execution_monitor.wait_done",
            source,
        )
        self.assertIn(
            "find_execution_window_inside_main(main)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
