from __future__ import annotations

from pywinauto.base_wrapper import BaseWrapper

from compartments.instrument_selector import InstrumentSelector
from compartments.metastock_app import MetaStockApp
from compartments.system_test_console import SystemTestConsole
from compartments.system_test_execution_monitor import (
    SystemTestExecutionMonitor,
)
from compartments.system_test_selector import SystemTestSelector
from system_test_request import SystemTestRequest
from ui_interacter.ui_core import log


class SystemTestWorkflow:
    """
    High-level MetaStock System Tester workflow.

    The primitive UI boundaries match ExploreWorkflow:

    - select_existing_system_test():
      open System Tester, select one test, select instruments.

    - run_selected_until_status_ready():
      assume selection is complete, click Start, wait for completion,
      and leave the completed execution status window open.
    """

    def __init__(
        self,
        app: MetaStockApp,
        console: SystemTestConsole,
        system_test_selector: SystemTestSelector,
        instrument_selector: InstrumentSelector,
        execution_monitor: SystemTestExecutionMonitor,
    ) -> None:
        self.app = app
        self.console = console
        self.system_test_selector = system_test_selector
        self.instrument_selector = instrument_selector
        self.execution_monitor = execution_monitor

    def select_existing_system_test(
        self,
        request: SystemTestRequest,
    ) -> BaseWrapper:
        """
        Select an existing System Test and instruments.

        This method does not create or run anything.
        """
        main = self.app.connect()
        self.console.open(main)
        self.system_test_selector.select(
            main,
            request.system_test_name,
        )

        if request.select_all_instruments:
            self.instrument_selector.ensure_all_selected(
                main
            )
        else:
            self.instrument_selector.select_named(
                main,
                request.instrument_names or [],
            )

        log(
            "System test and instruments selected. "
            "No execution has started."
        )
        return main

    def run_selected_until_status_ready(
        self,
        request: SystemTestRequest,
    ) -> BaseWrapper:
        """
        Run the currently selected System Test.

        This method assumes selection has already happened. It does not create
        or select a test. It starts execution, waits for completion, and leaves
        the completed execution status window open.
        """
        main = self.app.connect()
        self.console.start(main)

        execution_window = (
            self.execution_monitor.wait_for_window(main)
        )
        self.execution_monitor.wait_done(
            execution_window
        )

        refreshed_execution_window = (
            self.execution_monitor
            .find_execution_window_inside_main(main)
        )

        if refreshed_execution_window is not None:
            execution_window = refreshed_execution_window

        try:
            execution_window.set_focus()
        except Exception:
            pass

        log(
            "Selected System Test completed. Execution status "
            "window is ready."
        )
        return execution_window

    def run_until_status_ready(
        self,
        request: SystemTestRequest,
    ) -> BaseWrapper:
        """
        Legacy convenience wrapper: select existing test, then run it.
        """
        self.select_existing_system_test(request)
        return self.run_selected_until_status_ready(request)

    def run(
        self,
        request: SystemTestRequest,
    ) -> BaseWrapper:
        """
        Legacy combined CLI behavior: select -> run -> wait.
        """
        return self.run_until_status_ready(request)
