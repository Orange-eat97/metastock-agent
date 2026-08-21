from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from src.system_test_definition import SystemTestDefinition


VARIABLE_DEFINITION_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*\s*:=")
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:\d+(?:\.\d+)?|\.\d+)")
COL_REFERENCE_RE = re.compile(r"\bCol[A-L]\b", re.IGNORECASE)
OPT_RE = re.compile(r"\bOPT\d+\b", re.IGNORECASE)
SIMULATION_RE = re.compile(r"\bSimulation\.[A-Za-z][A-Za-z0-9_]*\b")

HISTORICAL_FUNCTIONS = {
    "ref",
    "mov",
    "hhv",
    "llv",
    "valuewhen",
    "barssince",
    "sum",
    "cum",
    "roc",
}


@dataclass(frozen=True)
class SystemTestValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _extract_balanced_calls(formula: str) -> Iterable[tuple[str, str]]:
    pattern = re.compile(r"\b([A-Za-z][A-Za-z0-9_.]*)\s*\(")
    for match in pattern.finditer(formula):
        name = match.group(1)
        opening = formula.find("(", match.start())
        depth = 1
        cursor = opening + 1
        while cursor < len(formula) and depth:
            char = formula[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            cursor += 1
        if depth == 0:
            yield name, formula[opening + 1 : cursor - 1]


def _split_top_level_args(text: str) -> list[str]:
    args: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(text[start:index].strip())
            start = index + 1
    args.append(text[start:].strip())
    return args


def _validate_formula(formula: str, field_name: str) -> list[str]:
    errors: list[str] = []
    if not formula.strip():
        return [f"{field_name} is required."]

    if COL_REFERENCE_RE.search(formula):
        errors.append(f"{field_name} still contains an Explorer ColA-style reference.")
    if OPT_RE.search(formula):
        errors.append(f"{field_name} contains OPT variables while optimizations are disabled.")

    for name, body in _extract_balanced_calls(formula):
        lowered = name.casefold()
        if lowered == "ref":
            args = _split_top_level_args(body)
            if len(args) == 2 and re.fullmatch(r"\+?[1-9]\d*", args[1]):
                errors.append(
                    f"{field_name} contains future lookahead in Ref(...,{args[1]})."
                )
        if lowered in HISTORICAL_FUNCTIONS and SIMULATION_RE.search(body):
            errors.append(
                f"{field_name} nests a Simulation.* value inside historical function {name}()."
            )

    variable_count = len(VARIABLE_DEFINITION_RE.findall(formula))
    if variable_count > 20:
        errors.append(
            f"{field_name} defines {variable_count} variables; MetaStock allows at most 20."
        )

    numeric_constant_count = len(NUMBER_RE.findall(formula))
    if numeric_constant_count > 20:
        errors.append(
            f"{field_name} contains {numeric_constant_count} numerical constants; "
            "MetaStock allows at most 20."
        )

    return errors


def validate_system_test_definition(
    definition: SystemTestDefinition,
) -> SystemTestValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(
        _validate_formula(
            definition.orders.buy.signal_formula,
            "orders.buy.signal_formula",
        )
    )
    errors.extend(
        _validate_formula(
            definition.orders.sell.signal_formula,
            "orders.sell.signal_formula",
        )
    )

    if "Simulation.LongPositionCount" not in definition.orders.buy.signal_formula:
        warnings.append(
            "Buy signal does not explicitly guard Simulation.LongPositionCount; "
            "the General-tab position limit remains the enforcement boundary."
        )

    return SystemTestValidationResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
    )
