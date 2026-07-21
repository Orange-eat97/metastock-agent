# ui_actions.py

from __future__ import annotations

import time
from typing import Optional

import pyperclip
from pywinauto import mouse
from pywinauto.base_wrapper import BaseWrapper
from pywinauto.keyboard import send_keys

from ui_interacter.coordinate_calibration import CoordinateMapper
from ui_interacter.ui_core import log, rect_center


class UiActions:
    def __init__(
        self,
        click_settle_delay: float = 0.03,
        text_settle_delay: float = 0.08,
        key_delay: float = 0.01,
        coordinate_mapper: Optional[CoordinateMapper] = None,
    ) -> None:
        self.click_settle_delay = click_settle_delay
        self.text_settle_delay = text_settle_delay
        self.key_delay = key_delay
        self.coordinate_mapper = coordinate_mapper

    def click_control(
        self,
        ctrl: BaseWrapper,
        label: str = "control",
    ) -> None:
        x, y = rect_center(ctrl)

        log(f"Clicking {label} at ({x}, {y})")

        ctrl.click_input()

        # Only allow Windows to dispatch the input event.
        # The caller must wait for the expected UI state.
        time.sleep(self.click_settle_delay)

    def invoke_or_click(
        self,
        ctrl: BaseWrapper,
        label: str = "control",
    ) -> None:
        """
        Prefer UIA InvokePattern and fall back to physical input.

        This method performs only a tiny event-dispatch wait.
        Business-level state changes must be verified by callers.
        """
        try:
            log(f"Invoking {label}")
            ctrl.invoke()
            time.sleep(self.click_settle_delay)
            return

        except Exception:
            self.click_control(
                ctrl,
                label,
            )

    def has_calibrated_point(
        self,
        point_name: str | None,
    ) -> bool:
        return (
            self.coordinate_mapper is not None
            and bool(point_name)
            and point_name in self.coordinate_mapper.profile.points
        )

    def resolve_calibrated_point(
        self,
        *,
        main: BaseWrapper,
        point_name: str,
    ) -> tuple[int, int]:
        if self.coordinate_mapper is None:
            raise RuntimeError(
                "No coordinate calibration profile is loaded."
            )

        return self.coordinate_mapper.resolve(
            main=main,
            point_name=point_name,
        )

    def click_point(
        self,
        x: int,
        y: int,
        label: str = "point",
        *,
        main: Optional[BaseWrapper] = None,
        calibration_point_name: Optional[str] = None,
    ) -> None:
        """
        Click an existing coordinate fallback point.

        Calibration can replace only coordinates supplied by the caller's
        existing fallback branch. It never selects a semantic UI target.
        """
        used_calibration = False

        if (
            main is not None
            and calibration_point_name
            and self.has_calibrated_point(calibration_point_name)
        ):
            x, y = self.resolve_calibrated_point(
                main=main,
                point_name=calibration_point_name,
            )
            used_calibration = True

        suffix = " [calibrated]" if used_calibration else ""
        log(f"Clicking {label}{suffix} at ({x}, {y})")

        mouse.click(
            button="left",
            coords=(x, y),
        )

        time.sleep(self.click_settle_delay)

    def paste_text(
        self,
        ctrl: BaseWrapper,
        text: str,
        label: str = "text field",
    ) -> None:
        """
        Paste text with minimal keyboard-event delays.

        The caller must wait for the resulting filtered list,
        selected count, dialog, or other expected state.
        """
        log(f"Pasting into {label}: {text!r}")

        ctrl.click_input()
        time.sleep(self.click_settle_delay)

        pyperclip.copy(text)

        send_keys(
            "^a",
            pause=self.key_delay,
        )
        send_keys(
            "{BACKSPACE}",
            pause=self.key_delay,
        )
        send_keys(
            "^v",
            pause=self.key_delay,
        )

        # WPF text binding/filtering usually needs slightly longer
        # than a normal button click.
        time.sleep(self.text_settle_delay)

    def click_checkbox_in_row(
        self,
        row: BaseWrapper,
        label: str,
        x_offset: int = 22,
    ) -> None:
        """
        Controlled coordinate fallback for rows whose checkbox
        is not exposed through UIA.
        """
        rectangle = row.rectangle()

        x = rectangle.left + x_offset
        y = (
            rectangle.top
            + rectangle.bottom
        ) // 2

        log(
            f"Fallback clicking checkbox in {label} row "
            f"using rect=("
            f"{rectangle.left},"
            f"{rectangle.top},"
            f"{rectangle.right},"
            f"{rectangle.bottom}), "
            f"point=({x},{y})"
        )

        mouse.click(
            button="left",
            coords=(x, y),
        )

        time.sleep(self.click_settle_delay)