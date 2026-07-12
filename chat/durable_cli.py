from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from uuid import UUID

from services.conversation_application_service import (
    ConversationApplicationService,
)


OutputFunction = Callable[[str], None]


class DurableChatCli:
    """
    Interactive CLI over ConversationApplicationService.

    The CLI contains presentation and command parsing only. It does
    not access Supabase, repositories, ToolRegistry, RAG, or the
    MetaStock Automator directly.
    """

    def __init__(
        self,
        *,
        service: ConversationApplicationService,
        active_conversation_id: UUID | None = None,
        output: OutputFunction = print,
    ) -> None:
        self._service = service
        self._active_conversation_id = (
            active_conversation_id
        )
        self._output = output

    @property
    def active_conversation_id(
        self,
    ) -> UUID | None:
        return self._active_conversation_id

    def run(self) -> None:
        self._print_banner()

        while True:
            try:
                line = input("\nYou: ")
            except (EOFError, KeyboardInterrupt):
                self._output("\nExiting.")
                return

            try:
                keep_running = self.handle_line(line)
            except Exception as exc:
                self._output(
                    "\n[ERROR] "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            if not keep_running:
                return

    def handle_line(self, line: str) -> bool:
        """
        Handle one CLI line.

        Returns False when the CLI should exit.
        """
        text = line.strip()

        if not text:
            return True

        if text.startswith("/"):
            return self._handle_command(text)

        self._execute_message(text)
        return True

    # --------------------------------------------------------
    # Commands
    # --------------------------------------------------------

    def _handle_command(self, text: str) -> bool:
        try:
            tokens = shlex.split(text)
        except ValueError as exc:
            self._output(
                f"Could not parse command: {exc}"
            )
            return True

        if not tokens:
            return True

        command = tokens[0].lower()
        arguments = tokens[1:]

        handlers = {
            "/help": self._command_help,
            "/new": self._command_new,
            "/list": self._command_list,
            "/use": self._command_use,
            "/current": self._command_current,
            "/history": self._command_history,
            "/state": self._command_state,
            "/rename": self._command_rename,
            "/clear": self._command_clear,
            "/delete": self._command_delete,
        }

        if command in {"/quit", "/exit"}:
            return False

        handler = handlers.get(command)

        if handler is None:
            self._output(
                f"Unknown command: {command}\n"
                "Type /help to see available commands."
            )
            return True

        handler(arguments)
        return True

    def _command_help(
        self,
        arguments: list[str],
    ) -> None:
        del arguments

        self._output(
            """
Commands:

  /new [title]
      Create and select a new conversation.

  /list
      List recent conversations.

  /use <conversation-id>
      Select an existing conversation.

  /current
      Show the selected conversation.

  /history
      Show completed turns in the selected conversation.

  /state
      Show recovered conversation context and partial-turn state.

  /rename <title>
      Rename the selected conversation.

  /clear confirm
      Clear turns, streams, and tool calls while keeping the
      conversation record.

  /delete confirm
      Permanently delete the selected conversation.

  /quit
      Exit the harness.
""".strip()
        )

    def _command_new(
        self,
        arguments: list[str],
    ) -> None:
        title = (
            " ".join(arguments).strip()
            if arguments
            else None
        )

        conversation = (
            self._service.create_conversation(
                title or None
            )
        )

        self._active_conversation_id = (
            conversation.conversation_id
        )

        self._output(
            "Created conversation:\n"
            f"  ID: {conversation.conversation_id}\n"
            f"  Title: {conversation.title or '(untitled)'}"
        )

    def _command_list(
        self,
        arguments: list[str],
    ) -> None:
        del arguments

        conversations = (
            self._service.list_conversations(
                limit=50
            )
        )

        if not conversations:
            self._output(
                "No conversations found."
            )
            return

        self._output("Recent conversations:")

        for conversation in conversations:
            marker = (
                " *"
                if (
                    conversation.conversation_id
                    == self._active_conversation_id
                )
                else ""
            )

            title = (
                conversation.title
                or "(untitled)"
            )

            self._output(
                "\n"
                f"{conversation.conversation_id}{marker}\n"
                f"  {title}\n"
                "  Updated: "
                f"{conversation.updated_at.isoformat()}"
            )

        self._output(
            "\n* currently selected"
        )

    def _command_use(
        self,
        arguments: list[str],
    ) -> None:
        if len(arguments) != 1:
            self._output(
                "Usage: /use <conversation-id>"
            )
            return

        conversation_id = self._parse_uuid(
            arguments[0]
        )

        conversation = (
            self._service.get_conversation(
                conversation_id
            )
        )

        self._active_conversation_id = (
            conversation.conversation_id
        )

        self._output(
            "Selected conversation:\n"
            f"  ID: {conversation.conversation_id}\n"
            f"  Title: {conversation.title or '(untitled)'}"
        )

    def _command_current(
        self,
        arguments: list[str],
    ) -> None:
        del arguments

        conversation_id = (
            self._require_active_conversation()
        )

        conversation = (
            self._service.get_conversation(
                conversation_id
            )
        )

        self._output(
            "Current conversation:\n"
            f"  ID: {conversation.conversation_id}\n"
            f"  Title: {conversation.title or '(untitled)'}\n"
            f"  Created: {conversation.created_at.isoformat()}\n"
            f"  Updated: {conversation.updated_at.isoformat()}"
        )

    def _command_history(
        self,
        arguments: list[str],
    ) -> None:
        del arguments

        conversation_id = (
            self._require_active_conversation()
        )

        turns = (
            self._service.get_conversation_turns(
                conversation_id
            )
        )

        if not turns:
            self._output(
                "This conversation has no completed turns."
            )
            return

        for index, turn in enumerate(
            turns,
            start=1,
        ):
            route = (
                turn.route.value
                if turn.route is not None
                else "unknown"
            )

            self._output(
                "\n"
                f"Turn {index} [{route}]\n"
                f"You:\n{turn.user_content}\n\n"
                f"Assistant:\n{turn.assistant_content}"
            )

            if turn.tool_call_ids:
                self._output(
                    "Tool calls: "
                    + ", ".join(
                        str(identifier)
                        for identifier
                        in turn.tool_call_ids
                    )
                )

    def _command_state(
        self,
        arguments: list[str],
    ) -> None:
        del arguments

        conversation_id = (
            self._require_active_conversation()
        )

        turns = (
            self._service.get_conversation_turns(
                conversation_id
            )
        )

        partial = (
            self._service
            .get_active_partial_turn(
                conversation_id
            )
        )

        context = (
            turns[-1].context
            if turns
            else None
        )

        payload = {
            "conversation_id": str(
                conversation_id
            ),
            "completed_turn_count": len(turns),
            "context": (
                context.model_dump(mode="json")
                if context is not None
                else {}
            ),
            "active_partial_turn": (
                {
                    "stream_id": str(
                        partial.stream_id
                    ),
                    "client_turn_id": str(
                        partial.client_turn_id
                    ),
                    "status": (
                        partial.status.value
                    ),
                    "last_sequence": (
                        partial.last_sequence
                    ),
                    "assistant_content": (
                        partial.assistant_content
                    ),
                }
                if partial is not None
                else None
            ),
        }

        self._output(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            )
        )

    def _command_rename(
        self,
        arguments: list[str],
    ) -> None:
        if not arguments:
            self._output(
                "Usage: /rename <title>"
            )
            return

        conversation_id = (
            self._require_active_conversation()
        )

        title = " ".join(arguments).strip()

        conversation = (
            self._service.rename_conversation(
                conversation_id,
                title,
            )
        )

        self._output(
            "Conversation renamed to:\n"
            f"  {conversation.title}"
        )

    def _command_clear(
        self,
        arguments: list[str],
    ) -> None:
        if arguments != ["confirm"]:
            self._output(
                "This removes all turns, streams, and tool calls "
                "from the current conversation.\n"
                "Run `/clear confirm` to continue."
            )
            return

        conversation_id = (
            self._require_active_conversation()
        )

        self._service.clear_conversation(
            conversation_id
        )

        self._output(
            "Conversation content cleared. "
            "The conversation record was retained."
        )

    def _command_delete(
        self,
        arguments: list[str],
    ) -> None:
        if arguments != ["confirm"]:
            self._output(
                "This permanently deletes the current "
                "conversation.\n"
                "Run `/delete confirm` to continue."
            )
            return

        conversation_id = (
            self._require_active_conversation()
        )

        deleted = (
            self._service.delete_conversation(
                conversation_id
            )
        )

        if deleted:
            self._output(
                f"Deleted conversation {conversation_id}."
            )
            self._active_conversation_id = None
        else:
            self._output(
                "The conversation no longer exists."
            )
            self._active_conversation_id = None

    # --------------------------------------------------------
    # User messages
    # --------------------------------------------------------

    def _execute_message(
        self,
        message: str,
    ) -> None:
        if self._active_conversation_id is None:
            self._output(
                "No conversation is selected.\n"
                "Use `/new [title]`, `/list`, or "
                "`/use <conversation-id>` first."
            )
            return

        result = (
            self._service
            .execute_conversation_turn(
                conversation_id=(
                    self._active_conversation_id
                ),
                user_content=message,
            )
        )

        replay_marker = (
            " [replayed]"
            if result.replayed
            else ""
        )

        self._output(
            "\n"
            f"Route: {result.route.value}"
            f"{replay_marker}\n"
            "Assistant:\n"
            f"{result.assistant_message}"
        )

        if result.tool_result is not None:
            self._output(
                "\nTool status: "
                f"{result.tool_result.status.value}; "
                f"ok={result.tool_result.ok}"
            )

        self._output(
            "\nTurn identifiers:\n"
            f"  Stream: {result.stream_id}\n"
            f"  Client turn: {result.client_turn_id}"
        )

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    def _require_active_conversation(
        self,
    ) -> UUID:
        if self._active_conversation_id is None:
            raise RuntimeError(
                "No conversation is selected."
            )

        return self._active_conversation_id

    @staticmethod
    def _parse_uuid(value: str) -> UUID:
        try:
            return UUID(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid conversation ID: {value}"
            ) from exc

    def _print_banner(self) -> None:
        self._output(
            "MetaStock durable conversation harness"
        )

        if self._active_conversation_id is None:
            self._output(
                "No conversation selected.\n"
                "Use /new, /list, or /use."
            )
        else:
            self._output(
                "Selected conversation: "
                f"{self._active_conversation_id}"
            )

        self._output(
            "Type /help for commands."
        )