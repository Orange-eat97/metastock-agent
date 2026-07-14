from __future__ import annotations

from enum import Enum


class ChatRoute(str, Enum):
    GENERATE_EXPLORER = "generate_explorer"
    REPAIR_EXPLORER = "repair_explorer"
    REVISE_EXPLORER = "revise_explorer"
    GET_EXPLORER = "get_explorer"
    GET_RAG_LOG = "get_rag_log"

    CREATE_METASTOCK_EXPLORER = (
        "create_explorer_in_metastock"
    )
    SELECT_METASTOCK_EXPLORER = (
        "select_explorer_in_metastock"
    )
    RUN_SELECTED_METASTOCK_EXPLORER = (
        "run_selected_explorer_in_metastock"
    )
    READ_METASTOCK_RESULTS = (
        "read_metastock_explorer_results"
    )

    GET_EXPLORER_RESULT = "get_explorer_result"
    GET_LATEST_EXPLORER_RESULT = (
        "get_latest_explorer_result"
    )
    LIST_EXPLORER_RESULTS = (
        "list_explorer_results"
    )

    RUN_EXPLORER = (
        "run_current_explorer_sequence"
    )
    RUN_AND_READ_EXPLORER = (
        "run_current_explorer_and_read_results_sequence"
    )
    CREATE_RUN_AND_READ_EXPLORER = (
        "create_run_and_read_explorer_sequence"
    )

    RESPOND = "respond"
    CLARIFY = "clarify"
    PLANNED_WORKFLOW = "planned_workflow"

    FALLBACK = "fallback"
