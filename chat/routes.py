from __future__ import annotations

from enum import Enum


class ChatRoute(str, Enum):
    GENERATE_EXPLORER = "generate_explorer"
    REPAIR_EXPLORER = "repair_explorer"
    GET_EXPLORER = "get_explorer"
    GET_RAG_LOG = "get_rag_log"

    CREATE_METASTOCK_EXPLORER = "create_explorer_in_metastock"
    SELECT_METASTOCK_EXPLORER = "select_explorer_in_metastock"
    RUN_SELECTED_METASTOCK_EXPLORER = "run_selected_explorer_in_metastock"

    # Controller-level composition route. This is intentionally not a tool.
    # The controller handles it by calling SELECT_METASTOCK_EXPLORER and then
    # RUN_SELECTED_METASTOCK_EXPLORER as two separate tool calls.
    RUN_EXPLORER = "run_current_explorer_sequence"
    RUN_AND_READ_EXPLORER = "run_current_explorer_and_read_results_sequence"

    READ_METASTOCK_RESULTS = "read_metastock_explorer_results"
    FALLBACK = "fallback"
