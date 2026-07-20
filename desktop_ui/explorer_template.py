from __future__ import annotations

import re
from dataclasses import dataclass, field

from desktop_ui.models import ExplorerColumn, ExplorerEditPatch
from services.explorer_upload_protocol import EXPLORER_TEMPLATE_TEXT


START_MARKER = "=== METASTOCK EXPLORER ==="
END_MARKER = "=== END METASTOCK EXPLORER ==="



@dataclass(frozen=True)
class ExplorerTemplateParseResult:
    matched: bool
    patch: ExplorerEditPatch | None = None
    errors: list[str] = field(default_factory=list)


def looks_like_explorer_template(value: str) -> bool:
    return START_MARKER in str(value or "")


def parse_explorer_template(
    value: str,
) -> ExplorerTemplateParseResult:
    text = str(value or "").replace("\r\n", "\n").replace(
        "\r",
        "\n",
    )
    if START_MARKER not in text:
        return ExplorerTemplateParseResult(
            matched=False
        )

    errors: list[str] = []
    start = text.find(START_MARKER)
    end = text.find(
        END_MARKER,
        start + len(START_MARKER),
    )
    if end < 0:
        errors.append(
            f"Missing closing marker: {END_MARKER}"
        )
        body = text[start + len(START_MARKER):]
    else:
        body = text[
            start + len(START_MARKER):end
        ]

    lines = body.splitlines()
    name_lines: list[str] = []
    description_lines: list[str] = []
    filter_lines: list[str] = []
    assumption_lines: list[str] = []
    columns: list[tuple[str, list[str]]] = []
    current_kind: str | None = None
    current_column: tuple[str, list[str]] | None = None
    seen_name = False
    seen_description = False
    seen_filter = False
    seen_assumptions = False

    def flush_column() -> None:
        nonlocal current_column
        if current_column is not None:
            columns.append(current_column)
            current_column = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        column_match = re.fullmatch(
            r"\[Column\s+([A-L])\]",
            stripped,
            flags=re.IGNORECASE,
        )
        if column_match:
            flush_column()
            current_kind = "column"
            current_column = (
                column_match.group(1).upper(),
                [],
            )
            continue

        if stripped.casefold() == "name:":
            flush_column()
            if seen_name:
                errors.append(
                    "Name section appears more than once."
                )
            seen_name = True
            current_kind = "name"
            continue

        if stripped.casefold() == "description:":
            flush_column()
            if seen_description:
                errors.append(
                    "Description section appears more than once."
                )
            seen_description = True
            current_kind = "description"
            continue

        if stripped.casefold() == "[filter]":
            flush_column()
            if seen_filter:
                errors.append(
                    "Filter section appears more than once."
                )
            seen_filter = True
            current_kind = "filter"
            continue

        if stripped.casefold() == "[assumptions]":
            flush_column()
            if seen_assumptions:
                errors.append(
                    "Assumptions section appears more than once."
                )
            seen_assumptions = True
            current_kind = "assumptions"
            continue

        if (
            stripped.startswith("[")
            and stripped.endswith("]")
            and stripped
        ):
            errors.append(
                f"Unknown section header: {stripped}"
            )
            current_kind = None
            flush_column()
            continue

        if current_kind == "name":
            name_lines.append(line)
        elif current_kind == "description":
            description_lines.append(line)
        elif current_kind == "filter":
            filter_lines.append(line)
        elif current_kind == "assumptions":
            assumption_lines.append(line)
        elif (
            current_kind == "column"
            and current_column is not None
        ):
            current_column[1].append(line)
        elif stripped:
            errors.append(
                f"Text appears outside a recognized section: {stripped}"
            )

    flush_column()

    name = "\n".join(name_lines).strip()
    description = "\n".join(
        description_lines
    ).strip()
    filter_code = "\n".join(filter_lines).strip()

    if name == "Explorer name":
        name = ""
    if description == "Optional description":
        description = ""
    if filter_code == "Explorer filter formula":
        filter_code = ""

    parsed_columns: list[ExplorerColumn] = []
    seen_letters: set[str] = set()
    for letter, formula_lines in columns:
        formula = "\n".join(
            formula_lines
        ).strip()
        if formula == f"Optional formula for Column {letter}":
            continue
        if formula == f"Formula for Column {letter}":
            formula = ""
        if letter in seen_letters:
            errors.append(
                f"Column {letter} appears more than once."
            )
            continue
        seen_letters.add(letter)
        parsed_columns.append(
            ExplorerColumn(
                label=letter,
                formula=formula,
            )
        )

    expected_letters = list(
        "ABCDEFGHIJKL"[:len(parsed_columns)]
    )
    actual_letters = [
        item.label
        for item in parsed_columns
    ]
    if actual_letters != expected_letters:
        errors.append(
            "Columns must be sequential from A. "
            f"Got {actual_letters or 'none'}."
        )

    assumptions = []
    for raw in assumption_lines:
        cleaned = raw.strip()
        if not cleaned:
            continue
        cleaned = re.sub(
            r"^[-*]\s*",
            "",
            cleaned,
        ).strip()
        if cleaned in {
            "Optional assumption",
            "Another assumption",
        }:
            continue
        if cleaned:
            assumptions.append(cleaned)

    if not seen_name:
        errors.append("Missing Name section.")
    if not name:
        errors.append("Explorer name cannot be blank.")
    if not parsed_columns:
        errors.append(
            "At least one Explorer column is required."
        )
    for column in parsed_columns:
        if not column.formula:
            errors.append(
                f"Column {column.label} formula cannot be blank."
            )
    if not seen_filter:
        errors.append("Missing Filter section.")
    if not filter_code:
        errors.append(
            "Explorer filter formula cannot be blank."
        )

    return ExplorerTemplateParseResult(
        matched=True,
        patch=ExplorerEditPatch(
            name=name,
            description=description,
            columns=parsed_columns or [
                ExplorerColumn(
                    label="A",
                    formula="",
                )
            ],
            filter_formula=filter_code,
            assumptions=assumptions,
        ),
        errors=errors,
    )
