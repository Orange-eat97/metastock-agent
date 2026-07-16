from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from .backend_port import ConversationBackendPort
from .models import TurnProgress


class TurnWorker(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        backend: ConversationBackendPort,
        conversation_id: str,
        user_text: str,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._conversation_id = conversation_id
        self._user_text = user_text

    @Slot()
    def run(self) -> None:
        try:
            response = self._backend.execute_turn(
                self._conversation_id,
                self._user_text,
                self._emit_progress,
            )
            self.completed.emit(response)
        except Exception as exc:  # UI boundary: convert runtime failures to a signal.
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def _emit_progress(self, progress: TurnProgress) -> None:
        self.progress.emit(progress)
