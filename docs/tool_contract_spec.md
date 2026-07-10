# MetaStock Agent Tool Contract Specification

**Document Status:** Draft  
**Version:** 0.1.0  
**Last Updated:** 2026-07-09  
**Owner:** MetaStock Agent Project  
**Audience:** Backend, agent orchestration, UI, automation, and future MCP integration developers

---

## 1. Overview

This document defines the standard contract for all LLM-accessible tools in the MetaStock Agent system.

The objective is to ensure that every tool exposed to the agent is:

- stable;
- testable;
- auditable;
- secure;
- UI-renderable;
- compatible with future MCP and LangGraph-style orchestration.

The LLM must interact only with approved tools through the `ToolRegistry`. It must not directly access Supabase, RAG internals, prompt builders, local file paths, pywinauto selectors, or credentials.

---

## 2. Scope

This specification applies to all tools that may be called by:

- the local chatbot orchestrator;
- future MCP server adapters;
- future LangGraph or LangChain agents;
- UI-triggered workflows;
- automated MetaStock execution workflows.

This specification does not define the internal implementation of RAG retrieval, Supabase schema design, MetaStock UI automation, or prompt engineering. It only defines the public tool boundary.

---

## 3. Design Principles

All tools MUST follow these principles:

1. **Intent-level interface**  
   Tools expose business capabilities, not internal implementation details.

2. **Narrow access**  
   Tools perform one well-defined action.

3. **Structured input and output**  
   Every tool input MUST be a Pydantic model. Every tool output MUST be a `ToolResult`.

4. **Durable state by ID**  
   Tools SHOULD return durable IDs such as `explorer_id`, `service_log_id`, `conversation_id`, or `run_id`.

5. **No secret exposure**  
   Tools MUST NOT expose Supabase URLs, service role keys, API keys, `.env` contents, or raw credentials.

6. **Validation before execution**  
   Execution tools MUST NOT run invalid or unapproved Explorer artifacts.

7. **MCP readiness**  
   Every tool SHOULD be serializable as a name, description, JSON Schema input, and JSON-serializable output.

---

## 4. System Boundary

The approved access pattern is:

```text
Chat UI / Orchestrator
↓
ToolRegistry
↓
Tool Service
↓
Workflow / Repository / Client
↓
RAG service / Supabase / MetaStock Automator
```

The forbidden access pattern is:

```text
LLM / Orchestrator
↓
Raw Supabase client / raw SQL / pywinauto internals / API keys
```

The LLM MUST only call tools through:

```python
registry.execute(tool_name, arguments)
```

---

## 5. Normative Language

The terms `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` are used in the RFC sense:

- `MUST`: required.
- `MUST NOT`: prohibited.
- `SHOULD`: recommended unless there is a documented reason.
- `MAY`: optional.

---

## 6. Standard Tool Interface

Every LLM-facing tool method MUST use this shape:

```python
def tool_name(self, payload: SomeInputModel) -> ToolResult:
    ...
```

Example:

```python
def generate_explorer(self, payload: GenerateExplorerInput) -> ToolResult:
    ...
```

Rules:

- `payload` MUST be a Pydantic model.
- The return value MUST be `ToolResult`.
- The tool MUST NOT return raw service objects.
- The tool SHOULD convert expected runtime exceptions into failed `ToolResult` objects.
- The tool MUST NOT expose credentials, file-system internals, raw SQL, or raw Supabase clients.

---

## 7. Standard Tool Result Envelope

All tools MUST return the following envelope:

```python
class ToolResult(BaseModel):
    tool_name: str
    ok: bool
    status: ToolStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    display: ToolDisplay | None = None
    error: ToolError | None = None
```

### 7.1 `tool_name`

The registered tool name.

Example:

```json
"generate_explorer"
```

### 7.2 `ok`

Indicates whether the tool call itself succeeded.

Important: `ok = true` does not always mean the generated artifact is valid or executable.

