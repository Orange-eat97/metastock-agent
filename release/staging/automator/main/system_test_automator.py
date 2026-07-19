from __future__ import annotations

from typing import Optional

from automator import (
    EXECUTION_POLL_INTERVAL,
    EXPLORE_LOAD_TIMEOUT,
    MEDIUM_DELAY,
    SEARCH_FILTER_TIMEOUT,
    build_shared_components,
)
from compartments.instrument_selector import InstrumentSelector
from compartments.system_test_console import SystemTestConsole
from compartments.system_test_creator import SystemTestCreator
from compartments.system_test_execution_monitor import (
    SystemTestExecutionMonitor,
)
from compartments.system_test_selector import SystemTestSelector
from compartments.system_test_workflow import SystemTestWorkflow
from system_test_definition import SystemTestCreationRequest
from system_test_request import SystemTestRequest
from ui_interacter.system_test_selectors import SystemTestSelectors


SYSTEM_TEST_LOAD_TIMEOUT = EXPLORE_LOAD_TIMEOUT
ALLOW_START_FALLBACK_CLICK = False
START_FALLBACK_ABSOLUTE_XY: Optional[
    tuple[int, int]
] = None


# ============================================================
# SHARED COMPOSITION
# ============================================================


def build_system_test_shared_components():
    """
    Build shared low-level components for System Tester.

    This mirrors automator.build_shared_components() while reusing its proven
    UiActions and MetaStockApp construction unchanged.
    """
    actions, _explore_selectors, app, _explore_console = (
        build_shared_components()
    )

    selectors = SystemTestSelectors()

    console = SystemTestConsole(
        actions=actions,
        selectors=selectors,
        system_test_load_timeout=(
            SYSTEM_TEST_LOAD_TIMEOUT
        ),
        allow_start_fallback_click=(
            ALLOW_START_FALLBACK_CLICK
        ),
        start_fallback_absolute_xy=(
            START_FALLBACK_ABSOLUTE_XY
        ),
    )

    return actions, selectors, app, console


# ============================================================
# RUN COMPOSITION ROOT
# ============================================================


def build_system_test_workflow(
    max_execution_wait_sec: int,
) -> SystemTestWorkflow:
    """
    Build and wire all System Tester run components.

    This is the direct counterpart of automator.build_workflow().
    """
    actions, selectors, app, console = (
        build_system_test_shared_components()
    )

    system_test_selector = SystemTestSelector(
        actions=actions,
        selectors=selectors,
        search_filter_timeout=SEARCH_FILTER_TIMEOUT,
    )

    instrument_selector = InstrumentSelector(
        actions=actions,
        selectors=selectors,
        medium_delay=MEDIUM_DELAY,
    )

    execution_monitor = SystemTestExecutionMonitor(
        max_execution_wait_sec=max_execution_wait_sec,
        poll_interval=EXECUTION_POLL_INTERVAL,
    )

    return SystemTestWorkflow(
        app=app,
        console=console,
        system_test_selector=system_test_selector,
        instrument_selector=instrument_selector,
        execution_monitor=execution_monitor,
    )


# ============================================================
# CREATE / SELECT / RUN BOUNDARIES
# ============================================================


def create_system_test_request(
    request: SystemTestCreationRequest,
) -> None:
    """
    Create a System Test in MetaStock.

    This function intentionally does not select or run the System Test.
    """
    actions, selectors, app, console = (
        build_system_test_shared_components()
    )

    creator = SystemTestCreator(
        actions=actions,
        selectors=selectors,
    )

    main_window = app.connect()
    console.open(main_window)
    creator.create(main_window, request)


def select_system_test_request(
    request: SystemTestRequest,
):
    """
    Select an existing System Test and instruments.

    This function intentionally does not create or run the System Test.
    """
    workflow = build_system_test_workflow(
        max_execution_wait_sec=(
            request.max_execution_wait_sec
        ),
    )
    return workflow.select_existing_system_test(request)


def run_selected_system_test_request(
    request: SystemTestRequest,
):
    """
    Run the currently selected System Test.

    This function intentionally does not create or select a System Test.
    It clicks Start, waits for completion, and leaves the status window open.
    """
    workflow = build_system_test_workflow(
        max_execution_wait_sec=(
            request.max_execution_wait_sec
        ),
    )
    return workflow.run_selected_until_status_ready(
        request
    )


def run_existing_system_test_request(
    request: SystemTestRequest,
):
    """
    Legacy convenience wrapper: select existing test, then run selected.
    """
    select_system_test_request(request)
    return run_selected_system_test_request(request)
