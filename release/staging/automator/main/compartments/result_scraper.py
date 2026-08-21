from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pyperclip
from pywinauto.base_wrapper import BaseWrapper
from pywinauto.keyboard import send_keys
from pywinauto.mouse import click as mouse_click

from ui_interacter.coordinate_calibration import CoordinateMapper
from ui_interacter.ui_core import (
    log,
    normalize_text,
    safe_descendants,
)


RESULTS_TAB_RE = re.compile(
    r"^Results\s*\(\s*(?P<count>\d+)\s*\)$",
    re.IGNORECASE,
)

RESULTS_GRID_AUTOMATION_ID = "ResultsGridControl"
RESULT_FIRST_ROW_CALIBRATION_POINT = "result_first_row"
RESULT_FIRST_ROW_FALLBACK_DELAY_SECONDS = 3.0

# After Results (N) appears, give the grid UIA object only a
# short grace period before using the calibrated result-row path.
RESULTS_GRID_UIA_GRACE_SECONDS = 0.75


@dataclass(frozen=True)
class ExplorationResultRow:
    """One scraped MetaStock result row."""

    row_index: int
    values_by_column: dict[int, str]
    values_by_name: dict[str, str]


@dataclass(frozen=True)
class ExplorationResultSet:
    """Complete result returned by the scraper."""

    expected_count: int
    headers: dict[int, str]
    rows: list[ExplorationResultRow] = field(
        default_factory=list
    )

    @property
    def matched_count(self) -> int:
        return len(self.rows)

    @property
    def has_matches(self) -> bool:
        return self.expected_count > 0

    def to_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        for row in self.rows:
            record: dict[str, Any] = {
                "row_index": row.row_index,
            }
            record.update(row.values_by_name)
            records.append(record)

        return records


