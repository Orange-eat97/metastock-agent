from __future__ import annotations

import re
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from chat.models import ChatContext
from chat.routes import ChatRoute
from orchestration.decisions import (
    OrchestratorDecision,
    PlannerRequest,
    ToolManifestItem,
)
from services.explorer_name_resolver import (
    ExplorerNameAmbiguousError,
    ExplorerNameResolutionError,
    ExplorerNotFoundError,
)


ResolutionOutcome = Literal[
    "execute",
    "respond",
    "clarify",
    "workflow",
    "sequence",
]


class ExplorerReferenceResolverProtocol(
    Protocol
):
    def resolve_explorer_id(
        self,
        explorer_name: str,
    ) -> str:
        ...


class DecisionResolution(BaseModel):
    outcome: ResolutionOutcome
    route: ChatRoute

    tool_name: str | None = None
    workflow_name: str | None = None

    arguments: dict[str, Any] = Field(
        default_factory=dict
    )

    message: str | None = None
    decision_reason: str


class DecisionContextResolver:
    """
    Validate planner output and resolve user references before execution.

    Planner output cannot invent durable IDs, arbitrary tool arguments, or
    unapproved workflows.
    """

    EXPLORER_ID_TOOLS = {
        "repair_explorer",
        "revise_explorer",
        "get_explorer",
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
        "get_latest_explorer_result",
        "list_explorer_results",
    }

    RESULT_ID_TOOLS = {
        "get_explorer_result",
    }

    LOG_ID_TOOLS = {
        "get_rag_log",
    }

    ACTIVE_REFERENCE_WORDS = {
        "active",
        "current",
        "this",
        "it",
        "latest",
    }

    WORKFLOW_ROUTE_MAP = {
        "run_explorer": (
            ChatRoute.RUN_EXPLORER
        ),
        "run_and_capture": (
            ChatRoute.RUN_AND_READ_EXPLORER
        ),
        "create_run_and_capture": (
            ChatRoute
            .CREATE_RUN_AND_READ_EXPLORER
        ),
    }

    RUN_PATTERN = re.compile(
        r"\b(run|execute|launch|start)\b",
        re.IGNORECASE,
    )
    CAPTURE_PATTERN = re.compile(
        (
            r"\b(read|capture|scrape|store|"
            r"persist|get|show)\b.*"
            r"\b(result|results|matches)\b"
        ),
        re.IGNORECASE,
    )
    CREATE_PATTERN = re.compile(
        (
            r"\b(create|add|write|push|send)\b"
            r".*\b(explorer|exploration|metastock)\b"
        ),
        re.IGNORECASE,
    )
    NEGATED_ACTION_PATTERN = re.compile(
        (
            r"\b(do\s+not|don't|dont|never|without)\b"
            r".{0,24}\b(run|execute|launch|start|"
            r"create|add|write|push|send|read|capture|"
            r"scrape|store|persist)\b"
        ),
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        explorer_name_resolver: (
            ExplorerReferenceResolverProtocol
            | None
        ) = None,
    ) -> None:
        self._explorer_name_resolver = (
            explorer_name_resolver
        )

    def resolve(
        self,
        *,
        request: PlannerRequest,
        decision: OrchestratorDecision,
    ) -> DecisionResolution:
        if decision.action == "respond":
            return DecisionResolution(
                outcome="respond",
                route=ChatRoute.RESPOND,
                message=decision.response_message,
                decision_reason=(
                    decision.decision_reason
                ),
            )

        if decision.action == "clarify":
            return DecisionResolution(
                outcome="clarify",
                route=ChatRoute.CLARIFY,
                message=decision.response_message,
                decision_reason=(
                    decision.decision_reason
                ),
            )

        if decision.action == "workflow":
            return self._resolve_workflow(
                request=request,
                decision=decision,
            )

        return self._resolve_single_tool(
            request=request,
            decision=decision,
        )

    def _resolve_workflow(
        self,
        *,
        request: PlannerRequest,
        decision: OrchestratorDecision,
    ) -> DecisionResolution:
        
        decision_arguments = (
            decision.argument_map()
        )

        workflow_name = (
            decision.workflow_name
            or ""
        )

        if (
            workflow_name
            not in request.available_workflows
        ):
            return self._clarify(
                (
                    "The requested workflow is "
                    "not available."
                ),
                decision,
            )

        route = self.WORKFLOW_ROUTE_MAP.get(
            workflow_name
        )

        if route is None:
            return self._clarify(
                (
                    "The requested workflow has "
                    "no approved route."
                ),
                decision,
            )

        safety_error = (
            self._workflow_safety_error(
                workflow_name=workflow_name,
                user_message=(
                    request.user_message
                ),
            )
        )

        if safety_error:
            return self._clarify(
                safety_error,
                decision,
            )

        explorer_id, error = (
            self._resolve_explorer_id(
                explicit_value=(
                    decision_arguments.get(
                        "explorer_id"
                    )
                ),
                reference=(
                    decision.explorer_reference
                ),
                context=request.context,
            )
        )

        if error:
            return self._clarify(
                error,
                decision,
            )

        return DecisionResolution(
            outcome="workflow",
            route=route,
            workflow_name=workflow_name,
            arguments={
                "explorer_id": explorer_id
            },
            decision_reason=(
                decision.decision_reason
            ),
        )

    def _resolve_single_tool(
        self,
        *,
        request: PlannerRequest,
        decision: OrchestratorDecision,
    ) -> DecisionResolution:
        tool_name = (
            decision.tool_name
            or ""
        )

        decision_arguments = (
            decision.argument_map()
        )

        manifest = {
            item.name: item
            for item in request.tools
        }
        tool = manifest.get(tool_name)

        if tool is None:
            return self._clarify(
                (
                    "The requested capability is "
                    "not an approved tool."
                ),
                decision,
            )

        if not tool.enabled:
            return self._clarify(
                (
                    f"The `{tool_name}` capability "
                    "is currently disabled."
                ),
                decision,
            )

        try:
            route = ChatRoute(tool_name)
        except ValueError:
            return self._clarify(
                (
                    "The selected tool has no "
                    "approved chat route."
                ),
                decision,
            )

        arguments = self._filter_arguments(
            decision_arguments,
            tool,
        )

        if tool_name == "generate_explorer":
            arguments["user_query"] = (
                request.user_message
            )

        if tool_name == "repair_explorer":
            arguments[
                "repair_instruction"
            ] = request.user_message

        if tool_name == "revise_explorer":
            arguments[
                "revision_instruction"
            ] = request.user_message

        if (
            tool_name
            in self.EXPLORER_ID_TOOLS
        ):
            explorer_id, error = (
                self._resolve_explorer_id(
                    explicit_value=(
                        decision_arguments.get(
                            "explorer_id"
                        )
                    ),
                    reference=(
                        decision
                        .explorer_reference
                    ),
                    context=request.context,
                )
            )

            if error:
                return self._clarify(
                    error,
                    decision,
                )

            arguments["explorer_id"] = (
                explorer_id
            )

        if tool_name in self.RESULT_ID_TOOLS:
            result_id, error = (
                self._resolve_context_id(
                    explicit_value=(
                        decision_arguments.get(
                            "result_id"
                        )
                    ),
                    reference=(
                        decision.result_reference
                    ),
                    active_value=(
                        request.context
                        .active_result_id
                    ),
                    artifact_label="result",
                )
            )

            if error:
                return self._clarify(
                    error,
                    decision,
                )

            arguments["result_id"] = result_id

        if tool_name in self.LOG_ID_TOOLS:
            log_id, error = (
                self._resolve_context_id(
                    explicit_value=(
                        decision_arguments.get(
                            "log_id"
                        )
                    ),
                    reference=(
                        decision.log_reference
                    ),
                    active_value=(
                        request.context
                        .active_service_log_id
                    ),
                    artifact_label="RAG log",
                )
            )

            if error:
                return self._clarify(
                    error,
                    decision,
                )

            arguments["log_id"] = log_id

        self._apply_defaults(
            tool_name,
            arguments,
        )

        return DecisionResolution(
            outcome="execute",
            route=route,
            tool_name=tool_name,
            arguments=arguments,
            decision_reason=(
                decision.decision_reason
            ),
        )

    def _workflow_safety_error(
        self,
        *,
        workflow_name: str,
        user_message: str,
    ) -> str | None:
        if self.NEGATED_ACTION_PATTERN.search(
            user_message
        ):
            return (
                "The request negates an action, "
                "so no MetaStock workflow was run."
            )

        if not self.RUN_PATTERN.search(
            user_message
        ):
            return (
                "Running MetaStock requires an "
                "explicit run or execute request."
            )

        if workflow_name in {
            "run_and_capture",
            "create_run_and_capture",
        } and not self.CAPTURE_PATTERN.search(
            user_message
        ):
            return (
                "Capturing results requires an "
                "explicit result-reading request."
            )

        if (
            workflow_name
            == "create_run_and_capture"
            and not self.CREATE_PATTERN.search(
                user_message
            )
        ):
            return (
                "Creating the Explorer in MetaStock "
                "requires an explicit create request."
            )

        return None

    def _resolve_explorer_id(
        self,
        *,
        explicit_value: Any,
        reference: str | None,
        context: ChatContext,
    ) -> tuple[str | None, str | None]:
        candidates = [
            explicit_value,
            reference,
        ]

        for candidate in candidates:
            text = self._clean_text(
                candidate
            )

            if not text:
                continue

            if self._is_active_reference(text):
                return self._validate_active_id(
                    context.active_explorer_id,
                    artifact_label="Explorer",
                )

            canonical = self._canonical_uuid(
                text
            )

            if canonical is not None:
                return canonical, None

            if (
                self._explorer_name_resolver
                is None
            ):
                return (
                    None,
                    (
                        "Provide an exact Explorer "
                        "UUID, or configure exact-name "
                        "resolution."
                    ),
                )

            try:
                resolved = (
                    self._explorer_name_resolver
                    .resolve_explorer_id(text)
                )
            except ExplorerNotFoundError:
                return (
                    None,
                    (
                        "No stored Explorer has that "
                        "exact name."
                    ),
                )
            except ExplorerNameAmbiguousError:
                return (
                    None,
                    (
                        "More than one stored Explorer "
                        "has that exact name. Provide "
                        "its UUID."
                    ),
                )
            except (
                ExplorerNameResolutionError,
                ValueError,
                RuntimeError,
            ):
                return (
                    None,
                    (
                        "The Explorer reference could "
                        "not be resolved safely."
                    ),
                )

            canonical = self._canonical_uuid(
                resolved
            )

            if canonical is None:
                return (
                    None,
                    (
                        "Explorer-name resolution "
                        "returned an invalid UUID."
                    ),
                )

            return canonical, None

        return self._validate_active_id(
            context.active_explorer_id,
            artifact_label="Explorer",
        )

    def _resolve_context_id(
        self,
        *,
        explicit_value: Any,
        reference: str | None,
        active_value: str | None,
        artifact_label: str,
    ) -> tuple[str | None, str | None]:
        for candidate in (
            explicit_value,
            reference,
        ):
            text = self._clean_text(
                candidate
            )

            if not text:
                continue

            if self._is_active_reference(text):
                return self._validate_active_id(
                    active_value,
                    artifact_label=(
                        artifact_label
                    ),
                )

            canonical = self._canonical_uuid(
                text
            )

            if canonical is None:
                return (
                    None,
                    (
                        f"Provide the exact "
                        f"{artifact_label} UUID."
                    ),
                )

            return canonical, None

        return self._validate_active_id(
            active_value,
            artifact_label=artifact_label,
        )

    def _validate_active_id(
        self,
        value: str | None,
        *,
        artifact_label: str,
    ) -> tuple[str | None, str | None]:
        if not value:
            return (
                None,
                (
                    f"There is no active "
                    f"{artifact_label} in this "
                    "conversation."
                ),
            )

        canonical = self._canonical_uuid(
            value
        )

        if canonical is None:
            return (
                None,
                (
                    f"The active {artifact_label} "
                    "ID is invalid."
                ),
            )

        return canonical, None

    @staticmethod
    def _filter_arguments(
        raw_arguments: dict[str, Any],
        tool: ToolManifestItem,
    ) -> dict[str, Any]:
        properties = (
            tool.input_schema.get(
                "properties",
                {}
            )
        )

        if not isinstance(
            properties,
            dict,
        ):
            return {}

        allowed = set(properties)

        return {
            key: value
            for key, value
            in raw_arguments.items()
            if key in allowed
        }

    @staticmethod
    def _apply_defaults(
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        if tool_name in {
            "create_explorer_in_metastock",
            "select_explorer_in_metastock",
            "run_selected_explorer_in_metastock",
        }:
            arguments.setdefault(
                "instruments",
                "all",
            )

        if (
            tool_name
            == "read_metastock_explorer_results"
        ):
            arguments.setdefault(
                "close_after_read",
                True,
            )

        if tool_name == "list_explorer_results":
            arguments.setdefault(
                "limit",
                20,
            )

    @classmethod
    def _is_active_reference(
        cls,
        value: str,
    ) -> bool:
        return (
            value.strip().casefold()
            in cls.ACTIVE_REFERENCE_WORDS
        )

    @staticmethod
    def _canonical_uuid(
        value: Any,
    ) -> str | None:
        text = str(value or "").strip()

        if not text:
            return None

        try:
            return str(UUID(text))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clean_text(
        value: Any,
    ) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _clarify(
        message: str,
        decision: OrchestratorDecision,
    ) -> DecisionResolution:
        return DecisionResolution(
            outcome="clarify",
            route=ChatRoute.CLARIFY,
            message=message,
            decision_reason=(
                decision.decision_reason
            ),
        )
