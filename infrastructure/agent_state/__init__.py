"""Infrastructure for the dedicated agent-state database."""

from infrastructure.agent_state.checkpoints import (
    CheckpointBackend,
    CheckpointStoreProtocol,
    InMemoryCheckpointStore,
    PostgresCheckpointSettings,
    PostgresCheckpointStore,
    build_checkpoint_store,
)
from infrastructure.agent_state.conversation_repository import (
    ConversationNotFoundError,
    ConversationRepository,
)
from infrastructure.agent_state.database import (
    AgentStateConfigurationError,
    AgentStateDatabase,
    AgentStateDatabaseSettings,
)
from infrastructure.agent_state.history_factory import (
    LangChainHistoryFactory,
)
from infrastructure.agent_state.models import (
    ConversationRecord,
    StreamAppendResult,
    StreamStartResult,
    ToolCallRecord,
    ToolCallStatus,
    TurnStreamRecord,
    TurnStreamStatus,
)
from infrastructure.agent_state.tool_call_repository import (
    ToolCallNotFoundError,
    ToolCallRepository,
    ToolCallStateError,
)
from infrastructure.agent_state.turn_stream_repository import (
    TurnStreamConflictError,
    TurnStreamNotFoundError,
    TurnStreamRepository,
    TurnStreamSequenceError,
    TurnStreamStateError,
)

__all__ = [
    "AgentStateConfigurationError",
    "AgentStateDatabase",
    "AgentStateDatabaseSettings",
    "CheckpointBackend",
    "CheckpointStoreProtocol",
    "ConversationNotFoundError",
    "ConversationRecord",
    "ConversationRepository",
    "InMemoryCheckpointStore",
    "LangChainHistoryFactory",
    "PostgresCheckpointSettings",
    "PostgresCheckpointStore",
    "StreamAppendResult",
    "StreamStartResult",
    "ToolCallNotFoundError",
    "ToolCallRecord",
    "ToolCallRepository",
    "ToolCallStateError",
    "ToolCallStatus",
    "TurnStreamConflictError",
    "TurnStreamNotFoundError",
    "TurnStreamRecord",
    "TurnStreamRepository",
    "TurnStreamSequenceError",
    "TurnStreamStateError",
    "TurnStreamStatus",
    "build_checkpoint_store",
]
