'''
simple helper script to build vector embedding from local knowledge cards
using OpenAI embeddings. Uploads embedding and text into supabase.
Checks cache in supabase to avoid unnecessary OpenAI calls. Then rebuilds local ChromaDB

sample call: 
CLI: python -m src.build_cached_index_openai --folders functions templates --folder-map functions=functions templates=templates
explanation: process the cards in function and template and upload to supabase.

CLI: python -m src.build_cached_index_openai --folder-map functions=functions examples=examples references=references templates=templates
explanation: process all cards

CLI: python -m src.build_cached_index_openai
explanation: process all cards, no explicit folder level requirements.

python -m src.build_cached_index_openai --folders functions --folder-map functions=functions
upload only functions

python -m src.build_cached_index_openai --folders templates --folder-map templates=templates
upload only templates

python -m src.build_cached_index_openai --folders functions templates --folder-map functions=functions templates=templates
upload functions and templates, with explicit bucket mapping (same as default in this case)

python -m src.build_cached_index_openai --folders examples --folder-map examples=examples
upload only examples, with explicit bucket mapping (same as default in this case)

python -m src.build_cached_index_openai --folders references --folder-map references=references
upload only references, with explicit bucket mapping (same as default in this case)

python -m src.build_cached_index_openai --folder-map functions=functions templates=templates examples=examples references=references --force-embed
force OpenAI embedding regeneration for all cards, even if Supabase has same card_id/model/hash. Useful if you want to refresh embeddings with a new OpenAI model or if you suspect the existing embeddings are corrupted.

'''

from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path
from typing import Any

import chromadb
import yaml
from dotenv import load_dotenv
from openai import OpenAI
from supabase import Client, create_client


load_dotenv()

KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "knowledge_base")
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "metastock_primer")

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build cached OpenAI embedding index from local knowledge_base markdown cards."
    )

    parser.add_argument(
        "--knowledge-dir",
        default=KNOWLEDGE_DIR,
        help="Knowledge base root directory. Default: knowledge_base",
    )

    parser.add_argument(
        "--folders",
        nargs="*",
        default=None,
        help=(
            "Optional list of top-level folders under knowledge_base to upload. "
            "Example: --folders functions templates examples"
        ),
    )

    parser.add_argument(
        "--folder-map",
        nargs="*",
        default=[],
        help=(
            "Optional mapping from top-level folder to logical bucket/subtable. "
            "Example: --folder-map functions=functions examples=examples templates=templates"
        ),
    )

    parser.add_argument(
        "--skip-chroma",
        action="store_true",
        help="Only upsert Supabase cards/embeddings. Do not rebuild local Chroma.",
    )

    parser.add_argument(
        "--force-embed",
        action="store_true",
        help="Force OpenAI embedding regeneration even if Supabase has same card_id/model/hash.",
    )

    return parser.parse_args()


