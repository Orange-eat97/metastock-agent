from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID, uuid4

from desktop_ui.adapters.conversation_service_adapter import Ms10ConversationAdapter
from desktop_ui.models import ExplorerColumn, ExplorerEditPatch


@dataclass
class Record:
    conversation_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


@dataclass
class Context:
    active_explorer_id: str | None = None
    active_explorer_metastock_state: str = "unknown"
    active_result_id: str | None = None
    active_service_log_id: str | None = None


@dataclass
class Turn:
    user_content: str
    assistant_content: str
    route: str
    context: Context
    stream_id: UUID
    tool_call_ids: list[UUID]


@dataclass
class Call:
    result_json: dict | None
    ordinal: int = 0


@dataclass
class ExecuteResult:
    conversation_id: UUID
    stream_id: UUID
    client_turn_id: UUID
    assistant_message: str
    route: str
    context: Context
    tool_result: dict | None
    replayed: bool = False


class FakeService:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.conversation_id = uuid4()
        self.record = Record(self.conversation_id, "Frozen backend", now, now)
        self.explorer_id = str(uuid4())
        self.log_id = str(uuid4())
        self.result_id = str(uuid4())
        self.stream_id = uuid4()
        self.context = Context(
            active_explorer_id=self.explorer_id,
            active_explorer_metastock_state="created",
            active_result_id=self.result_id,
            active_service_log_id=self.log_id,
        )
        self.turns = [
            Turn(
                "Build and run an MA crossover Explorer.",
                "I generated the Explorer and captured one result.",
                "generate_create_run_and_read_explorer_sequence",
                self.context,
                self.stream_id,
                [],
            )
        ]
        self.execute_tool_result: dict | None = None
        self.calls = {
            self.stream_id: [
                Call(
                    {
                        "tool_name": "generate_explorer",
                        "ok": True,
                        "status": "success",
                        "message": "Explorer generated.",
                        "data": {
                            "explorer": {
                                "explorer_id": self.explorer_id,
                                "explorer_created_at": "2026-07-15T10:00:00Z",
                                "name": "MA crossover",
                                "description": "Fast MA crosses slow MA.",
                                "filter_code": "Cross(ColA,ColB)",
                                "columns": [
                                    {"col_letter": "A", "col_code": "Mov(C,10,S)"},
                                    {"col_letter": "B", "col_code": "Mov(C,50,S)"},
                                ],
                                "validation": {"passed": True, "errors": [], "warnings": []},
                                "can_run_in_metastock": True,
                                "can_repair": True,
                                "source": "rag",
                                "service_log_id": self.log_id,
                            },
                            "assumptions": ["Simple averages"],
                            "retrieved_refs": [
                                {
                                    "key": "function.mov",
                                    "table_title": "Mov",
                                    "rag_score": 0.95,
                                    "retrieval_reason": "Moving average syntax",
                                }
                            ],
                        },
                        "display": {"title": "Generated Explorer", "markdown": "ok", "severity": "success"},
                    }
                ),
                Call(
                    {
                        "tool_name": "read_metastock_explorer_results",
                        "ok": True,
                        "status": "success",
                        "message": "Stored result.",
                        "data": {
                            "explorer_id": self.explorer_id,
                            "result_id": self.result_id,
                            "stored_at": "2026-07-15T10:01:00Z",
                            "persisted": True,
                            "succeeded": True,
                            "results": {
                                "schema_version": "1.0",
                                "outcome": "matches_found",
                                "expected_count": 1,
                                "matched_count": 1,
                                "has_matches": True,
                                "clipboard_verification": {
                                    "passed": True,
                                    "expected_count": 1,
                                    "scraped_count": 1,
                                    "clipboard_count": 1,
                                },
                                "rows": [
                                    {
                                        "row_index": 1,
                                        "instrument_name": "Apple Inc.",
                                        "symbol": "AAPL",
                                        "column_values": {"A": "189", "B": "184"},
                                    }
                                ],
                            },
                            "started_at": "2026-07-15T10:00:30Z",
                            "finished_at": "2026-07-15T10:01:00Z",
                            "diagnostics": {"capture_mode": "UIA"},
                        },
                        "display": {"title": "Explorer Results", "markdown": "1 result", "severity": "success"},
                    }
                ),
            ]
        }

    def list_conversations(self):
        return [self.record]

    def create_conversation(self, title=None):
        self.record.title = title or "Untitled"
        return self.record

    def get_conversation(self, conversation_id):
        assert conversation_id == self.conversation_id
        return self.record

    def rename_conversation(self, conversation_id, title):
        assert conversation_id == self.conversation_id
        self.record.title = title
        return self.record

    def clear_conversation(self, conversation_id):
        assert conversation_id == self.conversation_id
        self.turns = []
        return self.record

    def delete_conversation(self, conversation_id):
        return conversation_id == self.conversation_id

    def get_conversation_turns(self, conversation_id):
        assert conversation_id == self.conversation_id
        return self.turns

    def get_tool_calls_for_turn(self, stream_id):
        return self.calls.get(stream_id, [])

    def execute_conversation_turn(self, *, conversation_id, user_content, client_turn_id):
        assert conversation_id == self.conversation_id
        assert user_content
        assert isinstance(client_turn_id, UUID)
        return ExecuteResult(
            conversation_id=conversation_id,
            stream_id=self.stream_id,
            client_turn_id=client_turn_id,
            assistant_message="I generated the Explorer and captured one result.",
            route="generate_create_run_and_read_explorer_sequence",
            context=self.context,
            tool_result=self.execute_tool_result,
        )


