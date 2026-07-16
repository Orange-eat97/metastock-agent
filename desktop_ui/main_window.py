from __future__ import annotations

import sys

from PySide6.QtCore import QThread
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
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
    TurnProgress,
    TurnResponse,
)
from .widgets import (
    BG,
    CARD,
    FG,
    MUTED,
    PRIMARY,
    ChatArea,
    ConversationSidebar,
)
from .workers import TurnWorker


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
        self.sidebar.clear_requested.connect(self._clear_conversation)
        self.sidebar.delete_requested.connect(self._delete_conversation)
        self.chat.send_requested.connect(self._start_turn)
        self.chat.clarification_chosen.connect(self._start_turn)

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
            self.chat.add_message(message)
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

        self._turn_thread = QThread(self)
        self._turn_worker = TurnWorker(
            self._backend,
            conversation_id,
            text,
        )
        self._turn_worker.moveToThread(self._turn_thread)
        self._turn_thread.started.connect(self._turn_worker.run)
        self._turn_worker.progress.connect(self._on_turn_progress)
        self._turn_worker.completed.connect(self._on_turn_completed)
        self._turn_worker.failed.connect(self._on_turn_failed)
        self._turn_worker.finished.connect(self._turn_thread.quit)
        self._turn_worker.finished.connect(self._turn_worker.deleteLater)
        self._turn_thread.finished.connect(self._cleanup_turn)
        self._turn_thread.start()

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


def apply_palette(application: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(FG))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(MUTED))
    palette.setColor(QPalette.ColorRole.Text, QColor(FG))
    palette.setColor(QPalette.ColorRole.Button, QColor(CARD))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(FG))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    application.setPalette(palette)


def run(
    backend: ConversationBackendPort | None = None,
    *,
    application: QApplication | None = None,
) -> int:
    app = application or QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_palette(app)
    window = MainWindow(backend=backend)
    window.show()
    return app.exec()
