from __future__ import annotations

import json
from typing import Any


EXPLORER_UPLOAD_ENVELOPE_PREFIX = (
    "__METASTOCK_EXPLORER_UPLOAD_V1__"
)


EXPLORER_TEMPLATE_TEXT = """=== METASTOCK EXPLORER ===

Name:
Explorer name

Description:
Optional description

[Column A]
Formula for Column A

[Column B]
Optional formula for Column B

[Filter]
Explorer filter formula

[Assumptions]
- Optional assumption
- Another assumption

=== END METASTOCK EXPLORER ==="""


def encode_explorer_upload_envelope(
    *,
    draft_id: str,
    name: str,
    description: str,
    columns: list[dict[str, str]],
    filter_code: str,
    assumptions: list[str],
    frontend_errors: list[str] | None = None,
    display_text: str | None = None,
) -> str:
    payload = {
        "draft_id": str(draft_id).strip(),
        "name": str(name).strip(),
        "description": str(description).strip(),
        "columns": [
            {
                "col_letter": str(
                    item.get("col_letter") or ""
                ).strip().upper(),
                "col_code": str(
                    item.get("col_code") or ""
                ).strip(),
            }
            for item in columns
            if isinstance(item, dict)
        ],
        "filter_code": str(filter_code).strip(),
        "assumptions": [
            str(item).strip()
            for item in assumptions
            if str(item).strip()
        ],
        "display_text": str(display_text or "").strip(),
        "frontend_errors": [
            str(item).strip()
            for item in (frontend_errors or [])
            if str(item).strip()
        ],
    }
    return (
        EXPLORER_UPLOAD_ENVELOPE_PREFIX
        + "\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def decode_explorer_upload_envelope(
    value: str,
) -> dict[str, Any] | None:
    text = str(value or "")
    prefix = EXPLORER_UPLOAD_ENVELOPE_PREFIX + "\n"
    if not text.startswith(prefix):
        return None

    raw_json = text[len(prefix):].strip()
    if not raw_json:
        raise ValueError(
            "Explorer upload envelope is empty."
        )

    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError(
            "Explorer upload envelope must contain an object."
        )

    return payload
