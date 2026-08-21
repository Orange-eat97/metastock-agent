from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from pywinauto.base_wrapper import BaseWrapper

from ui_interacter.ui_actions import UiActions
from ui_interacter.explore_selectors import ExploreSelectors
from ui_interacter.ui_core import log, normalize_text
from ui_interacter.state_readers import get_instruments_selected_total


@dataclass(frozen=True)
class InstrumentState:
    row: BaseWrapper
    checkbox: Optional[BaseWrapper]
    toggle_state: Optional[int]
    count: Optional[tuple[int, int]]

    @property
    def count_is_full(self) -> bool:
        if self.count is None:
            return False
        selected, total = self.count
        return total > 0 and selected == total

    @property
    def count_is_unchecked(self) -> bool:
        if self.count is None:
            return False
        selected, total = self.count
        return total > 0 and selected == 0

    @property
    def count_is_partial(self) -> bool:
        if self.count is None:
            return False
        selected, total = self.count
        return total > 0 and 0 < selected < total

    @property
    def toggle_is_checked(self) -> bool:
        return self.toggle_state == 1

    @property
    def toggle_is_unchecked(self) -> bool:
        return self.toggle_state == 0

    @property
    def toggle_is_partial(self) -> bool:
        return self.toggle_state == 2

    @property
    def definitely_full(self) -> bool:
        """
        Important safety rule:
        If either reliable signal says fully selected, do not click.

        This prevents:
            already checked -> accidental uncheck -> recheck
        """
        return self.toggle_is_checked or self.count_is_full

    @property
    def definitely_unchecked(self) -> bool:
        """
        Only treat as unchecked if no signal says full.
        """
        if self.definitely_full:
            return False

        if self.toggle_is_unchecked:
            return True

        if self.toggle_state is None and self.count_is_unchecked:
            return True

        return False

    @property
    def definitely_partial(self) -> bool:
        """
        Only treat as partial if no signal says full.
        """
        if self.definitely_full:
            return False

        if self.toggle_is_partial:
            return True

        if self.toggle_state is None and self.count_is_partial:
            return True

        return False


@dataclass(frozen=True)
class NamedInstrumentState:
    row: BaseWrapper
    checkbox: Optional[BaseWrapper]
    label: str
    toggle_state: Optional[int]

    @property
    def selected(self) -> bool:
        return self.toggle_state == 1

    @property
    def unchecked(self) -> bool:
        return self.toggle_state == 0

