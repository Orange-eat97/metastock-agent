from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from chat.models import ChatContext, ChatTurnInput, ChatTurnOutput
from chat.result_mapper import update_context_from_tool_result
from chat.router import DeterministicChatRouter
from chat.routes import ChatRoute
from tools.tool_contracts import ToolError, ToolResult, ToolStatus


class ToolRegistryProtocol(Protocol):
    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        ...


class ChatTurnController:
    """
    Backend chat harness controller.

    Create, select, and run are separate tool calls. The controller may compose
    them for a high-level user command, but the underlying Automator services
    remain separate.
    """

    def __init__(
        self,
        registry: ToolRegistryProtocol,
        router: DeterministicChatRouter | None = None,
    ) -> None:
        self._registry = registry
        self._router = router or DeterministicChatRouter()

    def handle_turn(self, payload: ChatTurnInput) -> ChatTurnOutput:
        route = self._router.route(payload.user_message)

        if route is ChatRoute.GENERATE_EXPLORER:
            return self._execute(
                route=route,
                arguments={"user_query": payload.user_message},
                context=payload.context,
            )

        if route is ChatRoute.REPAIR_EXPLORER:
            explorer_id = payload.context.active_explorer_id
            if not explorer_id:
                return self._missing_context(
                    route=route,
                    context=payload.context,
                    message=(
                        "There is no active Explorer to repair. Generate or open "
                        "an Explorer first."
                    ),
                )

            return self._execute(
                route=route,
                arguments={
                    "explorer_id": explorer_id,
                    "repair_instruction": payload.user_message,
                },
                context=payload.context,
            )

        if route is ChatRoute.GET_EXPLORER:
            explorer_id = payload.context.active_explorer_id
            if not explorer_id:
                return self._missing_context(
                    route=route,
                    context=payload.context,
                    message=(
                        "There is no active Explorer. Generate an Explorer first "
                        "or supply one through the harness context."
                    ),
                )

            return self._execute(
                route=route,
                arguments={"explorer_id": explorer_id},
                context=payload.context,
            )

        if route is ChatRoute.GET_RAG_LOG:
            log_id = payload.context.active_service_log_id
            if not log_id:
                return self._missing_context(
                    route=route,
                    context=payload.context,
                    message=(
                        "The current session has no active RAG service log. "
                        "Generate or open an Explorer with a service_log_id first."
                    ),
                )

            return self._execute(
                route=route,
                arguments={"log_id": log_id},
                context=payload.context,
            )

        if route in {
            ChatRoute.CREATE_METASTOCK_EXPLORER,
            ChatRoute.SELECT_METASTOCK_EXPLORER,
            ChatRoute.RUN_SELECTED_METASTOCK_EXPLORER,
        }:
            explorer_id = payload.context.active_explorer_id
            if not explorer_id:
                return self._missing_context(
                    route=route,
                    context=payload.context,
                    message="There is no active Explorer for this MetaStock action.",
                )

            return self._execute(
                route=route,
                arguments={
                    "explorer_id": explorer_id,
                    "instruments": "all",
                },
                context=payload.context,
            )

        if route is ChatRoute.RUN_AND_READ_EXPLORER:
            explorer_id = payload.context.active_explorer_id
            if not explorer_id:
                return self._missing_context(
                    route=route,
                    context=payload.context,
                    message="There is no active Explorer to select, run, and read.",
                )

            select_output = self._execute(
                route=ChatRoute.SELECT_METASTOCK_EXPLORER,
                arguments={
                    "explorer_id": explorer_id,
                    "instruments": "all",
                },
                context=payload.context,
            )

            if (
                select_output.tool_result is None
                or not select_output.tool_result.ok
            ):
                return ChatTurnOutput(
                    assistant_message=select_output.assistant_message,
                    route=route,
                    context=select_output.context,
                    tool_result=select_output.tool_result,
                )

            run_output = self._execute(
                route=ChatRoute.RUN_SELECTED_METASTOCK_EXPLORER,
                arguments={
                    "explorer_id": explorer_id,
                    "instruments": "all",
                },
                context=select_output.context,
            )

            if (
                run_output.tool_result is None
                or not run_output.tool_result.ok
            ):
                return ChatTurnOutput(
                    assistant_message=run_output.assistant_message,
                    route=route,
                    context=run_output.context,
                    tool_result=run_output.tool_result,
                )

            read_output = self._execute(
                route=ChatRoute.READ_METASTOCK_RESULTS,
                arguments={
                    "explorer_id": explorer_id,
                    "close_after_read": True,
                },
                context=run_output.context,
            )

            return ChatTurnOutput(
                assistant_message=read_output.assistant_message,
                route=route,
                context=read_output.context,
                tool_result=read_output.tool_result,
            )

        if route is ChatRoute.RUN_EXPLORER:
            explorer_id = payload.context.active_explorer_id
            if not explorer_id:
                return self._missing_context(
                    route=route,
                    context=payload.context,
                    message="There is no active Explorer to run.",
                )

            # Intentional composition at the controller layer:
            # 1. select existing Explorer/instruments;
            # 2. run the currently selected Explorer.
            # These remain two separate ToolRegistry calls.
            select_output = self._execute(
                route=ChatRoute.SELECT_METASTOCK_EXPLORER,
                arguments={
                    "explorer_id": explorer_id,
                    "instruments": "all",
                },
                context=payload.context,
            )

            if (
                select_output.tool_result is None
                or not select_output.tool_result.ok
            ):
                return ChatTurnOutput(
                    assistant_message=select_output.assistant_message,
                    route=route,
                    context=select_output.context,
                    tool_result=select_output.tool_result,
                )

            run_output = self._execute(
                route=ChatRoute.RUN_SELECTED_METASTOCK_EXPLORER,
                arguments={
                    "explorer_id": explorer_id,
                    "instruments": "all",
                },
                context=select_output.context,
            )

            return ChatTurnOutput(
                assistant_message=run_output.assistant_message,
                route=route,
                context=run_output.context,
                tool_result=run_output.tool_result,
            )

        if route is ChatRoute.READ_METASTOCK_RESULTS:
            explorer_id = payload.context.active_explorer_id
            if not explorer_id:
                return self._missing_context(
                    route=route,
                    context=payload.context,
                    message="There is no active Explorer to attach the results to.",
                )

            return self._execute(
                route=route,
                arguments={
                    "explorer_id": explorer_id,
                    "close_after_read": True,
                },
                context=payload.context,
            )

        return ChatTurnOutput(
            assistant_message=(
                "This harness can generate, repair, retrieve, create in "
                "MetaStock, select in MetaStock, run the selected Explorer, "
                "read results, or inspect the RAG log."
            ),
            route=ChatRoute.FALLBACK,
            context=payload.context,
        )

    def _execute(
        self,
        *,
        route: ChatRoute,
        arguments: dict[str, Any],
        context: ChatContext,
    ) -> ChatTurnOutput:
        try:
            result = self._registry.execute(route.value, arguments)
        except ValidationError as exc:
            result = ToolResult(
                tool_name=route.value,
                ok=False,
                status=ToolStatus.FAILED,
                message="Tool arguments failed validation.",
                error=ToolError(
                    code="TOOL_ARGUMENT_VALIDATION_FAILED",
                    message="Tool arguments failed validation.",
                    details={"errors": exc.errors(include_url=False)},
                ),
            )
        except ValueError as exc:
            result = ToolResult(
                tool_name=route.value,
                ok=False,
                status=ToolStatus.FAILED,
                message=str(exc),
                error=ToolError(
                    code="UNKNOWN_TOOL",
                    message=str(exc),
                ),
            )
        except Exception as exc:
            result = ToolResult(
                tool_name=route.value,
                ok=False,
                status=ToolStatus.FAILED,
                message="The tool call failed unexpectedly.",
                error=ToolError(
                    code=type(exc).__name__,
                    message=str(exc),
                ),
            )

        next_context = update_context_from_tool_result(context, result)

        return ChatTurnOutput(
            assistant_message=self._assistant_message(result),
            route=route,
            context=next_context,
            tool_result=result,
        )

    @staticmethod
    def _assistant_message(result: ToolResult) -> str:
        if result.display and result.display.markdown.strip():
            return result.display.markdown

        return result.message

    @staticmethod
    def _missing_context(
        *,
        route: ChatRoute,
        context: ChatContext,
        message: str,
    ) -> ChatTurnOutput:
        return ChatTurnOutput(
            assistant_message=message,
            route=route,
            context=context,
        )
