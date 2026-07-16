from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from services.conversation_export_service import ConversationLogExportService


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Turn:
    user_content: str
    assistant_content: str
    route: str
    stream_id: UUID


@dataclass(frozen=True)
class ToolCall:
    ordinal: int
    tool_name: str
    status: str
    result_json: dict
    error_message: str | None = None


class FakeConversationService:
    def __init__(self) -> None:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        self.conversation_id = uuid4()
        self.stream_id = uuid4()
        self.record = ConversationRecord(
            conversation_id=self.conversation_id,
            title="Breakout session",
            created_at=now,
            updated_at=now,
        )
        self.turns = [
            Turn(
                user_content="Build a breakout Explorer.",
                assistant_content="The Explorer is ready.",
                route="generate_explorer",
                stream_id=self.stream_id,
            )
        ]
        self.calls = {
            self.stream_id: [
                ToolCall(
                    ordinal=0,
                    tool_name="generate_explorer",
                    status="succeeded",
                    result_json={
                        "message": "Explorer generated.",
                        "data": {"explorer": {"name": "Breakout"}},
                    },
                )
            ]
        }

    def get_conversation(self, conversation_id: UUID) -> ConversationRecord:
        self.assert_id(conversation_id)
        return self.record

    def get_conversation_turns(self, conversation_id: UUID) -> list[Turn]:
        self.assert_id(conversation_id)
        return self.turns

    def get_tool_calls_for_turn(self, stream_id: UUID) -> list[ToolCall]:
        return self.calls.get(stream_id, [])

    def assert_id(self, conversation_id: UUID) -> None:
        if conversation_id != self.conversation_id:
            raise AssertionError("Unexpected conversation id")


class ConversationLogExportServiceTests(unittest.TestCase):
    def test_exports_deterministic_summary_and_transcript_without_ids(self) -> None:
        source = FakeConversationService()
        service = ConversationLogExportService(source)

        with tempfile.TemporaryDirectory() as directory:
            path = service.export_markdown(
                conversation_id=source.conversation_id,
                destination_path=Path(directory) / "session",
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(path.suffix, ".md")
        self.assertIn("# Breakout session", content)
        self.assertIn("Completed conversation turns: 1", content)
        self.assertIn("generate_explorer: 1", content)
        self.assertIn("Build a breakout Explorer.", content)
        self.assertIn("The Explorer is ready.", content)
        self.assertIn("Explorer generated.", content)
        self.assertNotIn(str(source.conversation_id), content)
        self.assertNotIn(str(source.stream_id), content)


if __name__ == "__main__":
    unittest.main()
