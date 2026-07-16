from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    Field,
    model_validator,
    ConfigDict,
)

from chat.models import (
    ChatContext,
    PlannerConversationMessage,
)


DecisionAction = Literal[
    "respond",
    "clarify",
    "single_tool",
    "workflow",
]


class ToolManifestItem(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    enabled: bool = True


class PlannerRequest(BaseModel):
    user_message: str
    recent_messages: list[
        PlannerConversationMessage
    ] = Field(default_factory=list)
    context: ChatContext
    tools: list[ToolManifestItem]
    available_workflows: list[str] = Field(
        default_factory=list
    )

PlannerArgumentValue = (
    str
    | int
    | float
    | bool
    | None
)


class PlannerArgument(BaseModel):
    """
    One planner-supplied tool argument.

    A list of closed name/value objects is used instead of dict[str, Any]
    because OpenAI Structured Outputs does not allow open-ended objects.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    name: str = Field(
        min_length=1,
        max_length=100,
    )
    value: PlannerArgumentValue

class OrchestratorDecision(BaseModel):
    """
    Small, auditable planner result.

    decision_reason must be a concise routing explanation. It is not intended
    to contain hidden reasoning or a long chain of thought.
    """

    model_config = ConfigDict(
    extra="forbid"
    )

    action: DecisionAction

    tool_name: str | None = None
    workflow_name: str | None = None

    arguments: list[
        PlannerArgument
    ] = Field(default_factory=list)

    explorer_reference: str | None = None
    result_reference: str | None = None
    log_reference: str | None = None

    response_message: str | None = None
    decision_reason: str = Field(
        min_length=1,
        max_length=500,
    )

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_argument_dictionary(
        cls,
        value: Any,
    ) -> Any:
        """
        Preserve compatibility with tests and internal callers that still
        construct decisions with arguments={"limit": 10}.

        The LLM-facing JSON schema remains a closed array schema.
        """
        if not isinstance(value, dict):
            return value

        raw_arguments = value.get(
            "arguments"
        )

        if not isinstance(
            raw_arguments,
            dict,
        ):
            return value

        converted = dict(value)
        converted["arguments"] = [
            {
                "name": str(name),
                "value": argument_value,
            }
            for name, argument_value
            in raw_arguments.items()
        ]

        return converted

    @model_validator(mode="after")
    def validate_decision_shape(
        self,
    ) -> Self:
        argument_names = [
            argument.name.strip()
            for argument in self.arguments
        ]

        if len(argument_names) != len(
            set(argument_names)
        ):
            raise ValueError(
                "Planner arguments must have "
                "unique names."
            )

        if self.action == "single_tool":
            if not self.tool_name:
                raise ValueError(
                    "single_tool requires "
                    "tool_name."
                )

            if self.workflow_name is not None:
                raise ValueError(
                    "single_tool must not set "
                    "workflow_name."
                )

        elif self.action == "workflow":
            if not self.workflow_name:
                raise ValueError(
                    "workflow requires "
                    "workflow_name."
                )

            if self.tool_name is not None:
                raise ValueError(
                    "workflow must not set "
                    "tool_name."
                )

        else:
            if not (
                self.response_message
                and self.response_message.strip()
            ):
                raise ValueError(
                    f"{self.action} requires "
                    "response_message."
                )

            if (
                self.tool_name is not None
                or self.workflow_name is not None
            ):
                raise ValueError(
                    f"{self.action} must not "
                    "select a tool or workflow."
                )

        return self
    
    def argument_map(
        self,
    ) -> dict[str, PlannerArgumentValue]:
        """
        Convert structured planner arguments into the dictionary expected by
        DecisionContextResolver and ToolRegistry.
        """
        resolved: dict[
            str,
            PlannerArgumentValue,
        ] = {}

        for argument in self.arguments:
            name = argument.name.strip()

            if name in resolved:
                raise ValueError(
                    "Planner returned duplicate "
                    f"argument {name!r}."
                )

            if argument.value is not None:
                resolved[name] = (
                    argument.value
                )

        return resolved
