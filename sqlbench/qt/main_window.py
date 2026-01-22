"""
Main application window for SQLBench PyQt6 GUI.

Provides the primary interface with menu bar, connection tree,
and tabbed query/spool interface.
"""

from typing import Optional, Dict, Any
from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QSplitter,
    QVBoxLayout,
    QStatusBar,
    QMessageBox,
    QApplication,
)

from .theme import Theme
from .connection_tree import ConnectionTreeWidget
from .tab_widget import TabContainer
from .icons import get_db_icon
from ..database import get_setting, set_setting, get_connections, get_connection, _get_db


class MainWindow(QMainWindow):
    """Main application window."""

    theme_changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setWindowTitle("SQLBench")
        self.setMinimumSize(1024, 600)

        # Load theme preference
        dark_mode = get_setting("dark_mode", "1") == "1"
        Theme.set_dark(dark_mode)
        Theme.apply(QApplication.instance())

        # Track active connections
        self._connections: Dict[str, Any] = {}

        # Build UI
        self._create_actions()
        self._create_menu_bar()
        self._create_central_widget()
        self._create_status_bar()

        # Restore window state
        self._restore_state()

        # Connect theme change signal
        self.theme_changed.connect(self._on_theme_changed)

    def _create_actions(self) -> None:
        """Create menu actions."""
        # File menu actions
        self.action_dark_mode = QAction("Dark Mode", self)
        self.action_dark_mode.setCheckable(True)
        self.action_dark_mode.setChecked(Theme.is_dark())
        self.action_dark_mode.triggered.connect(self._toggle_dark_mode)

        self.action_settings = QAction("Settings...", self)
        self.action_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.action_settings.triggered.connect(self._show_settings)

        self.action_reset_layout = QAction("Reset Layout", self)
        self.action_reset_layout.triggered.connect(self._reset_layout)

        self.action_exit = QAction("Exit", self)
        self.action_exit.setShortcut(QKeySequence("Alt+F4"))
        self.action_exit.triggered.connect(self.close)

        # Help menu actions
        self.action_about = QAction("About", self)
        self.action_about.triggered.connect(self._show_about)

    def _create_menu_bar(self) -> None:
        """Create the menu bar."""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.action_dark_mode)
        file_menu.addSeparator()
        file_menu.addAction(self.action_settings)
        file_menu.addAction(self.action_reset_layout)
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction(self.action_about)

    def _create_central_widget(self) -> None:
        """Create the main content area."""
        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(3)
        self.splitter.setChildrenCollapsible(False)

        # Left panel - Connection tree
        self.connection_tree = ConnectionTreeWidget()
        self.connection_tree.connection_selected.connect(self._on_connection_selected)
        self.connection_tree.connect_requested.connect(self._on_connect_requested)
        self.connection_tree.disconnect_requested.connect(self._on_disconnect_requested)
        self.connection_tree.new_sql_requested.connect(self._on_new_sql_tab)
        self.connection_tree.new_spool_requested.connect(self._on_new_spool_tab)
        self.connection_tree.show_rows_requested.connect(self._on_show_rows)
        self.connection_tree.edit_connection_requested.connect(self._on_edit_connection)
        self.connection_tree.new_connection_requested.connect(self._on_new_connection)

        # Right panel - Tab container
        self.tab_container = TabContainer()

        # Add to splitter
        self.splitter.addWidget(self.connection_tree)
        self.splitter.addWidget(self.tab_container)

        # Set initial sizes (20% / 80%)
        self.splitter.setSizes([250, 1000])

        self.setCentralWidget(self.splitter)

    def _create_status_bar(self) -> None:
        """Create the status bar."""
        self.status_bar = QStatusBar()
        self.status_bar.setFixedHeight(22)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _restore_state(self) -> None:
        """Restore window geometry and state."""
        settings = QSettings("SQLBench", "SQLBench")

        # Restore geometry
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # Default size
            self.resize(1400, 900)
            # Center on screen
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2
            )

        # Restore splitter sizes
        splitter_sizes = settings.value("splitter_sizes")
        if splitter_sizes:
            self.splitter.setSizes([int(s) for s in splitter_sizes])

        # Restore connections and tabs after window is shown
        QTimer.singleShot(100, self._restore_session)

    def _restore_session(self) -> None:
        """Restore previous session (connections, tabs)."""
        # Load connections into tree
        self.connection_tree.load_connections()

        # Restore open tabs
        try:
            db = _get_db()
            saved_tabs = db.get_saved_tabs()
            for tab_info in saved_tabs:
                tab_type = tab_info.get('tab_type')
                connection_name = tab_info.get('connection_name')
                tab_data = tab_info.get('tab_data', '')

                if tab_type == 'sql':
                    self._on_new_sql_tab(connection_name)
                    # Restore SQL content
                    if tab_data and self.tab_container.count() > 0:
                        tab = self.tab_container.widget(self.tab_container.count() - 1)
                        if hasattr(tab, 'set_sql'):
                            tab.set_sql(tab_data)
                elif tab_type == 'spool':
                    self._on_new_spool_tab(connection_name)
        except Exception:
            pass  # Ignore errors restoring tabs

    def _save_state(self) -> None:
        """Save window geometry and state."""
        settings = QSettings("SQLBench", "SQLBench")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("splitter_sizes", self.splitter.sizes())

        # Save dark mode preference
        set_setting("dark_mode", "1" if Theme.is_dark() else "0")

        # Save open tabs
        try:
            tabs_to_save = []
            for i in range(self.tab_container.count()):
                tab = self.tab_container.widget(i)
                if hasattr(tab, 'connection_name'):
                    tab_info = {
                        'type': 'spool' if hasattr(tab, 'refresh_files') else 'sql',
                        'connection': tab.connection_name,
                        'data': ''
                    }
                    # Save SQL content for SQL tabs
                    if hasattr(tab, 'editor'):
                        tab_info['data'] = tab.editor.toPlainText()
                    tabs_to_save.append(tab_info)

            db = _get_db()
            db.save_tabs(tabs_to_save)
        except Exception:
            pass  # Ignore errors saving tabs

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close."""
        self._save_state()

        # Close all connections
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass

        event.accept()

    def _toggle_dark_mode(self) -> None:
        """Toggle dark/light mode."""
        Theme.toggle(QApplication.instance())
        self.action_dark_mode.setChecked(Theme.is_dark())
        self.theme_changed.emit()

    def _on_theme_changed(self) -> None:
        """Handle theme change - update child widgets."""
        # Update syntax highlighters
        for i in range(self.tab_container.count()):
            tab = self.tab_container.widget(i)
            if hasattr(tab, 'update_theme'):
                tab.update_theme()

    def _show_settings(self) -> None:
        """Show settings dialog."""
        from .dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec():
            # Apply settings
            pass

    def _reset_layout(self) -> None:
        """Reset window layout to defaults."""
        self.splitter.setSizes([250, 1000])
        self.resize(1400, 900)

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

        set_setting("font_size", "13")
        self.status_bar.showMessage("Layout reset to defaults", 3000)

    def _show_about(self) -> None:
        """Show about dialog."""
        from ..version import __version__
        QMessageBox.about(
            self,
            "About SQLBench",
            f"<h3>SQLBench</h3>"
            f"<p>Version {__version__}</p>"
            f"<p>A professional database query tool.</p>"
            f"<p>Supports IBM i, MySQL, and PostgreSQL.</p>"
        )

    def _on_connection_selected(self, connection_name: str) -> None:
        """Handle connection selection in tree."""
        self.status_bar.showMessage(f"Selected: {connection_name}")

    def _on_connect_requested(self, connection_name: str) -> None:
        """Handle request to connect to a database."""
        self._connect(connection_name)

    def _on_disconnect_requested(self, connection_name: str) -> None:
        """Handle request to disconnect from a database."""
        self.disconnect(connection_name)

    def _on_new_sql_tab(self, connection_name: str) -> None:
        """Create new SQL tab for connection."""
        from .tabs.sql_tab import SQLTab

        # Get or create connection
        if connection_name not in self._connections:
            self._connect(connection_name)

        connection = self._connections.get(connection_name)
        if connection:
            tab = SQLTab(connection_name, connection, self)
            index = self.tab_container.add_tab(tab, f"{connection_name} SQL")

            # Set tab icon based on database type
            conn_info = get_connection(connection_name)
            if conn_info:
                db_type = conn_info.get('db_type', '')
                self.tab_container.setTabIcon(index, get_db_icon(db_type))

            self.theme_changed.connect(tab.update_theme)

    def _on_new_spool_tab(self, connection_name: str) -> None:
        """Create new spool tab for IBM i connection."""
        from .tabs.spool_tab import SpoolTab

        if connection_name not in self._connections:
            self._connect(connection_name)

        connection = self._connections.get(connection_name)
        if connection:
            tab = SpoolTab(connection_name, connection, self)
            index = self.tab_container.add_tab(tab, f"{connection_name} Spool")

            # IBM i spool tab - set icon
            self.tab_container.setTabIcon(index, get_db_icon('ibmi'))

    def _on_show_rows(self, connection_name: str, schema: str, table: str) -> None:
        """Show first 1000 rows of a table."""
        from .tabs.sql_tab import SQLTab

        if connection_name not in self._connections:
            self._connect(connection_name)

        connection = self._connections.get(connection_name)
        if connection:
            tab = SQLTab(connection_name, connection, self)
            index = self.tab_container.add_tab(tab, f"{connection_name} SQL")

            # Set tab icon based on database type
            conn_info = get_connection(connection_name)
            if conn_info:
                db_type = conn_info.get('db_type', '')
                self.tab_container.setTabIcon(index, get_db_icon(db_type))

            self.theme_changed.connect(tab.update_theme)

            # Set SQL and execute
            if schema:
                sql = f"SELECT * FROM {schema}.{table}"
            else:
                sql = f"SELECT * FROM {table}"
            tab.set_sql(sql)
            tab.execute_query()

    def _on_edit_connection(self, connection_name: Optional[str] = None) -> None:
        """Show connection editor dialog."""
        from .dialogs.connection_dialog import ConnectionDialog
        dialog = ConnectionDialog(self, connection_name)
        if dialog.exec():
            self.connection_tree.load_connections()

    def _on_new_connection(self) -> None:
        """Create new connection."""
        self._on_edit_connection(None)

    def _connect(self, connection_name: str) -> bool:
        """Establish connection to database."""
        from ..database import get_connection
        from ..adapters import get_adapter

        try:
            conn_info = get_connection(connection_name)
            if not conn_info:
                QMessageBox.warning(
                    self,
                    "Connection Error",
                    f"Connection '{connection_name}' not found."
                )
                return False

            adapter = get_adapter(conn_info['db_type'])
            if not adapter:
                QMessageBox.warning(
                    self,
                    "Connection Error",
                    f"No adapter available for {conn_info['db_type']}."
                )
                return False

            self.status_bar.showMessage(f"Connecting to {connection_name}...")
            QApplication.processEvents()

            connection = adapter.connect(
                host=conn_info['host'],
                port=conn_info.get('port'),
                database=conn_info.get('database'),
                user=conn_info['user'],
                password=conn_info['password']
            )

            self._connections[connection_name] = connection
            self.connection_tree.set_connected(connection_name, True)
            self.status_bar.showMessage(f"Connected to {connection_name}", 3000)
            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Failed to connect to {connection_name}:\n{str(e)}"
            )
            self.status_bar.showMessage("Connection failed", 3000)
            return False

    def disconnect(self, connection_name: str) -> None:
        """Disconnect from database."""
        if connection_name in self._connections:
            try:
                self._connections[connection_name].close()
            except Exception:
                pass
            del self._connections[connection_name]
            self.connection_tree.set_connected(connection_name, False)
            self.status_bar.showMessage(f"Disconnected from {connection_name}", 3000)

    def set_status(self, message: str, timeout: int = 0) -> None:
        """Set status bar message."""
        self.status_bar.showMessage(message, timeout)

    def get_connection(self, name: str) -> Optional[Any]:
        """Get active connection by name."""
        return self._connections.get(name)
