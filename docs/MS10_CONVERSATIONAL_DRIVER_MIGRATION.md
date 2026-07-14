# MS10 conversational-driver migration

## Source baseline

Apply this patch to:

```text
Orange-eat97/metastock-agent
branch: ms10-langgraph-orchestrator
```

At patch creation time that branch is two commits ahead of `main`. The MS10
orchestration package does not yet exist on `main`.

## Architectural change

The production LangGraph path no longer asks OpenAI to return one global
`OrchestratorDecision` JSON object for every user message.

It now uses normal Responses API conversation output with optional function
calling:

```text
latest five messages
+ current message
+ active IDs
+ model-visible actions
        |
        v
OpenAI conversation model
        |
        +-- text only --------------------> finalize
        |
        +-- zero-or-one function call
                    |
                    v
             action policy
                    |
             +------+------+
             |             |
         direct tool    workflow
             |             |
             +------v------+
                ToolRegistry
                    |
             response composer
                    |
                 finalize
```

`parallel_tool_calls=False` limits the model to zero or one selected action.
ToolRegistry and Pydantic remain the execution validators.

## Model-visible direct tools

```text
generate_explorer
repair_explorer
get_explorer
get_rag_log
get_explorer_result
get_latest_explorer_result
list_explorer_results
```

`revise_explorer` is conversation-visible and enabled by the MS10 revision
closeout patch. It stores revisions as new Explorer rows.

## Model-visible workflows

```text
run_explorer
run_and_capture
create_run_and_capture
```

## Workflow-internal tools

These remain registered and auditable, but are not shown to the model:

```text
create_explorer_in_metastock
select_explorer_in_metastock
run_selected_explorer_in_metastock
read_metastock_explorer_results
```

## Context boundary

The model receives only:

```text
- current user message
- latest five completed user/assistant messages
- active Explorer/result/log IDs
- model-visible action descriptions and small argument schemas
```

It does not receive:

```text
- RAG cards or retrieval context
- raw Supabase rows
- raw results
- checkpoints
- the full transcript
```

RAG remains behind generation, repair, and future revision tools.

## Compatibility

The old structured-planner graph remains temporarily available to existing
tests and explicit callers. Production composition and `scripts.chat_harness`
construct `OpenAIConversationDriver`.

Do not apply the earlier discriminated-union bundle.

## Install

Copy the bundle contents into the repository root and overwrite matching files.

## Tests

```powershell
python -m pytest -q test/services/test_planner_history.py
python -m pytest -q test/orchestration/test_conversation_actions.py
python -m pytest -q test/orchestration/test_conversation_model.py
python -m pytest -q test/orchestration/test_action_policy.py
python -m pytest -q test/orchestration
python -m pytest -q test/application
python -m pytest -q
```

## Smoke test

```powershell
python -m scripts.chat_harness `
  --rag-repo "C:\GitHub\metastock-RAG-LLM" `
  --conversation-id "<conversation UUID>" `
  --disable-deterministic-fallback
```

Expected:

```text
"Why did you use 14 periods for RSI?"
    normal assistant reply; Route: respond; no tool call

"Show the current Explorer."
    get_explorer

"Run the Explorer as it is."
    run_explorer workflow

"Use 25 instead of 30."
    revise_explorer creates a new Explorer row and updates the active Explorer.
    Unmentioned conditions should remain unchanged.
```

## Closeout additions

The MS10 revision closeout adds `revise_explorer`, revision lineage, plain-run
normalization, capture-language synonyms, and the bounded `revise_and_run`
workflow.
