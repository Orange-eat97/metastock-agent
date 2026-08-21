import os
import chromadb
from dotenv import load_dotenv

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext
from llama_index.core import Settings
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding


load_dotenv()

KNOWLEDGE_DIR = "knowledge_base"
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "metastock_primer"


def main() -> None:
    print("[build_index] Loading knowledge cards...")

    if not os.path.exists(KNOWLEDGE_DIR):
        raise RuntimeError(
            f"Knowledge directory not found: {KNOWLEDGE_DIR}. "
            "Make sure you are running this script from the repo root."
        )

    Settings.embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-small-en-v1.5"
    )

    documents = SimpleDirectoryReader(
        KNOWLEDGE_DIR,
        recursive=True,
        required_exts=[".md"],
    ).load_data()

    print(f"[build_index] Loaded {len(documents)} markdown documents.")

    if not documents:
        raise RuntimeError(
            "No markdown documents found. "
            "Check that knowledge_base/ contains .md files."
        )

    print("[build_index] Creating ChromaDB persistent client...")

    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

    existing_collections = [c.name for c in chroma_client.list_collections()]

    if COLLECTION_NAME in existing_collections:
        print(f"[build_index] Deleting existing collection: {COLLECTION_NAME}")
        chroma_client.delete_collection(COLLECTION_NAME)

    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print("[build_index] Splitting documents with TokenTextSplitter...")

    splitter = TokenTextSplitter(
        chunk_size=512,
        chunk_overlap=50,
    )

    print("[build_index] Building vector index...")

    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        transformations=[splitter],
    )

    print("[build_index] Done. Index saved to chroma_db/.")


if __name__ == "__main__":
    main()