from __future__ import annotations

from typing import Any
from uuid import UUID

from chat.models import ChatContext
from chat.routes import ChatRoute
from orchestration.command_resolution import (
    ArtifactAction,
    CommandResolutionError,
    MetaStockAction,
    SemanticCommandResolver,
)
from orchestration.context_resolver import (
    DecisionResolution,
    ExplorerReferenceResolverProtocol,
)
from orchestration.conversation_actions import (
    COMMAND_ACTION_NAME,
    SEQUENCE_ACTION_NAME,
    ConversationActionDefinition,
    ConversationModelRequest,
    ConversationModelResponse,
)
from orchestration.sequence_workflows import (
    ExplorerSequenceRequest,
    ResolvedExplorerSequenceRequest,
    ResolvedExplorerSequenceStage,
)
from services.explorer_name_resolver import (
    ExplorerNameAmbiguousError,
    ExplorerNameResolutionError,
    ExplorerNotFoundError,
)


class ConversationActionPolicy:
    """
    Validate an optional model action and resolve durable references.

    Explorer lifecycle commands are normalized as independent semantic
    dimensions before a deterministic workflow is compiled. Narrow verb regexes
    are no longer used as the primary command resolver.
    """

    EXPLORER_ID_TOOLS = {
        "get_explorer",
        "get_latest_explorer_result",
        "list_explorer_results",
    }
    RESULT_ID_TOOLS = {
        "get_explorer_result",
    }
    LOG_ID_TOOLS = {
        "get_rag_log",
    }
    PASSTHROUGH_TOOLS = {
        "prepare_explorer_upload",
        "get_explorer_upload_template",
        "upload_explorer",
    }
    ACTIVE_REFERENCE_WORDS = {
        "active",
        "current",
        "this",
        "it",
        "latest",
    }

    def __init__(
        self,
        *,
        registry: Any,
        explorer_name_resolver: (
            ExplorerReferenceResolverProtocol | None
        ) = None,
        command_resolver: (
            SemanticCommandResolver | None
        ) = None,
    ) -> None:
        self._registry = registry
        self._explorer_name_resolver = explorer_name_resolver
        self._command_resolver = (
            command_resolver
            or SemanticCommandResolver()
        )

    def resolve(
        self,
        *,
        request: ConversationModelRequest,
        response: ConversationModelResponse,
    ) -> DecisionResolution:
        call = response.action_call

        if call is None:
            return DecisionResolution(
                outcome="respond",
                route=ChatRoute.RESPOND,
                message=(
                    response.assistant_message
                    or "I could not form a complete response."
                ),
                decision_reason=(
                    "The conversation model selected no action."
                ),
            )

        catalogue = {
            action.name: action
            for action in request.actions
        }
        action = catalogue.get(call.name)

        if action is None:
            return self._clarify(
                (
                    "The requested action is not an approved "
                    "conversation capability."
                ),
                call.name,
            )

        if (
            action.kind == "command"
            and action.name == COMMAND_ACTION_NAME
        ):
            return self._resolve_command(
                user_message=request.user_message,
                context=request.context,
                arguments=call.arguments,
            )

        if (
            action.kind == "command"
            and action.name == SEQUENCE_ACTION_NAME
        ):
            return self._resolve_sequence(
                context=request.context,
                arguments=call.arguments,
            )

        return self._resolve_tool(
            context=request.context,
            action=action,
            arguments=call.arguments,
        )

    def _resolve_command(
        self,
        *,
        user_message: str,
        context: ChatContext,
        arguments: dict[str, Any],
    ) -> DecisionResolution:
        try:
            command = self._command_resolver.resolve(
                user_message=user_message,
                arguments=arguments,
                context=context,
            )
        except CommandResolutionError as exc:
            return self._clarify(
                str(exc),
                COMMAND_ACTION_NAME,
            )

        source_explorer_id: str | None = None

        if command.needs_source_explorer:
            source_explorer_id, error = (
                self._resolve_explorer_id(
                    reference=(
                        command.explorer_reference
                    ),
                    context=context,
                )
            )

            external_name = self._clean_text(
                command.explorer_reference
            )
            can_use_external_metastock_name = (
                error
                == "No stored Explorer has that exact name."
                and command.artifact_action
                is ArtifactAction.NONE
                and command.metastock_action
                in {
                    MetaStockAction.RUN,
                    MetaStockAction.CREATE_AND_RUN,
                }
                and external_name is not None
                and not self._is_active_reference(
                    external_name
                )
            )

            if can_use_external_metastock_name:
                source_explorer_id = (
                    self._external_metastock_reference(
                        external_name
                    )
                )
                # Explicit unstored name means select/run an Explorer
                # that already exists in MetaStock. Do not create it.
                command = command.model_copy(
                    update={
                        "metastock_action": (
                            MetaStockAction.RUN
                        )
                    }
                )
                error = None

            if error:
                return self._clarify(
                    error,
                    COMMAND_ACTION_NAME,
                )

        resolution_arguments: dict[str, Any] = {
            "command": command.model_dump(
                mode="json"
            ),
        }

        if source_explorer_id:
            resolution_arguments[
                "explorer_id"
            ] = source_explorer_id

        return DecisionResolution(
            outcome="workflow",
            route=command.route,
            workflow_name=command.workflow_name,
            arguments=resolution_arguments,
            decision_reason=(
                "The semantic command resolver normalized "
                f"the request to {command.workflow_name}."
            ),
        )

    def _resolve_sequence(
        self,
        *,
        context: ChatContext,
        arguments: dict[str, Any],
    ) -> DecisionResolution:
        try:
            request = ExplorerSequenceRequest.model_validate(
                arguments
            )
        except Exception:
            return self._clarify(
                (
                    "The Explorer sequence is incomplete or "
                    "invalid. Provide one to ten stages, each "
                    "with an Explorer reference and its own "
                    "instrument selection."
                ),
                SEQUENCE_ACTION_NAME,
            )

        resolved_stages: list[
            ResolvedExplorerSequenceStage
        ] = []

        for index, stage in enumerate(request.stages):
            explorer_id, error = self._resolve_explorer_id(
                reference=stage.explorer_reference,
                context=context,
            )

            resolved_create_in_metastock = (
                stage.create_in_metastock
            )
            external_name = self._clean_text(
                stage.explorer_reference
            )

            can_use_external_metastock_name = (
                error
                == "No stored Explorer has that exact name."
                and external_name is not None
                and not self._is_active_reference(
                    external_name
                )
            )

            if can_use_external_metastock_name:
                explorer_id = (
                    self._external_metastock_reference(
                        external_name
                    )
                )

                # An unstored Explorer has no formula or
                # columns available to the Agent for creation.
                # Treat it as an existing MetaStock Explorer
                # and let the MetaStock selector determine
                # whether the exact name exists.
                resolved_create_in_metastock = False
                error = None

            if error or not explorer_id:
                return self._clarify(
                    (
                        f"Sequence stage {index + 1} could "
                        f"not resolve Explorer "
                        f"{stage.explorer_reference!r}: "
                        f"{error or 'missing Explorer ID'}"
                    ),
                    SEQUENCE_ACTION_NAME,
                )

            resolved_stages.append(
                ResolvedExplorerSequenceStage(
                    stage_index=index,
                    explorer_id=explorer_id,
                    explorer_reference=(
                        stage.explorer_reference
                    ),
                    instruments=stage.instruments,
                    create_in_metastock=(
                        resolved_create_in_metastock
                    ),
                )
            )

        resolved = ResolvedExplorerSequenceRequest(
            stages=resolved_stages,
            stop_on_failure=True,
        )

        return DecisionResolution(
            outcome="sequence",
            route=ChatRoute.EXECUTE_EXPLORER_SEQUENCE,
            workflow_name=SEQUENCE_ACTION_NAME,
            arguments={
                "sequence": resolved.model_dump(
                    mode="json"
                ),
            },
            decision_reason=(
                "The conversation model requested a "
                "validated multi-Explorer sequence."
            ),
        )
  
    def _resolve_tool(
        self,
        *,
        context: ChatContext,
        action: ConversationActionDefinition,
        arguments: dict[str, Any],
    ) -> DecisionResolution:
        try:
            tool = self._registry.get_tool(action.name)
        except (ValueError, RuntimeError):
            return self._clarify(
                "The selected tool is not registered.",
                action.name,
            )

        exposure = getattr(tool, "exposure", None)
        exposure_value = getattr(
            exposure,
            "value",
            exposure,
        )

        if exposure_value != "conversation":
            return self._clarify(
                (
                    "That capability is internal to an approved workflow "
                    "and cannot be selected directly."
                ),
                action.name,
            )

        if not bool(getattr(tool, "enabled", True)):
            return self._clarify(
                f"The `{action.name}` capability is currently disabled.",
                action.name,
            )

        try:
            route = ChatRoute(action.name)
        except ValueError:
            return self._clarify(
                "The selected tool has no approved chat route.",
                action.name,
            )

        resolved_arguments: dict[str, Any] = (
            dict(arguments)
            if action.name in self.PASSTHROUGH_TOOLS
            else {}
        )

        if action.name in self.EXPLORER_ID_TOOLS:
            explorer_id, error = self._resolve_explorer_id(
                reference=arguments.get("explorer_reference"),
                context=context,
            )

            if error:
                return self._clarify(error, action.name)

            resolved_arguments["explorer_id"] = explorer_id

        if action.name in self.RESULT_ID_TOOLS:
            result_id, error = self._resolve_context_id(
                reference=arguments.get("result_reference"),
                active_value=context.active_result_id,
                artifact_label="result",
            )

            if error:
                return self._clarify(error, action.name)

            resolved_arguments["result_id"] = result_id

        if action.name in self.LOG_ID_TOOLS:
            log_id, error = self._resolve_context_id(
                reference=arguments.get("log_reference"),
                active_value=context.active_service_log_id,
                artifact_label="RAG log",
            )

            if error:
                return self._clarify(error, action.name)

            resolved_arguments["log_id"] = log_id

        if action.name == "list_explorer_results":
            limit = arguments.get("limit", 20)
            try:
                resolved_arguments["limit"] = max(
                    1,
                    min(100, int(limit)),
                )
            except (TypeError, ValueError):
                resolved_arguments["limit"] = 20

        return DecisionResolution(
            outcome="execute",
            route=route,
            tool_name=action.name,
            arguments=resolved_arguments,
            decision_reason=(
                "The conversation model selected "
                f"conversation tool {action.name}."
            ),
        )

    def _resolve_explorer_id(
        self,
        *,
        reference: Any,
        context: ChatContext,
    ) -> tuple[str | None, str | None]:
        text = self._clean_text(reference)

        if not text or self._is_active_reference(text):
            return self._validate_active_id(
                context.active_explorer_id,
                artifact_label="Explorer",
            )

        canonical = self._canonical_uuid(text)

        if canonical is not None:
            return canonical, None

        if self._explorer_name_resolver is None:
            return (
                None,
                (
                    "Provide an exact Explorer UUID, or configure "
                    "exact-name resolution."
                ),
            )

        try:
            resolved = (
                self._explorer_name_resolver
                .resolve_explorer_id(text)
            )
        except ExplorerNotFoundError:
            return None, "No stored Explorer has that exact name."
        except ExplorerNameAmbiguousError:
            return (
                None,
                (
                    "More than one stored Explorer has that exact name. "
                    "Provide its UUID."
                ),
            )
        except (
            ExplorerNameResolutionError,
            ValueError,
            RuntimeError,
        ):
            return (
                None,
                "The Explorer reference could not be resolved safely.",
            )

        canonical = self._canonical_uuid(resolved)

        if canonical is None:
            return (
                None,
                "Explorer-name resolution returned an invalid UUID.",
            )

        return canonical, None

    def _resolve_context_id(
        self,
        *,
        reference: Any,
        active_value: str | None,
        artifact_label: str,
    ) -> tuple[str | None, str | None]:
        text = self._clean_text(reference)

        if not text or self._is_active_reference(text):
            return self._validate_active_id(
                active_value,
                artifact_label=artifact_label,
            )

        canonical = self._canonical_uuid(text)

        if canonical is None:
            return (
                None,
                f"Provide the exact {artifact_label} UUID.",
            )

        return canonical, None

    @staticmethod
    def _validate_active_id(
        value: str | None,
        *,
        artifact_label: str,
    ) -> tuple[str | None, str | None]:
        if not value:
            return (
                None,
                (
                    f"There is no active {artifact_label} in this "
                    "conversation."
                ),
            )

        canonical = ConversationActionPolicy._canonical_uuid(value)

        if canonical is None:
            return (
                None,
                f"The active {artifact_label} ID is invalid.",
            )

        return canonical, None

    @classmethod
    def _is_active_reference(cls, value: str) -> bool:
        return (
            value.strip().casefold()
            in cls.ACTIVE_REFERENCE_WORDS
        )

    @staticmethod
    def _external_metastock_reference(
        explorer_name: str,
    ) -> str:
        cleaned = str(explorer_name or "").strip()

        if not cleaned:
            raise ValueError(
                "External MetaStock Explorer name is required."
            )

        return f"metastock-name:{cleaned}"

    @staticmethod
    def _canonical_uuid(value: Any) -> str | None:
        text = str(value or "").strip()

        if not text:
            return None

        try:
            return str(UUID(text))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _clarify(
        message: str,
        action_name: str,
    ) -> DecisionResolution:
        return DecisionResolution(
            outcome="clarify",
            route=ChatRoute.CLARIFY,
            message=message,
            decision_reason=(
                "Action policy rejected or could not resolve "
                f"{action_name}."
            ),
        )
