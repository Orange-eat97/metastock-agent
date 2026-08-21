from __future__ import annotations

import argparse
import json

from system_test_request import SystemTestRequest
from system_test_service import MetaStockSystemTestService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an existing MetaStock system test."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--instrument",
        action="append",
        default=None,
        help="Named instrument/list/exchange; repeat as needed.",
    )
    parser.add_argument(
        "--all-instruments",
        action="store_true",
        help="Select all instruments.",
    )
    parser.add_argument(
        "--skip-visible-status-read",
        action="store_true",
    )
    args = parser.parse_args()

    select_all = args.all_instruments or not args.instrument
    request = SystemTestRequest(
        system_test_name=args.name,
        instrument_names=(None if select_all else args.instrument),
        select_all_instruments=select_all,
        read_status_if_visible=(
            not args.skip_visible_status_read
        ),
    )

    result = MetaStockSystemTestService().run_system_test(request)
    print(json.dumps(result.__dict__, indent=2, default=str))

    if not result.succeeded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
