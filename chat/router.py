from __future__ import annotations

import re
from dataclasses import dataclass

from chat.routes import ChatRoute


@dataclass(frozen=True)
class RouteRule:
    route: ChatRoute
    patterns: tuple[re.Pattern[str], ...]


class DeterministicChatRouter:
    """
    Explicit router for the local chat harness.

    Create, select, and run are separate tool-level service boundaries.
    A high-level user request like "run the current Explorer" is routed to a
    controller-level composition route, where the controller calls select and
    run-selected separately.
    """

    def __init__(self) -> None:
        flags = re.IGNORECASE

        self._rules = (
            RouteRule(
                route=ChatRoute.GET_RAG_LOG,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(show|get|open|inspect|view)\b.*\b(rag|retrieval|service)\s*log\b",
                        r"\b(debug|diagnostic)\s*log\b",
                        r"\bwhy\b.*\b(retriev|rag)\w*\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.REPAIR_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(repair|fix|correct)\b.*\b(explorer|formula|syntax|validation)\b",
                        r"\b(syntax|validation)\s*(error|failure|failed|issue)\b",
                        r"\bmake\b.*\b(valid|runnable)\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.RUN_AND_READ_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(select|load|open)\b.*\b(current|this)?\s*(explorer|exploration)\b.*\b(run|execute|launch|start)\b.*\b(read|capture|scrape|store|persist)\b.*\b(result|results|matches)\b",
                        r"\b(run|execute|launch|start)\b.*\b(current|this)?\s*(explorer|exploration)\b.*\b(read|capture|scrape|store|persist)\b.*\b(result|results|matches)\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.READ_METASTOCK_RESULTS,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(read|capture|scrape|store|persist)\b.*\b(result|results|matches|matched instruments)\b",
                        r"\b(show|get)\b.*\b(metastock|explorer)\s*results\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.CREATE_METASTOCK_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(create|add|write)\b.*\b(explorer|exploration)\b.*\b(metastock)\b",
                        r"\b(push|send)\b.*\b(current explorer)\b.*\b(metastock)\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.SELECT_METASTOCK_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(select|choose|load|open)\b.*\b(current|this|existing)?\s*(explorer|exploration)\b.*\b(metastock)?\b",
                        r"\bselect\b.*\binstruments?\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.RUN_SELECTED_METASTOCK_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(run|execute|launch|start)\b.*\b(selected)\b.*\b(explorer|exploration)\b",
                        r"\bstart\b.*\b(selected|loaded)\b.*\bexplorer\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.RUN_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(run|execute|launch|start)\b.*\b(current|this|existing)?\s*(explorer|exploration)\b.*\b(metastock)?\b",
                        r"\bexplore\s+now\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.GET_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(show|get|inspect|view)\b.*\bexplorer\b",
                        r"\bcurrent\s+explorer\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.GENERATE_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(generate|create|build|draft|make)\b.*\b(explorer|exploration|scan|screener)\b",
                        r"\b(find|screen|scan)\s+(stocks?|securities|shares)\b",
                        r"^\s*find\s+stocks?\s+where\b",
                    )
                ),
            ),
        )

    def route(self, user_message: str) -> ChatRoute:
        normalized = " ".join(user_message.strip().split())

        for rule in self._rules:
            if any(pattern.search(normalized) for pattern in rule.patterns):
                return rule.route

        return ChatRoute.FALLBACK