class InstrumentSelector:
    """
    Owns instrument selection.

    Current supported behavior:
    - ensure the broad Instruments parent row is fully selected.

    Safety principle:
    - Never click if checkbox/count already indicates selected.
    - Never click if state is unknown.
    """

    def __init__(
        self,
        actions: UiActions,
        selectors: ExploreSelectors,
        medium_delay: float = 0.35,
    ):
        self.actions = actions
        self.selectors = selectors
        self.medium_delay = medium_delay

    # ============================================================
    # PUBLIC API
    # ============================================================

    def ensure_all_selected(self, main: BaseWrapper) -> None:
        """
        Ensure Instruments is selected.

        Fixed behavior:
        - If already selected, do nothing.
        - If unchecked, click once and verify.
        - If partial, click and verify; if it becomes unchecked, click once more.
        - If state cannot be read, refuse to toggle blindly.
        """
        try:
            before = self.read_state(main)

            log(f"Instruments checkbox toggle state before: {before.toggle_state}")
            log(f"Instruments selected count before: {before.count}")

            # Critical guard.
            if before.definitely_full:
                log("Instruments already fully selected. Proceeding without clicking.")
                return

            if before.definitely_unchecked:
                log("Instruments is unchecked. Clicking once to select all...")
                self.click_instruments_checkbox(before)

                after = self.wait_for_state_change(
                    main,
                    before,
                )
                log(f"Instruments checkbox toggle state after click: {after.toggle_state}")
                log(f"Instruments selected count after click: {after.count}")

                if after.definitely_full:
                    log("Instruments is now fully selected.")
                    return

                raise RuntimeError(
                    "Clicked unchecked Instruments, but it did not become fully selected. "
                    f"BeforeToggle={before.toggle_state}, BeforeCount={before.count}, "
                    f"AfterToggle={after.toggle_state}, AfterCount={after.count}"
                )

            if before.definitely_partial:
                log(
                    "Instruments is partially selected. "
                    "Clicking once and re-scanning state..."
                )

                self.click_instruments_checkbox(before)

                after_first = self.wait_for_state_change(
                    main,
                    before,
                )
                log(f"Instruments toggle state after first partial click: {after_first.toggle_state}")
                log(f"Instruments selected count after first partial click: {after_first.count}")

                if after_first.definitely_full:
                    log("Instruments is now fully selected.")
                    return

                if after_first.definitely_unchecked:
                    log(
                        "Partial-state click changed Instruments to unchecked. "
                        "Clicking once more to select all..."
                    )

                    self.click_instruments_checkbox(after_first)

                    after_second = self.wait_for_state_change(
                        main,
                        after_first,
                    )

                    log(f"Instruments toggle state after second click: {after_second.toggle_state}")
                    log(f"Instruments selected count after second click: {after_second.count}")

                    if after_second.definitely_full:
                        log("Instruments is now fully selected.")
                        return

                    raise RuntimeError(
                        "Second click did not fully select Instruments. "
                        f"BeforeToggle={before.toggle_state}, BeforeCount={before.count}, "
                        f"AfterFirstToggle={after_first.toggle_state}, AfterFirstCount={after_first.count}, "
                        f"AfterSecondToggle={after_second.toggle_state}, AfterSecondCount={after_second.count}"
                    )

                raise RuntimeError(
                    "Instruments remained not fully selected after partial-state click. "
                    f"BeforeToggle={before.toggle_state}, BeforeCount={before.count}, "
                    f"AfterFirstToggle={after_first.toggle_state}, AfterFirstCount={after_first.count}"
                )

            raise RuntimeError(
                "Could not determine Instruments state safely. "
                "Refusing to toggle blindly. "
                f"ToggleState={before.toggle_state}, Count={before.count}"
            )

        except Exception as e:
            raise RuntimeError(
                f"Failed to ensure Instruments is checked without blind toggling: {e}"
            )

    def select_named(
        self,
        main: BaseWrapper,
        instrument_names: list[str],
    ) -> None:
        """
        Replace the current selection with exactly the requested named rows.

        Matching is whitespace-normalized, case-insensitive exact equality.
        Unknown or ambiguous rows fail safely instead of being guessed.
        """
        requested = self._normalize_requested_names(instrument_names)

        if not requested:
            raise ValueError(
                "At least one named instrument, exchange, "
                "or custom list is required."
            )

        self.ensure_none_selected(main)
        self.expand_instruments_tree(main)

        selected_labels: list[str] = []

        for requested_name in requested:
            before = self.read_named_state(main, requested_name)

            log(
                "Named instrument state before selection: "
                f"requested={requested_name!r}, "
                f"matched={before.label!r}, "
                f"toggle={before.toggle_state}"
            )

            if before.selected:
                selected_labels.append(before.label)
                continue

            if not before.unchecked:
                raise RuntimeError(
                    "Could not determine the checkbox state for "
                    f"instrument {before.label!r}. Refusing to "
                    "toggle it blindly."
                )

            self.click_named_checkbox(before)

            after = self.wait_for_named_state_change(
                main,
                requested_name,
                before_toggle_state=before.toggle_state,
            )

            if not after.selected:
                raise RuntimeError(
                    "The named instrument did not become selected: "
                    f"requested={requested_name!r}, "
                    f"matched={after.label!r}, "
                    f"toggle={after.toggle_state}"
                )

            selected_labels.append(after.label)

        parent_after = self.read_state(main)

        if parent_after.count is not None:
            selected_count, _ = parent_after.count

            if selected_count != len(selected_labels):
                raise RuntimeError(
                    "MetaStock selected-count verification failed "
                    "after named selection. "
                    f"Requested={len(selected_labels)}, "
                    f"MetaStockSelected={selected_count}, "
                    f"Labels={selected_labels}"
                )

        log(
            "Named instrument selection completed: "
            + ", ".join(selected_labels)
        )

    def ensure_none_selected(self, main: BaseWrapper) -> None:
        """Clear the aggregate selection before selecting named rows."""
        before = self.read_state(main)

        if before.definitely_unchecked:
            log("No instruments are currently selected.")
            return

        if not (before.definitely_full or before.definitely_partial):
            raise RuntimeError(
                "Could not determine the aggregate Instruments "
                "state safely. Refusing to clear it blindly. "
                f"ToggleState={before.toggle_state}, Count={before.count}"
            )

        self.click_instruments_checkbox(before)
        after_first = self.wait_for_state_change(main, before)

        if after_first.definitely_unchecked:
            log("Cleared the current instrument selection.")
            return

        if after_first.definitely_full:
            self.click_instruments_checkbox(after_first)
            after_second = self.wait_for_state_change(main, after_first)

            if after_second.definitely_unchecked:
                log("Cleared the current instrument selection.")
                return

            raise RuntimeError(
                "The second aggregate Instruments click did not clear "
                f"the selection. AfterSecond={after_second.count}"
            )

        raise RuntimeError(
            "The aggregate Instruments selection remained partial "
            "after clearing was attempted."
        )

    def expand_instruments_tree(self, main: BaseWrapper) -> BaseWrapper:
        root = self.selectors.find_instruments_tree_item(main)

        try:
            state = int(
                root.iface_expand_collapse.CurrentExpandCollapseState
            )
        except Exception:
            state = None

        if state in {1, 2, 3}:
            return root

        try:
            root.expand()
        except Exception:
            try:
                root.iface_expand_collapse.Expand()
            except Exception as exc:
                raise RuntimeError(
                    "Could not expand the Instruments UIA tree."
                ) from exc

        time.sleep(self.medium_delay)
        return self.selectors.find_instruments_tree_item(main)

    def read_named_state(
        self,
        main: BaseWrapper,
        requested_name: str,
    ) -> NamedInstrumentState:
        row, matched_label = self.find_named_instrument_row(
            main,
            requested_name,
        )
        checkbox = self.find_checkbox_inside_row(row)
        state_source = checkbox or row
        toggle_state = self.get_checkbox_toggle_state(state_source)

        return NamedInstrumentState(
            row=row,
            checkbox=checkbox,
            label=matched_label,
            toggle_state=toggle_state,
        )

    def find_named_instrument_row(
        self,
        main: BaseWrapper,
        requested_name: str,
    ) -> tuple[BaseWrapper, str]:
        root = self.expand_instruments_tree(main)
        target = normalize_text(requested_name).casefold()

        if not target:
            raise ValueError("Instrument names cannot be blank.")

        try:
            rows = root.descendants(control_type="TreeItem")
        except Exception:
            rows = []

        matches: list[tuple[BaseWrapper, str]] = []
        available_labels: list[str] = []

        for row in rows:
            labels = self._read_row_labels(row)

            for label in labels:
                if label not in available_labels:
                    available_labels.append(label)

                if label.casefold() == target:
                    matches.append((row, label))
                    break

        if not matches:
            preview = ", ".join(available_labels[:20])
            suffix = (
                f" Available visible labels: {preview}"
                if preview
                else ""
            )
            raise RuntimeError(
                "No exact instrument/list/exchange UIA row "
                f"matched {requested_name!r}.{suffix}"
            )

        unique: list[tuple[BaseWrapper, str]] = []
        seen: set[str] = set()

        for row, label in matches:
            try:
                runtime_key = repr(row.element_info.runtime_id)
            except Exception:
                runtime_key = f"{label.casefold()}:{row.rectangle()}"

            if runtime_key in seen:
                continue

            seen.add(runtime_key)
            unique.append((row, label))

        if len(unique) != 1:
            raise RuntimeError(
                "Instrument search is ambiguous. "
                f"Requested={requested_name!r}, "
                f"Matches={[label for _, label in unique]}"
            )

        return unique[0]

    def _read_row_labels(self, row: BaseWrapper) -> list[str]:
        raw_values: list[str] = []

        def add(value: object) -> None:
            cleaned = normalize_text(str(value or ""))

            if not cleaned:
                return

            lowered = cleaned.casefold()

            if lowered.startswith("selected:"):
                return

            if (
                "instrumentlisttypestvm" in lowered
                or lowered in {"treeviewitem", "checkbox"}
            ):
                return

            raw_values.append(cleaned)

        try:
            add(row.window_text())
        except Exception:
            pass

        try:
            add(row.element_info.name)
        except Exception:
            pass

        try:
            children = row.children()
        except Exception:
            children = []

        for child in children:
            try:
                add(child.window_text())
            except Exception:
                pass

            try:
                add(child.element_info.name)
            except Exception:
                pass

        labels: list[str] = []

        for value in raw_values:
            if value not in labels:
                labels.append(value)

        return labels

    def click_named_checkbox(self, state: NamedInstrumentState) -> None:
        if state.checkbox is not None:
            try:
                state.checkbox.toggle()
                return
            except Exception:
                self.actions.click_control(
                    state.checkbox,
                    f"instrument {state.label!r} checkbox",
                )
                return

        self.actions.click_checkbox_in_row(
            state.row,
            label=f"instrument {state.label!r}",
            x_offset=38,
        )

    def wait_for_named_state_change(
        self,
        main: BaseWrapper,
        requested_name: str,
        *,
        before_toggle_state: Optional[int],
        timeout: float = 1.5,
        poll_interval: float = 0.05,
    ) -> NamedInstrumentState:
        deadline = time.monotonic() + timeout
        latest = self.read_named_state(main, requested_name)

        while time.monotonic() < deadline:
            latest = self.read_named_state(main, requested_name)

            if latest.toggle_state != before_toggle_state:
                return latest

            time.sleep(poll_interval)

        return latest

    @staticmethod
    def _normalize_requested_names(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = normalize_text(str(value or ""))
            key = cleaned.casefold()

            if not cleaned or key in seen:
                continue

            seen.add(key)
            normalized.append(cleaned)

        return normalized

    # ============================================================
    # STATE READING
    # ============================================================

    def read_state(self, main: BaseWrapper) -> InstrumentState:
        """
        Always re-find the row before reading state.

        This matters because WPF rows can refresh after clicks.
        """
        item = self.selectors.find_instruments_tree_item(main)
        checkbox = self.find_checkbox_inside_row(item)
        toggle_state = (
            self.get_checkbox_toggle_state(checkbox)
            if checkbox is not None
            else None
        )
        count = get_instruments_selected_total(item)

        self.validate_count(count)

        return InstrumentState(
            row=item,
            checkbox=checkbox,
            toggle_state=toggle_state,
            count=count,
        )

    def validate_count(self, count: Optional[tuple[int, int]]) -> None:
        if count is None:
            return

        selected, total = count

        if total <= 0:
            raise RuntimeError(f"Invalid Instruments total count: {count}")

        if selected < 0:
            raise RuntimeError(f"Invalid Instruments selected count: {count}")

        if selected > total:
            raise RuntimeError(f"Invalid Instruments selected/total count: {count}")

    def find_checkbox_inside_row(self, row: BaseWrapper) -> Optional[BaseWrapper]:
        """
        Find a real CheckBox child inside a row, if UIA exposes it.
        """
        try:
            for child in row.children():
                try:
                    info = child.element_info
                    control_type = normalize_text(info.control_type or "")
                    class_name = normalize_text(info.class_name or "")

                    if control_type == "CheckBox" or "CheckBox" in class_name:
                        return child
                except Exception:
                    continue
        except Exception:
            pass

        try:
            for child in row.descendants():
                try:
                    info = child.element_info
                    control_type = normalize_text(info.control_type or "")
                    class_name = normalize_text(info.class_name or "")

                    if control_type == "CheckBox" or "CheckBox" in class_name:
                        return child
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def get_checkbox_toggle_state(self, checkbox: BaseWrapper) -> Optional[int]:
        """
        UIA ToggleState:
            0 = Off
            1 = On
            2 = Indeterminate / Partial

        Returns None if pywinauto cannot read the state.
        """
        if checkbox is None:
            return None

        try:
            pattern = checkbox.iface_toggle
            return int(pattern.CurrentToggleState)
        except Exception:
            pass

        try:
            return int(checkbox.get_toggle_state())
        except Exception:
            pass

        try:
            legacy = checkbox.legacy_properties()
            state = str(legacy.get("State", "")).lower()

            # Important:
            # Check "unchecked" before "checked", because "unchecked"
            # contains the substring "checked".
            if "unchecked" in state:
                return 0

            if "mixed" in state or "indeterminate" in state or "partial" in state:
                return 2

            if "checked" in state:
                return 1
        except Exception:
            pass

        return None
    
    def wait_for_state_change(
        self,
        main: BaseWrapper,
        before: InstrumentState,
        timeout: float = 0.8,
        poll_interval: float = 0.03,
    ) -> InstrumentState:
        """
        Wait until the Instruments toggle state or selected count changes.
        """
        deadline = time.monotonic() + timeout
        latest = before

        while time.monotonic() < deadline:
            latest = self.read_state(main)

            if (
                latest.toggle_state != before.toggle_state
                or latest.count != before.count
            ):
                return latest

            time.sleep(poll_interval)

        return latest

    # ============================================================
    # CLICKING
    # ============================================================

    def click_instruments_checkbox(
        self,
        state: InstrumentState,
    ) -> None:
        """
        Prefer TogglePattern and fall back to physical input.
        """
        if state.checkbox is not None:
            log(
                "Toggling real Instruments checkbox. "
                f"ToggleState before: {state.toggle_state}"
            )

            try:
                state.checkbox.toggle()
                return
            except Exception:
                self.actions.click_control(
                    state.checkbox,
                    "Instruments checkbox",
                )
                return

        log(
            "Could not find real Instruments checkbox. "
            "Using row-relative fallback click."
        )

        self.actions.click_checkbox_in_row(
            state.row,
            label="Instruments",
            x_offset=38,
        )