class ExplorationResultScraper:
    """
    Scrape MetaStock's result table through native grid copying.

    The tested MetaStock/DevExpress build exposes the lower result
    grid as ``ResultsGridControl`` but does not publish its visible
    rows as UIA descendants. The full table is nevertheless available
    through Ctrl+A followed by Ctrl+C.
    """

    def __init__(
        self,
        page_load_delay: float = 0.03,
        max_stale_pages: int = 4,
        result_ready_timeout: float = 3.0,
        page_change_timeout: float = 0.5,
        poll_interval: float = 0.04,
        clipboard_timeout: float = 5.0,
        preserve_existing_clipboard: bool = True,
        coordinate_mapper: Optional[CoordinateMapper] = None,
        result_row_fallback_delay: float = (
            RESULT_FIRST_ROW_FALLBACK_DELAY_SECONDS
        ),
    ) -> None:
        # Preserve the old constructor contract. The paging arguments
        # remain accepted because existing composition code passes them.
        self.event_dispatch_delay = min(
            max(float(page_load_delay), 0.01),
            0.05,
        )
        self.max_stale_pages = max_stale_pages
        self.result_ready_timeout = max(
            float(result_ready_timeout),
            1.0,
        )
        self.page_change_timeout = page_change_timeout
        self.poll_interval = max(
            float(poll_interval),
            0.02,
        )
        self.clipboard_timeout = max(
            float(clipboard_timeout),
            1.0,
        )
        self.preserve_existing_clipboard = bool(
            preserve_existing_clipboard
        )
        self.coordinate_mapper = coordinate_mapper
        self.result_row_fallback_delay = max(
            float(result_row_fallback_delay),
            0.0,
        )

    def scrape(
        self,
        execution_window: BaseWrapper,
    ) -> ExplorationResultSet:
        expected_count = self._wait_for_result_count(
            execution_window=execution_window,
            timeout=self.result_ready_timeout,
            poll_interval=self.poll_interval,
        )

        log(
            "MetaStock result count detected: "
            f"{expected_count}"
        )

        if expected_count == 0:
            return ExplorationResultSet(
                expected_count=0,
                headers={},
                rows=[],
            )

        # Results (N) is the safe boundary for result capture. Once it is
        # present, the run has reached the result surface and the DataGrid
        # UIA object becomes an optimization rather than a prerequisite.
        grid = self._wait_for_results_grid(
            execution_window=execution_window,
            expected_count=expected_count,
            timeout=min(
                self.result_ready_timeout,
                RESULTS_GRID_UIA_GRACE_SECONDS,
            ),
            poll_interval=self.poll_interval,
        )

        if grid is None:
            log(
                "Results (N) is available, but the result DataGrid did not "
                "materialize through UIA. Proceeding immediately through "
                "the calibrated first-result-row fallback."
            )

        headers, rows = self._copy_full_results_table(
            execution_window=execution_window,
            grid=grid,
            expected_count=expected_count,
        )

        log(
            "MetaStock result table copied successfully: "
            f"headers={headers}, rows={len(rows)}"
        )

        return ExplorationResultSet(
            expected_count=expected_count,
            headers=headers,
            rows=rows,
        )

    def _wait_for_result_count(
        self,
        *,
        execution_window: BaseWrapper,
        timeout: float,
        poll_interval: float,
    ) -> int:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                for controls in (
                    execution_window.descendants(
                        control_type="TabItem"
                    ),
                    execution_window.descendants(),
                ):
                    count = self._read_result_count_from_controls(
                        controls
                    )

                    if count is not None:
                        return count

            except Exception as exc:
                last_error = exc

            time.sleep(poll_interval)

        self._log_result_surface_snapshot(
            execution_window
        )

        raise RuntimeError(
            "MetaStock completed visually, but no Results (N) "
            "control appeared through UIA within "
            f"{timeout:.1f} seconds. "
            f"Last UIA error: {last_error}"
        )

    def _read_result_count_from_controls(
        self,
        controls: list[BaseWrapper],
    ) -> Optional[int]:
        for control in controls:
            for text in self._control_text_candidates(
                control
            ):
                match = RESULTS_TAB_RE.fullmatch(text)

                if match is not None:
                    count = int(match.group("count"))
                    log(
                        "Results count found through UIA: "
                        f"Results ({count})"
                    )
                    return count

        return None

    def _wait_for_results_grid(
        self,
        *,
        execution_window: BaseWrapper,
        expected_count: int,
        timeout: float,
        poll_interval: float,
    ) -> Optional[BaseWrapper]:
        """
        Best-effort UIA acquisition of the result grid.

        Results (N) has already been observed before this method is called.
        Therefore failure to materialize ResultsGridControl is not fatal:
        returning None tells the copy path to activate the calibrated
        result_first_row immediately.

        Deliberately do not take another full UIA snapshot after timeout.
        The same descendant traversal is the operation that may be failing
        to materialize, so repeating it here can make recovery slower.
        """
        deadline = time.monotonic() + max(float(timeout), 0.0)
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                fallback_candidates: list[BaseWrapper] = []

                for control in execution_window.descendants():
                    try:
                        info = control.element_info
                        automation_id = normalize_text(
                            info.automation_id or ""
                        )

                        if (
                            automation_id
                            == RESULTS_GRID_AUTOMATION_ID
                        ):
                            log(
                                "Found MetaStock result DataGrid by "
                                f"AutomationId="
                                f"{RESULTS_GRID_AUTOMATION_ID!r}; "
                                f"expected_rows={expected_count}."
                            )
                            return control

                        control_type = normalize_text(
                            info.control_type or ""
                        )
                        class_name = normalize_text(
                            info.class_name or ""
                        )
                        combined = (
                            f"{control_type} {class_name}"
                        ).casefold()

                        if (
                            control_type == "DataGrid"
                            or "datagrid" in combined
                        ):
                            fallback_candidates.append(
                                control
                            )

                    except Exception:
                        continue

                if len(fallback_candidates) == 1:
                    log(
                        "Found one MetaStock DataGrid through "
                        "control-type fallback."
                    )
                    return fallback_candidates[0]

            except Exception as exc:
                last_error = exc

            time.sleep(poll_interval)

        log(
            "Results (N) is available, but the lower MetaStock result "
            "DataGrid did not materialize through UIA within "
            f"{timeout:.2f} seconds. "
            "Skipping further grid UIA inspection and switching to the "
            "calibrated result_first_row recovery path. "
            f"expected_rows={expected_count}; "
            f"last UIA error={last_error}"
        )
        return None

    def _copy_full_results_table(
        self,
        *,
        execution_window: BaseWrapper,
        grid: Optional[BaseWrapper],
        expected_count: int,
    ) -> tuple[
        dict[int, str],
        list[ExplorationResultRow],
    ]:
        previous_clipboard = self._read_clipboard_safely()
        started_at = time.monotonic()
        deadline = started_at + self.clipboard_timeout
        fallback_at = (
            started_at
            + self.result_row_fallback_delay
        )
        last_error: Exception | None = None
        last_row_count: int | None = None
        attempt = 0
        result_row_fallback_attempted = False
        result_row_fallback_active = False

        # If Results (N) exists but the grid never materialized through UIA,
        # do not spend another fallback-delay interval retrying UIA. The
        # calibrated point exists specifically for this condition.
        if grid is None:
            result_row_fallback_attempted = True
            result_row_fallback_active = (
                self._click_result_window_relative_calibrated_first_row(
                    execution_window=execution_window,
                    reason=(
                        "Results (N) was found, but ResultsGridControl "
                        "did not materialize through UIA."
                    ),
                )
            )

            if not result_row_fallback_active:
                raise RuntimeError(
                    "Results (N) was found, but the MetaStock result grid "
                    "did not materialize through UIA and the calibrated "
                    "result_first_row fallback is unavailable. "
                    "Re-run coordinate calibration with a completed "
                    "Exploration Execution result window open."
                )

        try:
            while time.monotonic() < deadline:
                attempt += 1
                sentinel = (
                    "__METASTOCK_RESULT_COPY_PENDING_"
                    f"{time.time_ns()}__"
                )

                try:
                    pyperclip.copy(sentinel)
                    now = time.monotonic()

                    # Existing delayed fallback remains useful when UIA found
                    # the grid and activated it, but Ctrl+A/C still has not
                    # produced the complete result table.
                    if (
                        grid is not None
                        and not result_row_fallback_attempted
                        and now >= fallback_at
                    ):
                        result_row_fallback_attempted = True
                        result_row_fallback_active = (
                            self._click_result_window_relative_calibrated_first_row(
                                execution_window=execution_window,
                                reason=(
                                    "The UIA result grid was found, but "
                                    "complete result-table copying did not "
                                    "succeed within the fallback delay."
                                ),
                            )
                        )

                    if not result_row_fallback_active:
                        if grid is None:
                            raise RuntimeError(
                                "Internal result-capture state error: the "
                                "UIA grid is unavailable and the calibrated "
                                "result-row fallback is not active."
                            )

                        try:
                            self._activate_results_grid(
                                execution_window=execution_window,
                                grid=grid,
                            )

                        except Exception as activation_error:
                            # A materialized wrapper that cannot be activated is
                            # another UIA failure mode. Recover immediately rather
                            # than waiting for the delayed copy fallback.
                            if not result_row_fallback_attempted:
                                result_row_fallback_attempted = True
                                result_row_fallback_active = (
                                    self._click_result_window_relative_calibrated_first_row(
                                        execution_window=execution_window,
                                        reason=(
                                            "The result grid materialized "
                                            "through UIA, but UIA activation "
                                            f"failed: {activation_error}"
                                        ),
                                    )
                                )

                            if not result_row_fallback_active:
                                raise

                    send_keys("^a", pause=0.05)
                    time.sleep(self.event_dispatch_delay)
                    send_keys("^c", pause=0.05)

                    copy_wait_deadline = deadline

                    if not result_row_fallback_attempted:
                        copy_wait_deadline = min(
                            deadline,
                            fallback_at,
                        )

                    clipboard_text = (
                        self._wait_for_copied_table_text(
                            sentinel=sentinel,
                            deadline=copy_wait_deadline,
                        )
                    )

                    headers, rows = self._parse_copied_table(
                        clipboard_text
                    )
                    last_row_count = len(rows)

                    if last_row_count == expected_count:
                        log(
                            "Copied full MetaStock result table "
                            f"on attempt {attempt}: "
                            f"{last_row_count} rows."
                        )
                        return headers, rows

                    last_error = RuntimeError(
                        "Copied result row count does not match "
                        "Results (N). "
                        f"expected={expected_count}, "
                        f"copied={last_row_count}"
                    )

                except Exception as exc:
                    last_error = exc

                time.sleep(self.poll_interval)

        finally:
            if self.preserve_existing_clipboard:
                self._restore_clipboard_safely(
                    previous_clipboard
                )

        raise RuntimeError(
            "Could not copy the complete MetaStock result table "
            "with Ctrl+A / Ctrl+C within "
            f"{self.clipboard_timeout:.1f} seconds. "
            f"Expected rows={expected_count}, "
            f"last copied rows={last_row_count}, "
            f"uia_grid_available={grid is not None}, "
            f"result-row fallback attempted="
            f"{result_row_fallback_attempted}, "
            f"result-row fallback active="
            f"{result_row_fallback_active}, "
            f"last error={last_error}"
        )

    def _click_result_window_relative_calibrated_first_row(
        self,
        *,
        execution_window: BaseWrapper,
        reason: str = (
            "UIA result-grid activation/copy did not complete."
        ),
    ) -> bool:
        # Use an exact pixel offset from the current result window.
        # Do not normalize, scale, or call CoordinateMapper.resolve().
        mapper = self.coordinate_mapper

        if mapper is None:
            log(
                "Result first-row fallback is unavailable because no "
                "calibration profile is loaded."
            )
            return False

        point = mapper.profile.points.get(
            RESULT_FIRST_ROW_CALIBRATION_POINT
        )

        if point is None:
            log(
                "Result first-row fallback is unavailable because the "
                "active profile has no 'result_first_row' point."
            )
            return False

        rectangle = execution_window.rectangle()
        offset_x = int(point.window_relative_x)
        offset_y = int(point.window_relative_y)
        x = int(rectangle.left) + offset_x
        y = int(rectangle.top) + offset_y

        if not (
            rectangle.left <= x <= rectangle.right
            and rectangle.top <= y <= rectangle.bottom
        ):
            log(
                "Result first-row fallback is unavailable because the "
                "stored result-window-relative offset falls outside the "
                "current Exploration Execution window. Re-run calibration."
            )
            return False

        log(
            "Using calibrated first result-row fallback. "
            f"Reason: {reason} "
            "Clicking once relative to the result window: "
            f"offset=({offset_x},{offset_y}), absolute=({x},{y}); "
            "then selecting all."
        )

        mouse_click(
            button="left",
            coords=(x, y),
        )
        time.sleep(
            max(self.event_dispatch_delay, 0.05)
        )
        return True

    def _activate_results_grid(
        self,
        *,
        execution_window: BaseWrapper,
        grid: BaseWrapper,
    ) -> None:
        try:
            execution_window.set_focus()
        except Exception:
            pass

        data_panel: BaseWrapper | None = None

        for control in safe_descendants(grid):
            try:
                info = control.element_info
                automation_id = normalize_text(
                    info.automation_id or ""
                )
                name = normalize_text(info.name or "")

                if (
                    automation_id == "dataPresenter"
                    or name == "DataPanel"
                ):
                    data_panel = control
                    break

            except Exception:
                continue

        target = data_panel or grid

        try:
            rectangle = target.rectangle()
            width = max(int(rectangle.width()), 1)
            height = max(int(rectangle.height()), 1)

            x = max(1, min(50, width - 2))
            y = max(1, min(20, height - 2))

            target.click_input(coords=(x, y))
            time.sleep(
                max(self.event_dispatch_delay, 0.05)
            )
            return

        except Exception as click_error:
            try:
                grid.set_focus()
                time.sleep(
                    max(self.event_dispatch_delay, 0.05)
                )
                return

            except Exception as focus_error:
                raise RuntimeError(
                    "Could not activate the MetaStock result "
                    "grid. "
                    f"click_error={click_error}; "
                    f"focus_error={focus_error}"
                ) from focus_error

    def _wait_for_copied_table_text(
        self,
        *,
        sentinel: str,
        deadline: float,
    ) -> str:
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                value = pyperclip.paste()

                if (
                    isinstance(value, str)
                    and value != sentinel
                    and value.strip()
                ):
                    return value

            except Exception as exc:
                last_error = exc

            time.sleep(self.poll_interval)

        raise RuntimeError(
            "Ctrl+C did not publish result-table text to the "
            "clipboard. "
            f"Last clipboard error: {last_error}"
        )

    def _parse_copied_table(
        self,
        clipboard_text: str,
    ) -> tuple[
        dict[int, str],
        list[ExplorationResultRow],
    ]:
        cleaned_text = (
            clipboard_text
            .replace("\x00", "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip("\n")
        )

        if "\t" not in cleaned_text:
            raise RuntimeError(
                "MetaStock Ctrl+C did not return a "
                "tab-separated result table. "
                f"Clipboard preview={cleaned_text[:300]!r}"
            )

        reader = csv.reader(
            io.StringIO(cleaned_text),
            delimiter="\t",
        )
        raw_rows: list[list[str]] = []

        for raw_row in reader:
            row = [cell.strip() for cell in raw_row]

            while row and not row[-1]:
                row.pop()

            if any(row):
                raw_rows.append(row)

        if not raw_rows:
            raise RuntimeError(
                "MetaStock copied an empty result table."
            )

        raw_headers = raw_rows[0]

        if not raw_headers:
            raise RuntimeError(
                "MetaStock copied a result table without "
                "headers."
            )

        headers = {
            column_index: self._normalize_copied_header(
                header=header,
                column_index=column_index,
            )
            for column_index, header
            in enumerate(raw_headers)
        }

        header_names = set(headers.values())

        if (
            "instrument_name" not in header_names
            or "symbol" not in header_names
        ):
            raise RuntimeError(
                "Copied table is not the MetaStock result "
                "table because required headers are absent. "
                f"Raw headers={raw_headers!r}; "
                f"normalized headers={headers!r}"
            )

        rows: list[ExplorationResultRow] = []

        for row_index, raw_row in enumerate(
            raw_rows[1:]
        ):
            row = list(raw_row)

            if len(row) < len(raw_headers):
                row.extend(
                    [""] * (
                        len(raw_headers) - len(row)
                    )
                )

            if len(row) > len(raw_headers):
                extra_values = row[len(raw_headers):]

                if any(extra_values):
                    raise RuntimeError(
                        "A copied MetaStock result row has "
                        "more values than the header row. "
                        f"row_index={row_index}, "
                        f"headers={raw_headers!r}, "
                        f"row={raw_row!r}"
                    )

                row = row[:len(raw_headers)]

            values_by_column = {
                column_index: value
                for column_index, value
                in enumerate(row)
            }
            values_by_name = {
                headers[column_index]: value
                for column_index, value
                in enumerate(row)
            }

            rows.append(
                ExplorationResultRow(
                    row_index=row_index,
                    values_by_column=values_by_column,
                    values_by_name=values_by_name,
                )
            )

        return headers, rows

    @staticmethod
    def _normalize_copied_header(
        *,
        header: str,
        column_index: int,
    ) -> str:
        normalized = re.sub(
            r"[^a-z0-9]+",
            "",
            header.casefold(),
        )

        if normalized in {
            "instrument",
            "instrumentname",
            "security",
            "securityname",
            "stock",
            "stockname",
        }:
            return "instrument_name"

        if normalized == "symbol":
            return "symbol"

        column_match = re.fullmatch(
            r"(?:column)?([a-j])",
            normalized,
            re.IGNORECASE,
        )

        if column_match is not None:
            return (
                "column_"
                + column_match.group(1).upper()
            )

        fallback = re.sub(
            r"[^a-z0-9]+",
            "_",
            header.casefold(),
        ).strip("_")

        return fallback or f"column_{column_index}"

    @staticmethod
    def _read_clipboard_safely() -> str | None:
        try:
            value = pyperclip.paste()

            if isinstance(value, str):
                return value

        except Exception:
            pass

        return None

    @staticmethod
    def _restore_clipboard_safely(
        previous_value: str | None,
    ) -> None:
        if previous_value is None:
            return

        try:
            pyperclip.copy(previous_value)
        except Exception as exc:
            log(
                "Warning: could not restore the previous "
                "clipboard contents after result scraping: "
                f"{exc}"
            )

    @staticmethod
    def _control_text_candidates(
        control: BaseWrapper,
    ) -> list[str]:
        candidates: list[str] = []

        try:
            info = control.element_info

            for value in (
                info.name,
                info.automation_id,
            ):
                normalized = normalize_text(value or "")

                if normalized:
                    candidates.append(normalized)

        except Exception:
            pass

        try:
            text = normalize_text(
                control.window_text() or ""
            )

            if text:
                candidates.append(text)

        except Exception:
            pass

        return list(dict.fromkeys(candidates))

    def _log_result_surface_snapshot(
        self,
        execution_window: BaseWrapper,
    ) -> None:
        snapshot: list[tuple[str, str, str]] = []

        for control in safe_descendants(
            execution_window
        ):
            try:
                info = control.element_info
                snapshot.append(
                    (
                        normalize_text(
                            info.control_type or ""
                        ),
                        normalize_text(info.name or ""),
                        normalize_text(
                            info.automation_id or ""
                        ),
                    )
                )
            except Exception:
                continue

        log(
            "Exploration result UIA snapshot: "
            f"{snapshot[:120]}"
        )
