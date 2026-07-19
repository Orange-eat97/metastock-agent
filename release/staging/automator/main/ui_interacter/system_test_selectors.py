from __future__ import annotations

import re
from typing import Optional

from pywinauto import Desktop
from pywinauto.base_wrapper import BaseWrapper

from ui_interacter.explore_selectors import ExploreSelectors
from ui_interacter.ui_core import log, normalize_text, safe_descendants


_SYSTEM_TEST_RESULT_SUFFIX = re.compile(
    r"\s*<R>\s*$",
    re.IGNORECASE,
)


class SystemTestSelectors(ExploreSelectors):
    """
    System Tester adaptation of ExploreSelectors.

    The class deliberately inherits all proven generic Explorer selectors:
    - find_text_control_fuzzy()
    - find_search_combobox()
    - find_instruments_tree_item()
    - find_strategy_select_all_checkbox()

    Only controls that are different in System Tester are added below.
    """

    def find_system_test_caption(
        self,
        main: BaseWrapper,
    ) -> Optional[BaseWrapper]:
        """
        Direct adaptation of ExploreSelectors.find_explore_caption().

        Keep the same roots, the same unfiltered descendants traversal, the
        same failure behavior, and the same return contract. Only the target
        caption changes from Explore to SystemTest.
        """
        log("Searching for SystemTest tab/caption...")

        search_roots = [main]

        try:
            search_roots.append(Desktop(backend="uia"))
        except Exception:
            pass

        for root in search_roots:
            try:
                elems = root.descendants()
            except Exception:
                elems = []

            for elem in elems:
                try:
                    info = elem.element_info
                    name = normalize_text(info.name or "")
                    class_name = normalize_text(
                        info.class_name or ""
                    )
                    help_text = normalize_text(
                        getattr(info, "help_text", "") or ""
                    )

                    if help_text.lower() == "systemtest":
                        log(
                            "Found SystemTest by HelpText. "
                            f"name={name!r}, class={class_name!r}"
                        )
                        return elem

                    if name.lower() == "systemtest":
                        log(
                            "Found SystemTest by Name. "
                            f"class={class_name!r}"
                        )
                        return elem

                    if class_name == "TabCaptionControl":
                        child_texts = [
                            normalize_text(child.window_text())
                            for child in elem.descendants(
                                control_type="Text"
                            )
                            if normalize_text(
                                child.window_text()
                            )
                        ]

                        if "SystemTest" in child_texts:
                            log(
                                "Found SystemTest inside "
                                "TabCaptionControl children."
                            )
                            return elem

                except Exception:
                    continue

        log("Could not find SystemTest through UIA tree.")
        return None

    def find_system_test_list_view(
        self,
        main: BaseWrapper,
    ) -> BaseWrapper:
        """
        System Tester counterpart of find_strategy_list_view().

        The inspected New System Test button has the system-test list view as
        its next sibling. The visual placement is the same left-side list area
        used by Explorer, so preserve the proven list-view selector.
        """
        return super().find_strategy_list_view(main)

    def normalize_system_test_name(
        self,
        value: str,
    ) -> str:
        cleaned = normalize_text(value)
        return _SYSTEM_TEST_RESULT_SUFFIX.sub(
            "",
            cleaned,
        ).strip()

    def find_filtered_system_test_checkboxes(
        self,
        main: BaseWrapper,
    ) -> list[BaseWrapper]:
        """
        System Tester counterpart of find_filtered_strategy_rows().

        Unlike Explorer rows, the inspected System Tester result is exposed as
        a real CheckBox with a display name such as ``smoke test <R>``. Search
        only inside the discovered left-side list view and require that suffix.
        """
        list_view = self.find_system_test_list_view(main)
        list_rect = list_view.rectangle()

        candidates: list[
            tuple[int, int, int, BaseWrapper, str]
        ] = []

        try:
            descendants = list_view.descendants()
        except Exception:
            descendants = []

        for ctrl in descendants:
            try:
                info = ctrl.element_info
                rectangle = ctrl.rectangle()

                control_type = normalize_text(
                    info.control_type or ""
                )
                class_name = normalize_text(
                    info.class_name or ""
                )
                name = normalize_text(
                    info.name or ctrl.window_text() or ""
                )

                is_system_test_checkbox = (
                    control_type == "CheckBox"
                    or class_name == "CheckBox"
                )

                if not is_system_test_checkbox:
                    continue

                if not _SYSTEM_TEST_RESULT_SUFFIX.search(name):
                    continue

                if (
                    rectangle.right < list_rect.left
                    or rectangle.left > list_rect.right
                ):
                    continue

                if (
                    rectangle.bottom < list_rect.top
                    or rectangle.top > list_rect.bottom
                ):
                    continue

                if (
                    rectangle.width() <= 20
                    or rectangle.height() <= 8
                ):
                    continue

                score = 0

                if control_type == "CheckBox":
                    score += 30
                if class_name == "CheckBox":
                    score += 20
                if _SYSTEM_TEST_RESULT_SUFFIX.search(name):
                    score += 30
                if 15 <= rectangle.height() <= 80:
                    score += 10

                candidates.append(
                    (
                        score,
                        rectangle.top,
                        rectangle.left,
                        ctrl,
                        name,
                    )
                )

            except Exception:
                continue

        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1],
                item[2],
            )
        )

        checkboxes = [
            ctrl
            for _, _, _, ctrl, _ in candidates
        ]

        log(
            "Filtered system-test CheckBox candidate count: "
            f"{len(checkboxes)}"
        )

        for index, (
            score,
            _,
            _,
            ctrl,
            name,
        ) in enumerate(candidates[:10], start=1):
            rectangle = ctrl.rectangle()
            log(
                f"  system-test candidate {index}: "
                f"score={score}, "
                f"rect=("
                f"{rectangle.left},"
                f"{rectangle.top},"
                f"{rectangle.right},"
                f"{rectangle.bottom}), "
                f"name={name!r}"
            )

        return checkboxes

    def find_unique_filtered_system_test_checkbox(
        self,
        main: BaseWrapper,
    ) -> BaseWrapper:
        """
        Direct counterpart of find_unique_filtered_strategy_row().

        Safety rule:
        - zero results: fail;
        - one result: use it;
        - more than one result: fail as ambiguous.
        """
        checkboxes = self.find_filtered_system_test_checkboxes(
            main
        )

        if not checkboxes:
            raise RuntimeError(
                "No system-test CheckBox was found after search "
                "filtering."
            )

        if len(checkboxes) > 1:
            raise RuntimeError(
                "Search result is ambiguous: found "
                f"{len(checkboxes)} system-test checkboxes "
                "after filtering. Use a more unique search string."
            )

        checkbox = checkboxes[0]
        rectangle = checkbox.rectangle()

        log(
            "Using unique filtered system-test checkbox: "
            f"rect=("
            f"{rectangle.left},"
            f"{rectangle.top},"
            f"{rectangle.right},"
            f"{rectangle.bottom})"
        )

        return checkbox

    def find_system_test_select_all_checkbox(
        self,
        main: BaseWrapper,
    ) -> BaseWrapper:
        """
        Preserve the proven Explorer Select all selector unchanged.
        """
        return super().find_strategy_select_all_checkbox(main)

    def find_start_button(
        self,
        main: BaseWrapper,
    ) -> Optional[BaseWrapper]:
        """
        System Tester counterpart of ExploreSelectors.find_start_button().

        Prefer the inspected AutomationId, then retain the same exact-name and
        fuzzy-name fallback structure used by Explorer.
        """
        try:
            spec = main.child_window(
                auto_id="StartSystemTestButton",
                control_type="Button",
            )

            if spec.exists(timeout=0.2):
                log(
                    "Found Start System Test button by exact "
                    "AutomationId."
                )
                return spec.wrapper_object()

        except Exception:
            pass

        possible_names = [
            "Start System Test...",
            "Start System Test",
            "Start",
            "Run System Test",
            "Run",
            "System Test",
        ]

        buttons = safe_descendants(
            main,
            control_type="Button",
        )

        for target in possible_names:
            for button in buttons:
                try:
                    name = normalize_text(
                        button.window_text()
                    )
                    info_name = normalize_text(
                        button.element_info.name or ""
                    )
                except Exception:
                    continue

                if (
                    name.lower() == target.lower()
                    or info_name.lower() == target.lower()
                ):
                    log(
                        "Found Start System Test button by "
                        f"exact name: {name or info_name!r}"
                    )
                    return button

        for button in buttons:
            try:
                name = normalize_text(
                    button.window_text()
                )
                info_name = normalize_text(
                    button.element_info.name or ""
                )
                combined = f"{name} {info_name}".lower()
            except Exception:
                continue

            if (
                "start" in combined
                and "system test" in combined
            ):
                log(
                    "Found Start System Test button by fuzzy "
                    f"name: {name or info_name!r}"
                )
                return button

        return None
