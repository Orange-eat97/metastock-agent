from __future__ import annotations

from orchestration.orchestrator import (
    LangGraphOrchestrator,
)
from orchestration.planner import (
    OpenAIPlanner,
)
from services.explorer_name_resolver import (
    ExplorerNameResolver,
)


def build_structured_orchestrator(
    *,
    recording_registry,
    explorer_name_resolver: (
        ExplorerNameResolver
    ),
) -> LangGraphOrchestrator:
    """
    Example only.

    In MS10.5 this composition will be moved into the real application
    wiring together with executable workflow definitions.
    """
    return LangGraphOrchestrator(
        recording_registry,
        planner=OpenAIPlanner(),
        explorer_name_resolver=(
            explorer_name_resolver
        ),
    )
