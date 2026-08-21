from __future__ import annotations

import time
from typing import Optional

from pywinauto.base_wrapper import BaseWrapper

from system_test_definition import SystemTestCreationRequest
from ui_interacter.ui_core import (
    log,
    normalize_text,
    safe_descendants,
    wait_until,
)


class SystemTestCreator:
    """
    System Tester counterpart of ExplorerCreator.

    Responsibility:
        - click New System Test;
        - wait for System Editor;
        - fill General-tab fields;
        - define Buy Order and Sell Order formulas;
        - click OK.

    This class deliberately does not:
        - connect to MetaStock;
        - open the System Tester console;
        - select or run the System Test.
    """

    NAME_EDIT_ID = "11063"
    NOTES_EDIT_ID = "11067"
    LONG_ORDERS_ID = "11070"
    SINGLE_PORTFOLIO_ID = "11075"
    MULTIPLE_PORTFOLIO_ID = "11078"
    POSITION_LIMIT_ID = "11052"
    MAX_POSITIONS_ID = "11014"
    FORMULA_EDITOR_ID = "11081"
    OK_BUTTON_ID = "1"

    def __init__(
        self,
        actions,
        selectors=None,
        editor_load_timeout: int = 8,
        save_timeout: int = 10,
        tab_switch_delay: float = 0.35,
        formula_editor_timeout: int = 5,
    ) -> None:
        self.actions = actions
        self.selectors = selectors
        self.editor_load_timeout = editor_load_timeout
        self.save_timeout = save_timeout
        self.tab_switch_delay = tab_switch_delay
        self.formula_editor_timeout = formula_editor_timeout

    # ============================================================
    # PUBLIC API
    # ============================================================

    def create(
        self,
        main_window: BaseWrapper,
        request: SystemTestCreationRequest,
    ) -> None:
        request = request.normalized()

        log(
            f"Creating new system test: {request.name!r}"
        )

        editor = self._open_new_system_test_editor(
            main_window
        )

        name_field = self._find_control_by_auto_id(
            editor,
            self.NAME_EDIT_ID,
            control_type="Edit",
            label="system-test name",
        )
        notes_field = self._find_control_by_auto_id(
            editor,
            self.NOTES_EDIT_ID,
            control_type="Edit",
            label="system-test notes",
        )

        self.actions.paste_text(
            name_field,
            request.name,
            "system-test name",
        )
        self.actions.paste_text(
            notes_field,
            request.description,
            "system-test notes",
        )

        self._configure_general(editor, request)
        self._define_order_formulas(editor, request)
        self._save_editor(editor)

        log(
            f"System test created: {request.name!r}"
        )

    # ============================================================
    # OPEN EDITOR
    # ============================================================

    def _open_new_system_test_editor(
        self,
        main_window: BaseWrapper,
    ) -> BaseWrapper:
        new_button = self._find_new_system_test_button(
            main_window
        )

        self.actions.invoke_or_click(
            new_button,
            "New System Test button",
        )

        log("Waiting for System Editor window...")

        def find_editor() -> Optional[BaseWrapper]:
            try:
                editor = main_window.child_window(
                    title="System Editor",
                    control_type="Window",
                )

                if editor.exists(timeout=0.2):
                    return editor.wrapper_object()
            except Exception:
                pass

            for window in safe_descendants(
                main_window,
                control_type="Window",
            ):
                try:
                    name = normalize_text(
                        window.element_info.name or ""
                    )
                    text = normalize_text(
                        window.window_text()
                    )

                    if (
                        name == "System Editor"
                        or text == "System Editor"
                    ):
                        return window
                except Exception:
                    continue

            return None

        editor = wait_until(
            find_editor,
            timeout=self.editor_load_timeout,
            interval=0.2,
            error_msg="System Editor did not appear",
        )

        editor.set_focus()
        time.sleep(0.35)

        log("System Editor opened.")
        return editor

    def _find_new_system_test_button(
        self,
        main_window: BaseWrapper,
    ) -> BaseWrapper:
        log("Searching for New System Test button...")

        for button in safe_descendants(
            main_window,
            control_type="Button",
        ):
            try:
                name = normalize_text(
                    button.window_text()
                )
                info_name = normalize_text(
                    button.element_info.name or ""
                )

                if (
                    name == "New System Test"
                    or info_name == "New System Test"
                ):
                    log("Found New System Test button.")
                    return button
            except Exception:
                continue

        raise RuntimeError(
            "Could not find New System Test button."
        )

    # ============================================================
    # GENERAL TAB
    # ============================================================

    def _configure_general(
        self,
        editor: BaseWrapper,
        request: SystemTestCreationRequest,
    ) -> None:
        long_orders = self._find_control_by_auto_id(
            editor,
            self.LONG_ORDERS_ID,
            label="Long Orders radio",
        )
        self._ensure_selected(
            long_orders,
            "Long Orders radio",
        )

        if request.general.portfolio_bias == "single":
            portfolio_id = self.SINGLE_PORTFOLIO_ID
            portfolio_label = "Single portfolio radio"
        else:
            portfolio_id = self.MULTIPLE_PORTFOLIO_ID
            portfolio_label = "Multiple portfolio radio"

        portfolio = self._find_control_by_auto_id(
            editor,
            portfolio_id,
            label=portfolio_label,
        )
        self._ensure_selected(
            portfolio,
            portfolio_label,
        )

        position_limit = self._find_control_by_auto_id(
            editor,
            self.POSITION_LIMIT_ID,
            label="Position limit checkbox",
        )
        self._ensure_checked(
            position_limit,
            request.general.position_limit_enabled,
            "Position limit checkbox",
        )

        if request.general.position_limit_enabled:
            max_positions = self._find_control_by_auto_id(
                editor,
                self.MAX_POSITIONS_ID,
                control_type="Edit",
                label="maximum positions",
            )
            self.actions.paste_text(
                max_positions,
                str(request.general.max_positions),
                "maximum simultaneous positions",
            )

    def _find_control_by_auto_id(
        self,
        editor: BaseWrapper,
        auto_id: str,
        *,
        control_type: str | None = None,
        label: str,
    ) -> BaseWrapper:
        try:
            kwargs = {"auto_id": auto_id}
            if control_type is not None:
                kwargs["control_type"] = control_type

            spec = editor.child_window(**kwargs)

            if spec.exists(timeout=0.5):
                log(
                    f"Found {label} by AutomationId "
                    f"{auto_id}."
                )
                return spec.wrapper_object()
        except Exception:
            pass

        for control in safe_descendants(editor):
            try:
                info = control.element_info
                current_auto_id = normalize_text(
                    info.automation_id or ""
                )
                current_type = normalize_text(
                    info.control_type or ""
                )

                if current_auto_id != auto_id:
                    continue

                if (
                    control_type is not None
                    and current_type != control_type
                ):
                    continue

                log(
                    f"Found {label} in descendant scan by "
                    f"AutomationId {auto_id}."
                )
                return control
            except Exception:
                continue

        raise RuntimeError(
            f"Could not find {label} with "
            f"AutomationId={auto_id}."
        )

    # ============================================================
    # ORDER FORMULAS
    # ============================================================

    def _define_order_formulas(
        self,
        editor: BaseWrapper,
        request: SystemTestCreationRequest,
    ) -> None:
        definitions = [
            (
                "Buy Order",
                request.orders.buy.signal_formula,
            ),
            (
                "Sell Order",
                request.orders.sell.signal_formula,
            ),
        ]

        log(
            f"Defining {len(definitions)} system-test "
            "order formula(s)..."
        )

        for tab_name, formula in definitions:
            tab = self._find_order_tab(
                editor,
                tab_name,
            )

            log(f"Selecting {tab_name} tab...")
            self.actions.invoke_or_click(
                tab,
                f"{tab_name} tab",
            )
            time.sleep(self.tab_switch_delay)

            formula_editor = (
                self._wait_for_order_formula_editor(editor)
            )

            self.actions.paste_text(
                formula_editor,
                formula,
                f"{tab_name} formula",
            )

        log("Finished defining order formulas.")

    def _find_order_tab(
        self,
        editor: BaseWrapper,
        tab_name: str,
    ) -> BaseWrapper:
        target = normalize_text(tab_name)

        try:
            spec = editor.child_window(
                title=target,
                control_type="TabItem",
            )

            if spec.exists(timeout=0.5):
                return spec.wrapper_object()
        except Exception:
            pass

        for tab in safe_descendants(
            editor,
            control_type="TabItem",
        ):
            try:
                name = normalize_text(
                    tab.element_info.name or ""
                )
                text = normalize_text(tab.window_text())

                if (
                    name == target
                    or text == target
                ):
                    return tab
            except Exception:
                continue

        raise RuntimeError(
            f"Could not find {tab_name!r} tab."
        )

    def _wait_for_order_formula_editor(
        self,
        editor: BaseWrapper,
    ) -> BaseWrapper:
        return wait_until(
            lambda: self._find_order_formula_editor(editor),
            timeout=self.formula_editor_timeout,
            interval=0.15,
            error_msg=(
                "Order formula editor did not become available"
            ),
        )

    def _find_order_formula_editor(
        self,
        editor: BaseWrapper,
    ) -> Optional[BaseWrapper]:
        """
        Find the active inspected formula editor.

        Buy Order and Sell Order both expose a newly created visible Document
        with AutomationId 11081 and ClassName Edit, so reacquire it after every
        tab switch.
        """
        candidates: list[BaseWrapper] = []

        for control in safe_descendants(
            editor,
            control_type="Document",
        ):
            try:
                info = control.element_info
                auto_id = normalize_text(
                    info.automation_id or ""
                )
                class_name = normalize_text(
                    info.class_name or ""
                )

                if auto_id != self.FORMULA_EDITOR_ID:
                    continue

                if class_name != "Edit":
                    continue

                if (
                    not control.is_visible()
                    or not control.is_enabled()
                ):
                    continue

                candidates.append(control)
            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(
            key=lambda control: (
                control.rectangle().width()
                * control.rectangle().height()
            ),
            reverse=True,
        )

        formula_editor = candidates[0]
        rectangle = formula_editor.rectangle()
        log(
            "Found current order formula editor as Document: "
            f"rect=("
            f"{rectangle.left},"
            f"{rectangle.top},"
            f"{rectangle.right},"
            f"{rectangle.bottom})"
        )
        return formula_editor

    # ============================================================
    # CHECKED / SELECTED STATE
    # ============================================================

    def _ensure_selected(
        self,
        control: BaseWrapper,
        label: str,
    ) -> None:
        state = self._read_binary_state(control)

        if state == 1:
            return

        self.actions.click_control(control, label)
        time.sleep(0.1)

        after = self._read_binary_state(control)

        if after == 0:
            raise RuntimeError(
                f"Could not select {label}."
            )

    def _ensure_checked(
        self,
        control: BaseWrapper,
        desired: bool,
        label: str,
    ) -> None:
        desired_state = 1 if desired else 0
        state = self._read_binary_state(control)

        if state == desired_state:
            return

        self.actions.click_control(control, label)
        time.sleep(0.1)

        after = self._read_binary_state(control)

        if (
            after is not None
            and after != desired_state
        ):
            raise RuntimeError(
                f"Could not set {label} to "
                f"{desired_state}. Actual={after}."
            )

    @staticmethod
    def _read_binary_state(
        control: BaseWrapper,
    ) -> int | None:
        try:
            return int(control.get_check_state())
        except Exception:
            pass

        try:
            return int(
                control.iface_toggle.CurrentToggleState
            )
        except Exception:
            pass

        try:
            return int(control.get_toggle_state())
        except Exception:
            return None

    # ============================================================
    # SAVE
    # ============================================================

    def _save_editor(
        self,
        editor: BaseWrapper,
    ) -> None:
        ok_button = self._find_ok_button(editor)

        self.actions.invoke_or_click(
            ok_button,
            "Ok button",
        )

        log("Waiting for System Editor to close...")

        def editor_closed() -> bool:
            try:
                return not editor.exists(timeout=0.2)
            except Exception:
                return True

        try:
            wait_until(
                editor_closed,
                timeout=self.save_timeout,
                interval=0.3,
                error_msg=(
                    "System Editor did not close after "
                    "clicking Ok"
                ),
            )

            log("Editor closed. Save likely succeeded.")

        except Exception as exc:
            self._print_editor_debug_text(editor)

            raise RuntimeError(
                "Save may have failed, or MetaStock may be "
                "showing a validation error. Check the "
                "System Editor manually."
            ) from exc

    def _find_ok_button(
        self,
        editor: BaseWrapper,
    ) -> BaseWrapper:
        log("Searching for Ok button...")

        try:
            ok = editor.child_window(
                auto_id=self.OK_BUTTON_ID,
                control_type="Button",
            )

            if ok.exists(timeout=0.5):
                log(
                    "Found Ok button by AutomationId 1."
                )
                return ok.wrapper_object()
        except Exception:
            pass

        for button in safe_descendants(
            editor,
            control_type="Button",
        ):
            try:
                name = normalize_text(
                    button.window_text()
                )
                info_name = normalize_text(
                    button.element_info.name or ""
                )
                auto_id = normalize_text(
                    button.element_info.automation_id or ""
                )

                if (
                    auto_id == self.OK_BUTTON_ID
                    or name.lower() == "ok"
                    or info_name.lower() == "ok"
                ):
                    log("Found Ok button.")
                    return button
            except Exception:
                continue

        raise RuntimeError("Could not find Ok button.")

    # ============================================================
    # DEBUG
    # ============================================================

    def _print_editor_debug_text(
        self,
        editor: BaseWrapper,
    ) -> None:
        log("Visible System Editor text/debug values:")

        shown = 0

        for control in safe_descendants(editor):
            try:
                text = normalize_text(
                    control.window_text()
                )
                name = normalize_text(
                    control.element_info.name or ""
                )
                control_type = normalize_text(
                    control.element_info.control_type or ""
                )
                class_name = normalize_text(
                    control.element_info.class_name or ""
                )

                value = text or name

                if not value:
                    continue

                rectangle = control.rectangle()

                log(
                    f"  {control_type} "
                    f"class={class_name!r} "
                    f"value={value!r} "
                    f"rect=("
                    f"{rectangle.left},"
                    f"{rectangle.top},"
                    f"{rectangle.right},"
                    f"{rectangle.bottom})"
                )

                shown += 1

                if shown >= 80:
                    break
            except Exception:
                continue
