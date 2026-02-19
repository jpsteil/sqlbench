"""
Connection Editor Dialog for SQLBench PyQt6 GUI.

Provides interface for creating and editing database connections.
"""

from typing import Optional, Dict
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QSplitter,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QLabel,
    QGroupBox,
    QMessageBox,
    QFrame,
)

from ...database import (
    get_connections,
    get_connection,
    save_connection,
    delete_connection,
)
from ...adapters import get_available_adapters, get_adapter


class ConnectionDialog(QDialog):
    """Dialog for managing database connections."""

    def __init__(self, parent: Optional[QWidget] = None,
                 connection_name: Optional[str] = None):
        super().__init__(parent)

        self.setWindowTitle("Connections")
        self.setMinimumSize(700, 500)
        self.resize(800, 550)

        if parent is not None:
            pg = parent.frameGeometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

        self._current_connection: Optional[str] = None
        self._is_new = connection_name is None

        self._setup_ui()
        self._load_connections()

        if connection_name:
            self._select_connection(connection_name)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Connection list
        left_panel = self._create_list_panel()
        splitter.addWidget(left_panel)

        # Right: Connection form
        right_panel = self._create_form_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([200, 500])
        layout.addWidget(splitter)

    def _create_list_panel(self) -> QWidget:
        """Create the connection list panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 4, 8)

        # List
        self.conn_list = QListWidget()
        self.conn_list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.conn_list)

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_new = QPushButton("+")
        self.btn_new.setFixedWidth(32)
        self.btn_new.setToolTip("New connection")
        self.btn_new.clicked.connect(self._new_connection)
        btn_layout.addWidget(self.btn_new)

        self.btn_delete = QPushButton("−")
        self.btn_delete.setFixedWidth(32)
        self.btn_delete.setToolTip("Delete connection")
        self.btn_delete.clicked.connect(self._delete_connection)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return panel

    def _create_form_panel(self) -> QWidget:
        """Create the connection form panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 8, 8, 8)

        # Form
        form_group = QGroupBox("Connection Details")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(16, 16, 16, 16)

        # Name
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Connection name")
        form_layout.addRow("Name:", self.txt_name)

        # Type
        self.cmb_type = QComboBox()
        adapters = get_available_adapters()
        for adapter_name, available in adapters.items():
            display = adapter_name
            if not available:
                display += " (not installed)"
            self.cmb_type.addItem(display, adapter_name)
        self.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        form_layout.addRow("Type:", self.cmb_type)

        # Host
        self.txt_host = QLineEdit()
        self.txt_host.setPlaceholderText("hostname or IP address")
        form_layout.addRow("Host:", self.txt_host)

        # Port
        self.lbl_port = QLabel("Port:")
        self.txt_port = QLineEdit()
        self.txt_port.setPlaceholderText("port number")
        self.txt_port.setFixedWidth(100)
        form_layout.addRow(self.lbl_port, self.txt_port)

        # Database
        self.lbl_database = QLabel("Database:")
        self.txt_database = QLineEdit()
        self.txt_database.setPlaceholderText("database name")
        form_layout.addRow(self.lbl_database, self.txt_database)

        # User
        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("username")
        form_layout.addRow("User:", self.txt_user)

        # Password
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("password")
        form_layout.addRow("Password:", self.txt_password)

        # Options
        options_layout = QVBoxLayout()

        self.chk_production = QCheckBox("Production (confirm before destructive queries)")
        options_layout.addWidget(self.chk_production)

        self.chk_duplicate = QCheckBox("Duplicate protection (warn on repeated statements)")
        options_layout.addWidget(self.chk_duplicate)

        form_layout.addRow("Options:", options_layout)

        layout.addWidget(form_group)

        # Status
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self._test_connection)
        btn_layout.addWidget(self.btn_test)

        btn_layout.addStretch()

        self.btn_save = QPushButton("Save")
        self.btn_save.setProperty("primary", True)
        self.btn_save.clicked.connect(self._save_connection)
        btn_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        return panel

    def _load_connections(self) -> None:
        """Load connections into list."""
        self.conn_list.clear()

        connections = get_connections()
        for conn in connections:
            item = QListWidgetItem(conn['name'])
            item.setData(Qt.ItemDataRole.UserRole, conn['name'])
            self.conn_list.addItem(item)

    def _select_connection(self, name: str) -> None:
        """Select a connection in the list."""
        for i in range(self.conn_list.count()):
            item = self.conn_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self.conn_list.setCurrentItem(item)
                break

    def _on_selection_changed(self, row: int) -> None:
        """Handle connection selection change."""
        if row < 0:
            self._clear_form()
            return

        item = self.conn_list.item(row)
        name = item.data(Qt.ItemDataRole.UserRole)
        self._load_connection(name)

    def _load_connection(self, name: str) -> None:
        """Load connection details into form."""
        conn = get_connection(name)
        if not conn:
            return

        self._current_connection = name
        self._is_new = False

        self.txt_name.setText(conn.get('name', ''))
        self.txt_host.setText(conn.get('host', ''))
        self.txt_port.setText(str(conn.get('port', '')))
        self.txt_database.setText(conn.get('database', ''))
        self.txt_user.setText(conn.get('user', ''))
        self.txt_password.setText(conn.get('password', ''))
        self.chk_production.setChecked(conn.get('production', False))
        self.chk_duplicate.setChecked(conn.get('duplicate_protection', True))

        # Set type
        db_type = conn.get('db_type', '')
        for i in range(self.cmb_type.count()):
            if self.cmb_type.itemData(i) == db_type:
                self.cmb_type.setCurrentIndex(i)
                break

        self._on_type_changed()
        self._clear_status()

    def _clear_form(self) -> None:
        """Clear the form."""
        self._current_connection = None
        self.txt_name.clear()
        self.txt_host.clear()
        self.txt_port.clear()
        self.txt_database.clear()
        self.txt_user.clear()
        self.txt_password.clear()
        self.chk_production.setChecked(False)
        self.chk_duplicate.setChecked(True)
        self._clear_status()

    def _on_type_changed(self) -> None:
        """Handle database type change."""
        db_type = self.cmb_type.currentData()

        # IBM i doesn't use port/database
        is_ibmi = db_type == "ibmi"

        # Hide/show port and database fields with their labels
        self.txt_port.setVisible(not is_ibmi)
        self.txt_database.setVisible(not is_ibmi)
        self.lbl_port.setVisible(not is_ibmi)
        self.lbl_database.setVisible(not is_ibmi)

    def _new_connection(self) -> None:
        """Create a new connection."""
        self._clear_form()
        self._is_new = True
        self.txt_name.setFocus()
        self.conn_list.clearSelection()

    def _delete_connection(self) -> None:
        """Delete the selected connection."""
        if not self._current_connection:
            return

        result = QMessageBox.question(
            self,
            "Delete Connection",
            f"Delete connection '{self._current_connection}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if result == QMessageBox.StandardButton.Yes:
            delete_connection(self._current_connection)
            self._load_connections()
            self._clear_form()

    def _test_connection(self) -> None:
        """Test the current connection settings."""
        db_type = self.cmb_type.currentData()
        adapter = get_adapter(db_type)

        if not adapter:
            self._set_status(f"Adapter for {db_type} not available", error=True)
            return

        try:
            self._set_status("Testing connection...", error=False)

            port = self.txt_port.text()
            port = int(port) if port else None

            conn = adapter.connect(
                host=self.txt_host.text(),
                port=port,
                database=self.txt_database.text(),
                user=self.txt_user.text(),
                password=self.txt_password.text()
            )

            # Get version info
            version = adapter.get_version(conn)
            conn.close()

            self._set_status(f"Connected successfully!\n{version}", error=False)

        except Exception as e:
            self._set_status(f"Connection failed:\n{str(e)}", error=True)

    def _save_connection(self) -> None:
        """Save the current connection."""
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Connection name is required")
            return

        db_type = self.cmb_type.currentData()
        port = self.txt_port.text()

        conn_data = {
            'name': name,
            'db_type': db_type,
            'host': self.txt_host.text(),
            'port': int(port) if port else None,
            'database': self.txt_database.text(),
            'user': self.txt_user.text(),
            'password': self.txt_password.text(),
            'production': self.chk_production.isChecked(),
            'duplicate_protection': self.chk_duplicate.isChecked(),
        }

        # Check if renaming
        old_name = self._current_connection if not self._is_new else None

        save_connection(conn_data, old_name)
        self._current_connection = name
        self._is_new = False

        self._load_connections()
        self._select_connection(name)
        self._set_status("Connection saved", error=False)

    def _set_status(self, message: str, error: bool = False) -> None:
        """Set status message."""
        self.lbl_status.setText(message)
        if error:
            self.lbl_status.setStyleSheet("color: #f14c4c;")
        else:
            self.lbl_status.setStyleSheet("color: #4ec9b0;")

    def _clear_status(self) -> None:
        """Clear status message."""
        self.lbl_status.clear()
