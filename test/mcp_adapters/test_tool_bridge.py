from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from mcp_adapters.tool_bridge import McpInvocationAudit, PublicToolBridge


class FakeResult:
    def model_dump(self, mode="json"):
        return {"tool_name": "get_explorer", "ok": True, "status": "success"}


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def list_conversation_tools(self):
        return [SimpleNamespace(name="get_explorer", enabled=True)]

    def execute(self, name, args):
        self.calls.append((name, args))
        return FakeResult()


def test_public_only_and_audit(tmp_path):
    reg = FakeRegistry()
    path = tmp_path / "audit.jsonl"
    bridge = PublicToolBridge(reg, McpInvocationAudit(path))
    with pytest.raises(ValueError):
        bridge.invoke("select_explorer_in_metastock", {"x": 1})
    assert not path.exists()
    assert bridge.invoke("get_explorer", {"explorer_id": "private"})["ok"]
    assert reg.calls == [("get_explorer", {"explorer_id": "private"})]
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert [event["event"] for event in events] == ["start", "finish"]
    assert events[0]["invocation_id"] == events[1]["invocation_id"]
    assert "private" not in path.read_text()


def test_denies_execution_when_audit_unavailable(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    reg = FakeRegistry()
    bridge = PublicToolBridge(reg, McpInvocationAudit(blocked / "audit.jsonl"))
    with pytest.raises(OSError):
        bridge.invoke("get_explorer", {})
    assert not reg.calls
