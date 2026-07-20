from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from chat.models import (
    ChatContext,
    PlannerConversationMessage,
)


ActionKind = Literal[
    "tool",
    "command",
]
COMMAND_ACTION_NAME = "execute_explorer_command"


class RegistryCatalogProtocol(Protocol):
    def list_tools(self) -> list[Any]:
        ...


class ConversationActionDefinition(BaseModel):
    name: str
    description: str
    kind: ActionKind
    parameters: dict[str, Any]

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": False,
        }


class ConversationActionCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(
        default_factory=dict
    )
    call_id: str | None = None


class ConversationModelRequest(BaseModel):
    user_message: str
    recent_messages: list[
        PlannerConversationMessage
    ] = Field(default_factory=list)
    context: ChatContext
    actions: list[
        ConversationActionDefinition
    ] = Field(default_factory=list)


class ConversationModelResponse(BaseModel):
    assistant_message: str = ""
    action_call: ConversationActionCall | None = None


EXPLORER_REFERENCE_SCHEMA = {
    "type": "string",
    "description": (
        "Explorer UUID, exact stored name, or current/this/it."
    ),
}


DIRECT_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_explorer": {
        "type": "object",
        "properties": {
            "explorer_reference": EXPLORER_REFERENCE_SCHEMA,
        },
        "additionalProperties": False,
    },
    "get_rag_log": {
        "type": "object",
        "properties": {
            "log_reference": {
                "type": "string",
                "description": (
                    "RAG log UUID or current/this/it."
                ),
            },
        },
        "additionalProperties": False,
    },
    "get_explorer_result": {
        "type": "object",
        "properties": {
            "result_reference": {
                "type": "string",
                "description": (
                    "Stored result UUID or current/this/it."
                ),
            },
        },
        "additionalProperties": False,
    },
    "get_latest_explorer_result": {
        "type": "object",
        "properties": {
            "explorer_reference": EXPLORER_REFERENCE_SCHEMA,
        },
        "additionalProperties": False,
    },
    "list_explorer_results": {
        "type": "object",
        "properties": {
            "explorer_reference": EXPLORER_REFERENCE_SCHEMA,
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
            },
        },
        "additionalProperties": False,
    },
}


LIFECYCLE_TOOL_NAMES = {
    "generate_explorer",
    "repair_explorer",
    "revise_explorer",
    "create_explorer_in_metastock",
    "select_explorer_in_metastock",
    "run_selected_explorer_in_metastock",
    "read_metastock_explorer_results",
}


def _command_schema(
    enabled_tool_names: set[str],
) -> dict[str, Any]:
    artifact_actions = ["none"]

    if "generate_explorer" in enabled_tool_names:
        artifact_actions.append("generate")

    if "revise_explorer" in enabled_tool_names:
        artifact_actions.append("revise")

    if "repair_explorer" in enabled_tool_names:
        artifact_actions.append("repair")

    metastock_actions = ["none"]

    if "create_explorer_in_metastock" in enabled_tool_names:
        metastock_actions.append("create")

    if {
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
    }.issubset(enabled_tool_names):
        metastock_actions.append("run")

        if "create_explorer_in_metastock" in enabled_tool_names:
            metastock_actions.append("create_and_run")

    result_actions = ["none"]

    if (
        "read_metastock_explorer_results" in enabled_tool_names
        and {
            "select_explorer_in_metastock",
            "run_selected_explorer_in_metastock",
        }.issubset(enabled_tool_names)
    ):
        result_actions.append("capture_new")

    return {
        "type": "object",
        "properties": {
            "artifact_action": {
                "type": "string",
                "enum": artifact_actions,
                "description": (
                    "generate creates a new stored Explorer from a strategy "
                    "request; revise intentionally changes an existing "
                    "Explorer; repair fixes syntax or contract errors; none "
                    "uses the existing referenced Explorer unchanged."
                ),
            },
            "explorer_reference": EXPLORER_REFERENCE_SCHEMA,
            "resolved_instruction": {
                "type": "string",
                "description": (
                    "A standalone, explicit generation, revision, or repair "
                    "instruction. Resolve pronouns and ellipsis from recent "
                    "conversation. For example, output 'Change the RSI period "
                    "from 14 to 7' rather than 'change it to 7'. Preserve every "
                    "unmentioned condition. Required when artifact_action is "
                    "generate, revise, or repair."
                ),
            },
            "metastock_action": {
                "type": "string",
                "enum": metastock_actions,
                "description": (
                    "none performs no MetaStock UI action; create creates the "
                    "stored Explorer in MetaStock; run selects and runs an "
                    "Explorer already in MetaStock; create_and_run creates, "
                    "selects, and runs it. A user asking to create/build an "
                    "Explorer normally means create it in MetaStock too unless "
                    "they explicitly ask for a draft only."
                ),
            },
            "result_action": {
                "type": "string",
                "enum": result_actions,
                "description": (
                    "capture_new runs as needed, reads the newly produced "
                    "MetaStock result window, and persists it. Phrases such as "
                    "give me the results, return the results, show the results, "
                    "capture, record, save, or store the results all mean "
                    "capture_new when a fresh run is requested. Use the separate "
                    "stored-result tools when no fresh run is requested."
                ),
            },
            "instruments": {
                "type": "string",
                "description": (
                    "Use 'all' unless the user supplied exact MetaStock "
                    "instrument, exchange, or custom-list labels. Preserve "
                    "multiple labels as one comma-separated string in the "
                    "user's order. Do not broaden, abbreviate, or invent labels."
                ),
                "default": "all",
            },
        },
        "required": [
            "artifact_action",
            "metastock_action",
            "result_action",
        ],
        "additionalProperties": False,
    }


def build_conversation_actions(
    registry: RegistryCatalogProtocol,
    workflows: Any = None,
) -> list[ConversationActionDefinition]:
    del workflows  # Kept in the signature for a low-risk graph migration.

    actions: list[ConversationActionDefinition] = []
    enabled_definitions: dict[str, Any] = {}

    for definition in registry.list_tools():
        if not bool(getattr(definition, "enabled", True)):
            continue

        name = str(getattr(definition, "name", "")).strip()

        if name:
            enabled_definitions[name] = definition

    enabled_names = set(enabled_definitions)

    for name, parameters in DIRECT_ACTION_SCHEMAS.items():
        definition = enabled_definitions.get(name)

        if definition is None:
            continue

        exposure = getattr(definition, "exposure", None)
        exposure_value = getattr(
            exposure,
            "value",
            exposure,
        )

        if exposure_value != "conversation":
            continue

        actions.append(
            ConversationActionDefinition(
                name=name,
                description=str(
                    getattr(definition, "description", "")
                ),
                kind="tool",
                parameters=parameters,
            )
        )

    if enabled_names.intersection(LIFECYCLE_TOOL_NAMES):
        actions.append(
            ConversationActionDefinition(
                name=COMMAND_ACTION_NAME,
                description=(
                    "Resolve and execute one complete Explorer lifecycle "
                    "command. Use this single function for generation, "
                    "revision, repair, MetaStock creation, running, and fresh "
                    "result capture, including compound requests. Keep these "
                    "intent dimensions separate in the arguments."
                ),
                kind="command",
                parameters=_command_schema(enabled_names),
            )
        )

    return sorted(
        actions,
        key=lambda action: action.name,
    )
