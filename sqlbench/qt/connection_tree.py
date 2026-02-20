"""
Connection Tree Widget for SQLBench PyQt6 GUI.

Provides hierarchical view of database connections with drill-down
to schemas, tables, and columns.
"""

import re
from typing import Optional, Dict, List, Any
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QAction, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QPushButton,
    QMenu,
    QLabel,
    QFrame,
)

from ..database import get_connections, get_connection, delete_connection
from ..adapters import get_adapter
from .theme import Theme
from .icons import get_db_icon, get_node_icon


class ConnectionTreeWidget(QWidget):
    """Widget displaying hierarchical connection tree with filter."""

    # Signals
    connection_selected = pyqtSignal(str)  # connection_name
    new_sql_requested = pyqtSignal(str)  # connection_name
    new_spool_requested = pyqtSignal(str)  # connection_name
    show_rows_requested = pyqtSignal(str, str, str)  # connection, schema, table
    edit_connection_requested = pyqtSignal(str)  # connection_name
    new_connection_requested = pyqtSignal()
    connect_requested = pyqtSignal(str)  # connection_name (auto-activate on expand)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._connections_info: Dict[str, Dict] = {}
        self._connected: Dict[str, bool] = {}
        self._loaded_schemas: Dict[str, bool] = {}
        self._pending_expand: Optional[QTreeWidgetItem] = None
        self._loading_tables: set = set()
        self._loading_fields: set = set()

        self._setup_ui()
        self._setup_context_menu()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("connectionHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)

        # Title
        title = QLabel("Connections")
        title.setProperty("heading", True)
        header_layout.addWidget(title)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter tables...")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_input)

        self.ai_button = QPushButton("AI")
        self.ai_button.setFixedWidth(36)
        self.ai_button.setToolTip("Generate filter regex with AI")
        self.ai_button.clicked.connect(self._show_ai_builder)
        filter_layout.addWidget(self.ai_button)

        header_layout.addLayout(filter_layout)
        layout.addWidget(header)

        # Tree view
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(20)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.tree)

        # Button bar
        button_bar = QFrame()
        button_bar.setObjectName("buttonBar")
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(8, 4, 8, 4)
        button_layout.setSpacing(4)

        self.add_button = QPushButton("+")
        self.add_button.setFixedSize(28, 28)
        self.add_button.setToolTip("New connection")
        self.add_button.clicked.connect(lambda: self.new_connection_requested.emit())
        button_layout.addWidget(self.add_button)

        self.remove_button = QPushButton("−")
        self.remove_button.setFixedSize(28, 28)
        self.remove_button.setToolTip("Delete connection")
        self.remove_button.clicked.connect(self._delete_selected)
        button_layout.addWidget(self.remove_button)

        button_layout.addStretch()
        layout.addWidget(button_bar)

    def _setup_context_menu(self) -> None:
        """Set up right-click context menu."""
        self.context_menu = QMenu(self)

        self.action_new_sql = QAction("New SQL", self)
        self.action_new_sql.triggered.connect(self._new_sql_for_selected)

        self.action_new_spool = QAction("New Spool Files", self)
        self.action_new_spool.triggered.connect(self._new_spool_for_selected)

        self.action_show_rows = QAction("Show First 1000 Rows", self)
        self.action_show_rows.triggered.connect(self._show_rows_for_selected)

        self.action_new_connection = QAction("New Connection...", self)
        self.action_new_connection.triggered.connect(
            lambda: self.new_connection_requested.emit()
        )

        self.action_edit = QAction("Edit...", self)
        self.action_edit.triggered.connect(self._edit_selected)

        self.action_delete = QAction("Delete", self)
        self.action_delete.triggered.connect(self._delete_selected)

    def load_connections(self) -> None:
        """Load connections from database."""
        self.tree.clear()
        self._connections_info.clear()

        connections = get_connections()
        for conn in connections:
            self._add_connection_item(conn)

    def _add_connection_item(self, conn: Dict) -> QTreeWidgetItem:
        """Add a connection item to the tree."""
        name = conn['name']
        db_type = conn.get('db_type', 'unknown')

        self._connections_info[name] = conn
        self._connected[name] = False

        host = conn.get('host', '')
        display_name = f"{name} - {host}" if host else name
        item = QTreeWidgetItem([display_name])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            'type': 'connection',
            'name': name,
            'db_type': db_type
        })

        # Set icon based on database type
        item.setIcon(0, get_db_icon(db_type))
        item.setToolTip(0, f"{db_type.upper()} - {conn.get('host', '')}")

        # Add placeholder child so item is expandable
        placeholder = QTreeWidgetItem(["Loading..."])
        placeholder.setData(0, Qt.ItemDataRole.UserRole, {'type': 'placeholder'})
        item.addChild(placeholder)

        self.tree.addTopLevelItem(item)
        return item

    def set_connected(self, connection_name: str, connected: bool) -> None:
        """Update connection activation status."""
        self._connected[connection_name] = connected

        if not connected:
            # Clear cached schemas
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get('name') == connection_name:
                    item.takeChildren()
                    placeholder = QTreeWidgetItem(["Loading..."])
                    placeholder.setData(0, Qt.ItemDataRole.UserRole, {'type': 'placeholder'})
                    item.addChild(placeholder)
                    self._loaded_schemas[connection_name] = False
                    break
        else:
            # Expand if pending from expand attempt
            if self._pending_expand:
                for i in range(self.tree.topLevelItemCount()):
                    item = self.tree.topLevelItem(i)
                    data = item.data(0, Qt.ItemDataRole.UserRole)
                    if data and data.get('name') == connection_name and item == self._pending_expand:
                        item.setExpanded(True)
                        self._pending_expand = None
                        break

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle item expansion - load children if needed."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type = data.get('type')

        if item_type == 'connection':
            connection_name = data.get('name')
            if not self._connected.get(connection_name):
                # Need to connect first
                self.connect_requested.emit(connection_name)
            elif not self._loaded_schemas.get(connection_name):
                self._load_schemas(item, connection_name)

        elif item_type == 'schema':
            if item.childCount() == 1:
                child = item.child(0)
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                if child_data and child_data.get('type') == 'placeholder':
                    self._load_tables(item)

        elif item_type == 'table':
            if item.childCount() == 1:
                child = item.child(0)
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                if child_data and child_data.get('type') == 'placeholder':
                    self._load_columns(item)

    def _load_schemas(self, item: QTreeWidgetItem, connection_name: str) -> None:
        """Load schemas and tables for a connection."""
        from ..adapters import connect_from_info

        if connection_name in self._loading_tables:
            return
        self._loading_tables.add(connection_name)

        # Get connection info from main window
        main_window = self.window()
        if not hasattr(main_window, 'get_conn_info'):
            self._loading_tables.discard(connection_name)
            return

        conn_info = main_window.get_conn_info(connection_name)
        if not conn_info:
            self._loading_tables.discard(connection_name)
            return

        adapter = get_adapter(conn_info.get('db_type'))
        if not adapter:
            self._loading_tables.discard(connection_name)
            return

        connection = None
        try:
            connection = connect_from_info(adapter, conn_info)
            cursor = connection.cursor()
            cursor.execute(adapter.get_tables_query())
            tables = cursor.fetchall()
            cursor.close()

            # Clear placeholder
            item.takeChildren()

            # Group tables by schema
            schemas = {}
            for row in tables:
                schema_name = row[0]
                table_name = row[1]
                table_type = row[2] if len(row) > 2 else 'TABLE'

                if schema_name not in schemas:
                    schemas[schema_name] = []
                schemas[schema_name].append((table_name, table_type))

            # Create schema nodes
            for schema_name, schema_tables in sorted(schemas.items()):
                schema_item = QTreeWidgetItem([f"{schema_name} ({len(schema_tables)})"])
                schema_item.setIcon(0, get_node_icon('schema'))
                schema_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'schema',
                    'connection': connection_name,
                    'schema': schema_name
                })

                # Add tables directly (already loaded)
                for table_name, table_type in sorted(schema_tables):
                    is_view = 'VIEW' in str(table_type).upper()
                    table_item = QTreeWidgetItem([table_name])
                    table_item.setIcon(0, get_node_icon('view' if is_view else 'table'))
                    table_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'table',
                        'connection': connection_name,
                        'schema': schema_name,
                        'table': table_name,
                        'table_type': table_type
                    })

                    # Add placeholder for columns
                    placeholder = QTreeWidgetItem(["Loading..."])
                    placeholder.setData(0, Qt.ItemDataRole.UserRole, {'type': 'placeholder'})
                    table_item.addChild(placeholder)

                    schema_item.addChild(table_item)

                item.addChild(schema_item)

            self._loaded_schemas[connection_name] = True
            self._loading_tables.discard(connection_name)

        except Exception as e:
            item.takeChildren()
            error_item = QTreeWidgetItem([f"Error: {str(e)[:50]}"])
            item.addChild(error_item)
            self._loading_tables.discard(connection_name)
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass

    def _load_tables(self, schema_item: QTreeWidgetItem) -> None:
        """Load tables for a schema.

        Note: Tables are now loaded with schemas, so this is a no-op.
        Kept for compatibility with expand logic.
        """
        pass

    def _load_columns(self, table_item: QTreeWidgetItem) -> None:
        """Load columns for a table."""
        from ..adapters import connect_from_info

        data = table_item.data(0, Qt.ItemDataRole.UserRole)
        connection_name = data.get('connection')
        schema_name = data.get('schema')
        table_name = data.get('table')

        field_key = f"{connection_name}::{schema_name}.{table_name}"
        if field_key in self._loading_fields:
            return
        self._loading_fields.add(field_key)

        main_window = self.window()
        if not hasattr(main_window, 'get_conn_info'):
            self._loading_fields.discard(field_key)
            return

        conn_info = main_window.get_conn_info(connection_name)
        if not conn_info:
            self._loading_fields.discard(field_key)
            return

        adapter = get_adapter(conn_info.get('db_type'))
        if not adapter:
            self._loading_fields.discard(field_key)
            return

        connection = None
        try:
            connection = connect_from_info(adapter, conn_info)

            # Build table reference for adapter
            table_ref = f"{schema_name}.{table_name}" if schema_name else table_name

            cursor = connection.cursor()
            cursor.execute(adapter.get_columns_query([table_ref]))
            columns = cursor.fetchall()
            cursor.close()

            # Clear placeholder
            table_item.takeChildren()

            # Columns query returns: schema, table, column_name, data_type, length, scale
            for col_row in columns:
                col_name = col_row[2] if len(col_row) > 2 else col_row[0]
                col_type = col_row[3] if len(col_row) > 3 else ''
                col_length = col_row[4] if len(col_row) > 4 else ''
                col_scale = col_row[5] if len(col_row) > 5 else ''

                if col_length and col_scale:
                    display = f"{col_name} ({col_type}({col_length},{col_scale}))"
                elif col_length:
                    display = f"{col_name} ({col_type}({col_length}))"
                else:
                    display = f"{col_name} ({col_type})"

                col_item = QTreeWidgetItem([display])
                col_item.setIcon(0, get_node_icon('column'))
                col_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'column',
                    'connection': connection_name,
                    'schema': schema_name,
                    'table': table_name,
                    'column': col_name
                })

                table_item.addChild(col_item)

            # Update table node text with column count
            table_item.setText(0, f"{table_name} ({len(columns)})")
            self._loading_fields.discard(field_key)

        except Exception as e:
            table_item.takeChildren()
            error_item = QTreeWidgetItem([f"Error: {str(e)[:50]}"])
            table_item.addChild(error_item)
            self._loading_fields.discard(field_key)
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass

    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text change."""
        self._apply_filter(text)

    def _apply_filter(self, filter_text: str) -> None:
        """Apply filter to tree items."""
        if not filter_text:
            # Show all items
            self._set_all_visible(True)
            return

        # Try to compile as regex
        try:
            pattern = re.compile(filter_text, re.IGNORECASE)
            use_regex = True
        except re.error:
            pattern = None
            use_regex = False
            filter_lower = filter_text.lower()

        # Filter tables
        for i in range(self.tree.topLevelItemCount()):
            conn_item = self.tree.topLevelItem(i)
            conn_has_match = False

            for j in range(conn_item.childCount()):
                schema_item = conn_item.child(j)
                schema_data = schema_item.data(0, Qt.ItemDataRole.UserRole)

                if not schema_data or schema_data.get('type') != 'schema':
                    continue

                schema_has_match = False

                for k in range(schema_item.childCount()):
                    table_item = schema_item.child(k)
                    table_data = table_item.data(0, Qt.ItemDataRole.UserRole)

                    if not table_data or table_data.get('type') != 'table':
                        continue

                    table_name = table_data.get('table', '')
                    schema_name = table_data.get('schema', '')

                    # Check match
                    if use_regex:
                        matches = (pattern.search(table_name) or
                                   pattern.search(schema_name))
                    else:
                        matches = (filter_lower in table_name.lower() or
                                   filter_lower in schema_name.lower())

                    table_item.setHidden(not matches)
                    if matches:
                        schema_has_match = True

                schema_item.setHidden(not schema_has_match)
                if schema_has_match:
                    conn_has_match = True
                    schema_item.setExpanded(True)

            conn_item.setHidden(not conn_has_match)
            if conn_has_match:
                conn_item.setExpanded(True)

    def _set_all_visible(self, visible: bool) -> None:
        """Set visibility of all items."""
        for i in range(self.tree.topLevelItemCount()):
            conn_item = self.tree.topLevelItem(i)
            conn_item.setHidden(not visible)

            for j in range(conn_item.childCount()):
                schema_item = conn_item.child(j)
                schema_item.setHidden(not visible)

                for k in range(schema_item.childCount()):
                    table_item = schema_item.child(k)
                    table_item.setHidden(not visible)

    def _show_ai_builder(self) -> None:
        """Show AI regex builder dialog."""
        from .dialogs.regex_builder_dialog import RegexBuilderDialog
        dialog = RegexBuilderDialog(self)
        if dialog.exec():
            regex = dialog.get_regex()
            if regex:
                self.filter_input.setText(regex)

    def _show_context_menu(self, pos) -> None:
        """Show context menu at position."""
        item = self.tree.itemAt(pos)
        if not item:
            # Show minimal menu when clicking empty area
            menu = QMenu(self)
            menu.addAction(self.action_new_connection)
            menu.exec(self.tree.mapToGlobal(pos))
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type = data.get('type')
        menu = QMenu(self)

        if item_type == 'connection':
            connection_name = data.get('name')

            menu.addAction(self.action_new_sql)

            # Check if IBM i for spool files
            conn_info = self._connections_info.get(connection_name, {})
            if conn_info.get('db_type') == 'ibmi':
                menu.addAction(self.action_new_spool)

            menu.addSeparator()
            menu.addAction(self.action_new_connection)
            menu.addAction(self.action_edit)
            menu.addAction(self.action_delete)

        elif item_type == 'table':
            menu.addAction(self.action_show_rows)
            menu.addSeparator()
            menu.addAction(self.action_new_sql)

        menu.exec(self.tree.mapToGlobal(pos))

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type = data.get('type')

        if item_type in ('connection', 'schema', 'table'):
            item.setExpanded(not item.isExpanded())

    def _on_current_changed(self, current: QTreeWidgetItem,
                            previous: QTreeWidgetItem) -> None:
        """Handle selection change."""
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'connection':
            self.connection_selected.emit(data.get('name'))

    def _get_connection_for_item(self, item: QTreeWidgetItem) -> Optional[str]:
        """Get connection name for any tree item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return None

        if data.get('type') == 'connection':
            return data.get('name')
        else:
            return data.get('connection')

    def _new_sql_for_selected(self) -> None:
        """Create new SQL tab for selected connection."""
        item = self.tree.currentItem()
        if item:
            connection_name = self._get_connection_for_item(item)
            if connection_name:
                self.new_sql_requested.emit(connection_name)

    def _new_spool_for_selected(self) -> None:
        """Create new spool tab for selected connection."""
        item = self.tree.currentItem()
        if item:
            connection_name = self._get_connection_for_item(item)
            if connection_name:
                self.new_spool_requested.emit(connection_name)

    def _show_rows_for_selected(self) -> None:
        """Show first 1000 rows for selected table."""
        item = self.tree.currentItem()
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'table':
            self.show_rows_requested.emit(
                data.get('connection'),
                data.get('schema'),
                data.get('table')
            )

    def _edit_selected(self) -> None:
        """Edit the selected connection."""
        item = self.tree.currentItem()
        if item:
            connection_name = self._get_connection_for_item(item)
            if connection_name:
                self.edit_connection_requested.emit(connection_name)

    def _delete_selected(self) -> None:
        """Delete the selected connection."""
        item = self.tree.currentItem()
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'connection':
            return

        connection_name = data.get('name')

        from PyQt6.QtWidgets import QMessageBox
        result = QMessageBox.question(
            self,
            "Delete Connection",
            f"Are you sure you want to delete '{connection_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if result == QMessageBox.StandardButton.Yes:
            delete_connection(connection_name)
            self.load_connections()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard navigation."""
        key = event.key()
        item = self.tree.currentItem()

        if not item:
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Right:
            if not item.isExpanded() and item.childCount() > 0:
                item.setExpanded(True)
            elif item.childCount() > 0:
                self.tree.setCurrentItem(item.child(0))
        elif key == Qt.Key.Key_Left:
            if item.isExpanded():
                item.setExpanded(False)
            elif item.parent():
                self.tree.setCurrentItem(item.parent())
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            item.setExpanded(not item.isExpanded())
        else:
            super().keyPressEvent(event)
