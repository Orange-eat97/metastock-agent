from __future__ import annotations

import pytest

from infrastructure.agent_state.checkpoints import (
    CheckpointBackend,
    InMemoryCheckpointStore,
    build_checkpoint_store,
)


def test_memory_factory() -> None:
    store = build_checkpoint_store(
        backend=CheckpointBackend.MEMORY
    )

    assert isinstance(
        store,
        InMemoryCheckpointStore,
    )


def test_postgres_factory_requires_settings() -> None:
    with pytest.raises(
        ValueError,
        match="agent_state_settings",
    ):
        build_checkpoint_store(
            backend=(
                CheckpointBackend.POSTGRES
            )
        )


def test_memory_delete_thread_is_safe_when_empty() -> None:
    store = InMemoryCheckpointStore()

    store.delete_thread("missing-thread")
