from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SystemTestRequest:
    """Intent-level request for running an existing MetaStock system test."""

    system_test_name: str
    instrument_names: Optional[list[str]] = None
    select_all_instruments: bool = True
    max_execution_wait_sec: int = 300
    read_status_if_visible: bool = True
