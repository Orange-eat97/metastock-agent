from __future__ import annotations

import sys

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from .backend_port import ConversationBackendPort
from .demo_backend import DemoConversationBackend
from .models import (
    ChatMessageViewModel,
    ConversationSnapshot,
    ExplorerEditPatch,
    ExplorerViewModel,
    TurnProgress,
    TurnResponse,
)
from .theme import BG, apply_light_theme
from .widgets import (
    ChatArea,
    ConversationSidebar,
)
from .workers import (
    ConversationExportWorker,
    ExplorerSaveWorker,
    TurnWorker,
)


class MainWindow(QMainWindow):
    """Thin two-panel shell matching the supplied light chatbox design."""

    def __init__(
        self,
        backend: ConversationBackendPort | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend or DemoConversationBackend()
        self._active_conversation_id: str | None = None
        self._turn_thread: QThread | None = None
        self._turn_worker: TurnWorker | None = None

        self.setWindowTitle("MetaStock Agent")
        self.resize(1080, 720)
        self.setMinimumSize(820, 600)
        self.setStyleSheet(f"background:{BG};")

        central = QWidget()
        central.setStyleSheet(f"background:{BG};")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.sidebar = ConversationSidebar()
        self.chat = ChatArea()
        root.addWidget(self.sidebar)
        root.addWidget(self.chat, 1)

        self.sidebar.new_requested.connect(self._create_conversation)
        self.sidebar.conversation_selected.connect(self._load_conversation)
        self.sidebar.rename_requested.connect(self._rename_conversation)
        self.sidebar.export_requested.connect(self._export_conversation)
        self.sidebar.clear_requested.connect(self._clear_conversation)
        self.sidebar.delete_requested.connect(self._delete_conversation)
        self.chat.send_requested.connect(self._start_turn)
        self.chat.clarification_chosen.connect(self._start_turn)
        self.chat.explorer_save_requested.connect(self._save_explorer)

        self._reload_sidebar()
        summaries = self._backend.list_conversations()
        if summaries:
            self._load_conversation(summaries[0].conversation_id)
        else:
            self._create_conversation()

    def _reload_sidebar(self, selected_id: str | None = None) -> None:
        self.sidebar.set_conversations(
            self._backend.list_conversations(),
            selected_id or self._active_conversation_id,
        )

    def _render_snapshot(
        self,
        snapshot: ConversationSnapshot,
        *,
        resumed: bool = True,
    ) -> None:
        self._active_conversation_id = snapshot.conversation_id
        self.chat.set_title(snapshot.title)
        self.chat.clear_messages()
        for message in snapshot.messages:
            self.chat.add_message(message, scroll=False)
        self.chat.scroll_to_bottom_deferred()
        self.chat.status_bar.set_progress(
            "resumed" if resumed and snapshot.messages else snapshot.status
        )
        self._reload_sidebar(snapshot.conversation_id)

    def _create_conversation(self) -> None:
        if self._turn_thread is not None:
            return
        try:
            snapshot = self._backend.create_conversation()
        except Exception as exc:
            self._show_error("Could not create conversation", str(exc))
            return
        self._render_snapshot(snapshot, resumed=False)

    def _load_conversation(self, conversation_id: str) -> None:
        if self._turn_thread is not None:
            return
        try:
            snapshot = self._backend.load_conversation(conversation_id)
        except Exception as exc:
            self._show_error("Could not load conversation", str(exc))
            return
        self._render_snapshot(snapshot)

    def _rename_conversation(self, conversation_id: str, title: str) -> None:
        if self._turn_thread is not None:
            return
        try:
            self._backend.rename_conversation(conversation_id, title)
            if conversation_id == self._active_conversation_id:
                self.chat.set_title(title)
            self._reload_sidebar(conversation_id)
        except Exception as exc:
            self._show_error("Could not rename conversation", str(exc))

    def _clear_conversation(self, conversation_id: str) -> None:
        if self._turn_thread is not None:
            return
        if not self._confirm(
            "Clear messages",
            "Clear all messages and active context in this conversation?",
        ):
            return
        try:
            snapshot = self._backend.clear_conversation(conversation_id)
            self._render_snapshot(snapshot, resumed=False)
        except Exception as exc:
            self._show_error("Could not clear conversation", str(exc))

    def _delete_conversation(self, conversation_id: str) -> None:
        if self._turn_thread is not None:
            return
        if not self._confirm(
            "Delete conversation",
            "Delete this conversation? This cannot be undone.",
        ):
            return
        try:
            self._backend.delete_conversation(conversation_id)
            self._active_conversation_id = None
            summaries = self._backend.list_conversations()
            if summaries:
                self._load_conversation(summaries[0].conversation_id)
            else:
                self._create_conversation()
        except Exception as exc:
            self._show_error("Could not delete conversation", str(exc))

    def _save_explorer(
        self,
        explorer_id: str,
        expected_version: int,
        patch: ExplorerEditPatch,
    ) -> None:
        if self._turn_thread is not None or not self._active_conversation_id:
            return
        self.chat.set_running(True)
        self.sidebar.set_running(True)
        self.chat.status_bar.set_progress(
            TurnProgress("processing", "Saving Explorer changes…")
        )
        worker = ExplorerSaveWorker(
            self._backend,
            self._active_conversation_id,
            explorer_id,
            expected_version,
            patch,
        )
        self._start_background_worker(
            worker,
            self._on_explorer_saved,
            lambda message: self._on_operation_failed(
                "Could not save Explorer",
                message,
            ),
        )

    def _on_explorer_saved(
        self,
        payload: tuple[ExplorerViewModel, ConversationSnapshot],
    ) -> None:
        _explorer, snapshot = payload
        if snapshot.conversation_id != self._active_conversation_id:
            return
        self._render_snapshot(snapshot, resumed=False)
        self.chat.status_bar.set_progress(
            TurnProgress("completed", "Explorer changes saved")
        )

    def _export_conversation(self, conversation_id: str) -> None:
        if self._turn_thread is not None:
            return
        title = next(
            (
                item.title
                for item in self._backend.list_conversations()
                if item.conversation_id == conversation_id
            ),
            "conversation",
        )
        safe_title = "".join(
            char if char.isalnum() or char in {"-", "_"} else "-"
            for char in title.strip()
        ).strip("-") or "conversation"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export conversation session",
            f"{safe_title}.md",
            "Markdown files (*.md)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        self.chat.set_running(True)
        self.sidebar.set_running(True)
        self.chat.status_bar.set_progress(
            TurnProgress("processing", "Exporting conversation logs…")
        )
        worker = ConversationExportWorker(
            self._backend,
            conversation_id,
            path,
        )
        self._start_background_worker(
            worker,
            self._on_conversation_exported,
            lambda message: self._on_operation_failed(
                "Could not export conversation",
                message,
            ),
        )

    def _on_conversation_exported(self, path: str) -> None:
        self.chat.status_bar.set_progress(
            TurnProgress("completed", "Conversation exported")
        )
        QMessageBox.information(
            self,
            "Conversation exported",
            f"Saved the deterministic session summary and transcript to:\n{path}",
        )

    def _on_operation_failed(self, title: str, message: str) -> None:
        self.chat.status_bar.set_progress("failed")
        self._show_error(title, message)

    def _start_background_worker(
        self,
        worker: object,
        completed_slot: object,
        failed_slot: object,
    ) -> None:
        thread = QThread(self)
        self._turn_thread = thread
        self._turn_worker = worker  # type: ignore[assignment]
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(completed_slot)
        worker.failed.connect(failed_slot)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_turn)
        thread.start()

    def _start_turn(self, text: str) -> None:
        if self._turn_thread is not None or not self._active_conversation_id:
            return

        conversation_id = self._active_conversation_id
        self.chat.add_message(
            ChatMessageViewModel(
                role="user",
                text=text,
                created_at="Now",
            )
        )
        self.chat.set_running(True)
        self.sidebar.set_running(True)
        self.chat.status_bar.set_progress(
            TurnProgress("processing", "Processing your request…")
        )

        worker = TurnWorker(
            self._backend,
            conversation_id,
            text,
        )
        worker.progress.connect(self._on_turn_progress)
        self._start_background_worker(
            worker,
            self._on_turn_completed,
            self._on_turn_failed,
        )

    def _on_turn_progress(self, progress: TurnProgress) -> None:
        self.chat.status_bar.set_progress(progress)

    def _on_turn_completed(self, response: TurnResponse) -> None:
        if response.conversation_id != self._active_conversation_id:
            return
        for message in response.messages:
            self.chat.add_message(message)
        self.chat.status_bar.set_progress(
            TurnProgress("resumed", "Recovered the completed turn")
            if response.replayed
            else response.final_status
        )

    def _on_turn_failed(self, message: str) -> None:
        self.chat.status_bar.set_progress("failed")
        self.chat.add_message(
            ChatMessageViewModel(
                role="assistant",
                text=f"The turn could not be completed: {message}",
                created_at="Now",
            )
        )

    def _cleanup_turn(self) -> None:
        if self._turn_thread is not None:
            self._turn_thread.deleteLater()
        self._turn_thread = None
        self._turn_worker = None
        self.chat.set_running(False)
        self.sidebar.set_running(False)
        self._reload_sidebar(self._active_conversation_id)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._turn_thread is not None and self._turn_thread.isRunning():
            event.ignore()
            self._show_error(
                "Turn in progress",
                "Wait for the current turn to finish before closing the application.",
            )
            return
        super().closeEvent(event)

    def _confirm(self, title: str, message: str) -> bool:
        return (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)



def run(
    backend: ConversationBackendPort | None = None,
    *,
    application: QApplication | None = None,
) -> int:
    app = application or QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_light_theme(app)
    window = MainWindow(backend=backend)
    window.show()
    return app.exec()
