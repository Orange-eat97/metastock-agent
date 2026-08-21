import argparse
import json
import re
import time
from typing import Any

import ollama

from src.retrieval.context_builder import build_context_for_query
from src.validator import validate_explorer_output
from src.explorer_excel_store import save_explorer_output_to_excel


DEFAULT_MODEL = "qwen2.5-coder:3b"


def build_prompt(user_query: str, context: str) -> str:
    return f"""
You are a MetaStock Explorer formula generator.

Your task:
Convert the user's natural language request into a MetaStock Explorer object.

Use the provided context only.

Critical rules:
1. Output JSON only. Do not include markdown.
2. Generate MetaStock syntax that is likely to run in MetaStock Explorer.
3. Use price field abbreviations: C, O, H, L, V, OI.
4. Do not invent unsupported MetaStock functions.
5. Use AND and OR, not && or ||.
6. Use = for equality, not ==.
7. explorer_code_body must be directly pasteable into MetaStock Explorer's Filter editor.
8. explorer_code_body may be independent from the columns.
9. Prefer direct formulas in explorer_code_body, for example RSI(14) < 30.
10. Do not include "Filter:" inside explorer_code_body.
11. Do not include "col A =" inside col_code.
12. col_code must be MetaStock formula code only, not natural language.
13. col_letter must be one uppercase letter from A to L.
14. If the user omits a common default, reflect the assumption in explorer_description.

Required JSON shape:
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
- Prefer direct formulas in explorer_code_body.
- Do not include "Filter:" inside explorer_code_body.
- Do not include "col A =" inside col_code.
- Do not include natural language inside explorer_code_body or col_code.

Column definition examples:
- If col_letter is A and col_code is RSI(14), the automator can construct: col A = RSI(14)
- If col_letter is B and col_code is Mov(C,50,S), the automator can construct: col B = Mov(C,50,S)

Good output example:
{{
  "explorer_name": "RSI Below 30",
  "explorer_description": "Finds stocks where RSI is below 30, indicating potential oversold conditions.",
  "explorer_code_body": "RSI(14) < 30",
  "col_definitions": [
    {{
      "col_letter": "A",
      "col_code": "RSI(14)"
    }}
  ]
}}

Another good output example:
{{
  "explorer_name": "RSI Below 30 Above MA50",
  "explorer_description": "Finds stocks where RSI is below 30 and the close is above the 50-period simple moving average.",
  "explorer_code_body": "RSI(14) < 30 AND C > Mov(C,50,S)",
  "col_definitions": [
    {{
      "col_letter": "A",
      "col_code": "C"
    }},
    {{
      "col_letter": "B",
      "col_code": "RSI(14)"
    }},
    {{
      "col_letter": "C",
      "col_code": "Mov(C,50,S)"
    }}
  ]
}}

Context:
{context}

User request:
{user_query}

Return JSON only.
""".strip()


def extract_json_object(text: str) -> dict[str, Any]:
    """
    Ollama usually returns clean JSON when format='json',
    but this keeps the script robust if the model adds extra text.
    """
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text}")

    return json.loads(match.group(0))


def generate_with_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    response = ollama.generate(
        model=model,
        prompt=prompt,
        format="json",
        options={
            "temperature": 0,
            "num_ctx": 8192,
        },
    )

    raw_text = response.get("response", "")
    return extract_json_object(raw_text)


def print_context_summary(
    user_query: str,
    dynamic_items: list[dict],
    prompt: str,
    model: str,
) -> None:
    print("\n=== Context Summary ===")
    print(f"Model: {model}")
    print(f"User query: {user_query}")

    print("\nMandatory base files:")
    print("  1. price_fields.md")
    print("  2. explorer_basic.md")
    print("  3. explorer_columns_filter.md")

    print("\nDynamic retrieved files:")
    if not dynamic_items:
        print("  No dynamic files retrieved.")
    else:
        for i, item in enumerate(dynamic_items, start=1):
            print(f"  {i}. {item['file_name']} | score={item['score']:.4f}")

    print("\nPrompt size:")
    print(f"  {len(prompt)} characters")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate MetaStock Explorer columns/filter using local Ollama."
    )

    parser.add_argument(
        "query",
        nargs="*",
        help="Natural language query. If omitted, interactive mode is used.",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model name. Default: {DEFAULT_MODEL}",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build context and show summary without calling Ollama.",
    )

    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="In dry-run mode, print the full prompt.",
    )
    
    parser.add_argument(
    "--no-save",
    action="store_true",
    help="Do not save generated JSON output to local Excel.",
    )

    parser.add_argument(
        "--excel-path",
        default="data/explorer_outputs.xlsx",
        help="Path to local Excel output file.",
    )

    return parser.parse_args()


def run_one_query(
    user_query: str,
    model: str,
    dry_run: bool = False,
    show_prompt: bool = False,
    save_output: bool = True,
    excel_path: str = "data/explorer_outputs.xlsx",
) -> None:
    print("\n[generate_explorer_local] Building context...")
    context, dynamic_items = build_context_for_query(user_query)

    prompt = build_prompt(user_query, context)

    print_context_summary(
        user_query=user_query,
        dynamic_items=dynamic_items,
        prompt=prompt,
        model=model,
    )

    if dry_run:
        if show_prompt:
            print("\n" + "=" * 100)
            print("FULL DRY RUN PROMPT")
            print("=" * 100)
            print(prompt)
        else:
            print("\n[DRY RUN] Ollama call skipped. Use --show-prompt to print the full prompt.")
        return

    print("\n[generate_explorer_local] Calling Ollama...")
    start = time.time()

    output = generate_with_ollama(
        prompt=prompt,
        model=model,
    )
    print(f"[generate_explorer_local] Ollama returned in {time.time() - start:.2f} seconds.")

    print("\n=== Explorer Output ===")
    print(json.dumps(output, indent=2))

    errors = validate_explorer_output(output)

    print("\n=== Validation ===")
    if errors:
        print("[FAILED]")
        for e in errors:
            print(f"- {e}")
    else:
        print("[PASSED]")

    if save_output:
        saved_path = save_explorer_output_to_excel(
            output=output,
            user_query=user_query,
            backend="ollama",
            model=model,
            validation_errors=errors,
            excel_path=excel_path,
        )
        print(f"\n[generate_explorer_local] Saved output to: {saved_path}")    

def main() -> None:
    args = parse_args()

    if args.query:
        user_query = " ".join(args.query).strip()
        run_one_query(
        user_query=user_query,
        model=args.model,
        dry_run=args.dry_run,
        show_prompt=args.show_prompt,
        save_output=not args.no_save,
        excel_path=args.excel_path,
    )
        return

    print("[generate_explorer_local] Interactive mode. Type 'exit' to quit.")

    while True:
        user_query = input("\nUser query: ").strip()

        if user_query.lower() in {"exit", "quit"}:
            break

        if not user_query:
            continue

        run_one_query(
            user_query=user_query,
            model=args.model,
            dry_run=args.dry_run,
            show_prompt=args.show_prompt,
            save_output=not args.no_save,
            excel_path=args.excel_path,
        )


if __name__ == "__main__":
    main()