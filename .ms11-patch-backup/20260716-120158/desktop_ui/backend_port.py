from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from .models import (
    ConversationSnapshot,
    ConversationSummary,
    ExplorerEditPatch,
    ExplorerViewModel,
    TurnProgress,
    TurnResponse,
)


ProgressCallback = Callable[[TurnProgress], None]


class ConversationBackendPort(ABC):
    """
    Stable UI boundary for the MS10 conversational backend.

    The production implementation adapts ``ConversationApplicationService``
    from the ``ms10-langgraph-orchestrator`` branch. Widgets never receive or
    reconstruct the conversation model's function call, semantic command,
    deterministic workflow plan, graph state, or ToolRegistry sequence.
    """

    @abstractmethod
    def list_conversations(self) -> list[ConversationSummary]:
        raise NotImplementedError

    @abstractmethod
    def create_conversation(
        self,
        title: str = "New conversation",
    ) -> ConversationSnapshot:
        raise NotImplementedError

    @abstractmethod
    def load_conversation(
        self,
        conversation_id: str,
    ) -> ConversationSnapshot:
        raise NotImplementedError

    @abstractmethod
    def rename_conversation(
        self,
        conversation_id: str,
        title: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_conversation(
        self,
        conversation_id: str,
    ) -> ConversationSnapshot:
        raise NotImplementedError

    @abstractmethod
    def delete_conversation(
        self,
        conversation_id: str,
    ) -> None:
        raise NotImplementedError


    @abstractmethod
    def save_explorer_edits(
        self,
        explorer_id: str,
        expected_version: int,
        patch: ExplorerEditPatch,
    ) -> ExplorerViewModel:
        """Persist manual Explorer edits without invoking orchestration or AI."""
        raise NotImplementedError

    @abstractmethod
    def export_conversation_markdown(
        self,
        conversation_id: str,
        destination_path: str,
    ) -> str:
        """Export a deterministic Markdown summary and transcript from storage."""
        raise NotImplementedError

    @abstractmethod
    def execute_turn(
        self,
        conversation_id: str,
        user_text: str,
        on_progress: ProgressCallback,
    ) -> TurnResponse:
        """
        Execute one durable synchronous MS10 turn outside the Qt UI thread.

        MS10 does not currently publish workflow-step progress. The callback is
        intentionally coarse and must not simulate token streaming or expose
        internal tool/workflow selection.
        """
        raise NotImplementedError
