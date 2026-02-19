"""
Record Viewer Dialog for SQLBench PyQt6 GUI.

Shows a single row's data in a vertical column:value layout with navigation.
"""

from typing import Optional, List, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
    QWidget,
)


class RecordViewerDialog(QDialog):
    """Dialog for viewing a single record's fields vertically."""

    navigate = pyqtSignal(int)  # emitted when user navigates to a row index

    def __init__(self, parent: Optional[QWidget], columns: List[str],
                 rows: List[Any], initial_index: int = 0):
        super().__init__(parent)

        self.columns = columns
        self.rows = rows
        self.current_index = initial_index

        self.setWindowTitle("Record Viewer")
        self.setMinimumSize(450, 350)
        height = min(max(len(columns) * 28 + 100, 350), 700)
        self.resize(550, height)

        if parent is not None:
            pg = parent.window().frameGeometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

        self._setup_ui()
        self._setup_shortcuts()
        self._display_record()

    def _setup_ui(self) -> None:
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Navigation bar
        nav_layout = QHBoxLayout()

        self.btn_first = QPushButton("|<")
        self.btn_first.setFixedWidth(35)
        self.btn_first.clicked.connect(self._first_record)
        nav_layout.addWidget(self.btn_first)

        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedWidth(35)
        self.btn_prev.clicked.connect(self._prev_record)
        nav_layout.addWidget(self.btn_prev)

        self.position_label = QLabel()
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.position_label)

        self.btn_next = QPushButton(">")
        self.btn_next.setFixedWidth(35)
        self.btn_next.clicked.connect(self._next_record)
        nav_layout.addWidget(self.btn_next)

        self.btn_last = QPushButton(">|")
        self.btn_last.setFixedWidth(35)
        self.btn_last.clicked.connect(self._last_record)
        nav_layout.addWidget(self.btn_last)

        layout.addLayout(nav_layout)

        # Record content
        self.content = QTextEdit()
        self.content.setReadOnly(True)
        font = QFont("JetBrains Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.content.setFont(font)
        layout.addWidget(self.content)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _setup_shortcuts(self) -> None:
        """Set up keyboard navigation."""
        QShortcut(QKeySequence(Qt.Key.Key_Left), self).activated.connect(self._prev_record)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self).activated.connect(self._next_record)
        QShortcut(QKeySequence(Qt.Key.Key_Home), self).activated.connect(self._first_record)
        QShortcut(QKeySequence(Qt.Key.Key_End), self).activated.connect(self._last_record)

    def _display_record(self) -> None:
        """Display the current record."""
        if not self.rows or self.current_index >= len(self.rows):
            self.content.setPlainText("No record to display.")
            return

        row = self.rows[self.current_index]
        max_name_len = max(len(c) for c in self.columns) if self.columns else 0

        lines = []
        for col_name, value in zip(self.columns, row):
            display = "<NULL>" if value is None else str(value)
            lines.append(f"{col_name:<{max_name_len}}  {display}")

        self.content.setPlainText("\n".join(lines))
        self.position_label.setText(
            f"Record {self.current_index + 1} of {len(self.rows)}")

        # Update button states
        self.btn_first.setEnabled(self.current_index > 0)
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < len(self.rows) - 1)
        self.btn_last.setEnabled(self.current_index < len(self.rows) - 1)

        self.navigate.emit(self.current_index)

    def _prev_record(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self._display_record()

    def _next_record(self) -> None:
        if self.current_index < len(self.rows) - 1:
            self.current_index += 1
            self._display_record()

    def _first_record(self) -> None:
        self.current_index = 0
        self._display_record()

    def _last_record(self) -> None:
        self.current_index = len(self.rows) - 1
        self._display_record()
