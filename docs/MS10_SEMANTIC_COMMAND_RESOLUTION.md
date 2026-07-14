# MS10 semantic command resolution

## Production path

```text
user message + five recent messages + active context
→ normal conversation model
→ no function call: finalize normal response
→ execute_explorer_command: validate semantic dimensions
→ resolve durable Explorer reference
→ compile bounded deterministic workflow
→ execute every step through ToolRegistry
→ compose only from actual ToolResult records
```

## Why this replaces workflow-name selection

A single workflow name cannot reliably retain all parts of:

```text
create + run + capture
revise + create new version + run
specific instruments + capture
```

The semantic command keeps those concerns independent. The compiler, not the
LLM, owns internal tool names and order.

## Safety boundary

The resolver no longer uses a small positive verb list as the primary language
understanding layer. It does still enforce explicit negative constraints. For
example:

```text
Create this Explorer without running it
```

is valid and compiles to creation only, while:

```text
Do not run this Explorer
```

cannot compile to a run workflow.

## MetaStock synchronization context

```text
unknown
not_created
created
```

This state means only what the current conversation has proved about the active
Explorer. It is not a global MetaStock catalogue inventory.
