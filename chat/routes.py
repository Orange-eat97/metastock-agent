from __future__ import annotations

from enum import Enum


class ChatRoute(str, Enum):
    GENERATE_EXPLORER = "generate_explorer"
    REPAIR_EXPLORER = "repair_explorer"
    GET_EXPLORER = "get_explorer"
    GET_RAG_LOG = "get_rag_log"
    RUN_EXPLORER = "run_explorer_in_metastock"
    FALLBACK = "fallback"