Example:

```json
{
  "ok": true,
  "data": {
    "explorer": {
      "validation": {
        "passed": false
      },
      "can_run_in_metastock": false
    }
  }
}
```

This means the tool completed, but the generated Explorer failed validation.

### 7.3 `status`

Tools MUST use the shared status enum:

```python
class ToolStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_IMPLEMENTED = "not_implemented"
```

No tool may invent new status values without updating the shared enum.

### 7.4 `message`

A short human-readable summary.

Good:

```text
Explorer generated and prepared for review.
```

Bad:

```text
Done.
```

### 7.5 `data`

Machine-readable result payload.

Rules:

- MUST be JSON-serializable.
- SHOULD be produced from Pydantic DTOs using `model_dump(mode="json")`.
- SHOULD include durable IDs.
- MUST NOT include credentials or raw internal clients.
- SHOULD NOT include large logs unless the tool is specifically a log-reading tool.

### 7.6 `display`

Optional UI-ready representation.

Used by chatbot UI, review UI, or future desktop interface.

### 7.7 `error`

Structured error information. Required when `ok = false`.

---

## 8. Error Contract

All failed tools SHOULD return:

```python
class ToolError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
```

Example:

```json
{
  "code": "TOOL_BLOCKED",
  "message": "AutomatorClient is not implemented yet.",
  "details": {}
}
```

Rules:

- `code` MUST be stable and machine-readable.
- `message` SHOULD be safe for display.
- `details` MAY contain diagnostic metadata.
- `details` MUST NOT contain Supabase URLs, service role keys, API keys, `.env` contents, or raw credentials.
- Development tracebacks MAY be included during local testing, but MUST be sanitized before production.

---

## 9. Display Contract

Tools returning user-visible content SHOULD include:

```python
class ToolDisplay(BaseModel):
    title: str
    markdown: str
    severity: Literal["info", "success", "warning", "error"] = "info"
```

Severity usage:

| Severity | Meaning |
|---|---|
| `success` | Operation succeeded and result is usable |
| `info` | Neutral read or display operation |
| `warning` | Operation completed but requires attention |
| `error` | Operation failed |

For Explorer tools:

| Condition | Display Severity |
|---|---|
| Validation passed | `success` |
| Validation failed | `warning` |
| Tool failed | `error` |
| Read-only result | `info` |

---

## 10. Input Model Standard

Every tool input MUST be a Pydantic model.

Example:

```python
class GenerateExplorerInput(BaseModel):
    user_query: str = Field(
        description="Natural-language request for a MetaStock Explorer."
    )
```

Input models MUST NOT expose:

- raw SQL;
- arbitrary table names;
- Supabase URLs;
- Supabase keys;
- OpenAI API keys;
- local absolute paths unless the tool is explicitly a file tool;
- pywinauto selectors;
- raw UI coordinates;
- implementation-specific prompt controls.

Good:

```python
class GetExplorerInput(BaseModel):
    explorer_id: str
```

Bad:

```python
class QueryDatabaseInput(BaseModel):
    table: str
    where_clause: str
```

---

## 11. Output DTO Standard

Every successful tool SHOULD wrap its result in a named DTO.

Example:

```python
class GenerateExplorerOutput(BaseModel):
    explorer: ExplorerDTO
    retrieved_refs: list[dict[str, Any]] = Field(default_factory=list)
```

Rules:

- Tools SHOULD NOT return raw Supabase rows directly.
- Important fields SHOULD be flattened into stable DTOs.
- Durable IDs SHOULD be included.
- Validation, approval, and execution gates SHOULD be explicit.
- Implementation-only database columns SHOULD be omitted unless needed for debugging.

---

## 12. Explorer DTO Standard

Any tool that returns an Explorer MUST use the `ExplorerDTO` shape.

