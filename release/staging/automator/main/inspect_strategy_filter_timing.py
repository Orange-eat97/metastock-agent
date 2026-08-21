from __future__ import annotations

import argparse
import time

from automator import build_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure MetaStock Explorer UIA filtering without "
            "selecting or running an Explorer."
        )
    )
    parser.add_argument(
        "--strategy",
        required=True,
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.10,
    )
    return parser.parse_args()


def rectangle_tuple(control) -> tuple[int, int, int, int]:
    rectangle = control.rectangle()

    return (
        int(rectangle.left),
        int(rectangle.top),
        int(rectangle.right),
        int(rectangle.bottom),
    )


def main() -> int:
    args = parse_args()

    if args.samples < 1:
        raise ValueError("--samples must be at least 1")

    if args.pause < 0:
        raise ValueError("--pause cannot be negative")

    workflow = build_workflow(
        max_execution_wait_sec=30,
    )

    main_window = workflow.app.connect()
    workflow.console.open(main_window)

    selector = workflow.strategy_selector
    selectors = selector.selectors
    actions = selector.actions

    search_box = selectors.find_search_combobox(
        main_window
    )

    actions.paste_text(
        search_box,
        "",
        label="diagnostic clear Explorer search",
    )

    search_box = selectors.find_search_combobox(
        main_window
    )

    actions.paste_text(
        search_box,
        args.strategy,
        label="diagnostic Explorer search",
    )

    experiment_started = time.perf_counter()
    records: list[dict[str, object]] = []

    print()
    print("=== STRATEGY FILTER TIMING INSPECTION ===")
    print(f"strategy={args.strategy!r}")
    print(f"samples={args.samples}")
    print(f"pause={args.pause}")
    print(
        "This script does not click an Explorer row "
        "or start an exploration."
    )
    print()

    for sample_number in range(
        1,
        args.samples + 1,
    ):
        scan_started = time.perf_counter()

        list_view = selectors.find_strategy_list_view(
            main_window
        )
        list_rectangle = rectangle_tuple(
            list_view
        )

        rows = selectors.find_filtered_strategy_rows(
            main_window
        )

        scan_finished = time.perf_counter()

        row_rectangles = []

        for row in rows:
            try:
                row_rectangles.append(
                    rectangle_tuple(row)
                )
            except Exception as exc:
                row_rectangles.append(
                    (
                        "rectangle-error",
                        type(exc).__name__,
                        str(exc),
                    )
                )

        record = {
            "sample": sample_number,
            "start_elapsed": (
                scan_started - experiment_started
            ),
            "finish_elapsed": (
                scan_finished - experiment_started
            ),
            "scan_duration": (
                scan_finished - scan_started
            ),
            "list_rect": list_rectangle,
            "row_count": len(rows),
            "exactly_one": len(rows) == 1,
            "row_rectangles": row_rectangles,
        }
        records.append(record)

        print(
            f"[SAMPLE {sample_number:02d}] "
            f"start={record['start_elapsed']:.3f}s "
            f"finish={record['finish_elapsed']:.3f}s "
            f"duration={record['scan_duration']:.3f}s "
            f"list={list_rectangle} "
            f"rows={len(rows)} "
            f"exactly_one={len(rows) == 1}"
        )

        for row_number, row_rectangle in enumerate(
            row_rectangles,
            start=1,
        ):
            print(
                f"    row {row_number}: "
                f"{row_rectangle}"
            )

        if sample_number < args.samples:
            time.sleep(args.pause)

    print()
    print("=== TIMING SUMMARY ===")

    starts_inside_two_seconds = sum(
        1
        for record in records
        if record["start_elapsed"] < 2.0
    )

    starts_inside_five_seconds = sum(
        1
        for record in records
        if record["start_elapsed"] < 5.0
    )

    maximum_consecutive_exact_one = 0
    current_consecutive_exact_one = 0

    for record in records:
        if record["exactly_one"]:
            current_consecutive_exact_one += 1
            maximum_consecutive_exact_one = max(
                maximum_consecutive_exact_one,
                current_consecutive_exact_one,
            )
        else:
            current_consecutive_exact_one = 0

    unique_list_rectangles = {
        record["list_rect"]
        for record in records
    }

    print(
        "scans_started_within_2_seconds="
        f"{starts_inside_two_seconds}"
    )
    print(
        "scans_started_within_5_seconds="
        f"{starts_inside_five_seconds}"
    )
    print(
        "unique_list_rectangles="
        f"{len(unique_list_rectangles)}"
    )

    for rectangle in sorted(
        unique_list_rectangles
    ):
        print(f"    {rectangle}")

    print(
        "maximum_consecutive_exactly_one_reads="
        f"{maximum_consecutive_exact_one}"
    )

    if starts_inside_two_seconds < 2:
        print(
            "DIAGNOSIS: a two-second timeout cannot "
            "currently support stable_reads=2 because "
            "fewer than two scans begin before the deadline."
        )
    else:
        print(
            "DIAGNOSIS: at least two scans can begin "
            "inside two seconds; inspect the row-count "
            "sequence to determine whether filtering "
            "itself is unstable."
        )

    print()
    print(
        "Inspection complete. No Explorer row was clicked."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())