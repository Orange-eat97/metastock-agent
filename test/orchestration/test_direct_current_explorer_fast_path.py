from __future__ import annotations

import unittest

from chat.models import ChatContext, ChatTurnInput
from chat.routes import ChatRoute
from orchestration.orchestrator import LangGraphOrchestrator
from tools.tool_contracts import ToolResult, ToolStatus


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append((name, arguments))
        return ToolResult(
            tool_name=name,
            ok=True,
            status=ToolStatus.SUCCESS,
            message="Explorer fetched.",
            data={
                "explorer": {
                    "explorer_id": arguments["explorer_id"],
                    "name": "AI_Test",
                }
            },
        )


class FailingGraph:
    def __init__(self) -> None:
        self.invoked = False

    def invoke(self, input, config=None, *, context=None):
        del input, config, context
        self.invoked = True
        raise AssertionError("The conversational graph must not be invoked.")


class DirectCurrentExplorerFastPathTests(unittest.TestCase):
    def test_current_explorer_request_bypasses_graph(self) -> None:
        registry = FakeRegistry()
        graph = FailingGraph()
        orchestrator = LangGraphOrchestrator(
            registry,  # type: ignore[arg-type]
            graph=graph,
        )

        output = orchestrator.handle_turn(
            ChatTurnInput(
                user_message="Show me the current Explorer.",
                context=ChatContext(
                    active_explorer_id="explorer-123"
                ),
            )
        )

        self.assertFalse(graph.invoked)
        self.assertEqual(output.route, ChatRoute.GET_EXPLORER)
        self.assertEqual(output.assistant_message, "Here is the current Explorer.")
        self.assertIsNotNone(output.tool_result)
        self.assertEqual(
            registry.calls,
            [
                (
                    "get_explorer",
                    {"explorer_id": "explorer-123"},
                )
            ],
        )

    def test_missing_active_explorer_is_also_deterministic(self) -> None:
        registry = FakeRegistry()
        graph = FailingGraph()
        orchestrator = LangGraphOrchestrator(
            registry,  # type: ignore[arg-type]
            graph=graph,
        )

        output = orchestrator.handle_turn(
            ChatTurnInput(
                user_message="Display the active explorer",
                context=ChatContext(),
            )
        )

        self.assertFalse(graph.invoked)
        self.assertEqual(output.route, ChatRoute.GET_EXPLORER)
        self.assertIsNone(output.tool_result)
        self.assertEqual(registry.calls, [])
        self.assertIn("no current Explorer", output.assistant_message)

    def test_other_requests_continue_to_graph(self) -> None:
        class ReturningGraph:
            def __init__(self) -> None:
                self.invoked = False

            def invoke(self, input, config=None, *, context=None):
                del input, config, context
                self.invoked = True
                return {
                    "turn_output": {
                        "assistant_message": "Normal response",
                        "route": "respond",
                        "context": {},
                        "tool_result": None,
                    }
                }

        graph = ReturningGraph()
        orchestrator = LangGraphOrchestrator(
            FakeRegistry(),  # type: ignore[arg-type]
            graph=graph,
        )
        output = orchestrator.handle_turn(
            ChatTurnInput(user_message="Explain this Explorer")
        )

        self.assertTrue(graph.invoked)
        self.assertEqual(output.route, ChatRoute.RESPOND)


if __name__ == "__main__":
    unittest.main()
