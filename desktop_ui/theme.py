from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMenu

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


def _light_popup_stylesheet() -> str:
    return (
        "QMenu, QDialog, QMessageBox, QInputDialog {"
        f"background-color:{MUTED_SOFT}; color:{FG};"
        "}"
        "QMenu {"
        f"background-color:{MUTED_SOFT}; color:{FG}; "
        f"border:1px solid {BORDER}; padding:5px;"
        "}"
        "QMenu::item {"
        f"background-color:transparent; color:{FG}; "
        "padding:6px 22px 6px 10px; border-radius:5px;"
        "}"
        "QMenu::item:selected {"
        f"background-color:{MUTED}; color:{FG};"
        "}"
        "QMenu::item:disabled {"
        f"background-color:transparent; color:{FG_MUTED};"
        "}"
        "QMenu::separator {"
        f"height:1px; background-color:{BORDER}; margin:4px 7px;"
        "}"
        "QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {"
        f"color:{FG}; background-color:transparent;"
        "}"
        "QDialog QLineEdit, QInputDialog QLineEdit, QDialog QTextEdit, "
        "QDialog QPlainTextEdit {"
        f"background-color:{CARD}; color:{FG}; border:1px solid {BORDER};"
        "border-radius:6px; padding:6px; selection-background-color:"
        f"{ACCENT}; selection-color:{FG};"
        "}"
        "QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {"
        f"background-color:{CARD}; color:{FG}; border:1px solid {BORDER};"
        "border-radius:6px; min-width:70px; padding:5px 10px;"
        "}"
        "QDialog QPushButton:hover, QMessageBox QPushButton:hover, "
        "QInputDialog QPushButton:hover {"
        f"background-color:{MUTED};"
        "}"
    )


def apply_light_menu(menu: QMenu) -> None:
    """Force a non-native light palette on a popup menu.

    Windows can retain a dark native QMenu palette even after the application
    palette changes. Applying both a palette and a local stylesheet keeps the
    conversation menu light regardless of the operating-system theme.
    """

    palette = menu.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(MUTED_SOFT))
    palette.setColor(QPalette.ColorRole.Base, QColor(MUTED_SOFT))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(FG))
    palette.setColor(QPalette.ColorRole.Text, QColor(FG))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(FG))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(MUTED))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(FG))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(FG_MUTED))
    menu.setPalette(palette)
    menu.setStyleSheet(_light_popup_stylesheet())


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
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(FG_MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(FG_MUTED))
    application.setPalette(palette)

    # Application-level fallback for all dialogs. QMenu also gets an explicit
    # local style through apply_light_menu() because Windows can retain its
    # native dark popup palette.
    application.setStyleSheet(_light_popup_stylesheet())

