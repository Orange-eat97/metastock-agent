import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from src.supabase_store import (
    find_cached_explorer_output_by_query,
    save_explorer_output_to_supabase,
)

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from llama_index.core import Settings
from llama_index.llms.openai import OpenAI

from src.retrieval.context_builder import build_context_for_query
from src.validator import validate_explorer_output
from src.explorer_excel_store import save_explorer_output_to_excel


load_dotenv()


VALID_COL_LETTERS = set("ABCDEFGHIJKL")
MODEL = "gpt-5.5"

DEFAULT_EXCEL_PATH = "data/explorer_outputs.xlsx"
DEFAULT_AUTOMATOR_MAIN_DIR = Path(r"C:\GitHub\metastock-automator\main")
DEFAULT_AUTOMATOR_RUNNER = DEFAULT_AUTOMATOR_MAIN_DIR / "runLatestLlmResult.py"


class ColDefinition(BaseModel):
    col_letter: str = Field(
        description="Explorer column letter from A to L"
    )
    col_code: str = Field(
        description="MetaStock formula code body for this column, not natural language"
    )

    @field_validator("col_letter")
    @classmethod
    def validate_col_letter(cls, value: str) -> str:
        letter = value.strip().upper()
        if letter not in VALID_COL_LETTERS:
            raise ValueError("col_letter must be one of A through L.")
        return letter


class ExplorerOutput(BaseModel):
    explorer_name: str = Field(
        description=(
            "Short readable AI-managed Explorer name suitable for MetaStock. "
            "For an initial generation, prefix the otherwise generated name "
            "with the literal string AI_ and do not add a version suffix. "
            "This maps to explorer_body.explorer_name."
        )
    )
    explorer_description: str = Field(
        description="Optional explanation for the Explorer. This maps to explorer_body.explorer_description."
    )
    explorer_code_body: str = Field(
        description="Actual MetaStock Explorer Filter code body. Do not include the word Filter:"
    )
    col_definitions: list[ColDefinition] = Field(
        description="Column definitions for this Explorer. Each maps to col_definitions."
    )


def build_prompt(user_query: str, context: str) -> str:
    return f"""
You are a MetaStock Explorer formula generator.

Your task:
Convert the user's natural language request into a MetaStock Explorer object.

Use the provided context only.

Generation priorities:
1. Generate MetaStock syntax that is likely to run in MetaStock Explorer.
2. Use price field abbreviations from base context: C, O, H, L, V, OI.
3. Use retrieved function cards for exact MetaStock function syntax.
4. Use retrieved pattern cards for strategy composition, logical decomposition, and multi-condition formula structure.
5. Do not invent unsupported MetaStock functions.
6. Prefer simple valid formulas only when no retrieved pattern card suggests a richer structure.
7. When a pattern card is retrieved, follow its required logical components, formula building blocks, composition guidance, and pitfalls.
8. Use AND and OR, not && or ||.
9. Use = for equality, not ==.
10. If the user omits a common default, state the assumption by reflecting it in the description.

Explorer naming rules:
- Every newly generated Explorer is AI-managed.
- explorer_name must begin with the exact prefix `AI_`.
- After `AI_`, keep the concise descriptive Explorer name that you would
  otherwise generate.
- For an initial generation, do not append a version number.
- Initial-name format: `AI_<generated explorer name>`.
- Do not add `AI_` more than once.
- Keep the name concise enough for practical MetaStock searching.

Output must be valid JSON matching this exact schema:

{{
  "explorer_name": "string",
  "explorer_description": "string",
  "explorer_code_body": "string",
  "col_definitions": [
    {{
      "col_letter": "A",
      "col_code": "string"
    }}
  ]
}}

Database and automator contract:
- explorer_name maps to explorer_body.explorer_name.
- explorer_description maps to explorer_body.explorer_description.
- explorer_code_body maps to explorer_body.explorer_code_body.
- col_definitions maps to the col_definitions table.
- col_letter must be one uppercase letter from A to L.
- col_code must be the MetaStock formula body for that column.
- explorer_code_body must be the actual MetaStock Explorer Filter code body to paste into the Filter editor.
- explorer_code_body may be independent from col_definitions.
- Prefer direct formulas in explorer_code_body, for example RSI(14) < 30.
- Do not include "Filter:" inside explorer_code_body.
- Do not include "col A =" inside col_code.
- Do not include natural language inside explorer_code_body or col_code.

Column definition examples:
- If col_letter is A and col_code is RSI(14), the automator can construct: col A = RSI(14)
- If col_letter is B and col_code is Mov(C,50,S), the automator can construct: col B = Mov(C,50,S)

Pattern card usage rules:
- Pattern cards are not rigid templates.
- Do not blindly copy every example composition from a pattern card.
- Select only the components relevant to the user request.
- If the user asks for a pattern such as breakout, breakdown, volume spike, pullback, bounce, trend confirmation, or momentum confirmation, prefer the retrieved pattern card's composition guidance over a shallow single-condition formula.
- If a pattern card says a condition requires multiple components, include those components in explorer_code_body.
- Choose col_definitions that help inspect why the symbol passed the filter.
- Do not force every observable output from a pattern card into columns.

Good output example:
{{
  "explorer_name": "AI_RSI Below 30",
  "explorer_description": "Finds stocks where RSI is below 30, indicating potential oversold conditions.",
  "explorer_code_body": "RSI(14) < 30",
  "col_definitions": [
    {{
      "col_letter": "A",
      "col_code": "RSI(14)"
    }}
  ]
}}

Context:
{context}

User request:
{user_query}

Return JSON only.
""".strip()


