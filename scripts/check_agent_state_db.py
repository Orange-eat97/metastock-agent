from __future__ import annotations

import os
import sys

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


def main() -> int:
    load_dotenv()

    database_url = os.getenv(
        "AGENT_STATE_DATABASE_URL",
        "",
    ).strip()

    if not database_url:
        print(
            "[CONFIGURATION ERROR] "
            "AGENT_STATE_DATABASE_URL is missing.",
            file=sys.stderr,
        )
        return 2

    try:
        with psycopg.connect(
            database_url,
            connect_timeout=10,
            row_factory=dict_row,
            application_name="metastock-agent-health-check",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        current_database() AS database_name,
                        current_user AS database_user,
                        1 AS health_check
                    """
                )
                result = cursor.fetchone()

        if result is None or result["health_check"] != 1:
            raise RuntimeError("Unexpected health-check result.")

        print("[PASSED] Agent-state database connection")
        print(f"Database: {result['database_name']}")
        print(f"User: {result['database_user']}")
        return 0

    except Exception as exc:
        print(
            f"[FAILED] Agent-state database connection: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())