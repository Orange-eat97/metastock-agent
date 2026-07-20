from __future__ import annotations

import json
import os
from typing import Any, Protocol

from chat.routes import ChatRoute
from chat.router import DeterministicChatRouter
from orchestration.conversation_actions import (
    COMMAND_ACTION_NAME,
    ConversationActionCall,
    ConversationModelRequest,
    ConversationModelResponse,
)


CONVERSATION_SYSTEM_PROMPT = """
You are a conversational MetaStock assistant.

Talk to the user normally. Use the recent conversation and active durable
context to understand follow-ups, corrections, confirmations, and pronouns.

Calling a function is optional:
- Answer directly when no fresh artifact read, artifact mutation, or MetaStock
  side effect is required.
- Call exactly one supplied function only when an action is needed.
- Never call a function merely because one was mentioned in an earlier reply.
- Never invent UUIDs or instrument names.
- Questions such as "why did you use 14 periods?" normally receive a direct
  answer with no function call.

For Explorer lifecycle actions, use execute_explorer_command. Do not try to
choose among overlapping workflow names. Resolve these dimensions separately:
1. artifact_action: generate, revise, repair, or none;
2. metastock_action: create, run, create_and_run, or none;
3. result_action: capture_new or none;
4. exact MetaStock instrument, exchange, or custom-list labels, or all. Preserve every user-supplied label verbatim in one comma-separated instruments value; never broaden, abbreviate, or invent a label.

Interpretation rules:
- A user asking to create, build, make, or produce an Explorer normally wants
  it generated and created in MetaStock. Use artifact_action=generate and
  metastock_action=create unless they explicitly ask for a draft, preview, or
  review-only result without MetaStock creation.
- A request to change an existing strategy uses artifact_action=revise.
- A request to fix syntax or validation uses artifact_action=repair.
- For generate, revise, and repair, resolved_instruction must be a standalone,
  explicit instruction. Resolve pronouns using recent messages. Example:
  convert "change it to 7 days" after discussing RSI(14) into "Change the RSI
  period from 14 to 7". Do not leave an ambiguous "it" in the instruction.
- Preserve every unmentioned condition in a revision instruction.
- "Run it and give/show/return/provide me the results" means
  metastock_action=run and result_action=capture_new.
- "Capture", "record", "save", "collect", "store", or "persist" fresh run
  results also means result_action=capture_new.
- "Show the latest stored results" without requesting a fresh run uses the
  separate get_latest_explorer_result function, not capture_new.
- A compound request such as "create this in MetaStock, run it, and give me the
  results" must retain all three intentions: create_and_run + capture_new.
- Running or creating in MetaStock requires an affirmative current-message
  request. Negated requests must not trigger a side effect.
- Handle only one user turn and at most one function call.
- When describing the active Explorer, include only its user-facing name,
  filter, and useful stored-result summary. Do not mention Explorer IDs,
  MetaStock lifecycle state, or column definitions unless the user
  explicitly asks for them.
  - Asking to show, describe, or identify the current or active Explorer requires
  the get_explorer function. Durable context contains only an internal
  Explorer reference and does not contain the Explorer name or filter formula.

The context contains at most five completed messages. No RAG cards are present.
RAG is invoked later only if LangGraph executes a RAG-backed step.
""".strip()


class ConversationDriverProtocol(Protocol):
    def converse(
        self,
        request: ConversationModelRequest,
    ) -> ConversationModelResponse:
        ...


class ConversationDriverError(RuntimeError):
    pass


def _public_durable_context(
        request: ConversationModelRequest,
    ) -> dict[str, Any]:
        """
        Expose only conversation context useful to the model.

        Keep the durable Explorer ID and MetaStock lifecycle state
        internal to orchestration.
        """
        context = request.context

        return {
            "has_active_explorer": (
                context.active_explorer_id is not None
            ),
            "active_result_id": (
                context.active_result_id
            ),
            "active_service_log_id": (
                context.active_service_log_id
            ),
        }