def generate_with_openai(prompt: str) -> dict[str, Any]:
    Settings.llm = OpenAI(
        model=MODEL,
        temperature=0,
    )

    structured_llm = Settings.llm.as_structured_llm(ExplorerOutput)
    result = structured_llm.complete(prompt)

    output: ExplorerOutput = result.raw
    return output.model_dump()


def call_automator_latest_llm_result(
    *,
    excel_path: str | Path,
    automator_runner: str | Path = DEFAULT_AUTOMATOR_RUNNER,
    instruments: str = "all",
    max_wait: int = 300,
    dry_run: bool = False,
    allow_invalid: bool = False,
) -> None:
    """
    Calls the automator-side bridge.

    The automator reads the latest row from the Excel file's full_output_json column.
    """
    runner_path = Path(automator_runner)
    automator_main_dir = runner_path.parent

    if not runner_path.exists():
        raise FileNotFoundError(f"Automator runner not found: {runner_path}")

    resolved_excel_path = Path(excel_path).resolve()

    if not resolved_excel_path.exists():
        raise FileNotFoundError(f"Excel output file not found: {resolved_excel_path}")

    cmd = [
        sys.executable,
        str(runner_path),
        "--excel-path",
        str(resolved_excel_path),
        "--instruments",
        instruments,
        "--max-wait",
        str(max_wait),
    ]

    if dry_run:
        cmd.append("--dry-run")

    if allow_invalid:
        cmd.append("--allow-invalid")

    print("\n=== Calling MetaStock Automator ===")
    print(" ".join(f'"{part}"' if " " in part else part for part in cmd))
    print()

    completed = subprocess.run(
        cmd,
        cwd=str(automator_main_dir),
        text=True,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Automator failed with exit code {completed.returncode}."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate MetaStock Explorer columns/filter from natural language."
    )

    parser.add_argument(
        "query",
        nargs="*",
        help="Natural language query. If omitted, interactive mode is used.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build context and show a brief summary without calling the LLM.",
    )

    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="In dry-run mode, print the full prompt. This can be very long.",
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save generated JSON output to local Excel.",
    )

    parser.add_argument(
        "--excel-path",
        default=DEFAULT_EXCEL_PATH,
        help="Path to local Excel output file.",
    )

    parser.add_argument(
        "--run-automator",
        action="store_true",
        help="After saving generated JSON output to Excel, call the MetaStock automator.",
    )

    parser.add_argument(
        "--automator-dry-run",
        action="store_true",
        help="Call the automator in dry-run mode. Only prints the automator request.",
    )

    parser.add_argument(
        "--automator-runner",
        default=str(DEFAULT_AUTOMATOR_RUNNER),
        help="Path to automator runner script, usually runLatestLlmResult.py.",
    )

    parser.add_argument(
        "--instruments",
        default="all",
        help="Instrument selection passed to automator. Example: all, SGX, or SGX,NASDAQ.",
    )

    parser.add_argument(
        "--automator-max-wait",
        type=int,
        default=300,
        help="Maximum seconds automator should wait for exploration execution.",
    )

    parser.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Allow automator to read latest row even if validation_passed is false.",
    )

    parser.add_argument(
        "--save-supabase",
        action="store_true",
        help="Save generated Explorer output to Supabase.",
    )

    parser.add_argument(
        "--use-supabase-cache",
        action="store_true",
        help=(
            "Before calling the LLM, check Supabase for the exact same user_query "
            "and reuse the stored output if found."
        ),
    )

    parser.add_argument(
        "--cache-any-model",
        action="store_true",
        help=(
            "When using Supabase cache, allow cached outputs from any model. "
            "By default, cache is restricted to the current MODEL."
        ),
    )

    return parser.parse_args()


