"""Thin, synchronous transport-neutral facade over ConversationApplicationService.

No routing, LangGraph, persistence, or tool-execution rules live here.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID


class AgentGateway:
    def __init__(self, conversation_service: Any) -> None:
        self._service = conversation_service

    def create_conversation(self, title: str | None = None) -> dict[str, Any]:
        record = self._service.create_conversation(title)
        return record.model_dump(mode="json")

    def get_history(self, conversation_id: str) -> dict[str, Any]:
        cid = UUID(conversation_id)
        self._service.get_conversation(cid)  # Current not-found semantics.
        turns = self._service.get_conversation_turns(cid)
        return {
            "conversation_id": str(cid),
            "turns": [turn.model_dump(mode="json") for turn in turns],
        }

    def chat(
        self,
        conversation_id: str,
        message: str,
        client_turn_id: str | None = None,
    ) -> dict[str, Any]:
        if not message.strip():
            raise ValueError("Message cannot be blank")
        result = self._service.execute_conversation_turn(
            conversation_id=UUID(conversation_id),
            user_content=message,
            client_turn_id=UUID(client_turn_id) if client_turn_id else None,
        )
        return result.model_dump(mode="json")