```python
class ExplorerDTO(BaseModel):
    explorer_id: str
    explorer_created_at: str | None = None

    name: str
    description: str
    filter_code: str
    columns: list[ExplorerColumnDTO] = Field(default_factory=list)

    validation: ValidationDTO

    can_run_in_metastock: bool
    can_repair: bool

    source: str | None = None
    service_log_id: str | None = None
    service_log_created_at: str | None = None
```

Supporting DTOs:

```python
class ExplorerColumnDTO(BaseModel):
    col_letter: str
    col_code: str


class ValidationDTO(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

Rules:

- `filter_code` MUST contain only the MetaStock filter formula body.
- `columns` MUST be normalized as `col_letter` and `col_code`.
- `can_run_in_metastock` MUST be false if validation fails.
- `can_repair` SHOULD be true if validation fails.
- `service_log_id` SHOULD be included when available.

---

## 13. Tool Categories

Each tool MUST belong to one category.

### 13.1 Read Tools

Read stored state.

Examples:

```text
get_explorer
get_rag_log
get_conversation
get_latest_explorer
list_conversation_explorers
```

Rules:

- MUST NOT mutate state.
- MUST NOT execute external actions.
- SHOULD be safe to call repeatedly.
- MUST NOT expose credentials or arbitrary database access.

### 13.2 Generation Tools

Create new artifacts from user intent.

Examples:

```text
generate_explorer
```

Rules:

- MUST store the generated artifact.
- MUST return a durable ID.
- MUST validate generated output.
- MUST log the service call.
- MUST NOT execute MetaStock automatically.

### 13.3 Repair Tools

Create corrected artifacts from existing artifacts.

Examples:

```text
repair_explorer
```

Rules:

- MUST NOT overwrite the original artifact.
- SHOULD create a new row or version.
- SHOULD link back to the original artifact.
- SHOULD preserve original trading intent unless explicitly instructed otherwise.

### 13.4 Revision Tools

Create new versions based on human-requested strategy changes.

Examples:

```text
revise_explorer
```

Rules:

- MUST be separate from repair.
- SHOULD create a new version.
- MUST NOT overwrite prior versions.
- SHOULD preserve version lineage.

Repair means:

```text
Fix syntax, contract, or validation problems.
```

Revision means:

```text
Change the strategy logic based on human instruction.
```

### 13.5 Approval Tools

Change review state.

Examples:

```text
approve_explorer
reject_explorer
mark_explorer_needs_revision
```

Rules:

- MUST write approval state.
- MUST include actor/source.
- MUST include timestamp.
- MUST NOT modify formula content.
- MUST NOT execute MetaStock.

### 13.6 Execution Tools

Run actions outside the database.

Examples:

```text
run_explorer_in_metastock
```

Rules:

- MUST require validation passed.
- SHOULD require approval once approval service exists.
- MUST create a run record.
- MUST capture stdout/stderr or execution diagnostics.
- MUST NOT run invalid Explorers.
- MUST NOT execute directly from unsaved LLM output.

---

## 14. Tool Naming Standard

Tool names MUST use lowercase snake case.

Good:

```text
generate_explorer
repair_explorer
get_explorer
get_rag_log
approve_explorer
run_explorer_in_metastock
```

Bad:

```text
GenerateExplorer
runMetaStock
query_db
callRAG
```

Tool names SHOULD begin with a verb:

```text
generate_
repair_
revise_
get_
list_
approve_
reject_
run_
cancel_
```

---

## 15. Registry Standard

Every tool MUST be registered through `ToolDefinition`.

```python
@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: Type[BaseModel]
    handler: Callable[[Any], ToolResult]
    enabled: bool = True
