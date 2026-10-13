"""Opt-in Jev choice filter before existing OpenAI action argument generation.

This is a ConversationDriverProtocol decorator, not a replacement for LangGraph.
Existing action policy, context resolution and workflow execution remain in place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestration.conversation_actions import ConversationModelRequest, ConversationModelResponse


@dataclass(frozen=True)
class JevDecision:
    choice: str
    confidence: float


class TypeSafeJevSelector:
    def __init__(self, client: Any | None = None, model: str = "jev-latest") -> None:
        if client is None:
            from typesafe_sdk import TypeSafeClient
            client = TypeSafeClient()
        self.client = client
        self.model = model

    def choose(self, request: ConversationModelRequest) -> JevDecision:
        from typesafe_sdk import Choice

        choices = {action.name: action.description for action in request.actions}
        choices.update({
            "__no_action__": "Answer the user conversationally, without using a tool.",
            "__delegate__": "Ambiguous, multi-step, or needs richer model reasoning to decide.",
        })
        state = {
            "user_message": request.user_message,
            "recent_messages": [m.model_dump(mode="json") for m in request.recent_messages],
            "has_active_explorer": bool(request.context.active_explorer_id),
            "has_active_result": bool(request.context.active_result_id),
        }
        answer = self.client.system_one(
            model=self.model,
            state=state,
            questions={
                "action": Choice(
                    instructions=(
                        "Choose exactly one candidate action for this MetaStock assistant "
                        "turn, or no_action if a direct response is sufficient, "
                        "or delegate for ambiguity, sequences, or uncertainty. "
                        "Do not infer missing identifiers or instruments."
                    ),
                    criteria=choices,
                )
            },
        ).choices["action"]
        return JevDecision(choice=str(answer.choice), confidence=float(answer.confidence))


class JevChoiceConversationDriver:
    """Select allowed action schema; existing driver still writes arguments/dialogue."""

    def __init__(self, underlying: Any, selector: Any, min_confidence: float = 0.80) -> None:
        if not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        self.underlying = underlying
        self.selector = selector
        self.min_confidence = min_confidence

    def converse(self, request: ConversationModelRequest) -> ConversationModelResponse:
        if not request.actions:
            return self.underlying.converse(request)
        try:
            decision = self.selector.choose(request)
        except Exception:
            return self.underlying.converse(request)
        if decision.confidence < self.min_confidence or decision.choice == "__delegate__":
            return self.underlying.converse(request)
        if decision.choice == "__no_action__":
            return self.underlying.converse(request.model_copy(update={"actions": []}))
        selected = [action for action in request.actions if action.name == decision.choice]
        if len(selected) != 1:
            return self.underlying.converse(request)
        reply = self.underlying.converse(request.model_copy(update={"actions": selected}))
        if reply.action_call is not None and reply.action_call.name != decision.choice:
            return ConversationModelResponse(
                assistant_message="Please clarify which MetaStock action you would like to perform."
            )
        return reply