class FakeExplorerEditService:
    def __init__(self, explorer_id: str) -> None:
        self.explorer_id = explorer_id
        self.saved: dict | None = None

    def get_explorer(self, explorer_id: str) -> dict:
        if explorer_id != self.explorer_id:
            raise AssertionError("Unexpected Explorer id")
        return {
            "id": explorer_id,
            "created_at": "2026-07-15T10:00:00Z",
            "updated_at": "2026-07-15T12:00:00Z",
            "manual_edit_version": 2,
            "backend": "openai",
            "explorer_name": "MA crossover edited",
            "explorer_description": "Manually edited.",
            "explorer_code_body": "Cross(Mov(C,10,S),Mov(C,50,S))",
            "col_definitions": [
                {"col_letter": "A", "col_code": "Mov(C,10,S)"},
                {"col_letter": "B", "col_code": "Mov(C,50,S)"},
            ],
            "assumptions": ["Simple averages"],
            "validation_passed": True,
            "validation_errors": [],
            "retrieved_refs": [],
        }

    def get_explorers(self, explorer_ids: list[str]) -> list[dict]:
        return [self.get_explorer(explorer_id) for explorer_id in explorer_ids]

    def save_edits(self, **kwargs) -> dict:
        self.saved = kwargs
        row = self.get_explorer(kwargs["explorer_id"])
        row["explorer_name"] = kwargs["name"]
        row["explorer_description"] = kwargs["description"]
        row["explorer_code_body"] = kwargs["filter_formula"]
        row["col_definitions"] = kwargs["columns"]
        row["assumptions"] = kwargs["assumptions"]
        row["manual_edit_version"] = kwargs["expected_version"] + 1
        return row


class FakeConversationExportService:
    def __init__(self) -> None:
        self.call: tuple[UUID, str] | None = None

    def export_markdown(
        self,
        *,
        conversation_id: UUID,
        destination_path: str,
    ) -> Path:
        self.call = (conversation_id, destination_path)
        path = Path(destination_path).with_suffix(".md")
        path.write_text("# Exported\n", encoding="utf-8")
        return path


