from __future__ import annotations

import json
import re
from typing import Any, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.explorer_formula_expander import expand_explorer_filter
from src.rag_service import (
    RetrievedCardRef,
    ValidationResult,
    _RagServiceBase,
)
from src.system_test_definition import (
    GeneralSettings,
    OrderSignal,
    Orders,
    PositionLimit,
    SystemTestDefinition,
    SystemTestMetadata,
    ToggleSettings,
)
from src.system_test_validator import validate_system_test_definition


SYSTEM_TEST_TABLE = "system_test_outputs"
SYSTEM_TEST_CONTEXT_PATHS = [
    "references/system_tester_environment.md",
    "references/simulation_functions.md",
    "templates/explorer_to_system_test.md",
    "patterns/system_test_long_only.md",
]


class SystemTestConversionNeedsExitError(ValueError):
    """Raised when a safe exit cannot be inferred without user guidance."""


class ConvertExplorerToSystemTestInput(BaseModel):
    source_explorer_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    sell_signal_formula: str | None = None
    conversion_instruction: str | None = None


class GeneratedExitSignal(BaseModel):
    sell_signal_formula: str = Field(
        min_length=1,
        description="MetaStock Exit Long condition formula body.",
    )


class SystemTestConversionResponse(BaseModel):
    system_test_id: UUID
    source_explorer_id: UUID
    system_test: SystemTestDefinition
    service_log: str | None = None
    service_log_created_at: str | None = None
    retrieved_refs: list[RetrievedCardRef] = Field(default_factory=list)
    validation: ValidationResult


ExitSignalGenerator = Callable[
    [dict[str, Any], str, str, str],
    str,
]


