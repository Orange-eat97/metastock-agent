from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from compartments.metastock_app import MetaStockApp
from ui_interacter.coordinate_calibration import (
    CalibrationStore,
    CalibrationWizard,
)


APP_TITLE_RE = r"^Main - MetaStock$"

# Coordinate-only boundary: only console-level fallback points are recorded.
# Strategy and instrument rows remain owned by their stable selectors.
EXPLORE_ANCHORS = [
    (
        "explore_tab",
        "Click the middle of the word 'Explore' on the left-side "
        "MetaStock navigation.",
    ),
    (
        "start_exploration",
        "Open the Explore Console, then click the middle of the "
        "'Start Exploration' button.",
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
