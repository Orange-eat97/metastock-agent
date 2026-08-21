from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


COL_REFERENCE_RE = re.compile(r"\bCol([A-L])\b", re.IGNORECASE)


class ExplorerFormulaExpansionError(ValueError):
    """Raised when Explorer column references cannot be expanded safely."""


@dataclass(frozen=True)
class ExpandedExplorerFormula:
    source_filter: str
    expanded_filter: str
    referenced_columns: tuple[str, ...]


def expand_explorer_filter(
    explorer_output: dict[str, Any],
) -> ExpandedExplorerFormula:
    """Expand ColA–ColL references into their underlying Explorer formulas.

    Replacement is token-aware, recursive, parenthesized to preserve precedence,
    and rejects undefined references and dependency cycles.
    """
    if not isinstance(explorer_output, dict):
        raise ExplorerFormulaExpansionError("Explorer output must be a dictionary.")

    source_filter = str(explorer_output.get("explorer_code_body") or "").strip()
    if not source_filter:
        raise ExplorerFormulaExpansionError("explorer_code_body is required.")

    raw_columns = explorer_output.get("col_definitions") or []
    if not isinstance(raw_columns, list):
        raise ExplorerFormulaExpansionError("col_definitions must be a list.")

    columns: dict[str, str] = {}
    for item in raw_columns:
        if not isinstance(item, dict):
            raise ExplorerFormulaExpansionError(
                "Each col_definitions item must be an object."
            )
        letter = str(item.get("col_letter") or "").strip().upper()
        formula = str(item.get("col_code") or "").strip()
        if not re.fullmatch(r"[A-L]", letter):
            raise ExplorerFormulaExpansionError(
                f"Invalid Explorer column letter: {letter!r}."
            )
        if not formula:
            raise ExplorerFormulaExpansionError(
                f"Explorer column {letter} has an empty col_code."
            )
        if letter in columns:
            raise ExplorerFormulaExpansionError(
                f"Explorer column {letter} is defined more than once."
            )
        columns[letter] = formula

    cache: dict[str, str] = {}
    referenced: list[str] = []

    def expand_column(letter: str, stack: tuple[str, ...]) -> str:
        if letter in cache:
            return cache[letter]
        if letter not in columns:
            raise ExplorerFormulaExpansionError(
                f"Explorer filter references undefined column Col{letter}."
            )
        if letter in stack:
            cycle = " -> ".join([*stack, letter])
            raise ExplorerFormulaExpansionError(
                f"Explorer column reference cycle detected: {cycle}."
            )

        formula = columns[letter]

        def replace_nested(match: re.Match[str]) -> str:
            nested_letter = match.group(1).upper()
            expanded = expand_column(nested_letter, (*stack, letter))
            return f"({expanded})"

        expanded_formula = COL_REFERENCE_RE.sub(replace_nested, formula)
        cache[letter] = expanded_formula
        return expanded_formula

    def replace_filter_reference(match: re.Match[str]) -> str:
        letter = match.group(1).upper()
        if letter not in referenced:
            referenced.append(letter)
        return f"({expand_column(letter, ())})"

    expanded_filter = COL_REFERENCE_RE.sub(replace_filter_reference, source_filter)

    unresolved = COL_REFERENCE_RE.findall(expanded_filter)
    if unresolved:
        raise ExplorerFormulaExpansionError(
            "Explorer column expansion left unresolved references: "
            + ", ".join(f"Col{item.upper()}" for item in unresolved)
        )

    return ExpandedExplorerFormula(
        source_filter=source_filter,
        expanded_filter=expanded_filter.strip(),
        referenced_columns=tuple(referenced),
    )
