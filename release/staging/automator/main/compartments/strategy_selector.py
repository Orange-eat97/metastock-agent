# strategy_selector.py

from __future__ import annotations

import time

from pywinauto.base_wrapper import BaseWrapper

from ui_interacter.ui_actions import UiActions
from ui_interacter.explore_selectors import ExploreSelectors
from ui_interacter.ui_core import (
    log,
    normalize_text,
    wait_until,
    wait_until_stable,
)
from ui_interacter.state_readers import (
    get_selected_count,
    get_selected_count_text,
    parse_selected_count,
)


STRATEGY_CHECKBOX_CALIBRATION_POINT = (
    "strategy_checkbox"
)
STRATEGY_FILTER_INITIAL_SETTLE_SECONDS = 0.35
STRATEGY_FILTER_RETRY_DELAY_SECONDS = 0.50
STRATEGY_FILTER_MAX_UIA_ATTEMPTS = 2
STRATEGY_CALIBRATED_CLICK_VERIFY_SECONDS = 2.0


class StrategySelector:
    """
    Owns strategy selection.

    This class contains the strategy-selection state machine:
    - read current search box
    - search target strategy if needed
    - locate the unique filtered strategy row
    - click the row's checkbox area
    - verify using Selected:n
    - repair if the click accidentally untoggled an already-selected strategy
    """

    def __init__(
        self,
        actions: UiActions,
        selectors: ExploreSelectors,
        search_filter_timeout: float = 2,
    ):
        self.actions = actions
        self.selectors = selectors
        # MetaStock updates its WPF filtered list asynchronously.
        # Two seconds was too aggressive on packaged beta runs.
        self.search_filter_timeout = max(
            float(search_filter_timeout),
            5.0,
        )

    def select(self, main: BaseWrapper, strategy_name: str) -> None:
        self.select_by_search(main, strategy_name)

    def get_search_combobox_text(self, search_box: BaseWrapper) -> str:
        """
        Read current SearchComboBox text.
        """
        try:
            return normalize_text(search_box.window_text())
        except Exception:
            pass

        try:
            return normalize_text(search_box.element_info.name or "")
        except Exception:
            return ""
        
    def strategy_search_matches(
        self,
        current_text: str,
        strategy_name: str,
    ) -> bool:
        current = normalize_text(
            current_text
        ).casefold()
        target = normalize_text(
            strategy_name
        ).casefold()

        if not current:
            return False

        return (
            current == target
            or target in current
            or current in target
        )

    def wait_for_strategy_list_after_search(self, main: BaseWrapper) -> None:
        """
        Wait until the strategy list view is available after using the search box.
        """
        def ready():
            try:
                lv = self.selectors.find_strategy_list_view(main)
                r = lv.rectangle()
                return r.width() > 250 and r.height() > 100
            except Exception:
                return False

        wait_until(
            ready,
            timeout=self.search_filter_timeout,
            interval=0.15,
            error_msg="Strategy list did not become ready after search",
        )

    def click_strategy_checkbox(
        self,
        main: BaseWrapper,
        strategy_name: str,
        row: BaseWrapper | None = None,
    ) -> None:
        """
        Click the checkbox area for the unique filtered strategy row.

        We do not match strategy_name against row text because Inspect.exe showed
        the searched display name is not exposed in UIA. The row exposes:
        - generic ExplorationVM name
        - HelpText strategy description

        If no real checkbox is exposed, click relative to the discovered ListBoxItem row.
        """
        if row is None:
            rows = self.selectors.find_filtered_strategy_rows(
                main
            )

            if not rows:
                raise RuntimeError(
                    "No Explorer row was returned by the "
                    "MetaStock search."
                )

            row = rows[0]

        checkbox = self.selectors.find_checkbox_in_row(row)

        if checkbox is not None:
            log(f"Clicking real checkbox for strategy {strategy_name!r}.")
            self.actions.click_control(
                checkbox,
                f"strategy checkbox: {strategy_name}",
            )
            return

        r = row.rectangle()
        log(
            f"Strategy row found but checkbox is not exposed through UIA. "
            f"Using row-relative checkbox click. "
            f"Row rect=({r.left},{r.top},{r.right},{r.bottom})"
        )

        # Inspect row example:
        # row rect={l:91 t:201 r:400 b:249}
        # old working checkbox point around x=108, y=221
        # offset ~= 17, so use 20.
        self.actions.click_checkbox_in_row(
            row,
            label=f"strategy {strategy_name!r}",
            x_offset=20,
        )

    def _select_with_calibrated_strategy_checkbox(
        self,
        *,
        main: BaseWrapper,
        strategy_name: str,
        cause: Exception,
    ) -> None:
        # Last-resort path for WPF states where the filtered row is visible
        # but neither the ListBoxItem nor its checkbox is exposed by UIA.
        point_name = (
            STRATEGY_CHECKBOX_CALIBRATION_POINT
        )

        selected_before = get_selected_count(main)

        if selected_before != 0:
            raise RuntimeError(
                "Cannot use the calibrated strategy-checkbox "
                "fallback unless Selected: 0 is verified. "
                f"Actual selected count: {selected_before}"
            ) from cause

        if not self.actions.has_calibrated_point(
            point_name
        ):
            raise RuntimeError(
                "No Explorer row or checkbox appeared through "
                "UIA within 2 seconds, and calibration point "
                f"{point_name!r} is not available. Re-run "
                "calibrate_coordinates.py for the active profile."
            ) from cause

        log(
            "No Explorer row or checkbox appeared through UIA "
            "within 2 seconds. Clicking the absolute calibrated "
            f"strategy checkbox for {strategy_name!r}."
        )

        self.actions.click_absolute_calibrated_point(
            point_name=point_name,
            label=(
                "filtered Explorer strategy checkbox "
                f"for {strategy_name!r}"
            ),
        )

        try:
            wait_until(
                lambda: (
                    get_selected_count(main) == 1
                ),
                timeout=(
                    STRATEGY_CALIBRATED_CLICK_VERIFY_SECONDS
                ),
                interval=0.10,
                error_msg=(
                    "Absolute calibrated strategy-checkbox "
                    "click did not produce Selected: 1"
                ),
            )
        except RuntimeError as click_error:
            selected_after = get_selected_count(main)

            raise RuntimeError(
                "No Explorer row or checkbox appeared through "
                "UIA, and the absolute calibrated strategy "
                "checkbox click failed verification. "
                "Expected Selected: 1, "
                f"actual={selected_after}"
            ) from click_error

        log(
            "Absolute calibrated strategy-checkbox click "
            "produced Selected: 1."
        )

    def select_by_search(
        self,
        main: BaseWrapper,
        strategy_name: str,
    ) -> None:
        """
        Deterministic strategy-selection sequence:

        1. Clear old search.
        2. Reset Selected count to zero.
        3. Search for the target strategy.
        4. Resolve the strategy List once.
        5. Use at most two UIA reads and accept only one unique row.
        6. Fall back to the calibrated checkbox if UIA cannot select.
        7. Require Selected count to become exactly one.
        """
        log(
            "Selecting strategy with clean-state workflow: "
            f"{strategy_name!r}"
        )

        self.clear_all_selected_strategies(
            main
        )

        search_box = (
            self.selectors.find_search_combobox(main)
        )

        self.actions.paste_text(
            search_box,
            strategy_name,
            label="explorer search box",
        )

        log(
            "Waiting for a unique MetaStock Explorer search result..."
        )

        filtered_target = None
        strategy_list = None
        last_row_count: int | None = None
        last_error: Exception | None = None

        try:
            strategy_list = (
                self.selectors.find_strategy_list_view(
                    main
                )
            )
        except Exception as exc:
            last_error = exc
            log(
                "Strategy-list discovery failed before the "
                "bounded UIA reads: "
                f"{type(exc).__name__}: {exc}"
            )

        if strategy_list is not None:
            time.sleep(
                STRATEGY_FILTER_INITIAL_SETTLE_SECONDS
            )

            for attempt in range(
                1,
                STRATEGY_FILTER_MAX_UIA_ATTEMPTS + 1,
            ):
                try:
                    rows = (
                        self.selectors
                        .find_filtered_strategy_rows(
                            main,
                            list_view=strategy_list,
                        )
                    )
                    last_row_count = len(rows)

                    if last_row_count == 1:
                        filtered_target = (
                            "row",
                            rows[0],
                        )
                        log(
                            "Explorer search produced one unique "
                            f"UIA row on attempt {attempt}."
                        )
                        break

                    if last_row_count == 0:
                        checkbox = (
                            self.selectors
                            .find_first_filtered_strategy_checkbox(
                                main,
                                list_view=strategy_list,
                            )
                        )

                        if checkbox is not None:
                            filtered_target = (
                                "checkbox",
                                checkbox,
                            )
                            log(
                                "Explorer search exposed one "
                                "checkbox but no ListBoxItem row."
                            )
                            break

                    log(
                        "Explorer UIA result is not uniquely "
                        f"selectable on attempt {attempt}: "
                        f"row_count={last_row_count}."
                    )

                except Exception as exc:
                    last_error = exc
                    log(
                        "Explorer UIA result read failed on "
                        f"attempt {attempt}: "
                        f"{type(exc).__name__}: {exc}"
                    )

                if (
                    attempt
                    < STRATEGY_FILTER_MAX_UIA_ATTEMPTS
                ):
                    time.sleep(
                        STRATEGY_FILTER_RETRY_DELAY_SECONDS
                    )

        if filtered_target is None:
            details = (
                "UIA did not produce exactly one Explorer row "
                "or one usable checkbox after the bounded "
                "attempts. "
                f"last_row_count={last_row_count}, "
                f"last_error={last_error!r}"
            )
            self._select_with_calibrated_strategy_checkbox(
                main=main,
                strategy_name=strategy_name,
                cause=RuntimeError(details),
            )
            return

        # Let the checkbox hit target settle after the last list update.
        time.sleep(0.25)

        selected_before = get_selected_count(main)

        if selected_before != 0:
            raise RuntimeError(
                "Expected zero selected strategies before "
                "selecting the filtered target. "
                f"Actual selected count: {selected_before}"
            )

        target_type, target_control = (
            filtered_target
        )

        if target_type == "checkbox":
            log(
                "Explorer row was not exposed as a "
                "ListBoxItem; clicking its first visible "
                "checkbox directly."
            )

            self.actions.click_control(
                target_control,
                label=(
                    "first filtered Explorer checkbox"
                ),
            )

        else:
            self.click_strategy_checkbox(
                main,
                strategy_name,
                row=target_control,
            )

        try:
            wait_until_stable(
                lambda: get_selected_count(main) == 1,
                timeout=1.5,
                interval=0.03,
                stable_reads=1,
                error_msg=(
                    "Selected strategy count did not "
                    "stabilize at one"
                ),
            )
        except RuntimeError as click_error:
            selected_after_uia_click = (
                get_selected_count(main)
            )

            if selected_after_uia_click == 1:
                log(
                    "UIA click produced Selected: 1 despite "
                    "the verification wait ending with an error."
                )
            elif selected_after_uia_click == 0:
                log(
                    "UIA target click did not select an Explorer. "
                    "Using the absolute calibrated checkbox as "
                    "the final fallback."
                )
                self._select_with_calibrated_strategy_checkbox(
                    main=main,
                    strategy_name=strategy_name,
                    cause=click_error,
                )
                return
            else:
                raise RuntimeError(
                    "UIA target click left an unsafe selected "
                    "strategy count. Expected 0 or 1, "
                    f"actual={selected_after_uia_click}"
                ) from click_error

        selected_after = get_selected_count(main)

        if selected_after != 1:
            raise RuntimeError(
                "Target Explorer selection could not be verified. "
                f"Expected Selected: 1, actual={selected_after}"
            )

        log(
            f"Strategy selected successfully: "
            f"{strategy_name!r}"
        )

    def clear_all_selected_strategies(
        self,
        main: BaseWrapper,
    ) -> None:
        """
        Establish Selected: 0 before searching.

        Uses TogglePattern directly and waits only for the selected
        count to change. This avoids spending 1.5 seconds waiting
        for zero when the first toggle has selected every Explorer.
        """
        search_box = (
            self.selectors.find_search_combobox(main)
        )

        current_search = (
            self.get_search_combobox_text(search_box)
        )

        if current_search:
            log(
                "Clearing previous Explorer search before "
                "resetting strategy selection."
            )

            self.actions.paste_text(
                search_box,
                "",
                label="clear explorer search box",
            )

            self.wait_for_strategy_list_after_search(
                main
            )

        selected_count = get_selected_count(main)

        if selected_count is None:
            raise RuntimeError(
                "Could not read Selected:n before clearing "
                "strategy selections."
            )

        if selected_count == 0:
            log(
                "Strategy selected count is already zero."
            )
            return

        log(
            "Resetting selected strategies. "
            f"Current selected count: {selected_count}"
        )

        for attempt in range(1, 3):
            selected_before = get_selected_count(main)

            if selected_before is None:
                raise RuntimeError(
                    "Could not read Selected:n before "
                    "toggling Select all."
                )

            checkbox = (
                self.selectors
                .find_strategy_select_all_checkbox(main)
            )

            log(
                "Toggling strategy Select all checkbox "
                f"(attempt {attempt})."
            )

            try:
                # Inspect.exe confirmed TogglePattern is available.
                checkbox.toggle()

            except Exception:
                # Keep physical click only as a fallback.
                self.actions.click_control(
                    checkbox,
                    label=(
                        "strategy Select all checkbox "
                        f"(attempt {attempt})"
                    ),
                )

            # Wait only until the selected count changes.
            # Do not wait specifically for zero on the first click,
            # because the first click may select every Explorer.
            try:
                wait_until(
                    lambda: (
                        get_selected_count(main) is not None
                        and get_selected_count(main)
                        != selected_before
                    ),
                    timeout=0.75,
                    interval=0.03,
                    error_msg=(
                        "Selected count did not change after "
                        "toggling Select all"
                    ),
                )
            except RuntimeError:
                # Inspect the final state below. A delayed or
                # unchanged UIA read should not immediately fail.
                pass

            selected_after = get_selected_count(main)

            log(
                "Selected count after Select all toggle "
                f"{attempt}: {selected_after}"
            )

            if selected_after == 0:
                log(
                    "All previous strategy selections "
                    "have been cleared."
                )
                return

            if selected_after is None:
                raise RuntimeError(
                    "Could not read Selected:n after "
                    "toggling Select all."
                )

        raise RuntimeError(
            "Could not reset selected strategies to zero "
            "after two Select all toggles."
        )
    