def print_context_summary(
    user_query: str,
    dynamic_items: list[dict],
    prompt: str,
) -> None:
    print("\n=== Context Summary ===")
    print(f"User query: {user_query}")

    print("\nRetrieval backend:")
    if dynamic_items:
        print(f"  Dynamic: {dynamic_items[0].get('retrieval_source', 'unknown')}")
    else:
        print("  Dynamic: no dynamic retrieval result")

    print("  Base: supabase.rag_cards")
    
    print("\nMandatory base files:")
    print("  1. price_fields.md")
    print("  2. explorer_basic.md")
    print("  3. explorer_columns_filter.md")

    print("\nRetrieved cards:")
    if not dynamic_items:
        print("  None")
    else:
        for i, item in enumerate(dynamic_items, start=1):
            title = item.get("title") or item.get("file_name") or "Untitled"
            print(f"  {i}. {title}")

    print("\nPrompt size:")
    print(f"  {len(prompt)} characters")


def run_one_query(
    user_query: str,
    dry_run: bool = False,
    show_prompt: bool = False,
    save_output: bool = True,
    excel_path: str = DEFAULT_EXCEL_PATH,
    save_supabase: bool = False,
    use_supabase_cache: bool = False,
    cache_any_model: bool = False,
    run_automator: bool = False,
    automator_dry_run: bool = False,
    automator_runner: str = str(DEFAULT_AUTOMATOR_RUNNER),
    instruments: str = "all",
    automator_max_wait: int = 300,
    allow_invalid: bool = False,
) -> None:
    if run_automator and not save_output:
        raise ValueError(
            "--run-automator requires saving to Excel. Remove --no-save."
        )

    cached_row: dict[str, Any] | None = None
    cached_explorer_id: str | None = None

    # ============================================================
    # Supabase cache check FIRST
    # ============================================================
    if use_supabase_cache and not dry_run:
        print("\n[generate_explorer] Checking Supabase cache for exact user_query match...")

        cached_row = find_cached_explorer_output_by_query(
            user_query=user_query,
            require_validation_passed=True,
            model=None if cache_any_model else MODEL,
        )

        if cached_row:
            cached_explorer_id = str(cached_row["id"])
            output = cached_row["full_output_json"]

            print("[generate_explorer] Supabase cache hit. GPT call skipped.")
            print(f"[generate_explorer] cached explorer_id: {cached_explorer_id}")
            print(f"[generate_explorer] cached created_at: {cached_row.get('created_at')}")

            print("\n=== Explorer Output ===")
            print(json.dumps(output, indent=2))

            errors = validate_explorer_output(output) or []

            print("\n=== Validation ===")
            if errors:
                print("[FAILED]")
                for e in errors:
                    print(f"- {e}")
            else:
                print("[PASSED]")

            saved_path: Path | None = None

            if save_output:
                saved_path = save_explorer_output_to_excel(
                    output=output,
                    user_query=user_query,
                    backend=str(cached_row.get("backend") or "supabase-cache"),
                    model=str(cached_row.get("model") or MODEL),
                    validation_errors=errors,
                    excel_path=excel_path,
                )
                print(f"\n[generate_explorer] Saved cached output to Excel: {saved_path}")

            if run_automator:
                if saved_path is None:
                    raise RuntimeError(
                        "Automator currently needs Excel bridge. Keep save_output=True."
                    )

                if errors and not allow_invalid:
                    raise RuntimeError(
                        "Cached Explorer failed validation, so automator was not called. "
                        "Use --allow-invalid only if you intentionally want to test invalid output."
                    )

                call_automator_latest_llm_result(
                    excel_path=saved_path,
                    automator_runner=automator_runner,
                    instruments=instruments,
                    max_wait=automator_max_wait,
                    dry_run=automator_dry_run,
                    allow_invalid=allow_invalid,
                )

            return

        print("[generate_explorer] Supabase cache miss. Building context and calling GPT.")

    # ============================================================
    # Build RAG context only after cache miss / dry-run
    # ============================================================
    print("\n[generate_explorer] Building context...")
    context, dynamic_items = build_context_for_query(user_query)

    prompt = build_prompt(user_query, context)

    print_context_summary(
        user_query=user_query,
        dynamic_items=dynamic_items,
        prompt=prompt,
    )

    if dry_run:
        if show_prompt:
            print("\n" + "=" * 100)
            print("FULL DRY RUN PROMPT")
            print("=" * 100)
            print(prompt)

        print("\n[DRY RUN] LLM call skipped.")
        return

    print("\n[generate_explorer] Calling LLM...")

    output = generate_with_openai(prompt)

    print("\n=== Explorer Output ===")
    print(json.dumps(output, indent=2))

    errors = validate_explorer_output(output) or []

    print("\n=== Validation ===")
    if errors:
        print("[FAILED]")
        for e in errors:
            print(f"- {e}")
    else:
        print("[PASSED]")

    saved_path: Path | None = None

    if save_output:
        saved_path = save_explorer_output_to_excel(
            output=output,
            user_query=user_query,
            backend="openai",
            model=MODEL,
            validation_errors=errors,
            excel_path=excel_path,
        )
        print(f"\n[generate_explorer] Saved output to: {saved_path}")

    explorer_id: str | None = None

    if save_supabase:
        explorer_id = save_explorer_output_to_supabase(
            output=output,
            user_query=user_query,
            backend="openai",
            model=MODEL,
            validation_errors=errors,
        )

        print("\n[generate_explorer] Saved output to Supabase.")
        print(f"[generate_explorer] explorer_id: {explorer_id}")

    if run_automator:
        if saved_path is None:
            raise RuntimeError("Automator requested but no Excel file was saved.")

        if errors and not allow_invalid:
            raise RuntimeError(
                "Generated Explorer failed validation, so automator was not called. "
                "Use --allow-invalid only if you intentionally want to test invalid output."
            )

        call_automator_latest_llm_result(
            excel_path=saved_path,
            automator_runner=automator_runner,
            instruments=instruments,
            max_wait=automator_max_wait,
            dry_run=automator_dry_run,
            allow_invalid=allow_invalid,
        )


