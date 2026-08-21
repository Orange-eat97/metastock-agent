# explore_selectors.py

from __future__ import annotations

from typing import Optional

from pywinauto import Desktop
from pywinauto.base_wrapper import BaseWrapper

from ui_interacter.coordinate_calibration import CoordinateMapper
from ui_interacter.ui_core import normalize_text, safe_descendants, log
from ui_interacter.state_readers import parse_selected_total_text


class ExploreSelectors:
    STRATEGY_CHECKBOX_POINT = "strategy_checkbox"

    def __init__(
        self,
        coordinate_mapper: Optional[
            CoordinateMapper
        ] = None,
    ) -> None:
        self.coordinate_mapper = coordinate_mapper

    def find_text_control_fuzzy(
        self,
        root: BaseWrapper,
        target_text: str,
    ) -> Optional[BaseWrapper]:
        target = normalize_text(target_text).lower()

        for t in safe_descendants(root, control_type="Text"):
            try:
                txt = normalize_text(t.window_text())
                if not txt:
                    continue

                low = txt.lower()
                if target in low or low in target:
                    return t
            except Exception:
                continue

        return None

    def find_explore_caption(self, main: BaseWrapper) -> Optional[BaseWrapper]:
        log("Searching for Explore tab/caption...")

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

            for e in elems:
                try:
                    info = e.element_info
                    name = normalize_text(info.name or "")
                    class_name = normalize_text(info.class_name or "")
                    help_text = normalize_text(getattr(info, "help_text", "") or "")

                    if help_text.lower() == "explore":
                        log(f"Found Explore by HelpText. name={name!r}, class={class_name!r}")
                        return e

                    if name.lower() == "explore":
                        log(f"Found Explore by Name. class={class_name!r}")
                        return e

                    if class_name == "TabCaptionControl":
                        child_texts = [
                            normalize_text(c.window_text())
                            for c in e.descendants(control_type="Text")
                            if normalize_text(c.window_text())
                        ]

                        if "Explore" in child_texts:
                            log("Found Explore inside TabCaptionControl children.")
                            return e

                except Exception:
                    continue

        log("Could not find Explore through UIA tree.")
        return None

    def find_search_combobox(self, main: BaseWrapper) -> BaseWrapper:
        log("Searching for explorer SearchComboBox...")

        combos = safe_descendants(main, control_type="ComboBox")

        for combo in combos:
            try:
                info = combo.element_info
                name = normalize_text(info.name or "")
                auto_id = normalize_text(info.automation_id or "")
                class_name = normalize_text(info.class_name or "")
                text = normalize_text(combo.window_text())

                fields = " ".join([name, auto_id, class_name, text]).lower()

                if "searchcombobox" in fields or "search" in fields:
                    log(
                        f"Found SearchComboBox: "
                        f"name={name!r}, auto_id={auto_id!r}, "
                        f"class={class_name!r}, text={text!r}"
                    )
                    return combo
            except Exception:
                continue

        raise RuntimeError("Could not find SearchComboBox in Explore Console.")

    def _resolve_strategy_checkbox_anchor(
        self,
        main: BaseWrapper,
    ) -> Optional[tuple[int, int]]:
        mapper = self.coordinate_mapper

        if mapper is None:
            return None

        if (
            self.STRATEGY_CHECKBOX_POINT
            not in mapper.profile.points
        ):
            return None

        return mapper.resolve(
            main=main,
            point_name=(
                self.STRATEGY_CHECKBOX_POINT
            ),
        )

    def _find_strategy_list_from_calibrated_anchor(
        self,
        main: BaseWrapper,
        anchor: tuple[int, int],
    ) -> Optional[BaseWrapper]:
        """
        Locate the visible strategy List that contains the calibrated
        strategy-checkbox point.

        The calibrated checkbox lies in the first visible Explorer row,
        close to the list's top-left corner. Candidate ranking therefore
        uses candidate-relative distances rather than fixed desktop
        thresholds such as left < 750.
        """
        anchor_x, anchor_y = anchor
        candidates: list[
            tuple[
                float,
                int,
                int,
                int,
                BaseWrapper,
            ]
        ] = []

        log(
            "Using calibrated strategy-checkbox anchor "
            f"for list discovery at ({anchor_x},{anchor_y})."
        )

        for list_view in safe_descendants(
            main,
            control_type="List",
        ):
            try:
                rectangle = list_view.rectangle()
                width = int(rectangle.width())
                height = int(rectangle.height())

                if width <= 0 or height <= 0:
                    continue

                if not (
                    rectangle.left
                    <= anchor_x
                    <= rectangle.right
                    and rectangle.top
                    <= anchor_y
                    <= rectangle.bottom
                ):
                    continue

                try:
                    if not list_view.is_visible():
                        continue
                except Exception:
                    pass

                try:
                    if bool(
                        getattr(
                            list_view.element_info,
                            "offscreen",
                            False,
                        )
                    ):
                        continue
                except Exception:
                    pass

                relative_x = (
                    anchor_x - rectangle.left
                ) / max(width, 1)
                relative_y = (
                    anchor_y - rectangle.top
                ) / max(height, 1)
                normalized_edge_distance = (
                    relative_x + relative_y
                )
                area = width * height

                candidates.append(
                    (
                        normalized_edge_distance,
                        area,
                        int(rectangle.top),
                        int(rectangle.left),
                        list_view,
                    )
                )

                log(
                    "  calibrated strategy List candidate: "
                    f"rect=({rectangle.left},"
                    f"{rectangle.top},"
                    f"{rectangle.right},"
                    f"{rectangle.bottom}), "
                    f"anchor_relative="
                    f"({relative_x:.3f},"
                    f"{relative_y:.3f}), "
                    f"area={area}"
                )
            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                item[3],
            )
        )

        chosen = candidates[0][4]
        rectangle = chosen.rectangle()

        log(
            "Using calibrated strategy list view "
            f"rect=({rectangle.left},"
            f"{rectangle.top},"
            f"{rectangle.right},"
            f"{rectangle.bottom})"
        )
        return chosen

    def find_strategy_list_view(
        self,
        main: BaseWrapper,
    ) -> BaseWrapper:
        log("Searching for strategy list view...")

        try:
            calibrated_anchor = (
                self._resolve_strategy_checkbox_anchor(
                    main
                )
            )
        except Exception as exc:
            calibrated_anchor = None
            log(
                "Could not resolve calibrated strategy anchor: "
                f"{type(exc).__name__}: {exc}"
            )

        if calibrated_anchor is not None:
            calibrated_list = (
                self._find_strategy_list_from_calibrated_anchor(
                    main,
                    calibrated_anchor,
                )
            )

            if calibrated_list is not None:
                return calibrated_list

            log(
                "No visible List contained the calibrated "
                "strategy-checkbox anchor. Falling back to "
                "the legacy geometry heuristic."
            )

        list_views = safe_descendants(
            main,
            control_type="List",
        )
        candidates = []

        for list_view in list_views:
            try:
                rectangle = list_view.rectangle()
                name = normalize_text(
                    list_view.element_info.name
                    or ""
                )
                text = normalize_text(
                    list_view.window_text()
                )

                # Backward compatibility only. Calibrated profiles use the
                # anchor-containing List path above.
                if (
                    rectangle.width() > 250
                    and rectangle.height() > 120
                    and rectangle.left < 750
                ):
                    candidates.append(
                        (
                            rectangle.top,
                            rectangle.left,
                            list_view,
                            name,
                            text,
                            rectangle,
                        )
                    )
            except Exception:
                continue

        if not candidates:
            raise RuntimeError(
                "Could not find strategy list view."
            )

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        chosen = candidates[0][2]
        rectangle = chosen.rectangle()

        log(
            "Using legacy strategy list view "
            f"rect=({rectangle.left},"
            f"{rectangle.top},"
            f"{rectangle.right},"
            f"{rectangle.bottom})"
        )
        return chosen

    def find_filtered_strategy_rows(
        self,
        main: BaseWrapper,
        list_view: Optional[BaseWrapper] = None,
    ) -> list[BaseWrapper]:
        """
        Find strategy ListBoxItem rows after the search filter is applied.

        Inspect.exe showed each strategy result is exposed as:
            ControlType: ListItem
            ClassName: ListBoxItem
            Name: IMA.Presentation...ExplorationVM
            HelpText: strategy description/formula
            Children: none
            TogglePattern: unavailable

        The searched display name, e.g. '#Stoch and RSI', is not exposed as row text.
        """
        if list_view is None:
            list_view = self.find_strategy_list_view(
                main
            )

        list_rect = list_view.rectangle()

        candidates: list[tuple[int, int, int, BaseWrapper, str]] = []

        try:
            descendants = list_view.descendants()
        except Exception:
            descendants = []

        for ctrl in descendants:
            try:
                info = ctrl.element_info
                r = ctrl.rectangle()

                control_type = normalize_text(info.control_type or "")
                class_name = normalize_text(info.class_name or "")
                name = normalize_text(info.name or "")
                help_text = normalize_text(getattr(info, "help_text", "") or "")

                is_strategy_item = (
                    control_type == "ListItem"
                    or class_name == "ListBoxItem"
                    or "ExplorationVM" in name
                )

                if not is_strategy_item:
                    continue

                # Must overlap the strategy list view.
                if r.right < list_rect.left or r.left > list_rect.right:
                    continue
                if r.bottom < list_rect.top or r.top > list_rect.bottom:
                    continue

                # Avoid invalid/tiny elements.
                if r.width() <= 20 or r.height() <= 8:
                    continue

                score = 0

                if control_type == "ListItem":
                    score += 30
                if class_name == "ListBoxItem":
                    score += 30
                if "ExplorationVM" in name:
                    score += 20
                if help_text:
                    score += 10

                # Prefer row-sized items.
                if 15 <= r.height() <= 80:
                    score += 10

                candidates.append((score, r.top, r.left, ctrl, help_text or name))

            except Exception:
                continue

        candidates.sort(key=lambda x: (-x[0], x[1], x[2]))

        rows = [ctrl for _, _, _, ctrl, _ in candidates]

        log(f"Filtered strategy ListBoxItem candidate count: {len(rows)}")

        for idx, (score, _, _, ctrl, desc) in enumerate(candidates[:10], start=1):
            r = ctrl.rectangle()
            log(
                f"  strategy candidate {idx}: "
                f"score={score}, rect=({r.left},{r.top},{r.right},{r.bottom}), "
                f"description/name={desc!r}"
            )

        return rows

    def find_unique_filtered_strategy_row(self, main: BaseWrapper) -> BaseWrapper:
        """
        Return the unique visible filtered strategy row.

        Safety rule:
        - 0 rows: fail
        - 1 row: use it
        - >1 rows: fail safely because the search term is not unique enough
        """
        rows = self.find_filtered_strategy_rows(main)

        if not rows:
            raise RuntimeError(
                "No strategy ListBoxItem row found after search filtering. "
                "The filtered list may not be loaded, or MetaStock did not expose the result row."
            )

        if len(rows) > 1:
            raise RuntimeError(
                f"Search result is ambiguous: found {len(rows)} strategy rows after filtering. "
                "Use a more unique strategy search string before allowing automated selection."
            )

        row = rows[0]
        r = row.rectangle()

        log(
            "Using unique filtered strategy row: "
            f"rect=({r.left},{r.top},{r.right},{r.bottom})"
        )

        return row

    def find_first_filtered_strategy_checkbox(
        self,
        main: BaseWrapper,
        list_view: Optional[BaseWrapper] = None,
    ) -> Optional[BaseWrapper]:
        """
        Find the first visible Explorer-result checkbox.

        Some MetaStock/WPF states display the filtered Explorer row
        correctly but do not expose it as a descendant ListBoxItem.
        The row checkbox can still be available through the main UIA
        tree, so search for checkboxes whose centre lies inside the
        strategy-list rectangle.
        """
        if list_view is None:
            list_view = self.find_strategy_list_view(
                main
            )

        list_rect = list_view.rectangle()

        candidates: list[
            tuple[int, int, BaseWrapper]
        ] = []

        for checkbox in safe_descendants(
            main,
            control_type="CheckBox",
        ):
            try:
                rectangle = checkbox.rectangle()

                center_x = (
                    rectangle.left + rectangle.right
                ) // 2
                center_y = (
                    rectangle.top + rectangle.bottom
                ) // 2

                inside_strategy_list = (
                    list_rect.left
                    <= center_x
                    <= list_rect.right
                    and list_rect.top
                    <= center_y
                    <= list_rect.bottom
                )

                if not inside_strategy_list:
                    continue

                if (
                    rectangle.width() <= 5
                    or rectangle.height() <= 5
                    or rectangle.width() > 60
                    or rectangle.height() > 60
                ):
                    continue

                candidates.append(
                    (
                        rectangle.top,
                        rectangle.left,
                        checkbox,
                    )
                )

            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        first_checkbox = candidates[0][2]
        rectangle = first_checkbox.rectangle()

        log(
            "Using first visible Explorer-result "
            "checkbox fallback: "
            f"rect=({rectangle.left},"
            f"{rectangle.top},"
            f"{rectangle.right},"
            f"{rectangle.bottom})"
        )

        return first_checkbox

    def find_checkbox_in_row(self, row: BaseWrapper) -> Optional[BaseWrapper]:
        """
        Find a real CheckBox inside a row if UIA exposes one.

        For strategy rows this probably returns None because Inspect.exe showed
        ListBoxItem rows with no children and no TogglePattern. Still useful for
        any UIA-exposed checkbox row.
        """
        def is_checkbox(ctrl: BaseWrapper) -> bool:
            try:
                info = ctrl.element_info
                control_type = normalize_text(info.control_type or "")
                class_name = normalize_text(info.class_name or "")
                name = normalize_text(info.name or "")

                combined = f"{control_type} {class_name} {name}".lower()
                return "checkbox" in combined
            except Exception:
                return False

        try:
            for child in row.children():
                if is_checkbox(child):
                    return child
        except Exception:
            pass

        try:
            for child in row.descendants():
                if is_checkbox(child):
                    return child
        except Exception:
            pass

        return None

    def find_instruments_tree_item(
        self,
        main: BaseWrapper,
    ) -> BaseWrapper:
        """
        Find the Instruments TreeViewItem.

        Prefer a narrow UIA lookup. Fall back to scanning only
        TreeItem controls rather than the entire MetaStock tree.
        """
        log("Searching for Instruments tree item...")

        # Fast path using the UIA name observed in Inspect.exe.
        try:
            spec = main.child_window(
                title_re=r".*InstrumentListTypesTVM.*",
                control_type="TreeItem",
            )

            if spec.exists(timeout=0.15):
                item = spec.wrapper_object()
                log(
                    "Found Instruments tree item through "
                    "direct UIA lookup."
                )
                return item

        except Exception:
            pass

        # Narrow fallback: inspect TreeItems only.
        candidates = []

        for item in safe_descendants(
            main,
            control_type="TreeItem",
        ):
            try:
                info = item.element_info

                name = normalize_text(
                    info.name or ""
                )
                class_name = normalize_text(
                    info.class_name or ""
                )
                control_type = normalize_text(
                    info.control_type or ""
                )
                rectangle = item.rectangle()

                combined = (
                    f"{name} {class_name} {control_type}"
                )

                if "InstrumentListTypesTVM" not in combined:
                    continue

                if (
                    rectangle.width() <= 50
                    or rectangle.height() <= 10
                ):
                    continue

                if rectangle.left > 350:
                    continue

                child_texts = []

                try:
                    children = item.children()
                except Exception:
                    children = []

                for child in children:
                    try:
                        text = normalize_text(
                            child.window_text()
                        )

                        if text:
                            child_texts.append(text)
                    except Exception:
                        pass

                    try:
                        child_name = normalize_text(
                            child.element_info.name or ""
                        )

                        if child_name:
                            child_texts.append(
                                child_name
                            )
                    except Exception:
                        pass

                score = 0

                if "InstrumentListTypesTVM" in name:
                    score += 10

                if class_name == "TreeViewItem":
                    score += 5

                if control_type == "TreeItem":
                    score += 5

                if any(
                    text.casefold() == "instruments"
                    for text in child_texts
                ):
                    score += 5

                if any(
                    parse_selected_total_text(text)
                    is not None
                    for text in child_texts
                ):
                    score += 5

                candidates.append(
                    (
                        score,
                        rectangle.top,
                        rectangle.left,
                        item,
                    )
                )

            except Exception:
                continue

        if not candidates:
            raise RuntimeError(
                "Could not find Instruments TreeViewItem."
            )

        candidates.sort(
            key=lambda value: (
                -value[0],
                value[1],
                value[2],
            )
        )

        log(
            "Found Instruments tree item through "
            "TreeItem-only fallback."
        )

        return candidates[0][3]

    def find_start_button(self, main: BaseWrapper) -> Optional[BaseWrapper]:
        possible_names = [
            "Start Exploration...",
            "Start Exploration",
            "Start",
            "Run Exploration",
            "Run",
            "Explore",
            "Exploration",
        ]

        buttons = safe_descendants(main, control_type="Button")

        for target in possible_names:
            for btn in buttons:
                try:
                    name = normalize_text(btn.window_text())
                    info_name = normalize_text(btn.element_info.name or "")
                except Exception:
                    continue

                if name.lower() == target.lower() or info_name.lower() == target.lower():
                    log(f"Found Start button by exact name: {name or info_name!r}")
                    return btn

        for btn in buttons:
            try:
                name = normalize_text(btn.window_text())
                info_name = normalize_text(btn.element_info.name or "")
                combined = f"{name} {info_name}".lower()
            except Exception:
                continue

            if "start" in combined and "exploration" in combined:
                log(f"Found Start button by fuzzy name: {name or info_name!r}")
                return btn

        return None
    
    def find_strategy_select_all_checkbox(
        self,
        main: BaseWrapper,
    ) -> BaseWrapper:
        """
        Find the Select all checkbox beside the Explorer search box.

        Prefer an accessible name. Fall back to the checkbox nearest
        the visible 'Select all' text label.
        """
        checkboxes = safe_descendants(
            main,
            control_type="CheckBox",
        )

        for checkbox in checkboxes:
            try:
                info = checkbox.element_info

                values = [
                    normalize_text(info.name or ""),
                    normalize_text(
                        checkbox.window_text() or ""
                    ),
                    normalize_text(
                        getattr(info, "help_text", "")
                        or ""
                    ),
                ]

                if any(
                    value.casefold() == "select all"
                    for value in values
                ):
                    log(
                        "Found strategy Select all checkbox "
                        "by accessible name."
                    )
                    return checkbox

            except Exception:
                continue

        select_all_labels = []

        for text_control in safe_descendants(
            main,
            control_type="Text",
        ):
            try:
                text = normalize_text(
                    text_control.window_text()
                    or text_control.element_info.name
                    or ""
                )

                if text.casefold() == "select all":
                    select_all_labels.append(
                        text_control
                    )
            except Exception:
                continue

        candidates: list[
            tuple[int, BaseWrapper]
        ] = []

        for label in select_all_labels:
            try:
                label_rect = label.rectangle()
                label_center_y = (
                    label_rect.top + label_rect.bottom
                ) // 2
            except Exception:
                continue

            for checkbox in checkboxes:
                try:
                    checkbox_rect = checkbox.rectangle()
                    checkbox_center_y = (
                        checkbox_rect.top
                        + checkbox_rect.bottom
                    ) // 2

                    vertical_distance = abs(
                        checkbox_center_y
                        - label_center_y
                    )

                    horizontal_gap = (
                        label_rect.left
                        - checkbox_rect.right
                    )

                    # Screenshot/UI layout:
                    # checkbox is immediately left of the label.
                    if vertical_distance > 25:
                        continue

                    if horizontal_gap < -10:
                        continue

                    if horizontal_gap > 100:
                        continue

                    score = (
                        vertical_distance
                        + abs(horizontal_gap)
                    )

                    candidates.append(
                        (score, checkbox)
                    )

                except Exception:
                    continue

        if candidates:
            candidates.sort(
                key=lambda item: item[0]
            )

            log(
                "Found strategy Select all checkbox "
                "using label proximity."
            )

            return candidates[0][1]

        raise RuntimeError(
            "Could not find the strategy Select all checkbox."
        )