```

Example:

```python
ToolDefinition(
    name="generate_explorer",
    description=(
        "Generate a new MetaStock Explorer from a natural-language trading "
        "condition. Use this when the user asks to create, generate, build, "
        "or draft a stock screening Explorer."
    ),
    input_model=GenerateExplorerInput,
    handler=explorer_tool_service.generate_explorer,
    enabled=True,
)
```

Tool descriptions MUST be written for an LLM consumer.

Good:

```text
Generate a new MetaStock Explorer from a natural-language trading condition.
Use this when the user asks to create, generate, build, or draft a stock
screening Explorer.
```

Bad:

```text
Calls generate_explorer.py.
```

---

## 16. Disabled Tool Standard

A planned but unavailable tool MAY be registered with `enabled=False`.

Disabled tools MUST return a blocked result:

```python
ToolResult(
    tool_name=name,
    ok=False,
    status=ToolStatus.BLOCKED,
    message=f"Tool is disabled: {name}",
    error=ToolError(
        code="TOOL_DISABLED",
        message=f"The tool `{name}` is currently disabled.",
    ),
)
```

This allows the orchestrator to explain honestly that a capability exists conceptually but is not currently connected.

---

## 17. Validation and Execution Gates

Validation failure is not the same as tool failure.

A generation tool may return:

```json
{
  "ok": true,
  "status": "success",
  "data": {
    "explorer": {
      "validation": {
        "passed": false,
        "errors": ["Invalid function syntax"]
      },
      "can_run_in_metastock": false,
      "can_repair": true
    }
  },
  "display": {
    "severity": "warning"
  }
}
```

This means the tool executed successfully, but the artifact is not runnable.

Execution tools MUST check:

```text
validation.passed == true
```

Future execution tools SHOULD also check:

```text
approval.status == approved
```

---

## 18. State and ID Standard

Tools SHOULD pass durable IDs instead of in-memory objects.

Preferred IDs:

```text
explorer_id
service_log_id
conversation_id
message_id
tool_call_id
run_id
```

Any tool that creates a durable artifact MUST return its ID.

Example:

```json
{
  "explorer_id": "8b67f34a-2d8c-4467-8f85-06726da86a41",
  "service_log_id": "f5e3ed25-9394-4843-bd44-ae53c030dc2c"
}
```

The orchestrator MAY cache latest IDs in memory, but durable truth SHOULD live in Supabase.

---

## 19. Observability and Logging

Every meaningful tool call SHOULD be loggable.

Minimum recommended fields for `agent_tool_calls`:

```text
tool_call_id
conversation_id
message_id
tool_name
arguments_json
result_status
result_ok
result_summary
related_explorer_id
related_service_log_id
started_at
finished_at
error_code
error_message
```

Rules:

- Tool logs MUST NOT contain secrets.
- Generation and repair service stdout/stderr MAY live in `rag_service_logs`.
- Orchestrator-level tool calls SHOULD be stored separately in `agent_tool_calls`.
- Logs SHOULD include enough information to reconstruct what the agent did.

---

## 20. Security Requirements

Tools MUST NEVER return:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
OPENAI_API_KEY
.env contents
raw database credentials
raw API clients
```

Project-specific rule:

```text
Supabase URL must not be exposed to the user or LLM.
```

Therefore, tools MUST NOT include Supabase URLs in:

- `ToolResult`;
- `ToolDisplay`;
- `ToolError`;
- logs;
- tool descriptions;
- LLM context;
- UI messages.

---

## 21. Supabase Access Boundary

The preferred boundary is:

```text
LLM / Orchestrator
↓
ToolRegistry
↓
Tool Service
↓
Repository / Client
↓
Supabase
```

The LLM MUST NOT directly query Supabase.

The current design separates responsibilities:

```text
RAG repo:
- RAG artifact storage
- explorer_outputs
- rag_service_logs
- RAG card tables

Agent app:
- future conversation state
- messages
- explorer records
- approvals
- agent tool calls
- execution runs
```

Regardless of which component owns a table, Supabase access MUST remain below the tool or service layer.

---

## 22. MCP Compatibility Requirements

Every local tool SHOULD be MCP-compatible.

A tool is MCP-compatible if it has:

