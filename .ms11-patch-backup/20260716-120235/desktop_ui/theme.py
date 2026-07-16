from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Light palette copied from the supplied Figma/React page.
BG = "#ffffff"
CARD = "#ffffff"
FG = "#202024"
FG_DIM = "#717182"
FG_MUTED = "#9a9aa6"
PRIMARY = "#030213"
PRIMARY_FG = "#ffffff"
MUTED = "#ececf0"
MUTED_SOFT = "#f3f3f5"
ACCENT = "#e9ebef"
BORDER = "#e4e4e8"
SUCCESS = "#10b981"
SUCCESS_DARK = "#047857"
ERROR = "#d4183d"
WARNING = "#a16207"


def apply_light_theme(application: QApplication) -> None:
    """Apply one light palette and popup stylesheet to the entire desktop app."""

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(FG))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(MUTED))
    palette.setColor(QPalette.ColorRole.Text, QColor(FG))
    palette.setColor(QPalette.ColorRole.Button, QColor(CARD))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(FG))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(PRIMARY_FG))
    application.setPalette(palette)

    # Native Windows dialogs can inherit a dark system theme even while the
    # main page is light. Styling these Qt popup classes at application scope
    # keeps menus, rename dialogs, confirmations, and error dialogs consistent.
    application.setStyleSheet(
        "QMenu, QDialog, QMessageBox, QInputDialog {"
        f"background:{MUTED_SOFT}; color:{FG};"
        "}"
        "QMenu {"
        f"border:1px solid {BORDER}; padding:5px;"
        "}"
        "QMenu::item {"
        f"background:transparent; color:{FG}; padding:6px 22px 6px 10px;"
        "border-radius:5px;"
        "}"
        "QMenu::item:selected {"
        f"background:{MUTED}; color:{FG};"
        "}"
        "QMenu::separator {"
        f"height:1px; background:{BORDER}; margin:4px 7px;"
        "}"
        "QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {"
        f"color:{FG}; background:transparent;"
        "}"
        "QDialog QLineEdit, QInputDialog QLineEdit, QDialog QTextEdit, "
        "QDialog QPlainTextEdit {"
        f"background:{CARD}; color:{FG}; border:1px solid {BORDER};"
        "border-radius:6px; padding:6px; selection-background-color:"
        f"{ACCENT}; selection-color:{FG};"
        "}"
        "QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {"
        f"background:{CARD}; color:{FG}; border:1px solid {BORDER};"
        "border-radius:6px; min-width:70px; padding:5px 10px;"
        "}"
        "QDialog QPushButton:hover, QMessageBox QPushButton:hover, "
        "QInputDialog QPushButton:hover {"
        f"background:{MUTED};"
        "}"
    )