class OpenAIConversationDriver:
    """Normal assistant response with optional Responses API function calling."""

    def __init__(
        self,
        *,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = (
            model
            or os.getenv("METASTOCK_CONVERSATION_MODEL")
            or os.getenv("METASTOCK_ORCHESTRATOR_MODEL")
            or "gpt-5-mini"
        )

        if client is None:
            from openai import OpenAI

            client = OpenAI()

        self._client = client

    @property
    def model(self) -> str:
        return self._model

    def converse(
        self,
        request: ConversationModelRequest,
    ) -> ConversationModelResponse:
        instructions = (
            CONVERSATION_SYSTEM_PROMPT
            + "\n\nActive durable context:\n"
            + json.dumps(
                _public_durable_context(request),
                ensure_ascii=False,
            )
        )
        input_messages = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in request.recent_messages
        ]
        input_messages.append(
            {
                "role": "user",
                "content": request.user_message,
            }
        )

        try:
            response = self._client.responses.create(
                model=self._model,
                instructions=instructions,
                input=input_messages,
                tools=[
                    action.to_openai_tool()
                    for action in request.actions
                ],
                tool_choice="auto",
                parallel_tool_calls=False,
                store=False,
            )
        except Exception as exc:
            raise ConversationDriverError(
                "OpenAI conversation request failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        assistant_message = str(
            getattr(response, "output_text", "")
            or ""
        ).strip()
        calls = _read_function_calls(
            getattr(response, "output", [])
        )

        if len(calls) > 1:
            return ConversationModelResponse(
                assistant_message=(
                    "I identified more than one action. Please tell me "
                    "which action to do first."
                )
            )

        if not calls:
            if not assistant_message:
                raise ConversationDriverError(
                    "The conversation model returned neither text nor a "
                    "function call."
                )

            return ConversationModelResponse(
                assistant_message=assistant_message
            )

        call = calls[0]

        try:
            arguments = json.loads(
                call["arguments"] or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            return ConversationModelResponse(
                assistant_message=(
                    "I understood that an action may be needed, but its "
                    "arguments were not valid. Please restate the request."
                )
            )

        if not isinstance(arguments, dict):
            return ConversationModelResponse(
                assistant_message=(
                    "I could not safely interpret the action arguments. "
                    "Please restate the request."
                )
            )

        return ConversationModelResponse(
            assistant_message=assistant_message,
            action_call=ConversationActionCall(
                name=call["name"],
                arguments=arguments,
                call_id=call.get("call_id"),
            ),
        )


class DeterministicConversationDriver:
    """Temporary explicit fallback for model/API failures."""

    def __init__(
        self,
        router: DeterministicChatRouter | None = None,
    ) -> None:
        self._router = router or DeterministicChatRouter()

    def converse(
        self,
        request: ConversationModelRequest,
    ) -> ConversationModelResponse:
        route = self._router.route(
            request.user_message
        )

        if route is ChatRoute.FALLBACK:
            return ConversationModelResponse(
                assistant_message=(
                    "I can help generate, inspect, repair, revise, run, or "
                    "retrieve MetaStock Explorer results."
                )
            )

        direct_routes = {
            ChatRoute.GET_EXPLORER,
            ChatRoute.GET_RAG_LOG,
            ChatRoute.GET_EXPLORER_RESULT,
            ChatRoute.GET_LATEST_EXPLORER_RESULT,
            ChatRoute.LIST_EXPLORER_RESULTS,
        }

        if route in direct_routes:
            return ConversationModelResponse(
                action_call=ConversationActionCall(
                    name=route.value,
                    arguments={},
                )
            )

        command_arguments = {
            "artifact_action": "none",
            "metastock_action": "none",
            "result_action": "none",
            "instruments": "all",
        }

        if route is ChatRoute.GENERATE_EXPLORER:
            command_arguments.update(
                {
                    "artifact_action": "generate",
                    "resolved_instruction": request.user_message,
                    "metastock_action": "create",
                }
            )
        elif route is ChatRoute.REVISE_EXPLORER:
            command_arguments.update(
                {
                    "artifact_action": "revise",
                    "resolved_instruction": request.user_message,
                }
            )
        elif route is ChatRoute.REPAIR_EXPLORER:
            command_arguments.update(
                {
                    "artifact_action": "repair",
                    "resolved_instruction": request.user_message,
                }
            )
        elif route is ChatRoute.RUN_EXPLORER:
            command_arguments["metastock_action"] = "run"
        elif route is ChatRoute.RUN_AND_READ_EXPLORER:
            command_arguments.update(
                {
                    "metastock_action": "run",
                    "result_action": "capture_new",
                }
            )
        elif route is ChatRoute.CREATE_RUN_AND_READ_EXPLORER:
            command_arguments.update(
                {
                    "metastock_action": "create_and_run",
                    "result_action": "capture_new",
                }
            )
        else:
            return ConversationModelResponse(
                assistant_message=(
                    "Please restate the Explorer action you want me to take."
                )
            )

        return ConversationModelResponse(
            action_call=ConversationActionCall(
                name=COMMAND_ACTION_NAME,
                arguments=command_arguments,
            )
        )


class ConversationDriverWithFallback:
    def __init__(
        self,
        *,
        primary: ConversationDriverProtocol,
        fallback: ConversationDriverProtocol,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def converse(
        self,
        request: ConversationModelRequest,
    ) -> ConversationModelResponse:
        try:
            return self._primary.converse(request)
        except Exception as exc:
            print(
                "[orchestration] Primary conversation model failed; using "
                "deterministic fallback: "
                f"{type(exc).__name__}: {exc}"
            )
            return self._fallback.converse(request)


def _read_function_calls(
    output: Any,
) -> list[dict[str, str | None]]:
    calls: list[dict[str, str | None]] = []

    for item in output or []:
        if isinstance(item, dict):
            item_type = item.get("type")
            name = item.get("name")
            arguments = item.get("arguments")
            call_id = item.get("call_id")
        else:
            item_type = getattr(item, "type", None)
            name = getattr(item, "name", None)
            arguments = getattr(item, "arguments", None)
            call_id = getattr(item, "call_id", None)

        if item_type != "function_call":
            continue

        cleaned_name = str(name or "").strip()

        if not cleaned_name:
            continue

        calls.append(
            {
                "name": cleaned_name,
                "arguments": str(arguments or "{}"),
                "call_id": (
                    str(call_id)
                    if call_id
                    else None
                ),
            }
        )

    return calls
