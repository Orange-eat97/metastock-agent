from __future__ import annotations

import argparse
import time
import traceback

from automator import build_workflow
from ui_interacter.state_readers import get_selected_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repeatedly search for and select one existing "
            "MetaStock Explorer without running it."
        )
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="Exact existing Explorer name.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=30,
        help="Number of selection attempts.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.25,
        help="Pause between attempts in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.runs < 1:
        raise ValueError("--runs must be at least 1")

    workflow = build_workflow(
        max_execution_wait_sec=30,
    )

    # Open Explore once. The individual test iterations only exercise
    # StrategySelector rather than instruments, execution, or scraping.
    main_window = workflow.app.connect()
    workflow.console.open(main_window)

    passed = 0
    failures: list[dict[str, object]] = []

    print("")
    print("=== STRATEGY SELECTION STRESS TEST ===")
    print(f"strategy={args.strategy!r}")
    print(f"runs={args.runs}")
    print(f"pause={args.pause}")
    print("")

    for attempt in range(1, args.runs + 1):
        started = time.perf_counter()

        try:
            # Obtain a fresh main-window wrapper on every iteration.
            main_window = workflow.app.connect()

            workflow.strategy_selector.select(
                main_window,
                args.strategy,
            )

            selected_count = get_selected_count(
                main_window
            )

            if selected_count != 1:
                raise RuntimeError(
                    "StrategySelector returned without "
                    "Selected becoming 1. "
                    f"Actual value: {selected_count!r}"
                )

            elapsed = time.perf_counter() - started
            passed += 1

            print(
                f"[PASS {attempt:03d}/{args.runs}] "
                f"Selected=1 elapsed={elapsed:.2f}s"
            )

        except Exception as exc:
            elapsed = time.perf_counter() - started

            failure = {
                "attempt": attempt,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "elapsed_sec": round(elapsed, 3),
                "traceback": traceback.format_exc(),
            }
            failures.append(failure)

            print(
                f"[FAIL {attempt:03d}/{args.runs}] "
                f"{type(exc).__name__}: {exc} "
                f"elapsed={elapsed:.2f}s"
            )

        time.sleep(args.pause)

    print("")
    print("=== SUMMARY ===")
    print(f"passed={passed}")
    print(f"failed={len(failures)}")
    print(f"total={args.runs}")

    if failures:
        print("")
        print("=== FAILURE DETAILS ===")

        for failure in failures:
            print("")
            print(
                f"Attempt {failure['attempt']}: "
                f"{failure['error_type']}"
            )
            print(failure["error"])
            print(failure["traceback"])

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())