class Ms10AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeService()
        self.adapter = Ms10ConversationAdapter(self.service)

    def test_load_projects_frozen_contract_without_plan_models(self) -> None:
        snapshot = self.adapter.load_conversation(str(self.service.conversation_id))
        self.assertEqual(len(snapshot.messages), 2)
        self.assertEqual(snapshot.active_explorer.name, "MA crossover")
        self.assertEqual(snapshot.context.active_explorer_metastock_state, "created")
        self.assertEqual(snapshot.results[0].result_id, self.service.result_id)
        self.assertEqual(snapshot.results[0].rows[0][1], "AAPL")
        self.assertEqual(snapshot.messages[-1].tool_outcome.status, "success")
        self.assertEqual(snapshot.messages[-1].results[0].result_id, self.service.result_id)
        self.assertFalse(hasattr(snapshot.messages[-1], "plan"))

    def test_execute_uses_coarse_progress_and_durable_reload(self) -> None:
        progress = []
        response = self.adapter.execute_turn(
            str(self.service.conversation_id),
            "Run it and give me the results",
            progress.append,
        )
        self.assertEqual([item.state for item in progress], ["processing"])
        self.assertEqual(response.context.active_result_id, self.service.result_id)
        self.assertEqual(response.final_status, "completed")
        self.assertEqual(response.messages[0].route, "generate_create_run_and_read_explorer_sequence")
        self.assertEqual(response.messages[0].results[0].matched_count, 1)

    def test_clarification_is_a_route_not_a_frontend_plan(self) -> None:
        self.service.turns[0].route = "clarify"
        self.service.turns[0].assistant_content = "Provide the exact Explorer UUID."
        self.service.calls[self.service.stream_id] = []
        snapshot = self.adapter.load_conversation(str(self.service.conversation_id))
        assistant = snapshot.messages[-1]
        self.assertIsNotNone(assistant.clarification)
        self.assertIsNone(assistant.tool_outcome)


    def test_approval_placeholder_only_for_review_only_artifact(self) -> None:
        snapshot = self.adapter.load_conversation(str(self.service.conversation_id))
        self.assertIsNone(snapshot.messages[-1].approval_placeholder)

        self.service.turns[0].route = "revise_explorer"
        self.service.turns[0].context = Context(
            active_explorer_id=self.service.explorer_id,
            active_explorer_metastock_state="not_created",
            active_service_log_id=self.service.log_id,
        )
        self.service.calls[self.service.stream_id] = [
            Call(self.service.calls[self.service.stream_id][0].result_json)
        ]
        snapshot = self.adapter.load_conversation(str(self.service.conversation_id))
        self.assertIsNotNone(snapshot.messages[-1].approval_placeholder)

    def test_rag_log_is_projected_from_get_rag_log(self) -> None:
        self.service.turns[0].route = "get_rag_log"
        self.service.turns[0].assistant_content = "Here is the active RAG log."
        self.service.calls[self.service.stream_id] = [
            Call(
                {
                    "tool_name": "get_rag_log",
                    "ok": True,
                    "status": "success",
                    "message": "RAG service log fetched.",
                    "data": {
                        "log_id": self.service.log_id,
                        "created_at": "2026-07-15T10:00:00Z",
                        "event_type": "generate_explorer",
                        "stdout_text": "retrieval complete",
                        "stderr_text": "",
                        "metadata": {"validation_passed": True},
                    },
                    "display": {
                        "title": "RAG Service Log",
                        "markdown": "log",
                        "severity": "info",
                    },
                }
            )
        ]
        snapshot = self.adapter.load_conversation(str(self.service.conversation_id))
        self.assertEqual(snapshot.active_log.log_id, self.service.log_id)
        self.assertEqual(snapshot.messages[-1].rag_log.stdout_text, "retrieval complete")

    def test_execute_uses_returned_tool_result_when_audit_rows_are_unavailable(self) -> None:
        self.service.calls[self.service.stream_id] = []
        self.service.execute_tool_result = {
            "tool_name": "get_explorer_result",
            "ok": False,
            "status": "blocked",
            "message": "Result storage is not connected.",
            "data": {},
            "display": {
                "title": "Result Storage Not Connected",
                "markdown": "The stored result cannot be loaded.",
                "severity": "warning",
            },
            "error": {
                "code": "RESULT_PERSISTENCE_NOT_CONFIGURED",
                "message": "Result storage is not connected.",
                "details": {},
            },
        }
        response = self.adapter.execute_turn(
            str(self.service.conversation_id),
            "Show the stored result",
            lambda _progress: None,
        )
        self.assertEqual(response.final_status, "blocked")
        self.assertEqual(response.messages[0].tool_outcome.error_code, "RESULT_PERSISTENCE_NOT_CONFIGURED")
        self.assertIn("cannot be loaded", response.messages[0].tool_outcome.display_markdown)

    def test_result_history_no_match_does_not_mark_list_request_as_no_matches(self) -> None:
        self.service.calls[self.service.stream_id] = [
            Call(
                {
                    "tool_name": "list_explorer_results",
                    "ok": True,
                    "status": "success",
                    "message": "Loaded result history.",
                    "data": {
                        "explorer_id": self.service.explorer_id,
                        "count": 1,
                        "results": [
                            {
                                "result_id": self.service.result_id,
                                "explorer_id": self.service.explorer_id,
                                "created_at": "2026-07-15T10:01:00Z",
                                "schema_version": "1.0",
                                "outcome": "no_matches",
                                "expected_count": 0,
                                "matched_count": 0,
                                "has_matches": False,
                            }
                        ],
                    },
                }
            )
        ]
        response = self.adapter.execute_turn(
            str(self.service.conversation_id),
            "List stored results",
            lambda _progress: None,
        )
        self.assertEqual(response.final_status, "completed")

    def test_summary_does_not_replace_already_loaded_result_rows(self) -> None:
        detailed = {
            "tool_name": "get_explorer_result",
            "ok": True,
            "status": "success",
            "message": "Loaded stored result.",
            "data": {
                "result": {
                    "result_id": self.service.result_id,
                    "explorer_id": self.service.explorer_id,
                    "created_at": "2026-07-15T10:01:00Z",
                    "schema_version": "1.0",
                    "outcome": "matches_found",
                    "expected_count": 1,
                    "matched_count": 1,
                    "has_matches": True,
                    "rows": [
                        {
                            "row_index": 1,
                            "instrument_name": "Apple Inc.",
                            "symbol": "AAPL",
                            "column_values": {"A": "189"},
                        }
                    ],
                }
            },
        }
        summary = {
            "tool_name": "list_explorer_results",
            "ok": True,
            "status": "success",
            "message": "Loaded history.",
            "data": {
                "explorer_id": self.service.explorer_id,
                "count": 1,
                "results": [
                    {
                        "result_id": self.service.result_id,
                        "explorer_id": self.service.explorer_id,
                        "created_at": "2026-07-15T10:01:00Z",
                        "schema_version": "1.0",
                        "outcome": "matches_found",
                        "expected_count": 1,
                        "matched_count": 1,
                        "has_matches": True,
                    }
                ],
            },
        }
        self.service.calls[self.service.stream_id] = [
            Call(detailed, ordinal=0),
            Call(summary, ordinal=1),
        ]
        snapshot = self.adapter.load_conversation(str(self.service.conversation_id))
        self.assertFalse(snapshot.results[0].is_summary_only)
        self.assertEqual(snapshot.results[0].rows[0][1], "AAPL")


    def test_hydrates_inline_explorer_from_current_persisted_row(self) -> None:
        edit_service = FakeExplorerEditService(self.service.explorer_id)
        adapter = Ms10ConversationAdapter(
            self.service,
            explorer_edit_service=edit_service,
        )

        snapshot = adapter.load_conversation(str(self.service.conversation_id))

        self.assertEqual(snapshot.messages[-1].explorer.name, "MA crossover edited")
        self.assertEqual(snapshot.messages[-1].explorer.manual_edit_version, 2)
        self.assertTrue(snapshot.messages[-1].explorer.can_run_in_metastock)

    def test_direct_explorer_save_uses_non_conversational_service(self) -> None:
        edit_service = FakeExplorerEditService(self.service.explorer_id)
        adapter = Ms10ConversationAdapter(
            self.service,
            explorer_edit_service=edit_service,
        )
        patch = ExplorerEditPatch(
            name="MA crossover manual",
            description="Edited without AI.",
            columns=[
                ExplorerColumn("A", "Mov(C,12,S)"),
                ExplorerColumn("B", "Mov(C,50,S)"),
            ],
            filter_formula="Cross(Mov(C,12,S),Mov(C,50,S))",
            assumptions=["Simple averages"],
        )

        explorer = adapter.save_explorer_edits(
            self.service.explorer_id,
            2,
            patch,
        )

        self.assertEqual(explorer.name, "MA crossover manual")
        self.assertEqual(explorer.manual_edit_version, 3)
        self.assertEqual(edit_service.saved["expected_version"], 2)
        self.assertEqual(edit_service.saved["columns"][0]["col_letter"], "A")

    def test_conversation_export_delegates_without_executing_turn(self) -> None:
        exporter = FakeConversationExportService()
        adapter = Ms10ConversationAdapter(
            self.service,
            conversation_export_service=exporter,
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = str(Path(directory) / "session")
            result = adapter.export_conversation_markdown(
                str(self.service.conversation_id),
                destination,
            )

        self.assertTrue(result.endswith("session.md"))
        self.assertEqual(
            exporter.call,
            (self.service.conversation_id, destination),
        )


if __name__ == "__main__":
    unittest.main()
