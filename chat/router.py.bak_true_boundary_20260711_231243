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
    Small, explicit Milestone 3 router.

    It does not use an LLM, LangGraph, persistence, or direct service access.
    Route precedence is intentional:
        log -> repair -> run -> get -> generate -> fallback
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
                route=ChatRoute.RUN_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(run|execute|launch)\b.*\b(explorer|exploration|metastock)\b",
                        r"\bexplore\s+now\b",
                    )
                ),
            ),
            RouteRule(
                route=ChatRoute.GET_EXPLORER,
                patterns=tuple(
                    re.compile(pattern, flags)
                    for pattern in (
                        r"\b(show|get|open|inspect|view)\b.*\bexplorer\b",
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
