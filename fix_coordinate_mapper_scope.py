from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path


class PatchError(RuntimeError):
    pass


OLD_BLOCK = """    result_scraper = ExplorationResultScraper(
        page_load_delay=0.35,
        max_stale_pages=4,
        coordinate_mapper=coordinate_mapper,
        result_row_fallback_delay=3.0,
    )
"""

NEW_BLOCK = """    result_scraper = ExplorationResultScraper(
        page_load_delay=0.35,
        max_stale_pages=4,
        coordinate_mapper=actions.coordinate_mapper,
        result_row_fallback_delay=3.0,
    )
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fix the result-scraper composition regression where "
            "build_workflow() references an out-of-scope coordinate_mapper."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=(
            "Path to release/staging/automator/main. "
            "Defaults to auto-detection from the current directory."
        ),
    )
    return parser.parse_args()


def resolve_root(explicit_root: Path | None) -> Path:
    if explicit_root is not None:
        root = explicit_root.expanduser().resolve()
    else:
        cwd = Path.cwd().resolve()
        candidates = [
            cwd,
            cwd / "release" / "staging" / "automator" / "main",
        ]
        root = next(
            (
                candidate
                for candidate in candidates
                if (candidate / "automator.py").is_file()
            ),
            candidates[-1],
        )

    automator_path = root / "automator.py"
    if not automator_path.is_file():
        raise PatchError(
            f"Could not find automator.py under: {root}"
        )

    return root


def patch_automator(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")

    if NEW_BLOCK in text:
        print("[SKIP] automator.py is already corrected.")
        return False

    count = text.count(OLD_BLOCK)
    if count != 1:
        raise PatchError(
            "Expected exactly one affected ExplorationResultScraper "
            f"composition block, found {count}. "
            "Refusing to patch an unexpected source state."
        )

    updated = text.replace(
        OLD_BLOCK,
        NEW_BLOCK,
        1,
    )

    # Validate before touching the real file.
    compile(
        updated,
        str(path),
        "exec",
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(
        f"{path.name}.bak.{timestamp}"
    )
    shutil.copy2(path, backup)
    print(f"[BACKUP] {backup}")

    path.write_text(
        updated,
        encoding="utf-8",
        newline="\n",
    )

    py_compile.compile(
        str(path),
        doraise=True,
    )

    print(
        "[PATCH] result_scraper now reuses "
        "actions.coordinate_mapper."
    )
    print(f"[PASS] Syntax check: {path}")
    return True


def main() -> int:
    args = parse_args()
    root = resolve_root(args.root)

    print(f"[ROOT] {root}")
    changed = patch_automator(
        root / "automator.py"
    )

    if changed:
        print(
            "[DONE] build_workflow() no longer references "
            "an undefined coordinate_mapper."
        )
    else:
        print("[DONE] No changes required.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PatchError, SyntaxError, py_compile.PyCompileError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