def parse_folder_map(raw_items: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for item in raw_items:
        if "=" not in item:
            raise ValueError(
                f"Invalid --folder-map item: {item!r}. Expected format: folder=bucket"
            )

        folder, bucket = item.split("=", 1)
        folder = folder.strip().strip("/\\")
        bucket = bucket.strip()

        if not folder or not bucket:
            raise ValueError(
                f"Invalid --folder-map item: {item!r}. Expected non-empty folder and bucket."
            )

        mapping[folder] = bucket

    return mapping

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def make_supabase_client() -> Client:
    return create_client(
        require_env("SUPABASE_URL"),
        require_env("SUPABASE_SERVICE_ROLE_KEY"),
    )


def make_openai_client() -> OpenAI:
    return OpenAI(api_key=require_env("OPENAI_API_KEY"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    raw = raw.lstrip("\ufeff")

    if not raw.startswith("---"):
        return {}, raw.strip()

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, flags=re.DOTALL)
    if not match:
        raise ValueError("Markdown file starts with frontmatter but could not be parsed.")

    frontmatter_raw = match.group(1)
    body = match.group(2)

    frontmatter = yaml.safe_load(frontmatter_raw) or {}
    if not isinstance(frontmatter, dict):
        raise ValueError("YAML frontmatter must parse into a dictionary.")

    return frontmatter, body.strip()


def markdown_to_plain_text(markdown: str) -> str:
    text = markdown

    # Keep code content, remove code fences.
    text = re.sub(r"```[a-zA-Z0-9_-]*", "", text)
    text = text.replace("```", "")

    # Remove heading markers.
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove markdown bold markers.
    text = text.replace("**", "").replace("__", "")

    # Convert markdown links [text](url) -> text.
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    return normalize_whitespace(text)


def extract_title(body_markdown: str, file_path: Path) -> str:
    for line in body_markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()

    return file_path.stem.replace("_", " ").replace("-", " ").title()


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned if cleaned else None


def infer_card_id(
    file_path: Path,
    knowledge_dir: Path,
    frontmatter: dict[str, Any],
    title: str,
) -> str:
    card_type = str(frontmatter.get("type") or "").strip().lower()

    function_name = frontmatter.get("function")
    template_name = frontmatter.get("template")
    category = frontmatter.get("category")

    relative = file_path.relative_to(knowledge_dir).with_suffix("")
    relative_id = slugify(".".join(relative.parts))

    if card_type == "function" and function_name:
        return f"function.{slugify(str(function_name))}"

    if card_type == "template" and template_name:
        return f"template.{slugify(str(template_name))}"

    if card_type == "reference" and category:
        return f"reference.{slugify(str(category))}"

    # Important:
    # examples/breakout.md and examples/ma_breakout.md may both have category=breakout.
    # So use file path for pattern/example cards.
    if card_type in {"pattern", "example"}:
        return f"{card_type}.{relative_id}"

    return relative_id


def build_embedding_text(
    title: str,
    frontmatter: dict[str, Any],
    body_markdown: str,
    plain_text: str,
) -> str:
    """
    This is the exact text sent to OpenAI for embedding.

    Keep it stable. If this changes, content_hash changes and embeddings regenerate.
    """
    lines: list[str] = []

    lines.append(f"Title: {title}")

    card_type = frontmatter.get("type")
    category = frontmatter.get("category")
    function_name = frontmatter.get("function")
    template_name = frontmatter.get("template")
    source = frontmatter.get("source")
    priority = frontmatter.get("priority")
    status = frontmatter.get("status")

    if card_type:
        lines.append(f"Type: {card_type}")
    if category:
        lines.append(f"Category: {category}")
    if function_name:
        lines.append(f"Function: {function_name}")
    if template_name:
        lines.append(f"Template: {template_name}")
    if source:
        lines.append(f"Source: {source}")
    if priority:
        lines.append(f"Priority: {priority}")
    if status:
        lines.append(f"Status: {status}")

    lines.append("Markdown card:")
    lines.append(body_markdown.strip())

    lines.append("Plain text card:")
    lines.append(plain_text.strip())

    return "\n".join(line for line in lines if str(line).strip()).strip()

def get_file_structure_fields(
    file_path: Path,
    knowledge_dir: Path,
    folder_map: dict[str, str],
) -> dict[str, Any]:
    relative = file_path.relative_to(knowledge_dir)
    relative_path = str(relative).replace("\\", "/")
    parts = list(relative.parts)

    top_folder = parts[0] if parts else ""
    folder_path = str(relative.parent).replace("\\", "/")

    if folder_path == ".":
        folder_path = ""

    file_stem = file_path.stem

    # Logical bucket/subtable:
    # 1. explicit folder_map if supplied
    # 2. otherwise top-level folder
    card_bucket = folder_map.get(top_folder, top_folder)

    return {
        "kb_root": knowledge_dir.name,
        "relative_path": relative_path,
        "folder_path": folder_path,
        "top_folder": top_folder,
        "file_stem": file_stem,
        "path_parts": parts,
        "card_bucket": card_bucket,
        "upload_target": card_bucket,
    }

def parse_markdown_card(
    file_path: Path,
    knowledge_dir: Path,
    folder_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    
    raw = file_path.read_text(encoding="utf-8")
    frontmatter, body_markdown = split_frontmatter(raw)
    plain_text = markdown_to_plain_text(body_markdown)
    title = extract_title(body_markdown, file_path)

    relative_path = str(file_path.relative_to(knowledge_dir)).replace("\\", "/")
    path_parts = relative_path.split("/")

    top_folder = path_parts[0] if path_parts else ""
    file_stem = file_path.stem
    folder_map = folder_map or {}
    card_bucket = folder_map.get(top_folder, top_folder or "unknown")

    card_id = infer_card_id(
        file_path=file_path,
        knowledge_dir=knowledge_dir,
        frontmatter=frontmatter,
        title=title,
    )

    embedded_text = build_embedding_text(
        title=title,
        frontmatter=frontmatter,
        body_markdown=body_markdown,
        plain_text=plain_text,
    )

    content_hash = sha256_text(embedded_text)

    card_type = str(frontmatter.get("type") or "unknown").strip().lower()

    structured_json = {
        "metadata": {
            "function_name": optional_str(frontmatter.get("function")),
            "template_name": optional_str(frontmatter.get("template")),
            "category": optional_str(frontmatter.get("category")),
            "source": optional_str(frontmatter.get("source")),
            "priority": optional_str(frontmatter.get("priority")),
            "status": optional_str(frontmatter.get("status")),
        },
        "file": {
            "source_path": relative_path,
            "top_folder": top_folder,
            "file_stem": file_stem,
            "card_bucket": card_bucket,
        },
    }

    return {
        "card_id": card_id,
        "card_type": card_type,
        "card_bucket": card_bucket,

        "title": title,
        "category": optional_str(frontmatter.get("category")),
        "source": optional_str(frontmatter.get("source")),
        "priority": optional_str(frontmatter.get("priority")),
        "status": optional_str(frontmatter.get("status")),

        "source_path": relative_path,
        "top_folder": top_folder,
        "file_stem": file_stem,

        "frontmatter": frontmatter,
        "body_markdown": body_markdown,
        "plain_text": plain_text,
        "embedded_text": embedded_text,
        "structured_json": structured_json,

        "content_hash": content_hash,
    }


def iter_markdown_files(
    knowledge_dir: Path,
    include_folders: list[str] | None = None,
) -> list[Path]:
    all_paths = sorted(
        path
        for path in knowledge_dir.rglob("*.md")
        if path.is_file()
    )

    if not include_folders:
        return all_paths

    allowed = {folder.strip().strip("/\\") for folder in include_folders}

    filtered: list[Path] = []

    for path in all_paths:
        relative = path.relative_to(knowledge_dir)
        parts = relative.parts

        if not parts:
            continue

        top_folder = parts[0]

        if top_folder in allowed:
            filtered.append(path)

    return filtered


def upsert_card(supabase: Client, card: dict[str, Any]) -> None:
    row = {
        "card_id": card["card_id"],
        "card_type": card["card_type"],
        "card_bucket": card["card_bucket"],

        "title": card["title"],
        "category": card["category"],
        "source": card["source"],
        "priority": card["priority"],
        "status": card["status"],

        "source_path": card["source_path"],
        "top_folder": card["top_folder"],
        "file_stem": card["file_stem"],

        "frontmatter": card["frontmatter"],
        "body_markdown": card["body_markdown"],
        "plain_text": card["plain_text"],
        "structured_json": card["structured_json"],

        "content_hash": card["content_hash"],
    }

    supabase.table("rag_cards").upsert(
        row,
        on_conflict="card_id",
    ).execute()


def get_existing_embedding(
    supabase: Client,
    card_id: str,
    embedding_model: str,
    content_hash: str,
) -> list[float] | None:
    response = (
        supabase.table("rag_card_embeddings")
        .select("embedding, content_hash")
        .eq("card_id", card_id)
        .eq("embedding_model", embedding_model)
        .eq("content_hash", content_hash)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    if not rows:
        return None

    embedding = rows[0].get("embedding")
    if embedding is None:
        return None

    # Supabase may return pgvector either as a Python list or as a string like "[0.1,0.2,...]".
    if isinstance(embedding, list):
        return [float(x) for x in embedding]

    if isinstance(embedding, str):
        cleaned = embedding.strip().lstrip("[").rstrip("]")
        if not cleaned:
            return None
        return [float(x.strip()) for x in cleaned.split(",")]

    raise TypeError(f"Unexpected embedding type from Supabase: {type(embedding)}")


def create_openai_embedding(openai_client: OpenAI, text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return [float(x) for x in response.data[0].embedding]


def upsert_embedding(
    supabase: Client,
    card: dict[str, Any],
    embedding: list[float],
) -> None:
    row = {
        "card_id": card["card_id"],
        "embedding_model": EMBEDDING_MODEL,
        "embedding": embedding,
        "embedded_text": card["embedded_text"],
        "content_hash": card["content_hash"],
    }

    supabase.table("rag_card_embeddings").upsert(
        row,
        on_conflict="card_id,embedding_model",
    ).execute()


def rebuild_chroma(
    chroma_items: list[dict[str, Any]],
) -> None:
    print("[build_index] Creating ChromaDB persistent client...")

    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

    existing_collections = [c.name for c in chroma_client.list_collections()]

    if COLLECTION_NAME in existing_collections:
        print(f"[build_index] Deleting existing Chroma collection: {COLLECTION_NAME}")
        chroma_client.delete_collection(COLLECTION_NAME)

    collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

    if not chroma_items:
        print("[build_index] No Chroma items to add.")
        return

    ids = [item["card_id"] for item in chroma_items]
    documents = [item["embedded_text"] for item in chroma_items]
    embeddings = [item["embedding"] for item in chroma_items]
    metadatas = [
        {
            "card_id": item["card_id"],
            "title": item["title"],
            "card_type": item["card_type"],
            "card_bucket": item["card_bucket"],
            "category": item["category"] or "",
            "source": item["source"] or "",
            "priority": item["priority"] or "",
            "status": item["status"] or "",
            "source_path": item["source_path"],
            "top_folder": item["top_folder"],
            "file_stem": item["file_stem"],
            "content_hash": item["content_hash"],
            "embedding_model": EMBEDDING_MODEL,
        }
        for item in chroma_items
    ]

    print(f"[build_index] Adding {len(chroma_items)} card embedding(s) to Chroma...")

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    print(f"[build_index] Chroma index saved to {CHROMA_DIR}/.")


def main() -> None:
    args = parse_args()
    folder_map = parse_folder_map(args.folder_map)

    print("[build_index] Loading knowledge cards...")

    knowledge_dir = Path(args.knowledge_dir).resolve()

    if not knowledge_dir.exists():
        raise RuntimeError(
            f"Knowledge directory not found: {knowledge_dir}. "
            "Make sure you are running this script from the repo root."
        )

    supabase = make_supabase_client()
    openai_client = make_openai_client()

    markdown_files = iter_markdown_files(
        knowledge_dir=knowledge_dir,
        include_folders=args.folders,
    )

    print(f"[build_index] Knowledge dir: {knowledge_dir}")
    print(f"[build_index] Included folders: {args.folders or 'ALL'}")
    print(f"[build_index] Folder map: {folder_map or 'default top_folder mapping'}")
    print(f"[build_index] Found {len(markdown_files)} markdown card(s).")

    if not markdown_files:
        raise RuntimeError(
            "No markdown documents found. "
            "Check that knowledge_base/ contains .md files or that --folders is correct."
        )

    chroma_items: list[dict[str, Any]] = []

    skipped_existing = 0
    newly_embedded = 0

    for file_path in markdown_files:
        card = parse_markdown_card(
            file_path=file_path,
            knowledge_dir=knowledge_dir,
            folder_map=folder_map,
        )

        print()
        print(f"[build_index] Card: {card['card_id']}")
        print(f"[build_index] Source: {card['source_path']}")
        print(f"[build_index] Top folder: {card['top_folder']}")
        print(f"[build_index] Bucket: {card['card_bucket']}")
        print(f"[build_index] Hash: {card['content_hash'][:12]}...")

        upsert_card(supabase, card)

        existing_embedding = None

        if not args.force_embed:
            existing_embedding = get_existing_embedding(
                supabase=supabase,
                card_id=card["card_id"],
                embedding_model=EMBEDDING_MODEL,
                content_hash=card["content_hash"],
            )

        if existing_embedding is not None:
            print("[build_index] Supabase embedding found. Skipping OpenAI call.")
            embedding = existing_embedding
            skipped_existing += 1
        else:
            print("[build_index] No matching Supabase embedding. Calling OpenAI...")
            embedding = create_openai_embedding(openai_client, card["embedded_text"])
            upsert_embedding(supabase, card, embedding)
            newly_embedded += 1

        chroma_items.append(
            {
                **card,
                "embedding": embedding,
            }
        )

    if not args.skip_chroma:
        print()
        print("[build_index] Rebuilding local Chroma from cached/new embeddings...")
        rebuild_chroma(chroma_items)
    else:
        print()
        print("[build_index] --skip-chroma enabled. Not rebuilding local Chroma.")

    print()
    print("=== build_index summary ===")
    print(f"Cards processed: {len(markdown_files)}")
    print(f"Embeddings reused from Supabase: {skipped_existing}")
    print(f"New OpenAI embedding calls: {newly_embedded}")

    if newly_embedded == 0:
        print(
            "[build_index] All selected card embeddings already exist in Supabase. "
            "No OpenAI embedding calls were made."
        )
    else:
        print(
            f"[build_index] {newly_embedded} embedding(s) were newly generated "
            "and stored in Supabase."
        )

    print("[build_index] Done.")


if __name__ == "__main__":
    main()