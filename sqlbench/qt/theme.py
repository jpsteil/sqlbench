"""
Theme system for SQLBench PyQt6 GUI.

Uses Qt's built-in Fusion style with system or custom palettes.
"""

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication, QStyleFactory


class Theme:
    """Theme manager using Qt's Fusion style."""

    _is_dark: bool = True

    @classmethod
    def is_dark(cls) -> bool:
        return cls._is_dark

    @classmethod
    def set_dark(cls, dark: bool) -> None:
        cls._is_dark = dark

    @classmethod
    def apply(cls, app: QApplication) -> None:
        """Apply Fusion style with dark palette if enabled."""
        app.setStyle(QStyleFactory.create("Fusion"))

        if cls._is_dark:
            # Dark palette for Fusion
            p = QPalette()
            p.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            p.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
            p.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
            p.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            p.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
            p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            p.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
            app.setPalette(p)
            app.setStyleSheet(cls._dark_stylesheet())
        else:
            # Use default Fusion light palette
            app.setPalette(app.style().standardPalette())
            app.setStyleSheet(cls._light_stylesheet())

    @classmethod
    def _dark_stylesheet(cls) -> str:
        return """
            QPushButton {
                background: transparent;
                color: #ccc;
                border: 1px solid transparent;
                border-radius: 0px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QPushButton:disabled {
                color: #555;
            }
            QPushButton[primary="true"] {
                color: #6cb4ff;
            }
            QPushButton[primary="true"]:hover {
                background-color: #1e3a55;
                border-color: #2a5a80;
            }
            QPushButton[danger="true"] {
                color: #e07070;
            }
            QPushButton[danger="true"]:hover {
                background-color: #4a2020;
                border-color: #6a3030;
            }
            QPushButton::menu-indicator {
                width: 0px;
            }
            QToolBar {
                spacing: 1px;
                padding: 2px 2px;
                border: none;
                border-bottom: 1px solid #2a2a2a;
            }
            QToolBar QToolButton {
                background: transparent;
                color: #ccc;
                border: 1px solid transparent;
                border-radius: 0px;
                padding: 4px 6px 2px 6px;
                font-size: 11px;
            }
            QToolBar QToolButton:hover {
                background-color: #4a4a4a;
                border-color: #5a5a5a;
            }
            QToolBar QToolButton:pressed {
                background-color: #3a3a3a;
            }
            QToolBar QToolButton:disabled {
                color: #555;
            }
            QToolBar QToolButton[primary="true"] {
                color: #6cb4ff;
            }
            QToolBar QToolButton[primary="true"]:hover {
                background-color: #1e3a55;
                border-color: #2a5a80;
            }
            QToolBar QToolButton[danger="true"] {
                color: #e07070;
            }
            QToolBar QToolButton[danger="true"]:hover {
                background-color: #4a2020;
                border-color: #6a3030;
            }
            QToolBar::separator {
                width: 1px;
                background: #444;
                margin: 4px 3px;
            }
            QSpinBox {
                border: 1px solid transparent;
                border-radius: 0px;
                padding: 3px 6px;
                background: transparent;
                color: #ccc;
            }
            QSpinBox:hover {
                border-color: #5a5a5a;
                background-color: #4a4a4a;
            }
            QSpinBox:focus {
                border-color: #2a82da;
            }
            QLineEdit {
                border: 1px solid #505050;
                border-radius: 0px;
                padding: 3px 6px;
                background-color: #2b2b2b;
                color: #ddd;
            }
            QLineEdit:focus {
                border-color: #2a82da;
            }
            QCheckBox {
                spacing: 5px;
            }
        """

    @classmethod
    def _light_stylesheet(cls) -> str:
        return """
            QPushButton {
                background: transparent;
                color: #444;
                border: 1px solid transparent;
                border-radius: 0px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #d8e8f8;
                border-color: #b0cce8;
            }
            QPushButton:pressed {
                background-color: #c0d8f0;
            }
            QPushButton:disabled {
                color: #aaa;
            }
            QPushButton[primary="true"] {
                color: #1a6daa;
            }
            QPushButton[primary="true"]:hover {
                background-color: #cce0f4;
                border-color: #80b8e0;
            }
            QPushButton[danger="true"] {
                color: #bb3333;
            }
            QPushButton[danger="true"]:hover {
                background-color: #f4d8d8;
                border-color: #e0a0a0;
            }
            QPushButton::menu-indicator {
                width: 0px;
            }
            QToolBar {
                spacing: 1px;
                padding: 2px 2px;
                border: none;
                border-bottom: 1px solid #ccc;
            }
            QToolBar QToolButton {
                background: transparent;
                color: #444;
                border: 1px solid transparent;
                border-radius: 0px;
                padding: 4px 6px 2px 6px;
                font-size: 11px;
            }
            QToolBar QToolButton:hover {
                background-color: #d8e8f8;
                border-color: #b0cce8;
            }
            QToolBar QToolButton:pressed {
                background-color: #c0d8f0;
            }
            QToolBar QToolButton:disabled {
                color: #aaa;
            }
            QToolBar QToolButton[primary="true"] {
                color: #1a6daa;
            }
            QToolBar QToolButton[primary="true"]:hover {
                background-color: #cce0f4;
                border-color: #80b8e0;
            }
            QToolBar QToolButton[danger="true"] {
                color: #bb3333;
            }
            QToolBar QToolButton[danger="true"]:hover {
                background-color: #f4d8d8;
                border-color: #e0a0a0;
            }
            QToolBar::separator {
                width: 1px;
                background: #ccc;
                margin: 4px 3px;
            }
            QSpinBox {
                border: 1px solid transparent;
                border-radius: 0px;
                padding: 3px 6px;
                background: transparent;
            }
            QSpinBox:hover {
                border-color: #b0cce8;
                background-color: #d8e8f8;
            }
            QSpinBox:focus {
                border-color: #3b8ed0;
            }
            QLineEdit {
                border: 1px solid #c0c0c0;
                border-radius: 0px;
                padding: 3px 6px;
            }
            QLineEdit:focus {
                border-color: #3b8ed0;
            }
            QCheckBox {
                spacing: 5px;
            }
        """

    @classmethod
    def toggle(cls, app: QApplication) -> None:
        cls._is_dark = not cls._is_dark
        cls.apply(app)

    @classmethod
    def current(cls):
        """Get syntax colors for current theme."""
        return DarkSyntax() if cls._is_dark else LightSyntax()


class DarkSyntax:
    keyword = "#569cd6"
    function = "#dcdcaa"
    string = "#ce9178"
    comment = "#6a9955"
    number = "#b5cea8"
    operator = "#d4d4d4"


class LightSyntax:
    keyword = "#0000ff"
    function = "#795e26"
    string = "#a31515"
    comment = "#008000"
    number = "#098658"
    operator = "#000000"
