from __future__ import annotations

from desktop_ui.explorer_template import (
    EXPLORER_TEMPLATE_TEXT,
    parse_explorer_template,
)


def test_template_parses_to_structured_explorer() -> None:
    text = EXPLORER_TEMPLATE_TEXT.replace(
        "Explorer name",
        "Uploaded RSI Explorer",
    ).replace(
        "Optional description",
        "Manual upload",
    ).replace(
        "Formula for Column A",
        "RSI(14)",
    ).replace(
        "Optional formula for Column B",
        "Mov(C,50,S)",
    ).replace(
        "Explorer filter formula",
        "ColA < 30 AND C > ColB",
    )

    result = parse_explorer_template(text)

    assert result.matched is True
    assert result.patch is not None
    assert result.errors == []
    assert result.patch.name == "Uploaded RSI Explorer"
    assert [item.label for item in result.patch.columns] == ["A", "B"]
    assert result.patch.columns[0].formula == "RSI(14)"
    assert result.patch.filter_formula == "ColA < 30 AND C > ColB"


def test_missing_end_marker_returns_transient_errors() -> None:
    result = parse_explorer_template(
        EXPLORER_TEMPLATE_TEXT.replace(
            "=== END METASTOCK EXPLORER ===",
            "",
        )
    )

    assert result.matched is True
    assert result.patch is not None
    assert any("Missing closing marker" in item for item in result.errors)
