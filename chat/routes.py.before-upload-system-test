from __future__ import annotations

from enum import Enum


class ChatRoute(str, Enum):
    GENERATE_EXPLORER = "generate_explorer"
    GENERATE_AND_CREATE_EXPLORER = (
        "generate_and_create_explorer_sequence"
    )
    GENERATE_CREATE_AND_RUN_EXPLORER = (
        "generate_create_and_run_explorer_sequence"
    )
    GENERATE_CREATE_RUN_AND_READ_EXPLORER = (
        "generate_create_run_and_read_explorer_sequence"
    )

    REPAIR_EXPLORER = "repair_explorer"
    REPAIR_AND_CREATE_EXPLORER = (
        "repair_and_create_explorer_sequence"
    )
    REPAIR_CREATE_AND_RUN_EXPLORER = (
        "repair_create_and_run_explorer_sequence"
    )
    REPAIR_CREATE_RUN_AND_READ_EXPLORER = (
        "repair_create_run_and_read_explorer_sequence"
    )

    REVISE_EXPLORER = "revise_explorer"
    REVISE_AND_CREATE_EXPLORER = (
        "revise_and_create_explorer_sequence"
    )
    REVISE_CREATE_AND_RUN_EXPLORER = (
        "revise_create_and_run_explorer_sequence"
    )
    REVISE_CREATE_RUN_AND_READ_EXPLORER = (
        "revise_create_run_and_read_explorer_sequence"
    )
    # Compatibility route retained for the legacy planner path.
    REVISE_AND_RUN_EXPLORER = (
        "revise_and_run_explorer_sequence"
    )

    GET_EXPLORER = "get_explorer"
    GET_RAG_LOG = "get_rag_log"

    CREATE_METASTOCK_EXPLORER = (
        "create_explorer_in_metastock"
    )
    CREATE_AND_RUN_EXPLORER = (
        "create_and_run_explorer_sequence"
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
