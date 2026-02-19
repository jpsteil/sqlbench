"""
Query Manager Dialog for SQLBench PyQt6 GUI.

Provides interface for loading, deleting, exporting, and importing saved queries.
"""

import json
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
    QFileDialog,
    QMessageBox,
)

from ...database import _get_db


class QueryManagerDialog(QDialog):
    """Dialog for managing saved queries."""

    def __init__(self, parent: Optional[QWidget] = None,
                 db_type: str = '', connection_name: str = ''):
        super().__init__(parent)

        self.db_type = db_type
        self.connection_name = connection_name
        self.selected_sql: Optional[str] = None

        self.setWindowTitle("Saved Queries")
        self.setMinimumSize(500, 400)
        self.resize(550, 450)

        if parent is not None:
            pg = parent.window().frameGeometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self) -> None:
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Filter bar
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter queries...")
        self.filter_input.textChanged.connect(self._refresh_list)
        layout.addWidget(self.filter_input)

        # Query list
        self.query_list = QListWidget()
        self.query_list.doubleClicked.connect(self._on_load)
        layout.addWidget(self.query_list)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_load = QPushButton("Load")
        btn_load.clicked.connect(self._on_load)
        btn_layout.addWidget(btn_load)

        btn_delete = QPushButton("Delete")
        btn_delete.clicked.connect(self._on_delete)
        btn_layout.addWidget(btn_delete)

        btn_layout.addStretch()

        btn_import = QPushButton("Import")
        btn_import.clicked.connect(self._on_import)
        btn_layout.addWidget(btn_import)

        btn_export = QPushButton("Export")
        btn_export.clicked.connect(self._on_export)
        btn_layout.addWidget(btn_export)

        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _refresh_list(self, filter_text: str = "") -> None:
        """Reload queries from database, applying filter."""
        self.query_list.clear()
        db = _get_db()
        queries = db.get_saved_queries(self.db_type)

        filter_lower = filter_text.lower() if filter_text else ""
        for q in queries:
            name = q["name"]
            if filter_lower and filter_lower not in name.lower():
                continue
            suffix = "" if q.get("db_type") else " (any)"
            item = QListWidgetItem(f"{name}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, q)
            self.query_list.addItem(item)

    def _get_selected_query(self):
        """Get the currently selected query dict."""
        item = self.query_list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_load(self) -> None:
        """Load selected query."""
        query = self._get_selected_query()
        if query:
            self.selected_sql = query["sql"]
            self.accept()

    def _on_delete(self) -> None:
        """Delete selected query."""
        query = self._get_selected_query()
        if not query:
            return

        result = QMessageBox.question(
            self, "Delete Query",
            f"Delete query '{query['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if result == QMessageBox.StandardButton.Yes:
            db = _get_db()
            db.delete_query(query["id"])
            self._refresh_list(self.filter_input.text())

    def _on_export(self) -> None:
        """Export queries to JSON file."""
        db = _get_db()
        queries = db.get_saved_queries(self.db_type)
        if not queries:
            QMessageBox.information(self, "Export", "No queries to export.")
            return

        default_name = f"queries_{self.db_type}.json" if self.db_type else "queries.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Queries", default_name, "JSON Files (*.json)")
        if not path:
            return

        export_data = [
            {"name": q["name"], "sql": q["sql"], "db_type": q.get("db_type")}
            for q in queries
        ]
        with open(path, 'w') as f:
            json.dump(export_data, f, indent=2)

        QMessageBox.information(
            self, "Export", f"Exported {len(export_data)} queries.")

    def _on_import(self) -> None:
        """Import queries from JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Queries", "", "JSON Files (*.json)")
        if not path:
            return

        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))
            return

        db = _get_db()
        count = 0
        for entry in data:
            entry_type = entry.get("db_type")
            if self.db_type and entry_type and entry_type != self.db_type:
                continue
            db.save_query(
                entry["name"], entry["sql"],
                None, entry_type or self.db_type
            )
            count += 1

        self._refresh_list(self.filter_input.text())
        QMessageBox.information(
            self, "Import", f"Imported {count} queries.")
