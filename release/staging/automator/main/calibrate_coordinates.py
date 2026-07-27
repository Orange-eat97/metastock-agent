from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from compartments.execution_monitor import ExecutionMonitor
from compartments.metastock_app import MetaStockApp
from ui_interacter.coordinate_calibration import (
    CalibrationStore,
    CalibrationWizard,
)


APP_TITLE_RE = r"^Main - MetaStock$"

# Approved coordinate fallback boundary:
# - console navigation and Start buttons;
# - one absolute strategy-checkbox point, used only when the filtered
#   Explorer row and checkbox remain unavailable through UIA for 2 seconds.
# Instrument and System Tester rows remain selector-owned.
EXPLORE_ANCHORS = [
    (
        "explore_tab",
        "Click the middle of the word 'Explore' on the left-side "
        "MetaStock navigation.",
    ),
    (
        "strategy_checkbox",
        "Open the Explore Console and search until exactly one Explorer "
        "row is visible. Click the centre of that row's checkbox.",
    ),
    (
        "start_exploration",
        "Open the Explore Console, then click the middle of the "
        "'Start Exploration' button.",
    ),
    (
        "result_first_row",
        "Run an Explorer until the completed result window is visible, "
        "then click the centre of the first result data row. This point "
        "is stored as an exact pixel offset from the result window.",
    ),
]

SYSTEM_TEST_ANCHORS = [
    (
        "system_test_tab",
        "Click the middle of the word 'SystemTest' on the left-side "
        "MetaStock navigation.",
    ),
    (
        "start_system_test",
        "Open the System Tester Console, then click the middle of the "
        "'Start System Test' button.",
    ),
]

ANCHORS_BY_MODE = {
    "explore": EXPLORE_ANCHORS,
    "system-test": SYSTEM_TEST_ANCHORS,
    "all": EXPLORE_ANCHORS + SYSTEM_TEST_ANCHORS,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Interactively record MetaStock console coordinate fallback "
            "points without changing selector semantics."
        )
    )
    parser.add_argument(
        "--profile",
        default="default",
        help=(
            "Calibration profile name, for example "
            "'t490-main-display'."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=sorted(ANCHORS_BY_MODE),
        default="explore",
        help=(
            "Which console fallback points to record. Use 'all' when "
            "one profile should support Explorer and System Tester."
        ),
    )
    return parser


def _rebase_result_first_row_to_result_window(
    *,
    profile,
    main_window,
    store: CalibrationStore,
):
    # Reinterpret window_relative_x/y as exact pixel offsets from the
    # Exploration Execution result window. Runtime ignores normalized values.
    point = profile.points.get("result_first_row")

    if point is None:
        return profile

    result_window = ExecutionMonitor(
        max_execution_wait_sec=1,
        poll_interval=0.1,
    ).find_execution_window_inside_main(
        main_window
    )

    if result_window is None:
        raise RuntimeError(
            "The result_first_row point was recorded, but no open "
            "Exploration Execution result window could be found. "
            "Leave the completed result window open while calibrating."
        )

    rectangle = result_window.rectangle()
    absolute_x = int(point.absolute_x)
    absolute_y = int(point.absolute_y)

    if not (
        rectangle.left <= absolute_x <= rectangle.right
        and rectangle.top <= absolute_y <= rectangle.bottom
    ):
        raise RuntimeError(
            "The recorded result_first_row point is outside the "
            "Exploration Execution result window. Re-run calibration "
            "and click the first actual result row."
        )

    offset_x = absolute_x - int(rectangle.left)
    offset_y = absolute_y - int(rectangle.top)

    corrected_point = replace(
        point,
        window_relative_x=offset_x,
        window_relative_y=offset_y,
    )
    corrected_points = dict(profile.points)
    corrected_points["result_first_row"] = corrected_point
    corrected_profile = replace(
        profile,
        points=corrected_points,
    )
    store.save(corrected_profile)

    print(
        "[Calibration] Stored 'result_first_row' relative to the "
        "Exploration Execution window: "
        f"offset=({offset_x}, {offset_y})."
    )
    return corrected_profile


def run_calibration(
    *,
    profile_name: str = "default",
    mode: str = "explore",
    store_directory: str | Path | None = None,
) -> Path:
    if mode not in ANCHORS_BY_MODE:
        raise ValueError(
            f"Unsupported calibration mode: {mode!r}"
        )

    store = CalibrationStore(
        directory=store_directory
    )
    app = MetaStockApp(
        app_title_re=APP_TITLE_RE
    )
    main_window = app.connect()

    print(
        "Prepare MetaStock in the exact layout used for automation "
        "before continuing."
    )
    print(
        "Do not resize or move MetaStock during this calibration run."
    )
    print(
        "For each point: press R to arm, click the target, then press R "
        "again to accept."
    )

    profile = CalibrationWizard(
        store=store
    ).run(
        main=main_window,
        profile_name=profile_name,
        anchors=ANCHORS_BY_MODE[mode],
    )
    profile = _rebase_result_first_row_to_result_window(
        profile=profile,
        main_window=main_window,
        store=store,
    )
    store.set_active_profile(
        profile.profile_name
    )
    profile_path = store.profile_path(
        profile.profile_name
    )

    print()
    print(
        "Calibration complete. Active profile: "
        f"{profile.profile_name!r}"
    )
    print(
        "Profile saved to: "
        f"{profile_path}"
    )
    print(
        "Future MetaStock Agent launches on this computer will load "
        "this profile automatically."
    )
    return profile_path


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = build_parser().parse_args(
        argv
    )
    run_calibration(
        profile_name=args.profile,
        mode=args.mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
