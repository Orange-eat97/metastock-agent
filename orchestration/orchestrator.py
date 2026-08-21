from __future__ import annotations

import re
from typing import Any, Protocol

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)

from chat.controller import (
    ToolRegistryProtocol,
)
from chat.models import (
    ChatTurnInput,
    ChatTurnOutput,
)
from chat.routes import (
    ChatRoute,
)
from chat.router import (
    DeterministicChatRouter,
)

from chat.result_mapper import update_context_from_tool_result

from orchestration.context_resolver import (
    ExplorerReferenceResolverProtocol,
)
from orchestration.conversation_graph import (
    build_conversational_graph,
)
from orchestration.conversation_model import (
    ConversationDriverProtocol,
)
from orchestration.graph import (
    build_deterministic_parity_graph,
    build_structured_planning_graph,
)
from orchestration.planner import (
    PlannerProtocol,
)
from orchestration.response_composer import (
    ResponseComposerProtocol,
)


class CompiledGraphProtocol(Protocol):
    def invoke(
        self,
        input: dict[str, Any],
        config: (
            dict[str, Any] | None
        ) = None,
        *,
        context: (
            dict[str, Any] | None
        ) = None,
    ) -> dict[str, Any]:
        ...


_DIRECT_CURRENT_EXPLORER_REQUESTS = frozenset(
    {
        "show me the current explorer",
        "show the current explorer",
        "show current explorer",
        "display the current explorer",
        "display current explorer",
        "open the current explorer",
        "open current explorer",
        "show me the active explorer",
        "show the active explorer",
        "show active explorer",
        "display the active explorer",
        "display active explorer",
        "open the active explorer",
        "open active explorer",
    }
)


def _normalise_direct_request(value: str) -> str:
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    )


class LangGraphOrchestrator:
    def __init__(
        self,
        registry: ToolRegistryProtocol,
        router: (
            DeterministicChatRouter | None
        ) = None,
        *,
        conversation_driver: (
            ConversationDriverProtocol | None
        ) = None,
        # Kept temporarily so the existing structured-planner tests and
        # rollback path remain valid during this migration.
        planner: PlannerProtocol | None = None,
        response_composer: (
            ResponseComposerProtocol | None
        ) = None,
        explorer_name_resolver: (
            ExplorerReferenceResolverProtocol
            | None
        ) = None,
        available_workflows: (
            list[str] | None
        ) = None,
        enable_deterministic_fallback: bool = True,
        checkpointer: (
            BaseCheckpointSaver | None
        ) = None,
        graph: (
            CompiledGraphProtocol | None
        ) = None,
    ) -> None:
        if (
            conversation_driver is not None
            and planner is not None
        ):
            raise ValueError(
                "Provide conversation_driver or "
                "planner, not both."
            )

        self._registry = registry
        self._structured_mode = (
            conversation_driver is not None
            or planner is not None
        )
        self._conversation_mode = (
            conversation_driver is not None
        )
        self._checkpointing_enabled = (
            checkpointer is not None
        )

        if graph is not None:
            self._graph = graph
        elif conversation_driver is not None:
            self._graph = (
                build_conversational_graph(
                    registry=registry,
                    driver=conversation_driver,
                    response_composer=(
                        response_composer
                    ),
                    explorer_name_resolver=(
                        explorer_name_resolver
                    ),
                    fallback_router=router,
                    enable_deterministic_fallback=(
                        enable_deterministic_fallback
                    ),
                    checkpointer=checkpointer,
                )
            )
        elif planner is None:
            self._graph = (
                build_deterministic_parity_graph(
                    registry=registry,
                    router=router,
                    checkpointer=checkpointer,
                )
            )
        else:
            # Temporary compatibility path. Production composition no longer
            # constructs OpenAIPlanner.
            self._graph = (
                build_structured_planning_graph(
                    registry=registry,
                    planner=planner,
                    response_composer=(
                        response_composer
                    ),
                    explorer_name_resolver=(
                        explorer_name_resolver
                    ),
                    fallback_router=router,
                    available_workflows=(
                        available_workflows
                    ),
                    enable_deterministic_fallback=(
                        enable_deterministic_fallback
                    ),
                    checkpointer=checkpointer,
                )
            )

    @property
    def graph(self) -> CompiledGraphProtocol:
        return self._graph

    @property
    def structured_mode(self) -> bool:
        return self._structured_mode

    @property
    def conversation_mode(self) -> bool:
        return self._conversation_mode

    @property
    def checkpointing_enabled(self) -> bool:
        return self._checkpointing_enabled


    def _try_direct_current_explorer(
        self,
        payload: ChatTurnInput,
    ) -> ChatTurnOutput | None:
        request = _normalise_direct_request(
            payload.user_message
        )
        if request not in _DIRECT_CURRENT_EXPLORER_REQUESTS:
            return None

        explorer_id = payload.context.active_explorer_id
        if not explorer_id:
            return ChatTurnOutput(
                assistant_message=(
                    "There is no current Explorer in this conversation yet."
                ),
                route=ChatRoute.GET_EXPLORER,
                context=payload.context,
                tool_result=None,
            )

        tool_result = self._registry.execute(
            "get_explorer",
            {"explorer_id": explorer_id},
        )

        next_context = update_context_from_tool_result(
            payload.context,
            tool_result,
        )

        if (
            tool_result.display is not None
            and tool_result.display.markdown.strip()
        ):
            assistant_message = (
                tool_result.display.markdown
            )
        elif tool_result.ok:
            assistant_message = (
                "Here is the current Explorer."
            )
        else:
            assistant_message = (
                tool_result.message
            )

        return ChatTurnOutput(
            assistant_message=assistant_message,
            route=ChatRoute.GET_EXPLORER,
            context=next_context,
            tool_result=tool_result,
        )

    def handle_turn(
        self,
        payload: ChatTurnInput,
    ) -> ChatTurnOutput:
        direct_output = self._try_direct_current_explorer(
            payload
        )
        if direct_output is not None:
            return direct_output

        config: dict[str, Any] | None = None

        if self._checkpointing_enabled:
            if payload.thread_id is None:
                raise ValueError(
                    "thread_id is required when "
                    "LangGraph checkpointing is "
                    "enabled."
                )

            config = {
                "configurable": {
                    "thread_id": str(
                        payload.thread_id
                    ),
                }
            }

        state_input = payload.model_dump(
            mode="json",
            exclude={"recent_messages"},
        )
        runtime_context = {
            "recent_messages": [
                message.model_dump(
                    mode="json"
                )
                for message
                in payload.recent_messages
            ]
        }

        graph_result = self._graph.invoke(
            {
                "turn_input": state_input
            },
            config=config,
            context=runtime_context,
        )

        if not isinstance(
            graph_result,
            dict,
        ):
            raise RuntimeError(
                "LangGraph returned a "
                "non-dictionary turn result."
            )

        raw_output = graph_result.get(
            "turn_output"
        )

        if not isinstance(
            raw_output,
            dict,
        ):
            raise RuntimeError(
                "LangGraph did not return a "
                "'turn_output' dictionary."
            )

        return ChatTurnOutput.model_validate(
            raw_output
        )
