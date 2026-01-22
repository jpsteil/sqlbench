"""
Settings Dialog for SQLBench PyQt6 GUI.

Provides interface for configuring application settings.
"""

from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QWidget,
    QSpinBox,
    QPushButton,
    QLabel,
    QGroupBox,
    QDialogButtonBox,
    QMessageBox,
)

from ...database import get_setting, set_setting
from ...launcher import create_launcher, remove_launcher


class SettingsDialog(QDialog):
    """Dialog for application settings."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        self.setModal(True)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)
        appearance_layout.setSpacing(12)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(8, 24)
        self.spin_font_size.setSuffix(" pt")
        appearance_layout.addRow("Font Size:", self.spin_font_size)

        layout.addWidget(appearance_group)

        # Desktop integration group
        desktop_group = QGroupBox("Desktop Integration")
        desktop_layout = QVBoxLayout(desktop_group)

        desc = QLabel(
            "Create a desktop launcher to start SQLBench from your "
            "application menu."
        )
        desc.setWordWrap(True)
        desc.setProperty("subheading", True)
        desktop_layout.addWidget(desc)

        btn_layout = QHBoxLayout()

        self.btn_install = QPushButton("Install Launcher")
        self.btn_install.clicked.connect(self._install_launcher)
        btn_layout.addWidget(self.btn_install)

        self.btn_remove = QPushButton("Remove Launcher")
        self.btn_remove.clicked.connect(self._remove_launcher)
        btn_layout.addWidget(self.btn_remove)

        btn_layout.addStretch()
        desktop_layout.addLayout(btn_layout)

        layout.addWidget(desktop_group)

        layout.addStretch()

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_settings(self) -> None:
        """Load current settings."""
        font_size = int(get_setting("font_size", "13"))
        self.spin_font_size.setValue(font_size)

    def _save_and_close(self) -> None:
        """Save settings and close."""
        set_setting("font_size", str(self.spin_font_size.value()))
        self.accept()

    def _install_launcher(self) -> None:
        """Install desktop launcher."""
        try:
            create_launcher()
            QMessageBox.information(
                self,
                "Success",
                "Desktop launcher installed successfully."
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to install launcher:\n{str(e)}"
            )

    def _remove_launcher(self) -> None:
        """Remove desktop launcher."""
        try:
            remove_launcher()
            QMessageBox.information(
                self,
                "Success",
                "Desktop launcher removed."
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to remove launcher:\n{str(e)}"
            )
