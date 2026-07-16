from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Protocol
from uuid import UUID


class ConversationReadProtocol(Protocol):
    def get_conversation(self, conversation_id: UUID) -> Any:
        ...

    def get_conversation_turns(self, conversation_id: UUID) -> list[Any]:
        ...

    def get_tool_calls_for_turn(self, stream_id: UUID) -> list[Any]:
        ...


class ConversationLogExportService:
    """
    Export one durable Supabase-backed conversation as deterministic Markdown.

    The summary is computed from persisted conversation turns and tool-call
    records. No AI model, planner, LangGraph execution, or RAG retrieval is
    invoked.
    """

    def __init__(self, conversation_service: ConversationReadProtocol) -> None:
        self._conversations = conversation_service

    def export_markdown(
        self,
        *,
        conversation_id: UUID,
        destination_path: str | Path,
    ) -> Path:
        record = self._conversations.get_conversation(conversation_id)
        turns = self._conversations.get_conversation_turns(conversation_id)

        tool_calls_by_turn: list[list[Any]] = []
        for turn in turns:
            stream_id = getattr(turn, "stream_id", None)
            calls = (
                self._conversations.get_tool_calls_for_turn(stream_id)
                if stream_id is not None
                else []
            )
            tool_calls_by_turn.append(
                sorted(calls, key=lambda call: int(getattr(call, "ordinal", 0)))
            )

        markdown = self._build_markdown(
            record=record,
            turns=turns,
            tool_calls_by_turn=tool_calls_by_turn,
        )
        destination = Path(destination_path).expanduser().resolve()
        if destination.suffix.casefold() != ".md":
            destination = destination.with_suffix(".md")
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Atomic replacement prevents a partial export if the process exits
        # while writing a long transcript.
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=destination.parent,
            suffix=".tmp",
        ) as handle:
            handle.write(markdown)
            temporary = Path(handle.name)
        temporary.replace(destination)
        return destination

    def _build_markdown(
        self,
        *,
        record: Any,
        turns: list[Any],
        tool_calls_by_turn: list[list[Any]],
    ) -> str:
        title = str(getattr(record, "title", None) or "Untitled conversation")
        created_at = self._datetime_text(getattr(record, "created_at", None))
        updated_at = self._datetime_text(getattr(record, "updated_at", None))
        exported_at = datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"
        )

        route_counts: Counter[str] = Counter()
        tool_counts: Counter[str] = Counter()
        status_counts: Counter[str] = Counter()
        explorer_artifacts = 0
        result_artifacts = 0
        rag_log_artifacts = 0

        for turn, calls in zip(turns, tool_calls_by_turn, strict=True):
            route = self._enum_text(getattr(turn, "route", None))
            if route:
                route_counts[route] += 1
            for call in calls:
                tool_name = str(getattr(call, "tool_name", "") or "unknown")
                tool_counts[tool_name] += 1
                status = self._enum_text(getattr(call, "status", None)) or "unknown"
                status_counts[status] += 1
                result = getattr(call, "result_json", None)
                if isinstance(result, dict):
                    data = result.get("data")
                    if isinstance(data, dict):
                        if isinstance(data.get("explorer"), dict):
                            explorer_artifacts += 1
                        if any(
                            key in data
                            for key in ("result", "results", "result_summaries")
                        ):
                            result_artifacts += 1
                        if tool_name == "get_rag_log":
                            rag_log_artifacts += 1

        lines = [
            f"# {self._escape_heading(title)}",
            "",
            "## Session summary",
            "",
            f"- Created: {created_at or 'Unavailable'}",
            f"- Last updated: {updated_at or 'Unavailable'}",
            f"- Exported: {exported_at}",
            f"- Completed conversation turns: {len(turns)}",
            f"- User messages: {len(turns)}",
            f"- Assistant messages: {len(turns)}",
            f"- Persisted tool calls: {sum(len(calls) for calls in tool_calls_by_turn)}",
            f"- Explorer artifacts returned: {explorer_artifacts}",
            f"- Result artifacts returned: {result_artifacts}",
            f"- RAG log artifacts returned: {rag_log_artifacts}",
        ]

        if route_counts:
            lines.extend(["", "### Routes", ""])
            lines.extend(
                f"- {name}: {count}"
                for name, count in sorted(route_counts.items())
            )
        if tool_counts:
            lines.extend(["", "### Tool activity", ""])
            lines.extend(
                f"- {name}: {count}"
                for name, count in sorted(tool_counts.items())
            )
        if status_counts:
            lines.extend(["", "### Tool outcomes", ""])
            lines.extend(
                f"- {name}: {count}"
                for name, count in sorted(status_counts.items())
            )

        lines.extend(["", "## Transcript", ""])
        for index, (turn, calls) in enumerate(
            zip(turns, tool_calls_by_turn, strict=True),
            start=1,
        ):
            route = self._enum_text(getattr(turn, "route", None))
            lines.extend(
                [
                    f"### Turn {index}",
                    "",
                    f"**Route:** {route or 'Unspecified'}",
                    "",
                    "#### User",
                    "",
                    str(getattr(turn, "user_content", "") or ""),
                    "",
                    "#### Assistant",
                    "",
                    str(getattr(turn, "assistant_content", "") or ""),
                    "",
                ]
            )
            if calls:
                lines.extend(["#### Persisted tool log", ""])
                for call in calls:
                    tool_name = str(
                        getattr(call, "tool_name", "") or "unknown"
                    )
                    status = self._enum_text(
                        getattr(call, "status", None)
                    ) or "unknown"
                    lines.append(f"- **{tool_name}** — {status}")
                    result = getattr(call, "result_json", None)
                    message = self._tool_message(result)
                    if message:
                        lines.append(f"  - {message}")
                    error_message = str(
                        getattr(call, "error_message", "") or ""
                    ).strip()
                    if error_message:
                        lines.append(f"  - Error: {error_message}")
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _tool_message(result: Any) -> str:
        if not isinstance(result, dict):
            return ""
        message = str(result.get("message") or "").strip()
        if message:
            return message
        display = result.get("display")
        if isinstance(display, dict):
            return str(display.get("title") or "").strip()
        return ""

    @staticmethod
    def _enum_text(value: Any) -> str | None:
        if value is None:
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _datetime_text(value: Any) -> str:
        if value is None:
            return ""
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            return str(isoformat(timespec="seconds"))
        return str(value)

    @staticmethod
    def _escape_heading(value: str) -> str:
        return " ".join(value.replace("#", "").split()) or "Untitled conversation"
