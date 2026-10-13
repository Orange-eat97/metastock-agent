"""Public ToolRegistry adapter with separate, append-only MCP invocation audit.

Only ToolExposure.CONVERSATION tools are callable. Internal UI steps remain
private. No modification to existing RAG, tool, or LangGraph implementations.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class McpInvocationAudit:
    def __init__(self, filename: str | Path) -> None:
        self.path = Path(filename).expanduser()
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        # Append-only JSONL. No arguments, prompt text, secrets, or full result bodies.
        data = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(data)
                stream.flush()


class PublicToolBridge:
    def __init__(self, registry: Any, audit: McpInvocationAudit) -> None:
        self._registry = registry
        self._audit = audit
        self._execution_lock = threading.Lock()  # UIA/MetaStock must not run concurrently.

    def definitions(self) -> list[Any]:
        return [
            definition for definition in self._registry.list_conversation_tools()
            if definition.enabled
        ]

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        public = {definition.name for definition in self.definitions()}
        if name not in public:
            raise ValueError("Unknown or non-public MCP tool")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")

        invocation_id = str(uuid4())
        started = time.monotonic()
        # Refuse execution if we cannot record its beginning.
        self._audit.append({
            "event": "start", "at": _now(), "invocation_id": invocation_id,
            "tool_name": name,
            "argument_keys": sorted(str(key) for key in arguments),
        })
        with self._execution_lock:
            try:
                result = self._registry.execute(name, arguments)
                payload = result.model_dump(mode="json")
            except Exception as exc:
                self._audit.append({
                    "event": "finish", "at": _now(), "invocation_id": invocation_id,
                    "tool_name": name, "outcome": "exception",
                    "exception_type": type(exc).__name__,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                })
                raise
            self._audit.append({
                "event": "finish", "at": _now(), "invocation_id": invocation_id,
                "tool_name": name, "outcome": str(payload.get("status", "unknown")),
                "ok": bool(payload.get("ok", False)),
                "duration_ms": round((time.monotonic() - started) * 1000),
            })
            return payload
