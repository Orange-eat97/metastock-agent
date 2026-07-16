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


class ExplorerSaveWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        backend: ConversationBackendPort,
        conversation_id: str,
        explorer_id: str,
        expected_version: int,
        patch: object,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._conversation_id = conversation_id
        self._explorer_id = explorer_id
        self._expected_version = expected_version
        self._patch = patch

    @Slot()
    def run(self) -> None:
        try:
            explorer = self._backend.save_explorer_edits(
                self._explorer_id,
                self._expected_version,
                self._patch,
            )
            snapshot = self._backend.load_conversation(
                self._conversation_id
            )
            self.completed.emit((explorer, snapshot))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class ConversationExportWorker(QObject):
    completed = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        backend: ConversationBackendPort,
        conversation_id: str,
        destination_path: str,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._conversation_id = conversation_id
        self._destination_path = destination_path

    @Slot()
    def run(self) -> None:
        try:
            path = self._backend.export_conversation_markdown(
                self._conversation_id,
                self._destination_path,
            )
            self.completed.emit(path)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
