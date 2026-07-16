from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import (
    ChatMessageViewModel,
    ClarificationViewModel,
    ConversationSummary,
    ExplorerColumn,
    ExplorerEditPatch,
    ExplorerViewModel,
    RagLogViewModel,
    ResultViewModel,
    ToolOutcomeViewModel,
    TurnProgress,
)

from .theme import (
    ACCENT,
    BG,
    BORDER,
    CARD,
    ERROR,
    FG,
    FG_DIM,
    FG_MUTED,
    MUTED,
    MUTED_SOFT,
    PRIMARY,
    PRIMARY_FG,
    SUCCESS,
    SUCCESS_DARK,
    WARNING,
)

_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)


def _is_private_metadata_key(key: Any) -> bool:
    normalized = str(key).strip().casefold()
    return (
        normalized == "id"
        or normalized.endswith("_id")
        or normalized.endswith(" id")
        or "uuid" in normalized
        or normalized in {"stream", "stream id", "tool call"}
    )


def _redact_uuid_text(value: Any) -> str:
    return _UUID_PATTERN.sub("[internal identifier hidden]", str(value))


def _sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_metadata(item)
            for key, item in value.items()
            if not _is_private_metadata_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_metadata(item) for item in value)
    if isinstance(value, str):
        return _redact_uuid_text(value)
    return value


def font(
    size: int = 11,
    weight: QFont.Weight = QFont.Weight.Normal,
    *,
    mono: bool = False,
) -> QFont:
    value = QFont("Consolas" if mono else "Segoe UI", size)
    value.setWeight(weight)
    return value


def _set_pointer(widget: QWidget) -> None:
    widget.setCursor(Qt.CursorShape.PointingHandCursor)


