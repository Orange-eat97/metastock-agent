from __future__ import annotations

from typing import Optional

from pywinauto.base_wrapper import BaseWrapper

from ui_interacter.system_test_selectors import SystemTestSelectors
from ui_interacter.ui_actions import UiActions
from ui_interacter.ui_core import log, wait_until


class SystemTestConsole:
    """
    System Tester counterpart of ExploreConsole.

    The control flow is intentionally the same as ExploreConsole:
    - use the caption selector first;
    - use one main-window-relative vertical-tab fallback if absent;
    - try to verify the console by visible markers;
    - log and continue when the marker check is unavailable.
    """

    def __init__(
        self,
        actions: UiActions,
        selectors: SystemTestSelectors,
        system_test_load_timeout: float = 8,
        allow_start_fallback_click: bool = False,
        start_fallback_absolute_xy: Optional[
            tuple[int, int]
        ] = None,
    ):
        self.actions = actions
        self.selectors = selectors
        self.system_test_load_timeout = (
            system_test_load_timeout
        )
        self.allow_start_fallback_click = (
            allow_start_fallback_click
        )
        self.start_fallback_absolute_xy = (
            start_fallback_absolute_xy
        )

    def open(self, main: BaseWrapper) -> None:
        """
        Open System Tester using the same approach as ExploreConsole.open().
        """
        system_test = self.selectors.find_system_test_caption(
            main
        )

        if system_test is not None:
            self.actions.click_control(
                system_test,
                "SystemTest tab/caption",
            )
        else:
            rectangle = main.rectangle()

            # Inspected System Tester caption clickable point:
            # x=31, y=533 while MetaStock is maximized.
            # Keep the point relative to the main window, exactly like the
            # proven Explore fallback at main.left+28, main.top+390.
            x = rectangle.left + 31
            y = rectangle.top + 533

            self.actions.click_point(
                x,
                y,
                "SystemTest tab fallback",
            )

        log("Waiting for SystemTest Console to load...")

        def loaded():
            for text in [
                "All System Tests",
                "New System Test",
                "Start System Test",
            ]:
                if (
                    self.selectors.find_text_control_fuzzy(
                        main,
                        text,
                    )
                    is not None
                ):
                    return True
            return False

        try:
            wait_until(
                loaded,
                timeout=self.system_test_load_timeout,
                interval=0.2,
                error_msg=(
                    "SystemTest Console did not finish loading"
                ),
            )
            log("SystemTest Console loaded.")
        except Exception:
            log(
                "Could not verify SystemTest Console by text, "
                "continuing anyway."
            )

    def start(self, main: BaseWrapper) -> None:
        """
        Click Start System Test.
        """
        log("Searching for Start System Test button...")

        button = self.selectors.find_start_button(main)

        if button is not None:
            self.actions.click_control(
                button,
                "Start System Test button",
            )
            return

        if (
            self.allow_start_fallback_click
            and self.start_fallback_absolute_xy is not None
        ):
            x, y = self.start_fallback_absolute_xy
            self.actions.click_point(
                x,
                y,
                "Start System Test fallback",
            )
            return

        raise RuntimeError(
            "Could not find Start System Test button safely. "
            "Inspect the button name, or configure "
            "start_fallback_absolute_xy."
        )
