from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from chat.models import ChatContext
from chat.routes import ChatRoute


class ArtifactAction(str, Enum):
    NONE = "none"
    GENERATE = "generate"
    REVISE = "revise"
    REPAIR = "repair"


class MetaStockAction(str, Enum):
    NONE = "none"
    CREATE = "create"
    RUN = "run"
    CREATE_AND_RUN = "create_and_run"


class ResultAction(str, Enum):
    NONE = "none"
    CAPTURE_NEW = "capture_new"


class MetaStockSyncState(str, Enum):
    UNKNOWN = "unknown"
    NOT_CREATED = "not_created"
    CREATED = "created"


class ExplorerCommandArguments(BaseModel):
    """
    Semantic command emitted by the conversation model for an action turn.

    The fields deliberately separate artifact mutation, MetaStock side effects,
    and result capture. This prevents one overlapping workflow name from losing
    another part of a compound request.
    """

    artifact_action: ArtifactAction
    explorer_reference: str | None = None
    resolved_instruction: str | None = None
    metastock_action: MetaStockAction
    result_action: ResultAction
    instruments: str = "all"

    @field_validator(
        "explorer_reference",
        "resolved_instruction",
        mode="before",
    )
    @classmethod
    def clean_optional_text(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        cleaned = str(value).strip()
        return cleaned or None

    @field_validator(
        "instruments",
        mode="before",
    )
    @classmethod
    def clean_instruments(
        cls,
        value: Any,
    ) -> str:
        cleaned = str(value or "all").strip()
        return cleaned or "all"

    @model_validator(mode="after")
    def validate_command(self) -> "ExplorerCommandArguments":
        if (
            self.artifact_action
            in {
                ArtifactAction.GENERATE,
                ArtifactAction.REVISE,
                ArtifactAction.REPAIR,
            }
            and not self.resolved_instruction
        ):
            raise ValueError(
                "resolved_instruction is required for "
                f"artifact_action={self.artifact_action.value}."
            )

        if (
            self.artifact_action is ArtifactAction.NONE
            and self.metastock_action is MetaStockAction.NONE
            and self.result_action is ResultAction.NONE
        ):
            raise ValueError(
                "The semantic command does not request an action."
            )

        return self


class NormalizedExplorerCommand(BaseModel):
    artifact_action: ArtifactAction
    explorer_reference: str | None = None
    resolved_instruction: str | None = None
    metastock_action: MetaStockAction
    result_action: ResultAction
    instruments: str = "all"

    @property
    def needs_source_explorer(self) -> bool:
        return self.artifact_action in {
            ArtifactAction.NONE,
            ArtifactAction.REVISE,
            ArtifactAction.REPAIR,
        }

    @property
    def produces_new_explorer(self) -> bool:
        return self.artifact_action in {
            ArtifactAction.GENERATE,
            ArtifactAction.REVISE,
            ArtifactAction.REPAIR,
        }

    @property
    def workflow_name(self) -> str:
        parts: list[str] = []

        if self.artifact_action is not ArtifactAction.NONE:
            parts.append(self.artifact_action.value)

        if self.metastock_action is MetaStockAction.CREATE:
            parts.append("create")
        elif self.metastock_action is MetaStockAction.RUN:
            parts.append("run")
        elif self.metastock_action is MetaStockAction.CREATE_AND_RUN:
            parts.extend(["create", "run"])

        if self.result_action is ResultAction.CAPTURE_NEW:
            parts.append("capture")

        if not parts:
            raise RuntimeError(
                "A normalized command must compile to at least one step."
            )

        if parts == ["generate"]:
            return "generate_explorer"

        if parts == ["revise"]:
            return "revise_explorer"

        if parts == ["repair"]:
            return "repair_explorer"

        if parts == ["create"]:
            return "create_in_metastock"

        if parts == ["run"]:
            return "run_explorer"

        if parts == ["create", "run"]:
            return "create_and_run"

        if parts == ["run", "capture"]:
            return "run_and_capture"

        if parts == ["create", "run", "capture"]:
            return "create_run_and_capture"

        return "_".join(parts)

    @property
    def route(self) -> ChatRoute:
        mapping = {
            "generate_explorer": ChatRoute.GENERATE_EXPLORER,
            "generate_create": ChatRoute.GENERATE_AND_CREATE_EXPLORER,
            "generate_create_run": (
                ChatRoute.GENERATE_CREATE_AND_RUN_EXPLORER
            ),
            "generate_create_run_capture": (
                ChatRoute.GENERATE_CREATE_RUN_AND_READ_EXPLORER
            ),
            "revise_explorer": ChatRoute.REVISE_EXPLORER,
            "revise_create": ChatRoute.REVISE_AND_CREATE_EXPLORER,
            "revise_create_run": (
                ChatRoute.REVISE_CREATE_AND_RUN_EXPLORER
            ),
            "revise_create_run_capture": (
                ChatRoute.REVISE_CREATE_RUN_AND_READ_EXPLORER
            ),
            "repair_explorer": ChatRoute.REPAIR_EXPLORER,
            "repair_create": ChatRoute.REPAIR_AND_CREATE_EXPLORER,
            "repair_create_run": (
                ChatRoute.REPAIR_CREATE_AND_RUN_EXPLORER
            ),
            "repair_create_run_capture": (
                ChatRoute.REPAIR_CREATE_RUN_AND_READ_EXPLORER
            ),
            "create_in_metastock": (
                ChatRoute.CREATE_METASTOCK_EXPLORER
            ),
            "run_explorer": ChatRoute.RUN_EXPLORER,
            "create_and_run": ChatRoute.CREATE_AND_RUN_EXPLORER,
            "run_and_capture": ChatRoute.RUN_AND_READ_EXPLORER,
            "create_run_and_capture": (
                ChatRoute.CREATE_RUN_AND_READ_EXPLORER
            ),
        }

        try:
            return mapping[self.workflow_name]
        except KeyError as exc:
            raise RuntimeError(
                "No ChatRoute is defined for normalized workflow "
                f"{self.workflow_name!r}."
            ) from exc


class CommandResolutionError(ValueError):
    pass


class SemanticCommandResolver:
    """
    Normalize one model-produced semantic command.

    Language understanding comes from the conversation model. This layer only
    applies deterministic invariants and safe defaults; it does not attempt to
    reconstruct the whole command with a narrow verb regex.
    """

    DRAFT_ONLY_PATTERN = re.compile(
        (
            r"\b(draft|preview|review[- ]only|draft[- ]only)\b"
            r"|\b(do\s+not|don't|dont|without)\b.{0,24}"
            r"\b(create|add|write|push|send)\b.{0,24}"
            r"\b(meta\s*stock|explorer|exploration)\b"
        ),
        re.IGNORECASE,
    )
    NEGATED_RUN_PATTERN = re.compile(
        (
            r"\b(do\s+not|don't|dont|never|without)\b"
            r".{0,32}\b(run|execute|launch|start)\b"
        ),
        re.IGNORECASE,
    )
    NEGATED_CREATE_PATTERN = re.compile(
        (
            r"\b(do\s+not|don't|dont|never|without)\b"
            r".{0,32}\b(create|add|write|push|send)\b"
            r".{0,32}\b(meta\s*stock|explorer|exploration)\b"
        ),
        re.IGNORECASE,
    )
    NEGATED_CAPTURE_PATTERN = re.compile(
        (
            r"\b(do\s+not|don't|dont|never|without)\b"
            r".{0,32}\b(capture|record|save|collect|store|persist|read|"
            r"give|show|return|provide)\b"
            r".{0,24}\b(result|results|matches|output)\b"
        ),
        re.IGNORECASE,
    )
    NEGATED_GENERATE_PATTERN = re.compile(
        r"\b(do\s+not|don't|dont|never)\b.{0,32}\b(generate|build|make)\b",
        re.IGNORECASE,
    )
    NEGATED_REVISE_PATTERN = re.compile(
        r"\b(do\s+not|don't|dont|never)\b.{0,32}\b(revise|change|modify)\b",
        re.IGNORECASE,
    )
    NEGATED_REPAIR_PATTERN = re.compile(
        r"\b(do\s+not|don't|dont|never)\b.{0,32}\brepair\b",
        re.IGNORECASE,
    )

    def resolve(
        self,
        *,
        user_message: str,
        arguments: dict[str, Any],
        context: ChatContext,
    ) -> NormalizedExplorerCommand:
        try:
            command = ExplorerCommandArguments.model_validate(
                arguments
            )
        except Exception as exc:
            raise CommandResolutionError(
                "The Explorer command arguments were incomplete or invalid."
            ) from exc

        metastock_action = command.metastock_action
        draft_only = bool(
            self.DRAFT_ONLY_PATTERN.search(user_message)
        )

        if (
            command.artifact_action is ArtifactAction.GENERATE
            and self.NEGATED_GENERATE_PATTERN.search(user_message)
        ):
            raise CommandResolutionError(
                "The request explicitly negates Explorer generation."
            )

        if (
            command.artifact_action is ArtifactAction.REVISE
            and self.NEGATED_REVISE_PATTERN.search(user_message)
        ):
            raise CommandResolutionError(
                "The request explicitly negates Explorer revision."
            )

        if (
            command.artifact_action is ArtifactAction.REPAIR
            and self.NEGATED_REPAIR_PATTERN.search(user_message)
        ):
            raise CommandResolutionError(
                "The request explicitly negates Explorer repair."
            )

        if (
            metastock_action
            in {
                MetaStockAction.RUN,
                MetaStockAction.CREATE_AND_RUN,
            }
            and self.NEGATED_RUN_PATTERN.search(user_message)
        ):
            raise CommandResolutionError(
                "The request explicitly says not to run the Explorer."
            )

        if (
            command.result_action is ResultAction.CAPTURE_NEW
            and self.NEGATED_CAPTURE_PATTERN.search(user_message)
        ):
            raise CommandResolutionError(
                "The request explicitly says not to capture results."
            )

        if (
            metastock_action
            in {
                MetaStockAction.CREATE,
                MetaStockAction.CREATE_AND_RUN,
            }
            and (
                draft_only
                or self.NEGATED_CREATE_PATTERN.search(user_message)
            )
        ):
            if command.artifact_action is ArtifactAction.GENERATE:
                metastock_action = MetaStockAction.NONE
            else:
                raise CommandResolutionError(
                    "The request explicitly says not to create the Explorer "
                    "in MetaStock."
                )

        # Product default: asking to generate/create an Explorer means creating
        # it in MetaStock as well. The model may omit this side effect only when
        # the current message explicitly asks for a draft or says not to create
        # it in MetaStock.
        if (
            command.artifact_action is ArtifactAction.GENERATE
            and metastock_action is MetaStockAction.NONE
            and not draft_only
        ):
            metastock_action = MetaStockAction.CREATE

        # Capturing a fresh result necessarily requires a run. This is a
        # dependency completion, not a lexical authorization gate.
        if command.result_action is ResultAction.CAPTURE_NEW:
            if metastock_action is MetaStockAction.NONE:
                metastock_action = MetaStockAction.RUN
            elif metastock_action is MetaStockAction.CREATE:
                metastock_action = MetaStockAction.CREATE_AND_RUN

        # A generated, revised, or repaired Explorer is a new durable artifact.
        # It cannot be selected in MetaStock until the workflow creates it.
        if (
            command.artifact_action
            in {
                ArtifactAction.GENERATE,
                ArtifactAction.REVISE,
                ArtifactAction.REPAIR,
            }
            and metastock_action is MetaStockAction.RUN
        ):
            metastock_action = MetaStockAction.CREATE_AND_RUN

        # The active durable Explorer may be known not to exist in MetaStock,
        # for example immediately after a revision-only turn. Running it must
        # first satisfy the creation precondition.
        if (
            command.artifact_action is ArtifactAction.NONE
            and metastock_action is MetaStockAction.RUN
            and context.active_explorer_metastock_state
            == MetaStockSyncState.NOT_CREATED.value
        ):
            metastock_action = MetaStockAction.CREATE_AND_RUN

        return NormalizedExplorerCommand(
            artifact_action=command.artifact_action,
            explorer_reference=command.explorer_reference,
            resolved_instruction=command.resolved_instruction,
            metastock_action=metastock_action,
            result_action=command.result_action,
            instruments=command.instruments,
        )