def _time_label(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    for parser in (
        lambda raw: datetime.fromisoformat(raw.replace("Z", "+00:00")),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            return parser(text).astimezone().strftime("%H:%M")
        except (ValueError, TypeError):
            continue
    return text


def _year_label(value: str) -> str:
    text = (value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return "Recent"


def _plain_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setFont(font(9, QFont.Weight.Medium))
    button.setFixedHeight(24)
    _set_pointer(button)
    button.setStyleSheet(
        "QPushButton {"
        f"background:{MUTED_SOFT}; color:{FG_DIM}; border:none;"
        "border-radius:6px; padding:0 8px;"
        "}"
        "QPushButton:hover {"
        f"background:{ACCENT}; color:{FG};"
        "}"
    )
    return button


class CopyButton(QPushButton):
    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__("Copy", parent)
        self._value = value
        self.setFont(font(8, QFont.Weight.Medium))
        self.setFixedHeight(21)
        _set_pointer(self)
        self.setStyleSheet(
            "QPushButton {"
            f"background:{CARD}; color:{FG_DIM}; border:1px solid {BORDER};"
            "border-radius:5px; padding:0 7px;"
            "}"
            "QPushButton:hover {"
            f"background:{MUTED_SOFT}; color:{FG};"
            "}"
        )
        self.clicked.connect(self._copy)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._value)
        self.setText("Copied")
        QTimer.singleShot(1200, lambda: self.setText("Copy"))


class TurnStatusBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("turnStatus")
        self.setStyleSheet(
            "QFrame#turnStatus {"
            f"background:{CARD}; border-top:1px solid {BORDER};"
            "}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(7)
        self._dot = QLabel("●")
        self._dot.setFont(font(8))
        self._label = QLabel("")
        self._label.setFont(font(9))
        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        layout.addStretch()
        self.hide()

    def set_progress(self, progress: TurnProgress | str) -> None:
        if isinstance(progress, TurnProgress):
            state = progress.state
            message = progress.message
        else:
            state = progress
            message = {
                "loading": "Loading conversation…",
                "processing": "Processing your request…",
                "clarifying": "Clarification required",
                "completed": "Completed",
                "no_matches": "Completed — no matches",
                "blocked": "Action unavailable",
                "failed": "Turn failed",
                "resumed": "Conversation resumed",
                "idle": "",
            }.get(state, "")

        if state == "idle" or not message:
            self.hide()
            return

        color = {
            "blocked": WARNING,
            "failed": ERROR,
            "clarifying": WARNING,
            "completed": SUCCESS_DARK,
            "no_matches": WARNING,
            "resumed": FG_DIM,
        }.get(state, FG_DIM)
        self._dot.setStyleSheet(f"color:{color};")
        self._label.setStyleSheet(f"color:{color};")
        self._label.setText(message)
        self.show()


class ConversationEntry(QFrame):
    selected = Signal(str)
    rename_requested = Signal(str, str)
    export_requested = Signal(str)
    clear_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(
        self,
        summary: ConversationSummary,
        *,
        active: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._summary = summary
        self._active = active
        self.setObjectName("conversationEntry")
        self.setStyleSheet(
            "QFrame#conversationEntry { background:transparent; border:none; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        row = QFrame()
        row.setObjectName("conversationRow")
        row.setStyleSheet(
            "QFrame#conversationRow {"
            f"background:{ACCENT if active else CARD}; border:none; border-radius:6px;"
            "}"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(3, 3, 3, 3)
        row_layout.setSpacing(5)

        dot = QLabel("●")
        dot.setFixedWidth(12)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setFont(font(6))
        dot.setStyleSheet(
            f"color:{FG if active else BORDER}; background:transparent;"
        )

        title = QPushButton(summary.title)
        title.setToolTip(summary.title)
        title.setFont(font(9, QFont.Weight.Medium if active else QFont.Weight.Normal))
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title.setFixedHeight(28)
        title.setStyleSheet(
            "QPushButton {"
            f"background:transparent; color:{FG if active else FG_DIM};"
            "border:none; text-align:left; padding:0 3px;"
            "}"
            "QPushButton:hover {"
            f"color:{FG};"
            "}"
        )
        _set_pointer(title)
        title.clicked.connect(
            lambda checked=False: self.selected.emit(summary.conversation_id)
        )

        menu_button = QToolButton()
        menu_button.setText("⋯")
        menu_button.setFont(font(11, QFont.Weight.Medium))
        menu_button.setFixedSize(24, 24)
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        _set_pointer(menu_button)
        menu_button.setStyleSheet(
            "QToolButton {"
            f"background:transparent; color:{FG_DIM}; border:none; border-radius:5px;"
            "}"
            "QToolButton:hover {"
            f"background:{MUTED}; color:{FG};"
            "}"
        )
        menu = QMenu(menu_button)
        rename_action = menu.addAction("Rename")
        export_action = menu.addAction("Export session (.md)")
        clear_action = menu.addAction("Clear messages")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        rename_action.triggered.connect(lambda checked=False: self._rename())
        export_action.triggered.connect(
            lambda checked=False: self.export_requested.emit(summary.conversation_id)
        )
        clear_action.triggered.connect(
            lambda checked=False: self.clear_requested.emit(summary.conversation_id)
        )
        delete_action.triggered.connect(
            lambda checked=False: self.delete_requested.emit(summary.conversation_id)
        )
        menu_button.setMenu(menu)

        row_layout.addWidget(dot)
        row_layout.addWidget(title, 1)
        row_layout.addWidget(menu_button)
        root.addWidget(row)

        if active:
            detail = QFrame()
            detail.setStyleSheet(
                f"background:{MUTED_SOFT}; border:none; border-radius:6px;"
            )
            detail_layout = QVBoxLayout(detail)
            detail_layout.setContentsMargins(9, 7, 9, 7)
            updated = QLabel(
                f"Updated {_time_label(summary.updated_at) or 'recently'}"
            )
            updated.setFont(font(8))
            updated.setStyleSheet(f"color:{FG_DIM};")
            updated.setWordWrap(True)
            detail_layout.addWidget(updated)
            root.addWidget(detail)

    def _rename(self) -> None:
        title, accepted = QInputDialog.getText(
            self,
            "Rename conversation",
            "Conversation title",
            text=self._summary.title,
        )
        if accepted and title.strip():
            self.rename_requested.emit(
                self._summary.conversation_id,
                title.strip(),
            )


class ConversationSidebar(QFrame):
    new_requested = Signal()
    conversation_selected = Signal(str)
    rename_requested = Signal(str, str)
    export_requested = Signal(str)
    clear_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("conversationSidebar")
        self.setFixedWidth(224)
        self.setStyleSheet(
            "QFrame#conversationSidebar {"
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:12px;"
            "}"
        )
        self._running = False
        self._selected_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("sidebarHeader")
        header.setStyleSheet(
            "QFrame#sidebarHeader {"
            f"background:{CARD}; border:none; border-bottom:1px solid {BORDER};"
            "border-top-left-radius:12px; border-top-right-radius:12px;"
            "}"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 9, 9, 9)
        header_layout.setSpacing(7)
        icon = QLabel("◫")
        icon.setFont(font(9))
        icon.setStyleSheet(f"color:{FG_DIM};")
        title = QLabel("Conversations")
        title.setFont(font(9, QFont.Weight.Medium))
        title.setStyleSheet(f"color:{FG};")
        self._new_button = QToolButton()
        self._new_button.setText("+")
        self._new_button.setToolTip("New conversation")
        self._new_button.setFixedSize(25, 25)
        self._new_button.setFont(font(12, QFont.Weight.Medium))
        _set_pointer(self._new_button)
        self._new_button.setStyleSheet(
            "QToolButton {"
            f"background:transparent; color:{FG_DIM}; border:none; border-radius:6px;"
            "}"
            "QToolButton:hover {"
            f"background:{MUTED}; color:{FG};"
            "}"
        )
        self._new_button.clicked.connect(
            lambda checked=False: self.new_requested.emit()
        )
        header_layout.addWidget(icon)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self._new_button)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        self._content = QWidget()
        self._content.setStyleSheet("background:transparent;")
        self._list_layout = QVBoxLayout(self._content)
        self._list_layout.setContentsMargins(11, 9, 11, 11)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._content)
        root.addWidget(scroll, 1)

    def set_running(self, running: bool) -> None:
        self._running = running
        self._new_button.setEnabled(not running)
        self.setEnabled(not running)

    def set_conversations(
        self,
        summaries: list[ConversationSummary],
        selected_id: str | None,
    ) -> None:
        self._selected_id = selected_id
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        previous_year: str | None = None
        for summary in summaries:
            year = _year_label(summary.updated_at)
            if year != previous_year:
                year_label = QLabel(year.upper())
                year_label.setFont(font(7, QFont.Weight.DemiBold))
                year_label.setStyleSheet(f"color:{FG_MUTED}; padding:8px 0 2px 20px;")
                self._list_layout.insertWidget(
                    self._list_layout.count() - 1,
                    year_label,
                )
                previous_year = year

            entry = ConversationEntry(
                summary,
                active=summary.conversation_id == selected_id,
            )
            entry.selected.connect(self.conversation_selected)
            entry.rename_requested.connect(self.rename_requested)
            entry.export_requested.connect(self.export_requested)
            entry.clear_requested.connect(self.clear_requested)
            entry.delete_requested.connect(self.delete_requested)
            self._list_layout.insertWidget(
                self._list_layout.count() - 1,
                entry,
            )


class MessageEditor(QTextEdit):
    submit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setPlaceholderText("Type a message...")
        self.setFont(font(10))
        self.setFixedHeight(42)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(
            "QTextEdit {"
            f"background:transparent; color:{FG}; border:none; padding:7px 2px;"
            "}"
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ):
            event.accept()
            self.submit_requested.emit()
            return
        super().keyPressEvent(event)


class FormulaBlock(QFrame):
    def __init__(
        self,
        label: str,
        formula: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        header = QHBoxLayout()
        caption = QLabel(label)
        caption.setFont(font(8, QFont.Weight.Medium))
        caption.setStyleSheet(f"color:{FG_DIM};")
        header.addWidget(caption)
        header.addStretch()
        header.addWidget(CopyButton(formula))
        code = QLabel(formula or "—")
        code.setFont(font(9, mono=True))
        code.setWordWrap(True)
        code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code.setStyleSheet(
            f"background:{MUTED_SOFT}; color:{FG}; border:1px solid {BORDER};"
            "border-radius:6px; padding:7px 8px;"
        )
        root.addLayout(header)
        root.addWidget(code)


class CollapsibleDetails(QFrame):
    def __init__(self, title: str = "Details", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)
        self.button = QToolButton()
        self.button.setText(f"›  {title}")
        self.button.setCheckable(True)
        self.button.setFont(font(8, QFont.Weight.Medium))
        self.button.setStyleSheet(
            "QToolButton {"
            f"background:transparent; color:{FG_DIM}; border:none; padding:2px 0;"
            "}"
            "QToolButton:hover {"
            f"color:{FG};"
            "}"
        )
        _set_pointer(self.button)
        self.body = QFrame()
        self.body.setStyleSheet(
            f"background:{MUTED_SOFT}; border:none; border-radius:6px;"
        )
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(9, 8, 9, 8)
        self.body_layout.setSpacing(5)
        self.body.hide()
        self.button.toggled.connect(self._toggle)
        root.addWidget(self.button)
        root.addWidget(self.body)

    def _toggle(self, checked: bool) -> None:
        self.button.setText(
            ("⌄" if checked else "›") + "  " + self.button.text()[3:]
        )
        self.body.setVisible(checked)

    def add_text(self, text: str, *, mono: bool = False) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setFont(font(8, mono=mono))
        label.setStyleSheet(f"color:{FG_DIM}; background:transparent;")
        self.body_layout.addWidget(label)


class ExplorerInlineCard(QFrame):
    save_requested = Signal(str, int, object)

    def __init__(
        self,
        explorer: ExplorerViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._explorer = explorer
        self.setObjectName("explorerCard")
        self.setStyleSheet(
            "QFrame#explorerCard {"
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:9px;"
            "}"
        )
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 11, 12, 11)
        self._root.setSpacing(8)

        header = QHBoxLayout()
        self._title = QLabel(explorer.name or "Explorer")
        self._title.setFont(font(10, QFont.Weight.DemiBold))
        self._title.setStyleSheet(f"color:{FG};")
        header.addWidget(self._title)
        header.addStretch()

        self._edit_button = _plain_button("Edit")
        self._edit_button.setToolTip(
            "Edit stored Explorer fields directly. This does not call AI."
        )
        self._edit_button.clicked.connect(self._show_editor)
        header.addWidget(self._edit_button)

        validation = QLabel(
            "✓  VALID" if explorer.validation_status == "passed" else
            "✕  INVALID" if explorer.validation_status == "failed" else
            "…  PENDING"
        )
        validation.setFont(font(7, QFont.Weight.DemiBold))
        validation_color = (
            SUCCESS_DARK if explorer.validation_status == "passed" else
            ERROR if explorer.validation_status == "failed" else
            FG_DIM
        )
        validation.setStyleSheet(
            f"color:{validation_color}; background:{MUTED_SOFT};"
            "border-radius:5px; padding:3px 7px;"
        )
        header.addWidget(validation)
        self._root.addLayout(header)

        self._view = QWidget()
        self._view.setStyleSheet("background:transparent;")
        view_layout = QVBoxLayout(self._view)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(8)

        if explorer.description:
            description = QLabel(explorer.description)
            description.setFont(font(9))
            description.setWordWrap(True)
            description.setStyleSheet(f"color:{FG_DIM};")
            view_layout.addWidget(description)

        for column in explorer.columns:
            view_layout.addWidget(
                FormulaBlock(f"Column {column.label}", column.formula)
            )
        view_layout.addWidget(FormulaBlock("Filter", explorer.filter_formula))

        details = CollapsibleDetails()
        if explorer.assumptions:
            details.add_text("Assumptions")
            for item in explorer.assumptions:
                details.add_text(f"• {item}")
        if explorer.validation_errors:
            details.add_text("Validation errors")
            for item in explorer.validation_errors:
                details.add_text(f"• {item}")
        if explorer.validation_warnings:
            details.add_text("Validation warnings")
            for item in explorer.validation_warnings:
                details.add_text(f"• {item}")
        if explorer.retrieved_references:
            details.add_text("Retrieved references")
            for ref in explorer.retrieved_references:
                reason = f" — {ref.retrieval_reason}" if ref.retrieval_reason else ""
                details.add_text(f"• {ref.table_title} ({ref.score:.2f}){reason}")
        details.add_text(f"Source: {explorer.source or 'agent-generated'}")
        if explorer.explorer_created_at:
            details.add_text(f"Created: {explorer.explorer_created_at}")
        if explorer.updated_at:
            details.add_text(f"Last edited: {explorer.updated_at}")
        if explorer.revised_from_explorer_id:
            details.add_text("Lineage: revised from an earlier Explorer version")
        if explorer.repaired_from_explorer_id:
            details.add_text("Lineage: repaired from an earlier Explorer version")
        if explorer.revision_instruction:
            details.add_text(f"Revision: {explorer.revision_instruction}")
        view_layout.addWidget(details)
        self._root.addWidget(self._view)

        self._editor_panel = QFrame()
        self._editor_panel.setStyleSheet(
            f"background:{MUTED_SOFT}; border:none; border-radius:8px;"
        )
        editor_layout = QVBoxLayout(self._editor_panel)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.setSpacing(7)

        self._name_editor = self._line_editor(explorer.name)
        editor_layout.addWidget(self._field_label("Explorer name"))
        editor_layout.addWidget(self._name_editor)

        self._description_editor = self._text_editor(explorer.description, 70)
        editor_layout.addWidget(self._field_label("Description"))
        editor_layout.addWidget(self._description_editor)

        editor_layout.addWidget(self._field_label("Columns"))
        self._column_editors: list[tuple[QLineEdit, QPlainTextEdit]] = []
        for column in explorer.columns:
            row = QHBoxLayout()
            label_editor = self._line_editor(column.label)
            label_editor.setFixedWidth(42)
            formula_editor = self._text_editor(column.formula, 52)
            row.addWidget(label_editor)
            row.addWidget(formula_editor, 1)
            editor_layout.addLayout(row)
            self._column_editors.append((label_editor, formula_editor))

        self._filter_editor = self._text_editor(explorer.filter_formula, 70)
        editor_layout.addWidget(self._field_label("Filter formula"))
        editor_layout.addWidget(self._filter_editor)

        assumptions_text = "\n".join(explorer.assumptions)
        self._assumptions_editor = self._text_editor(assumptions_text, 70)
        self._assumptions_editor.setPlaceholderText("One assumption per line")
        editor_layout.addWidget(self._field_label("Assumptions"))
        editor_layout.addWidget(self._assumptions_editor)

        self._editor_error = QLabel("")
        self._editor_error.setWordWrap(True)
        self._editor_error.setFont(font(8))
        self._editor_error.setStyleSheet(f"color:{ERROR};")
        self._editor_error.hide()
        editor_layout.addWidget(self._editor_error)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = _plain_button("Cancel")
        cancel.clicked.connect(self._hide_editor)
        self._save_button = QPushButton("Save")
        self._save_button.setFont(font(8, QFont.Weight.Medium))
        self._save_button.setFixedHeight(26)
        self._save_button.setStyleSheet(
            f"background:{PRIMARY}; color:{PRIMARY_FG}; border:none;"
            "border-radius:6px; padding:0 10px;"
        )
        _set_pointer(self._save_button)
        self._save_button.clicked.connect(self._submit_edits)
        actions.addWidget(cancel)
        actions.addWidget(self._save_button)
        editor_layout.addLayout(actions)

        self._editor_panel.hide()
        self._root.addWidget(self._editor_panel)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(font(8, QFont.Weight.Medium))
        label.setStyleSheet(f"color:{FG_DIM}; background:transparent;")
        return label

    @staticmethod
    def _line_editor(value: str) -> QLineEdit:
        editor = QLineEdit(value)
        editor.setFont(font(9))
        editor.setStyleSheet(
            f"background:{CARD}; color:{FG}; border:1px solid {BORDER};"
            "border-radius:6px; padding:5px 7px;"
        )
        return editor

    @staticmethod
    def _text_editor(value: str, height: int) -> QPlainTextEdit:
        editor = QPlainTextEdit(value)
        editor.setFont(font(9, mono=True))
        editor.setFixedHeight(height)
        editor.setStyleSheet(
            f"background:{CARD}; color:{FG}; border:1px solid {BORDER};"
            "border-radius:6px; padding:5px 7px;"
        )
        return editor

    def _show_editor(self) -> None:
        self._view.hide()
        self._edit_button.setEnabled(False)
        self._editor_panel.show()
        self._name_editor.setFocus()

    def _hide_editor(self) -> None:
        self._editor_error.hide()
        self._editor_panel.hide()
        self._edit_button.setEnabled(True)
        self._view.show()

    def set_saving(self, saving: bool) -> None:
        self._save_button.setEnabled(not saving)
        self._save_button.setText("Saving…" if saving else "Save")

    def _submit_edits(self) -> None:
        name = self._name_editor.text().strip()
        filter_formula = self._filter_editor.toPlainText().strip()
        columns: list[ExplorerColumn] = []
        for label_editor, formula_editor in self._column_editors:
            label = label_editor.text().strip().upper()
            formula = formula_editor.toPlainText().strip()
            if not label or not formula:
                self._show_editor_error(
                    "Every displayed column needs a letter and formula."
                )
                return
            columns.append(ExplorerColumn(label=label, formula=formula))

        if not name:
            self._show_editor_error("Explorer name cannot be blank.")
            return
        if not filter_formula:
            self._show_editor_error("Filter formula cannot be blank.")
            return

        assumptions = [
            line.strip()
            for line in self._assumptions_editor.toPlainText().splitlines()
            if line.strip()
        ]
        self._editor_error.hide()
        self.save_requested.emit(
            self._explorer.explorer_id,
            self._explorer.manual_edit_version,
            ExplorerEditPatch(
                name=name,
                description=self._description_editor.toPlainText().strip(),
                columns=columns,
                filter_formula=filter_formula,
                assumptions=assumptions,
            ),
        )

    def _show_editor_error(self, message: str) -> None:
        self._editor_error.setText(message)
        self._editor_error.show()

class ResultInlineCard(QFrame):
    def __init__(
        self,
        result: ResultViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self.setObjectName("resultCard")
        self.setStyleSheet(
            "QFrame#resultCard {"
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:9px;"
            "}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 11, 12, 11)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Explorer results")
        title.setFont(font(10, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{FG};")
        header.addWidget(title)
        header.addStretch()
        count = QLabel(
            f"{result.matched_count} match{'es' if result.matched_count != 1 else ''}"
        )
        count.setFont(font(8, QFont.Weight.DemiBold))
        count.setStyleSheet(
            f"color:{SUCCESS_DARK if result.has_matches else WARNING};"
            f"background:{MUTED_SOFT}; border-radius:5px; padding:3px 7px;"
        )
        header.addWidget(count)
        root.addLayout(header)

        meta_parts = [value for value in [result.created_at, "latest" if result.is_latest else ""] if value]
        if meta_parts:
            meta = QLabel(" · ".join(meta_parts))
            meta.setFont(font(8))
            meta.setStyleSheet(f"color:{FG_DIM};")
            root.addWidget(meta)

        if result.is_summary_only:
            summary = QLabel(
                "This is a stored-result summary. Ask the agent to show the result rows."
            )
            summary.setWordWrap(True)
            summary.setFont(font(9))
            summary.setStyleSheet(
                f"background:{MUTED_SOFT}; color:{FG_DIM}; border-radius:6px; padding:8px;"
            )
            root.addWidget(summary)
        elif not result.rows:
            empty = QLabel("No instruments matched this exploration.")
            empty.setFont(font(9))
            empty.setStyleSheet(
                f"background:{MUTED_SOFT}; color:{FG_DIM}; border-radius:6px; padding:8px;"
            )
            root.addWidget(empty)
        else:
            table = QTableWidget()
            table.setColumnCount(len(result.columns))
            table.setHorizontalHeaderLabels(result.columns)
            visible_rows = result.rows[:100]
            table.setRowCount(len(visible_rows))
            for row_index, row in enumerate(visible_rows):
                for column_index, value in enumerate(row[: len(result.columns)]):
                    table.setItem(
                        row_index,
                        column_index,
                        QTableWidgetItem("" if value is None else str(value)),
                    )
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setAlternatingRowColors(False)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setStretchLastSection(True)
            table.setMinimumHeight(120)
            table.setMaximumHeight(260)
            table.setStyleSheet(
                "QTableWidget {"
                f"background:{CARD}; color:{FG}; border:1px solid {BORDER};"
                "border-radius:6px; gridline-color:" + BORDER + ";"
                "}"
                "QHeaderView::section {"
                f"background:{MUTED_SOFT}; color:{FG_DIM}; border:none;"
                f"border-bottom:1px solid {BORDER}; padding:6px;"
                "}"
                "QTableWidget::item { padding:5px; }"
                "QTableWidget::item:selected {"
                f"background:{ACCENT}; color:{FG};"
                "}"
            )
            root.addWidget(table)
            actions = QHBoxLayout()
            export = _plain_button("Export CSV")
            export.clicked.connect(self._export_csv)
            actions.addWidget(export)
            if len(result.rows) > len(visible_rows):
                clipped = QLabel(
                    f"Showing the first {len(visible_rows)} of {len(result.rows)} rows"
                )
                clipped.setFont(font(8))
                clipped.setStyleSheet(f"color:{FG_DIM};")
                actions.addWidget(clipped)
            actions.addStretch()
            root.addLayout(actions)

        details = CollapsibleDetails()
        details.add_text(f"Outcome: {result.outcome.replace('_', ' ')}")
        if result.expected_count is not None:
            details.add_text(f"Expected count: {result.expected_count}")
        if result.capture_started_at:
            details.add_text(f"Capture started: {result.capture_started_at}")
        if result.capture_completed_at:
            details.add_text(f"Capture completed: {result.capture_completed_at}")
        if result.clipboard_verified is not None:
            details.add_text(
                "Clipboard verification: "
                + ("passed" if result.clipboard_verified else "failed")
            )
        for key, value in result.diagnostics.items():
            if _is_private_metadata_key(key):
                continue
            safe_value = _sanitize_metadata(value)
            details.add_text(
                f"{str(key).replace('_', ' ').title()}: {safe_value}"
            )
        root.addWidget(details)

    def _export_csv(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suggested = f"metastock-results-{timestamp}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export MetaStock results",
            suggested,
            "CSV files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        destination = Path(path)
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(self._result.columns)
            writer.writerows(self._result.rows)


class RagLogInlineCard(QFrame):
    def __init__(
        self,
        log: RagLogViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ragLogCard")
        self.setStyleSheet(
            "QFrame#ragLogCard {"
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:9px;"
            "}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 11, 12, 11)
        root.setSpacing(6)
        title = QLabel("Generation log")
        title.setFont(font(10, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{FG};")
        root.addWidget(title)
        summary_parts = [value for value in [log.event_type, log.created_at] if value]
        if summary_parts:
            summary = QLabel(" · ".join(summary_parts))
            summary.setFont(font(8))
            summary.setStyleSheet(f"color:{FG_DIM};")
            root.addWidget(summary)
        details = CollapsibleDetails("Log output")
        if log.stdout_text:
            details.add_text(_redact_uuid_text(log.stdout_text), mono=True)
        if log.stderr_text:
            details.add_text(_redact_uuid_text(log.stderr_text), mono=True)
        for key, value in log.metadata.items():
            if _is_private_metadata_key(key):
                continue
            safe_value = _sanitize_metadata(value)
            details.add_text(
                f"{str(key).replace('_', ' ').title()}: {safe_value}"
            )
        root.addWidget(details)


class NoticeCard(QFrame):
    def __init__(
        self,
        outcome: ToolOutcomeViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        is_error = outcome.status == "failed"
        color = ERROR if is_error else WARNING
        self.setStyleSheet(
            f"background:{MUTED_SOFT}; border:1px solid {BORDER}; border-radius:8px;"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)
        title = QLabel(outcome.display_title or "Action unavailable")
        title.setFont(font(8, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{color};")
        root.addWidget(title)
        message = outcome.display_markdown or outcome.error_message or outcome.message
        if message:
            body = QLabel(_redact_uuid_text(message))
            body.setWordWrap(True)
            body.setFont(font(9))
            body.setStyleSheet(f"color:{FG_DIM};")
            root.addWidget(body)


class ClarificationCard(QFrame):
    submitted = Signal(str)

    def __init__(
        self,
        clarification: ClarificationViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:8px;"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(7)
        title = QLabel(clarification.title)
        title.setFont(font(8, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{FG_DIM};")
        root.addWidget(title)
        for option in clarification.options:
            button = _plain_button(option)
            button.clicked.connect(
                lambda checked=False, value=option: self.submitted.emit(value)
            )
            root.addWidget(button)
        row = QHBoxLayout()
        self._editor = QTextEdit()
        self._editor.setAcceptRichText(False)
        self._editor.setPlaceholderText(clarification.placeholder)
        self._editor.setFixedHeight(45)
        self._editor.setFont(font(9))
        self._editor.setStyleSheet(
            f"background:{MUTED_SOFT}; color:{FG}; border:none; border-radius:6px; padding:6px;"
        )
        send = QPushButton("Send")
        send.setFixedHeight(32)
        send.setFont(font(8, QFont.Weight.Medium))
        send.setStyleSheet(
            f"background:{PRIMARY}; color:{PRIMARY_FG}; border:none; border-radius:6px; padding:0 10px;"
        )
        _set_pointer(send)
        send.clicked.connect(self._submit)
        row.addWidget(self._editor, 1)
        row.addWidget(send)
        root.addLayout(row)

    def _submit(self) -> None:
        text = self._editor.toPlainText().strip()
        if text:
            self._editor.clear()
            self.submitted.emit(text)


class ApprovalPlaceholderCard(QFrame):
    def __init__(self, prompt: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:8px;"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(7)
        label = QLabel("APPROVAL REQUIRED · PREVIEW ONLY")
        label.setFont(font(7, QFont.Weight.DemiBold))
        label.setStyleSheet(f"color:{FG_DIM};")
        root.addWidget(label)
        text = QLabel(prompt)
        text.setWordWrap(True)
        text.setFont(font(9))
        text.setStyleSheet(f"color:{FG};")
        root.addWidget(text)
        actions = QHBoxLayout()
        approve = QPushButton("✓  Approve")
        reject = QPushButton("×  Reject")
        for button in (approve, reject):
            button.setEnabled(False)
            button.setFont(font(8, QFont.Weight.Medium))
            button.setFixedHeight(28)
        approve.setStyleSheet(
            f"background:{SUCCESS}; color:white; border:none; border-radius:6px; padding:0 10px;"
        )
        reject.setStyleSheet(
            f"background:{MUTED}; color:{FG_DIM}; border:none; border-radius:6px; padding:0 10px;"
        )
        actions.addWidget(approve)
        actions.addWidget(reject)
        actions.addStretch()
        root.addLayout(actions)


class MessageBubble(QWidget):
    clarification_submitted = Signal(str)
    explorer_save_requested = Signal(str, int, object)

    def __init__(
        self,
        message: ChatMessageViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)

        avatar = QLabel("U" if message.role == "user" else "A")
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFont(font(8, QFont.Weight.DemiBold))
        avatar.setStyleSheet(
            f"background:{PRIMARY if message.role == 'user' else MUTED};"
            f"color:{PRIMARY_FG if message.role == 'user' else FG_DIM};"
            "border-radius:14px;"
        )

        column = QWidget()
        column.setStyleSheet("background:transparent;")
        column.setMaximumWidth(760)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(6)
        column_layout.setAlignment(
            Qt.AlignmentFlag.AlignRight
            if message.role == "user"
            else Qt.AlignmentFlag.AlignLeft
        )

        text = QLabel(message.text)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setFont(font(10))
        text.setStyleSheet(
            f"background:{PRIMARY if message.role == 'user' else MUTED};"
            f"color:{PRIMARY_FG if message.role == 'user' else FG};"
            "border-radius:11px; padding:8px 10px;"
        )
        text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        column_layout.addWidget(text)

        if message.role == "assistant":
            if message.explorer is not None:
                explorer_card = ExplorerInlineCard(message.explorer)
                explorer_card.save_requested.connect(
                    self.explorer_save_requested
                )
                column_layout.addWidget(explorer_card)
            for result in message.results:
                column_layout.addWidget(ResultInlineCard(result))
            if message.rag_log is not None:
                column_layout.addWidget(RagLogInlineCard(message.rag_log))
            if message.tool_outcome is not None and message.tool_outcome.status != "success":
                column_layout.addWidget(NoticeCard(message.tool_outcome))
            if message.clarification is not None:
                clarification = ClarificationCard(message.clarification)
                clarification.submitted.connect(self.clarification_submitted)
                column_layout.addWidget(clarification)
            if message.approval_placeholder:
                column_layout.addWidget(
                    ApprovalPlaceholderCard(message.approval_placeholder)
                )

        timestamp = _time_label(message.created_at)
        if timestamp:
            time = QLabel(timestamp)
            time.setFont(font(7))
            time.setStyleSheet(f"color:{FG_MUTED}; padding:0 3px;")
            column_layout.addWidget(time)

        if message.role == "user":
            root.addStretch()
            root.addWidget(column)
            root.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        else:
            root.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            root.addWidget(column)
            root.addStretch()


class ChatArea(QFrame):
    send_requested = Signal(str)
    clarification_chosen = Signal(str)
    explorer_save_requested = Signal(str, int, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatArea")
        self.setStyleSheet(
            "QFrame#chatArea {"
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:12px;"
            "}"
        )
        self._running = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("chatHeader")
        header.setStyleSheet(
            "QFrame#chatHeader {"
            f"background:{CARD}; border:none; border-bottom:1px solid {BORDER};"
            "border-top-left-radius:12px; border-top-right-radius:12px;"
            "}"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(8)
        dot = QLabel("●")
        dot.setFont(font(8))
        dot.setStyleSheet(f"color:{SUCCESS};")
        self._title = QLabel("MetaStock Agent")
        self._title.setFont(font(10, QFont.Weight.Medium))
        self._title.setStyleSheet(f"color:{FG};")
        self._mode = QLabel("assistant")
        self._mode.setFont(font(8))
        self._mode.setStyleSheet(f"color:{FG_DIM};")
        header_layout.addWidget(dot)
        header_layout.addWidget(self._title)
        header_layout.addStretch()
        header_layout.addWidget(self._mode)
        root.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        self._message_host = QWidget()
        self._message_host.setStyleSheet("background:transparent;")
        self._message_layout = QVBoxLayout(self._message_host)
        self._message_layout.setContentsMargins(14, 14, 14, 14)
        self._message_layout.setSpacing(14)
        self._message_layout.addStretch()
        self._scroll.setWidget(self._message_host)
        root.addWidget(self._scroll, 1)

        self.status_bar = TurnStatusBar()
        root.addWidget(self.status_bar)

        composer = QFrame()
        composer.setObjectName("composer")
        composer.setStyleSheet(
            "QFrame#composer {"
            f"background:{CARD}; border:none; border-top:1px solid {BORDER};"
            "border-bottom-left-radius:12px; border-bottom-right-radius:12px;"
            "}"
        )
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(14, 10, 14, 9)
        composer_layout.setSpacing(5)
        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_frame.setStyleSheet(
            "QFrame#inputFrame {"
            f"background:{MUTED}; border:none; border-radius:11px;"
            "}"
        )
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 4, 7, 4)
        input_layout.setSpacing(7)
        self._editor = MessageEditor()
        self._editor.submit_requested.connect(self._send)
        self._send_button = QPushButton("➤")
        self._send_button.setFixedSize(28, 28)
        self._send_button.setFont(font(9, QFont.Weight.DemiBold))
        self._send_button.setStyleSheet(
            "QPushButton {"
            f"background:{PRIMARY}; color:{PRIMARY_FG}; border:none; border-radius:7px;"
            "}"
            "QPushButton:disabled {"
            f"background:{FG_MUTED}; color:{MUTED};"
            "}"
        )
        _set_pointer(self._send_button)
        self._send_button.clicked.connect(self._send)
        input_layout.addWidget(self._editor, 1)
        input_layout.addWidget(self._send_button, 0, Qt.AlignmentFlag.AlignVCenter)
        hint = QLabel("Shift+Enter for new line")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setFont(font(7))
        hint.setStyleSheet(f"color:{FG_MUTED};")
        composer_layout.addWidget(input_frame)
        composer_layout.addWidget(hint)
        root.addWidget(composer)

    def set_title(self, title: str) -> None:
        cleaned = title.strip() or "MetaStock Agent"
        self._title.setText(cleaned)
        self._title.setToolTip(cleaned)

    def set_running(self, running: bool) -> None:
        self._running = running
        self._editor.setEnabled(not running)
        self._send_button.setEnabled(not running)
        self._mode.setText("working" if running else "assistant")

    def clear_messages(self) -> None:
        while self._message_layout.count() > 1:
            item = self._message_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_message(
        self,
        message: ChatMessageViewModel,
        *,
        scroll: bool = True,
    ) -> None:
        bubble = MessageBubble(message)
        bubble.clarification_submitted.connect(self.clarification_chosen)
        bubble.explorer_save_requested.connect(
            self.explorer_save_requested
        )
        self._message_layout.insertWidget(
            self._message_layout.count() - 1,
            bubble,
        )
        if scroll:
            QTimer.singleShot(
                0,
                lambda target=bubble: self._ensure_message_visible(target),
            )

    def scroll_to_bottom_deferred(self) -> None:
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _ensure_message_visible(self, bubble: QWidget) -> None:
        self._scroll.ensureWidgetVisible(bubble, 0, 16)
        self._scroll_to_bottom()

    def _send(self) -> None:
        if self._running:
            return
        text = self._editor.toPlainText().strip()
        if not text:
            return
        self._editor.clear()
        self.send_requested.emit(text)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