```text
name
description
JSON Schema input
JSON-serializable output
stable error shape
no direct UI dependency
no secrets in input/output
no required human interaction during execution
```

The future MCP adapter SHOULD call:

```python
registry.execute(tool_name, arguments)
```

The MCP adapter MUST NOT duplicate business logic.

Correct MCP design:

```text
MCP Client
↓
MCP Server Adapter
↓
ToolRegistry.execute(...)
↓
Tool Service
```

Incorrect MCP design:

```text
MCP Server
↓
Raw Supabase / RAG internals / pywinauto internals
```

---

## 23. Versioning and Compatibility

Tool contracts SHOULD be versioned.

Recommended policy:

- Adding optional fields is backward compatible.
- Removing fields is breaking.
- Renaming fields is breaking.
- Changing field meaning is breaking.
- Changing enum values is breaking.
- Adding new tools is backward compatible.
- Changing tool behavior that affects safety gates is breaking.

Breaking changes SHOULD update the document version and include a migration note.

---

## 24. Test Requirements

Every new tool MUST have at least one registry-level test.

The test MUST verify:

```text
1. Tool is registered.
2. Tool input validates.
3. Tool returns ToolResult.
4. ToolResult is JSON-serializable.
5. Success path works.
6. Failure, blocked, or not-implemented path works where applicable.
7. Result does not expose credentials.
```

Example:

```python
result = registry.execute(
    "get_explorer",
    {
        "explorer_id": explorer_id,
    },
)

assert result.tool_name == "get_explorer"
assert result.ok is True
assert result.status == ToolStatus.SUCCESS
assert "SUPABASE" not in result.model_dump_json()
assert "SERVICE_ROLE_KEY" not in result.model_dump_json()
```

---

## 25. Definition of Done for New Tools

A new tool is complete only when:

```text
[ ] It has a Pydantic input model.
[ ] It has a named output DTO where applicable.
[ ] It returns ToolResult.
[ ] It is registered in ToolRegistry.
[ ] It has a clear LLM-facing description.
[ ] It has a registry-level test.
[ ] It returns durable IDs where applicable.
[ ] It does not expose secrets.
[ ] It follows validation/execution gates.
[ ] It is JSON-serializable.
[ ] It is MCP-compatible.
```

---

## 26. Standard Tool Skeleton

```python
from __future__ import annotations

import traceback

from tools.tool_contracts import (
    ToolDisplay,
    ToolError,
    ToolResult,
    ToolStatus,
)


class ExampleToolService:
    def example_tool(self, payload: ExampleToolInput) -> ToolResult:
        try:
            output = self._do_work(payload)

            return ToolResult(
                tool_name="example_tool",
                ok=True,
                status=ToolStatus.SUCCESS,
                message="Tool completed successfully.",
                data=output.model_dump(mode="json"),
                display=ToolDisplay(
                    title="Tool Completed",
                    markdown="Tool completed successfully.",
                    severity="success",
                ),
            )

        except Exception as exc:
            return ToolResult(
                tool_name="example_tool",
                ok=False,
                status=ToolStatus.FAILED,
                message=str(exc),
                error=ToolError(
                    code=type(exc).__name__,
                    message=str(exc),
                    details={
                        "traceback": traceback.format_exc(),
                    },
                ),
                display=ToolDisplay(
                    title="Tool Failed",
                    markdown="\n".join(
                        [
                            "```text",
                            traceback.format_exc(),
                            "```",
                        ]
                    ),
                    severity="error",
                ),
            )
```

Production tools SHOULD sanitize tracebacks before exposing them to the UI or LLM.

---

## 27. Final Rule

Every backend capability MUST first become a clean local tool before being exposed to:

```text
chatbot orchestrator
MCP server
LangGraph agent
UI button
automation workflow
```

The source of truth is:

```text
ToolRegistry + ToolResult contract
```

Not the UI, not the orchestrator, and not MCP.