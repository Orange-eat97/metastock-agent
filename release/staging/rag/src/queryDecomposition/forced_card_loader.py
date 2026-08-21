# src/forced_card_loader.py

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_KNOWLEDGE_ROOT = "knowledge_base"


@dataclass(frozen=True)
class ForcedCard:
    title: str
    path: Path
    text: str


def normalize_card_name(name: str) -> str:
    """
    Normalize card names for fuzzy matching.

    Examples:
    - "Pattern: Volume Above Average" -> "volumeaboveaverage"
    - "volume_above_average.md" -> "volumeaboveaverage"
    """
    name = name.lower()
    name = name.replace("pattern:", "")
    name = name.replace(".md", "")
    return re.sub(r"[^a-z0-9]+", "", name)


def extract_card_title(text: str, path: Path) -> str:
    """
    Try to infer a card title from frontmatter, H1, or filename.
    """
    # Frontmatter title/name/function
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)

        for key in ["title", "name", "function"]:
            m = re.search(rf"^{key}\s*:\s*(.+)$", frontmatter, re.MULTILINE | re.IGNORECASE)
            if m:
                return m.group(1).strip().strip('"').strip("'")

    # Markdown H1
    h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    # Filename fallback
    return path.stem.replace("_", " ").replace("-", " ").title()


def load_all_markdown_cards(knowledge_root: str = DEFAULT_KNOWLEDGE_ROOT) -> list[ForcedCard]:
    root = Path(knowledge_root)

    if not root.exists():
        raise FileNotFoundError(
            f"Knowledge root not found: {root.resolve()}"
        )

    cards: list[ForcedCard] = []

    for path in root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")

        title = extract_card_title(text, path)

        cards.append(
            ForcedCard(
                title=title,
                path=path,
                text=text,
            )
        )

    return cards


def find_forced_cards(
    requested_card_names: list[str],
    knowledge_root: str = DEFAULT_KNOWLEDGE_ROOT,
) -> tuple[list[ForcedCard], list[str]]:
    """
    Returns:
    - matched cards
    - missing requested card names
    """
    all_cards = load_all_markdown_cards(knowledge_root)

    card_lookup: dict[str, ForcedCard] = {}

    for card in all_cards:
        normalized_title = normalize_card_name(card.title)
        normalized_stem = normalize_card_name(card.path.stem)

        card_lookup[normalized_title] = card
        card_lookup[normalized_stem] = card

        # Helpful fallback:
        # "Pattern: Volume Above Average" may be stored as "volume_above_average.md"
        if card.path.parent.name:
            combined = normalize_card_name(f"{card.path.parent.name} {card.path.stem}")
            card_lookup[combined] = card

    matched: list[ForcedCard] = []
    missing: list[str] = []
    seen_paths: set[Path] = set()

    for requested_name in requested_card_names:
        key = normalize_card_name(requested_name)
        card = card_lookup.get(key)

        if card is None:
            missing.append(requested_name)
            continue

        if card.path not in seen_paths:
            matched.append(card)
            seen_paths.add(card.path)

    return matched, missing


def build_forced_context_block(cards: list[ForcedCard]) -> str:
    if not cards:
        return ""

    blocks: list[str] = []

    for card in cards:
        blocks.append(
            "\n".join(
                [
                    f"### Forced Card: {card.title}",
                    f"Source path: {card.path.as_posix()}",
                    "",
                    card.text.strip(),
                ]
            )
        )

    return "\n\n".join(blocks)