def main() -> None:
    args = parse_args()

    if args.query:
        user_query = " ".join(args.query).strip()
        run_one_query(
            user_query,

            dry_run=args.dry_run,

            use_supabase_cache=args.use_supabase_cache,
            cache_any_model=args.cache_any_model,

            show_prompt=args.show_prompt,

            save_output=not args.no_save,
            excel_path=args.excel_path,

            run_automator=args.run_automator,
            automator_dry_run=args.automator_dry_run,
            automator_runner=args.automator_runner,
            instruments=args.instruments,
            automator_max_wait=args.automator_max_wait,
            allow_invalid=args.allow_invalid,

            save_supabase=args.save_supabase,
        )
        return

    print("[generate_explorer] Interactive mode. Type 'exit' to quit.")

    while True:
        user_query = input("\nUser query: ").strip()

        if user_query.lower() in {"exit", "quit"}:
            break

        if not user_query:
            continue

        run_one_query(
            user_query,
            dry_run=args.dry_run,

            use_supabase_cache=args.use_supabase_cache,
            cache_any_model=args.cache_any_model,

            show_prompt=args.show_prompt,
            save_output=not args.no_save,
            excel_path=args.excel_path,
            run_automator=args.run_automator,
            automator_dry_run=args.automator_dry_run,
            automator_runner=args.automator_runner,
            instruments=args.instruments,
            automator_max_wait=args.automator_max_wait,
            allow_invalid=args.allow_invalid,
            
            save_supabase=args.save_supabase,
        )


if __name__ == "__main__":
    main()