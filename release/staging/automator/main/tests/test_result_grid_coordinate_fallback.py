from __future__ import annotations

import sys
import unittest
from pathlib import Path


MAIN = Path(__file__).resolve().parents[1]

if str(MAIN) not in sys.path:
    sys.path.insert(0, str(MAIN))

from compartments import result_scraper as result_scraper_module
from compartments.result_scraper import (
    ExplorationResultRow,
    ExplorationResultScraper,
)


class EmptyExecutionWindow:
    def descendants(self, *args, **kwargs):
        del args, kwargs
        return []


class ResultGridCoordinateFallbackTests(unittest.TestCase):
    def make_row(self) -> ExplorationResultRow:
        return ExplorationResultRow(
            row_index=0,
            values_by_column={
                0: "Example Instrument",
                1: "EXAMPLE",
            },
            values_by_name={
                "instrument_name": "Example Instrument",
                "symbol": "EXAMPLE",
            },
        )

    def test_result_grid_timeout_returns_none_after_results_count_gate(self):
        scraper = ExplorationResultScraper(
            preserve_existing_clipboard=False,
        )

        grid = scraper._wait_for_results_grid(
            execution_window=EmptyExecutionWindow(),
            expected_count=1,
            timeout=0.01,
            poll_interval=0.001,
        )

        self.assertIsNone(grid)

    def test_missing_grid_uses_coordinate_fallback_immediately(self):
        scraper = ExplorationResultScraper(
            clipboard_timeout=1.0,
            preserve_existing_clipboard=False,
            result_row_fallback_delay=999.0,
        )

        reasons: list[str] = []
        sent_keys: list[str] = []
        row = self.make_row()

        scraper._read_clipboard_safely = lambda: None
        scraper._click_result_window_relative_calibrated_first_row = (
            lambda *, execution_window, reason: (
                reasons.append(reason) or True
            )
        )
        scraper._wait_for_copied_table_text = (
            lambda *, sentinel, deadline: "fake-table"
        )
        scraper._parse_copied_table = (
            lambda clipboard_text: (
                {
                    0: "instrument_name",
                    1: "symbol",
                },
                [row],
            )
        )

        original_copy = result_scraper_module.pyperclip.copy
        original_send_keys = result_scraper_module.send_keys

        result_scraper_module.pyperclip.copy = lambda value: None
        result_scraper_module.send_keys = (
            lambda keys, pause=0.0: sent_keys.append(keys)
        )

        try:
            headers, rows = scraper._copy_full_results_table(
                execution_window=object(),
                grid=None,
                expected_count=1,
            )
        finally:
            result_scraper_module.pyperclip.copy = original_copy
            result_scraper_module.send_keys = original_send_keys

        self.assertEqual(
            headers,
            {
                0: "instrument_name",
                1: "symbol",
            },
        )
        self.assertEqual(rows, [row])
        self.assertEqual(sent_keys, ["^a", "^c"])
        self.assertEqual(len(reasons), 1)
        self.assertIn(
            "did not materialize through UIA",
            reasons[0],
        )

    def test_grid_activation_failure_uses_coordinate_fallback_immediately(self):
        scraper = ExplorationResultScraper(
            clipboard_timeout=1.0,
            preserve_existing_clipboard=False,
            result_row_fallback_delay=999.0,
        )

        reasons: list[str] = []
        sent_keys: list[str] = []
        row = self.make_row()

        scraper._read_clipboard_safely = lambda: None

        def fail_activation(*, execution_window, grid):
            del execution_window, grid
            raise RuntimeError("synthetic UIA activation failure")

        scraper._activate_results_grid = fail_activation
        scraper._click_result_window_relative_calibrated_first_row = (
            lambda *, execution_window, reason: (
                reasons.append(reason) or True
            )
        )
        scraper._wait_for_copied_table_text = (
            lambda *, sentinel, deadline: "fake-table"
        )
        scraper._parse_copied_table = (
            lambda clipboard_text: (
                {
                    0: "instrument_name",
                    1: "symbol",
                },
                [row],
            )
        )

        original_copy = result_scraper_module.pyperclip.copy
        original_send_keys = result_scraper_module.send_keys

        result_scraper_module.pyperclip.copy = lambda value: None
        result_scraper_module.send_keys = (
            lambda keys, pause=0.0: sent_keys.append(keys)
        )

        try:
            headers, rows = scraper._copy_full_results_table(
                execution_window=object(),
                grid=object(),
                expected_count=1,
            )
        finally:
            result_scraper_module.pyperclip.copy = original_copy
            result_scraper_module.send_keys = original_send_keys

        self.assertEqual(len(rows), 1)
        self.assertEqual(sent_keys, ["^a", "^c"])
        self.assertEqual(len(reasons), 1)
        self.assertIn(
            "UIA activation failed",
            reasons[0],
        )


if __name__ == "__main__":
    unittest.main()
