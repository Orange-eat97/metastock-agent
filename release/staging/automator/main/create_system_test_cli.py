from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from system_test_service import MetaStockSystemTestService


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a MetaStock System Test from a structured RAGLLM JSON object."
        )
    )
    parser.add_argument(
        "--json-file",
        required=True,
        help="Path to a schema_version=1.0 system-test JSON file.",
    )
    args = parser.parse_args()

    path = Path(args.json_file)
    if not path.exists():
        raise FileNotFoundError(f"JSON file does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    result = MetaStockSystemTestService().create_system_test(payload)
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))

    if not result.succeeded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
