from __future__ import annotations

from pywinauto.base_wrapper import BaseWrapper

from ui_interacter.system_test_selectors import SystemTestSelectors
from ui_interacter.ui_actions import UiActions
from ui_interacter.ui_core import (
    log,
    normalize_text,
    wait_until,
    wait_until_stable,
)
from ui_interacter.state_readers import get_selected_count


class SystemTestSelector:
    """
    System Tester counterpart of StrategySelector.

    The state machine is kept the same:
    - clear the previous search;
    - reset Selected:n to zero through Select all;
    - search for the requested name;
    - require exactly one filtered result;
    - click it;
    - verify Selected: 1.
    """

    def __init__(
        self,
        actions: UiActions,
        selectors: SystemTestSelectors,
        search_filter_timeout: float = 2,
    ):
        self.actions = actions
        self.selectors = selectors
        self.search_filter_timeout = search_filter_timeout

    def select(
        self,
        main: BaseWrapper,
        system_test_name: str,
    ) -> None:
        self.select_by_search(
            main,
            system_test_name,
        )

    def get_search_combobox_text(
        self,
        search_box: BaseWrapper,
    ) -> str:
        """
        Read current SearchComboBox text.
        """
        try:
            return normalize_text(search_box.window_text())
        except Exception:
            pass

        try:
            return normalize_text(
                search_box.element_info.name or ""
            )
        except Exception:
            return ""

    def system_test_search_matches(
        self,
        current_text: str,
        system_test_name: str,
    ) -> bool:
        """
        Return True when the current search contains the requested name.
        """
        current = normalize_text(current_text).lower()
        target = normalize_text(system_test_name).lower()

        if not current:
            return False

        return (
            current == target
            or target in current
            or current in target
        )

    def wait_for_system_test_list_after_search(
        self,
        main: BaseWrapper,
    ) -> None:
        """
        Wait until the System Tester list view is available after search.
        """
        def ready():
            try:
                list_view = (
                    self.selectors
                    .find_system_test_list_view(main)
                )
                rectangle = list_view.rectangle()
                return (
                    rectangle.width() > 250
                    and rectangle.height() > 100
                )
            except Exception:
                return False

        wait_until(
            ready,
            timeout=self.search_filter_timeout,
            interval=0.15,
            error_msg=(
                "System-test list did not become ready "
                "after search"
            ),
        )

    def click_system_test_checkbox(
        self,
        main: BaseWrapper,
        system_test_name: str,
    ) -> None:
        """
        Click the real checkbox exposed for the unique filtered system test.
        """
        checkbox = (
            self.selectors
            .find_unique_filtered_system_test_checkbox(main)
        )

        log(
            "Clicking real checkbox for system test "
            f"{system_test_name!r}."
        )
        self.actions.click_control(
            checkbox,
            f"system-test checkbox: {system_test_name}",
        )

    def select_by_search(
        self,
        main: BaseWrapper,
        system_test_name: str,
    ) -> None:
        """
        Deterministic System Tester selection sequence.

        1. Clear old search.
        2. Reset Selected count to zero.
        3. Search for the target system test.
        4. Require one unique filtered checkbox.
        5. Select it.
        6. Require Selected count to become exactly one.
        """
        log(
            "Selecting system test with clean-state workflow: "
            f"{system_test_name!r}"
        )

        self.clear_all_selected_system_tests(main)

        search_box = self.selectors.find_search_combobox(main)

        self.actions.paste_text(
            search_box,
            system_test_name,
            label="system-test search box",
        )

        log(
            "Waiting for one filtered System Tester checkbox..."
        )

        def unique_filtered_checkbox_ready():
            try:
                return (
                    self.selectors
                    .find_unique_filtered_system_test_checkbox(
                        main
                    )
                )
            except Exception:
                return None

        wait_until(
            unique_filtered_checkbox_ready,
            timeout=self.search_filter_timeout,
            interval=0.03,
            error_msg=(
                "A unique System Tester checkbox did not "
                "appear after searching"
            ),
        )

        selected_before = get_selected_count(main)

        if selected_before != 0:
            raise RuntimeError(
                "Expected zero selected system tests before "
                "selecting the filtered target. "
                f"Actual selected count: {selected_before}"
            )

        self.click_system_test_checkbox(
            main,
            system_test_name,
        )

        wait_until_stable(
            lambda: get_selected_count(main) == 1,
            timeout=1.5,
            interval=0.03,
            stable_reads=2,
            error_msg=(
                "Selected system-test count did not "
                "stabilize at one"
            ),
        )

        selected_after = get_selected_count(main)

        if selected_after != 1:
            raise RuntimeError(
                "Target System Test selection could not be "
                "verified. Expected Selected: 1, "
                f"actual={selected_after}"
            )

        log(
            "System test selected successfully: "
            f"{system_test_name!r}"
        )

    def clear_all_selected_system_tests(
        self,
        main: BaseWrapper,
    ) -> None:
        """
        Establish Selected: 0 before searching.

        This is the direct System Tester adaptation of
        StrategySelector.clear_all_selected_strategies().
        """
        search_box = self.selectors.find_search_combobox(main)

        current_search = self.get_search_combobox_text(
            search_box
        )

        if current_search:
            log(
                "Clearing previous System Tester search before "
                "resetting system-test selection."
            )

            self.actions.paste_text(
                search_box,
                "",
                label="clear system-test search box",
            )

            self.wait_for_system_test_list_after_search(main)

        selected_count = get_selected_count(main)

        if selected_count is None:
            raise RuntimeError(
                "Could not read Selected:n before clearing "
                "system-test selections."
            )

        if selected_count == 0:
            log(
                "System-test selected count is already zero."
            )
            return

        log(
            "Resetting selected system tests. "
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
                .find_system_test_select_all_checkbox(main)
            )

            log(
                "Toggling system-test Select all checkbox "
                f"(attempt {attempt})."
            )

            try:
                checkbox.toggle()
            except Exception:
                self.actions.click_control(
                    checkbox,
                    label=(
                        "system-test Select all checkbox "
                        f"(attempt {attempt})"
                    ),
                )

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
                pass

            selected_after = get_selected_count(main)

            log(
                "Selected count after Select all toggle "
                f"{attempt}: {selected_after}"
            )

            if selected_after == 0:
                log(
                    "All previous system-test selections "
                    "have been cleared."
                )
                return

            if selected_after is None:
                raise RuntimeError(
                    "Could not read Selected:n after "
                    "toggling Select all."
                )

        raise RuntimeError(
            "Could not reset selected system tests to zero "
            "after two Select all toggles."
        )