class RagSystemTestConversionService(_RagServiceBase):
    """Convert one validated Explorer artifact into an Automator-ready System Test.

    The buy side is deterministic: the expanded Explorer filter is preserved and
    guarded so that at most one long position can be open. The sell side is:

    1. the explicit sell_signal_formula supplied by the caller;
    2. a safely reversible Cross(A,B) converted to Cross(B,A); or
    3. generated from a caller-provided conversion_instruction using only the
       dedicated Primer-derived System Tester context cards.

    The service stores a new immutable system_test_outputs artifact. It never
    invokes pywinauto or MetaStock directly.
    """

    def __init__(
        self,
        config=None,
        *,
        exit_signal_generator: ExitSignalGenerator | None = None,
    ) -> None:
        super().__init__(config=config)
        self.exit_signal_generator = (
            exit_signal_generator or self._generate_exit_with_openai
        )

    def convert_explorer_to_system_test(
        self,
        payload: ConvertExplorerToSystemTestInput,
    ) -> SystemTestConversionResponse:
        source_id = str(payload.source_explorer_id)
        source_row = self._fetch_explorer_output(source_id)

        if source_row.get("validation_passed") is not True:
            raise ValueError(
                "Only a validated explorer_outputs artifact can be converted."
            )

        explorer_output = source_row.get("full_output_json")
        if not isinstance(explorer_output, dict):
            raise ValueError("Stored Explorer full_output_json must be an object.")

        expanded = expand_explorer_filter(explorer_output)
        buy_formula = self._build_buy_signal(expanded.expanded_filter)

        retrieved_refs: list[RetrievedCardRef] = []
        sell_formula = str(payload.sell_signal_formula or "").strip()

        if not sell_formula:
            sell_formula = self._reverse_simple_cross(expanded.expanded_filter) or ""

        if not sell_formula:
            instruction = str(payload.conversion_instruction or "").strip()
            if not instruction:
                raise SystemTestConversionNeedsExitError(
                    "The Explorer entry filter does not have an unambiguous reversible "
                    "Cross(A,B) exit. Supply sell_signal_formula or a precise "
                    "conversion_instruction for the long exit."
                )

            context, retrieved_refs = self._load_system_test_context()
            sell_formula = self.exit_signal_generator(
                explorer_output,
                expanded.expanded_filter,
                instruction,
                context,
            ).strip()

        system_test_id = uuid4()
        description = (
            str(payload.description).strip()
            if payload.description is not None
            else "Created from a validated Explorer output."
        )

        definition = SystemTestDefinition(
            system_test_id=system_test_id,
            source_explorer_id=payload.source_explorer_id,
            name=payload.name,
            description=description,
            general=GeneralSettings(
                order_bias="long",
                portfolio_bias="single",
                position_limit=PositionLimit(
                    enabled=True,
                    max_positions=1,
                ),
            ),
            orders=Orders(
                buy=OrderSignal(
                    enabled=True,
                    signal_formula=buy_formula,
                ),
                sell=OrderSignal(
                    enabled=True,
                    signal_formula=sell_formula,
                ),
                sell_short=OrderSignal(
                    enabled=False,
                    signal_formula="",
                ),
                buy_to_cover=OrderSignal(
                    enabled=False,
                    signal_formula="",
                ),
            ),
            stops=ToggleSettings(enabled=False),
            optimizations=ToggleSettings(enabled=False),
            metadata=SystemTestMetadata(
                generator="metastock-RAG-LLM",
                conversion_kind="explorer_to_system_test",
            ),
        )

        validation = validate_system_test_definition(definition)
        stored_row = self._save_system_test(
            definition=definition,
            source_explorer_created_at=self._as_optional_str(
                source_row.get("created_at")
            ),
            expanded_filter=expanded.expanded_filter,
            retrieved_refs=retrieved_refs,
            validation=validation,
        )

        log_row = self._save_rag_service_log(
            event_type="rag_service.system_test_conversion",
            user_query=str(source_row.get("user_query") or ""),
            explorer_output_id=source_id,
            explorer_output_created_at=self._as_optional_str(
                source_row.get("created_at")
            ),
            metadata={
                "system_test_id": str(system_test_id),
                "source_explorer_id": source_id,
                "conversion_kind": "explorer_to_system_test",
                "validation_passed": validation.passed,
                "validation_error_count": len(validation.errors),
                "validation_warning_count": len(validation.warnings),
                "retrieved_ref_count": len(retrieved_refs),
                "stored_row_created_at": stored_row.get("created_at"),
            },
        )

        self._attach_service_log(
            system_test_id=str(system_test_id),
            service_log_id=str(log_row["log_id"]),
        )

        return SystemTestConversionResponse(
            system_test_id=system_test_id,
            source_explorer_id=payload.source_explorer_id,
            system_test=definition,
            service_log=str(log_row.get("log_id") or "") or None,
            service_log_created_at=self._as_optional_str(
                log_row.get("created_at")
            ),
            retrieved_refs=retrieved_refs,
            validation=ValidationResult(
                passed=validation.passed,
                errors=validation.errors,
                warnings=validation.warnings,
            ),
        )

    def get_system_test(self, system_test_id: str | UUID) -> SystemTestDefinition:
        cleaned_id = self._clean_required_text(
            str(system_test_id),
            "system_test_id",
        )
        response = (
            self._make_supabase_client()
            .table(SYSTEM_TEST_TABLE)
            .select("id, full_output_json")
            .eq("id", cleaned_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise ValueError(
                f"No {SYSTEM_TEST_TABLE} row found for id={cleaned_id}"
            )
        output = response.data[0].get("full_output_json")
        return SystemTestDefinition.model_validate(output)

    def _save_system_test(
        self,
        *,
        definition: SystemTestDefinition,
        source_explorer_created_at: str | None,
        expanded_filter: str,
        retrieved_refs: list[RetrievedCardRef],
        validation,
    ) -> dict[str, Any]:
        row = {
            "id": str(definition.system_test_id),
            "source_explorer_id": str(definition.source_explorer_id),
            "source_explorer_created_at": source_explorer_created_at,
            "schema_version": definition.schema_version,
            "name": definition.name,
            "description": definition.description,
            "expanded_explorer_filter": expanded_filter,
            "full_output_json": definition.model_dump(mode="json"),
            "validation_passed": validation.passed,
            "validation_errors": validation.errors,
            "validation_warnings": validation.warnings,
            "retrieved_refs": [
                item.model_dump(mode="json")
                for item in retrieved_refs
            ],
            "metadata": definition.metadata.model_dump(mode="json"),
        }
        response = (
            self._make_supabase_client()
            .table(SYSTEM_TEST_TABLE)
            .insert(row)
            .execute()
        )
        if not response.data:
            raise RuntimeError(
                "Supabase inserted no system_test_outputs row."
            )
        return response.data[0]

    def _attach_service_log(
        self,
        *,
        system_test_id: str,
        service_log_id: str,
    ) -> None:
        (
            self._make_supabase_client()
            .table(SYSTEM_TEST_TABLE)
            .update({"service_log_id": service_log_id})
            .eq("id", system_test_id)
            .execute()
        )

    def _load_system_test_context(
        self,
    ) -> tuple[str, list[RetrievedCardRef]]:
        client = self._make_supabase_client()
        response = (
            client.table("rag_cards")
            .select(
                "card_id,title,source_path,body_markdown"
            )
            .in_("source_path", SYSTEM_TEST_CONTEXT_PATHS)
            .execute()
        )
        rows = response.data or []
        by_path = {
            str(row.get("source_path") or ""): row
            for row in rows
            if isinstance(row, dict)
        }
        missing = [
            path
            for path in SYSTEM_TEST_CONTEXT_PATHS
            if path not in by_path
        ]
        if missing:
            raise RuntimeError(
                "Missing Primer-derived System Tester cards in Supabase: "
                + ", ".join(missing)
            )

        parts: list[str] = []
        refs: list[RetrievedCardRef] = []
        for path in SYSTEM_TEST_CONTEXT_PATHS:
            row = by_path[path]
            parts.append(
                f"## SYSTEM TEST CONTEXT: {path}\n"
                f"Card ID: {row['card_id']}\n"
                f"Title: {row.get('title', '')}\n\n"
                f"{row.get('body_markdown', '')}"
            )
            refs.append(
                RetrievedCardRef(
                    key=str(row["card_id"]),
                    table_title="rag_cards",
                    rag_score=None,
                    retrieval_reason=(
                        "Required Primer-derived System Tester conversion context."
                    ),
                )
            )
        return "\n\n".join(parts), refs

    def _generate_exit_with_openai(
        self,
        explorer_output: dict[str, Any],
        expanded_filter: str,
        instruction: str,
        context: str,
    ) -> str:
        from llama_index.core import Settings
        from llama_index.llms.openai import OpenAI

        Settings.llm = OpenAI(
            model=self.config.model,
            temperature=0,
        )
        structured_llm = Settings.llm.as_structured_llm(
            GeneratedExitSignal
        )
        prompt = f"""
You convert a validated MetaStock Explorer entry condition into one long-only
System Tester Exit Long condition.

Use only the Primer-derived context below. Do not invent functions. Return the
condition formula body only through the structured output.

Rules:
- The source Explorer is the entry strategy and must not be rewritten.
- Produce only the sell/Exit Long condition requested by the conversion instruction.
- Do not use ColA-ColL; the expanded filter is provided.
- Do not use OPT variables because optimizations are disabled.
- Do not introduce positive Ref offsets or future data.
- Simulation functions are current-bar values and must not be nested in Ref,
  Mov, HHV, LLV, ValueWhen, BarsSince, Sum, Cum, or ROC.
- Do not create short-side logic, stops, position sizing, or execution settings.

Stored Explorer JSON:
{json.dumps(explorer_output, indent=2)}

Expanded entry filter:
{expanded_filter}

Conversion instruction:
{instruction}

Primer-derived context:
{context}
""".strip()
        result = structured_llm.complete(prompt)
        output: GeneratedExitSignal = result.raw
        return output.sell_signal_formula

    @staticmethod
    def _build_buy_signal(expanded_filter: str) -> str:
        statements = _split_top_level_statements(expanded_filter)
        if not statements:
            raise ValueError("Expanded Explorer filter is empty.")

        terminal_expression = statements[-1].strip()
        declarations = statements[:-1]

        # A valid MetaStock formula may define variables and then finish with one
        # terminal logical expression. Preserve those declarations and assign only
        # the terminal expression to BuySignal.
        lines = [f"{statement.strip()};" for statement in declarations]
        lines.append(f"BuySignal := {terminal_expression};")
        lines.append("BuySignal AND Simulation.LongPositionCount = 0")
        return "\n".join(lines)

    @staticmethod
    def _reverse_simple_cross(formula: str) -> str | None:
        cleaned = formula.strip().rstrip(";")
        match = _match_whole_function_call(cleaned, "Cross")
        if match is None:
            return None
        args = _split_top_level_args(match)
        if len(args) != 2:
            return None
        return f"Cross({args[1]}, {args[0]})"


def _match_whole_function_call(
    formula: str,
    function_name: str,
) -> str | None:
    re_match = re.match(
        rf"^\s*{function_name}\s*\(",
        formula,
        flags=re.IGNORECASE,
    )
    if re_match is None:
        return None
    opening = formula.find("(", re_match.start())
    depth = 1
    cursor = opening + 1
    while cursor < len(formula) and depth:
        if formula[cursor] == "(":
            depth += 1
        elif formula[cursor] == ")":
            depth -= 1
        cursor += 1
    if depth != 0 or formula[cursor:].strip():
        return None
    return formula[opening + 1 : cursor - 1]


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


def _split_top_level_statements(formula: str) -> list[str]:
    statements: list[str] = []
    depth = 0
    start = 0
    in_comment = False

    for index, char in enumerate(formula):
        if char == "{":
            in_comment = True
        elif char == "}":
            in_comment = False
        elif not in_comment:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == ";" and depth == 0:
                statement = formula[start:index].strip()
                if statement:
                    statements.append(statement)
                start = index + 1

    trailing = formula[start:].strip().rstrip(";").strip()
    if trailing:
        statements.append(trailing)
    return statements
