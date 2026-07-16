from __future__ import annotations

import sys

from application.composition import OrchestratorMode
from infrastructure.agent_state import CheckpointBackend
from scripts.chat_harness import parse_args


def test_harness_defaults_to_langgraph_and_postgres(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "AGENT_ORCHESTRATOR",
        raising=False,
    )
    monkeypatch.delenv(
        "AGENT_CHECKPOINT_BACKEND",
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["chat_harness"],
    )

    args = parse_args()

    assert args.orchestrator == (
        OrchestratorMode.LANGGRAPH.value
    )
    assert args.checkpoint_backend == (
        CheckpointBackend.POSTGRES.value
    )


def test_harness_accepts_legacy_rollback(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chat_harness",
            "--orchestrator",
            "legacy",
            "--checkpoint-backend",
            "memory",
        ],
    )

    args = parse_args()

    assert args.orchestrator == "legacy"
    assert args.checkpoint_backend == "memory"
