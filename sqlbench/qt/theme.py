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
        else:
            # Use default Fusion light palette
            app.setPalette(app.style().standardPalette())

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
