"""
Main application window for SQLBench PyQt6 GUI.

Provides the primary interface with menu bar, connection tree,
and tabbed query/spool interface.
"""

import subprocess
import threading
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

        from ..version import __version__
        self.setWindowTitle(f"SQLBench v{__version__}")
        self.setMinimumSize(1024, 600)

        # Load theme preference
        dark_mode = get_setting("dark_mode", "1") == "1"
        Theme.set_dark(dark_mode)
        Theme.apply(QApplication.instance())

        # Track active connections (credentials only, no persistent connection objects)
        self._conn_infos: Dict[str, Dict] = {}
        self._adapters: Dict[str, Any] = {}
        self._db_types: Dict[str, str] = {}

        # Build UI
        self._create_actions()
        self._create_menu_bar()
        self._create_central_widget()
        self._create_status_bar()

        # Restore window state
        self._restore_state()

        # Connect theme change signal
        self.theme_changed.connect(self._on_theme_changed)

        # Check for updates after startup
        QTimer.singleShot(500, self._check_for_updates)

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

        # Restore main splitter from ratio
        ratio_str = get_setting("layout_main_ratio")
        if ratio_str:
            try:
                ratio = float(ratio_str)
                if 0.05 <= ratio <= 0.95:
                    total = self.width()
                    self.splitter.setSizes([int(ratio * total), int((1 - ratio) * total)])
            except (ValueError, TypeError):
                pass

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

        # Restore per-tab splitter ratios
        self._restore_tab_layouts()

        # Auto-connect last used connection
        last_conn = get_setting("last_connection")
        if last_conn and last_conn not in self._conn_infos:
            conn_info = get_connection(last_conn)
            if conn_info:
                self._connect(last_conn)

    def _save_state(self) -> None:
        """Save window geometry and state."""
        settings = QSettings("SQLBench", "SQLBench")
        settings.setValue("geometry", self.saveGeometry())

        # Save main splitter as ratio
        sizes = self.splitter.sizes()
        total = sum(sizes)
        if total > 100:
            ratio = sizes[0] / total
            set_setting("layout_main_ratio", f"{ratio:.4f}")

        # Save per-tab splitter ratios (one SQL, one spool)
        for i in range(self.tab_container.count()):
            tab = self.tab_container.widget(i)
            if hasattr(tab, 'splitter'):
                tab_sizes = tab.splitter.sizes()
                tab_total = sum(tab_sizes)
                if tab_total > 100:
                    tab_ratio = tab_sizes[0] / tab_total
                    if hasattr(tab, 'refresh_files'):
                        set_setting("layout_spool_ratio", f"{tab_ratio:.4f}")
                    else:
                        set_setting("layout_sql_ratio", f"{tab_ratio:.4f}")

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
        # Check for unsaved changes in any SQL tab
        unsaved_tabs = []
        for i in range(self.tab_container.count()):
            tab = self.tab_container.widget(i)
            if hasattr(tab, 'has_unsaved_changes') and tab.has_unsaved_changes():
                unsaved_tabs.append(self.tab_container.tabText(i))

        if unsaved_tabs:
            msg = QMessageBox(
                QMessageBox.Icon.Warning, "Unsaved Changes",
                f"You have unsaved changes in: {', '.join(unsaved_tabs)}",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                self)
            msg.setDefaultButton(QMessageBox.StandardButton.Save)
            msg.layout().activate()
            msg.adjustSize()
            fg = self.frameGeometry()
            ds = msg.sizeHint()
            msg.setGeometry(
                fg.x() + (fg.width() - ds.width()) // 2,
                fg.y() + (fg.height() - ds.height()) // 2,
                ds.width(), ds.height(),
            )
            msg.setAttribute(Qt.WidgetAttribute.WA_Moved, True)
            result = msg.exec()
            if result == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if result == QMessageBox.StandardButton.Save:
                for i in range(self.tab_container.count()):
                    tab = self.tab_container.widget(i)
                    if hasattr(tab, 'has_unsaved_changes') and tab.has_unsaved_changes():
                        tab._save_changes()

        self._save_state()
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
            self._apply_font_size()

    def _apply_font_size(self) -> None:
        """Apply current font size setting to all open tabs."""
        from .tabs.sql_tab import SQLTab
        size = int(get_setting("font_size", "13"))
        for i in range(self.tab_container.count()):
            tab = self.tab_container.widget(i)
            if isinstance(tab, SQLTab):
                tab.set_font_size(size)
        self.status_bar.showMessage(f"Font size set to {size}", 3000)

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
        self._apply_font_size()
        self.status_bar.showMessage("Layout reset to defaults", 3000)

    def _restore_tab_layouts(self) -> None:
        """Restore per-tab splitter ratios."""
        sql_ratio_str = get_setting("layout_sql_ratio")
        spool_ratio_str = get_setting("layout_spool_ratio")

        for i in range(self.tab_container.count()):
            tab = self.tab_container.widget(i)
            if not hasattr(tab, 'splitter'):
                continue
            try:
                if hasattr(tab, 'refresh_files') and spool_ratio_str:
                    ratio = float(spool_ratio_str)
                elif sql_ratio_str:
                    ratio = float(sql_ratio_str)
                else:
                    continue
                if 0.1 <= ratio <= 0.9:
                    total = sum(tab.splitter.sizes()) or tab.height()
                    if total > 100:
                        tab.splitter.setSizes([int(ratio * total), int((1 - ratio) * total)])
            except (ValueError, TypeError):
                pass

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
        """Handle request to activate a connection (verify credentials)."""
        self._connect(connection_name)

    def _on_new_sql_tab(self, connection_name: str) -> None:
        """Create new SQL tab for connection."""
        from .tabs.sql_tab import SQLTab

        # Ensure connection is activated
        if connection_name not in self._conn_infos:
            self._connect(connection_name)

        conn_info = self._conn_infos.get(connection_name)
        if conn_info:
            adapter = self._adapters.get(connection_name)
            db_type = self._db_types.get(connection_name, '')
            tab = SQLTab(connection_name, conn_info, adapter, db_type, self)
            index = self.tab_container.add_tab(tab, f"{connection_name} SQL")

            # Set tab icon based on database type
            self.tab_container.setTabIcon(index, get_db_icon(db_type))

            self.theme_changed.connect(tab.update_theme)

    def _on_new_spool_tab(self, connection_name: str) -> None:
        """Create new spool tab for IBM i connection."""
        from .tabs.spool_tab import SpoolTab

        if connection_name not in self._conn_infos:
            self._connect(connection_name)

        conn_info = self._conn_infos.get(connection_name)
        if conn_info:
            adapter = self._adapters.get(connection_name)
            tab = SpoolTab(connection_name, conn_info, adapter, self)
            index = self.tab_container.add_tab(tab, f"{connection_name} Spool")

            # IBM i spool tab - set icon
            self.tab_container.setTabIcon(index, get_db_icon('ibmi'))

    def _on_show_rows(self, connection_name: str, schema: str, table: str) -> None:
        """Show first 1000 rows of a table."""
        from .tabs.sql_tab import SQLTab

        if connection_name not in self._conn_infos:
            self._connect(connection_name)

        conn_info = self._conn_infos.get(connection_name)
        if conn_info:
            adapter = self._adapters.get(connection_name)
            db_type = self._db_types.get(connection_name, '')
            tab = SQLTab(connection_name, conn_info, adapter, db_type, self)
            index = self.tab_container.add_tab(tab, f"{connection_name} SQL")

            # Set tab icon based on database type
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
        old_name = connection_name
        dialog = ConnectionDialog(self, connection_name)
        if dialog.exec():
            self.connection_tree.load_connections()
            if old_name:
                self._update_tab_names(old_name)

    def _on_new_connection(self) -> None:
        """Create new connection."""
        self._on_edit_connection(None)

    def _connect(self, connection_name: str) -> bool:
        """Verify connection credentials and activate connection."""
        from ..database import get_connection
        from ..adapters import get_adapter, connect_from_info

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

            # Test connection then close immediately
            test_conn = connect_from_info(adapter, conn_info)
            test_conn.close()

            # Store credentials (no persistent connection)
            self._conn_infos[connection_name] = conn_info
            self._adapters[connection_name] = adapter
            self._db_types[connection_name] = conn_info['db_type']
            self.connection_tree.set_connected(connection_name, True)
            set_setting("last_connection", connection_name)
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
        """Deactivate connection."""
        self._conn_infos.pop(connection_name, None)
        self._adapters.pop(connection_name, None)
        self._db_types.pop(connection_name, None)
        self.connection_tree.set_connected(connection_name, False)
        self.status_bar.showMessage(f"Disconnected from {connection_name}", 3000)

    def _update_tab_names(self, old_name: str) -> None:
        """Update tab names if a connection was renamed."""
        # Check if old name still exists — if so, no rename happened
        conn = get_connection(old_name)
        if conn:
            return

        if old_name not in self._conn_infos:
            return

        # Find the new name: look for a connection name we don't recognize
        known_names = set(self._conn_infos.keys())
        new_name = None
        for c in get_connections():
            if c['name'] not in known_names:
                new_name = c['name']
                break

        if not new_name or new_name == old_name:
            return

        # Update dicts
        self._conn_infos[new_name] = self._conn_infos.pop(old_name)
        if old_name in self._adapters:
            self._adapters[new_name] = self._adapters.pop(old_name)
        if old_name in self._db_types:
            self._db_types[new_name] = self._db_types.pop(old_name)

        # Update all tabs
        for i in range(self.tab_container.count()):
            tab = self.tab_container.widget(i)
            if hasattr(tab, 'connection_name') and tab.connection_name == old_name:
                tab.connection_name = new_name
                tab.conn_info = self._conn_infos[new_name]
                current_text = self.tab_container.tabText(i)
                new_text = current_text.replace(old_name, new_name)
                self.tab_container.setTabText(i, new_text)
                if hasattr(tab, 'lbl_connection'):
                    tab.lbl_connection.setText(new_name)

        # Update last_connection if it was the renamed one
        if get_setting("last_connection") == old_name:
            set_setting("last_connection", new_name)

        self.connection_tree.set_connected(new_name, True)
        self.status_bar.showMessage(f"Renamed: {old_name} → {new_name}", 3000)

    def _check_for_updates(self) -> None:
        """Check for updates in background."""
        from ..version import get_pypi_version, is_newer_version, __version__

        def do_check():
            try:
                latest = get_pypi_version()
                if latest and is_newer_version(latest, __version__):
                    self._update_version = latest
            except Exception:
                pass

        def on_done():
            version = getattr(self, '_update_version', None)
            if version:
                self._show_update_dialog(version)

        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()
        # Poll from main thread until the background check completes
        QTimer.singleShot(3000, on_done)

    def _show_update_dialog(self, latest_version: str) -> None:
        """Show update available dialog."""
        from ..version import __version__
        result = QMessageBox.question(
            self, "Update Available",
            f"A new version of SQLBench is available.\n\n"
            f"Installed: {__version__}\n"
            f"Latest: {latest_version}\n\n"
            f"Would you like to upgrade now?\n\n"
            f"(This will run: pipx upgrade sqlbench)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if result == QMessageBox.StandardButton.Yes:
            self._run_upgrade()

    def _run_upgrade(self) -> None:
        """Run pipx upgrade in background."""
        self._upgrade_result = None  # (success: bool, message: str)

        def do_upgrade():
            try:
                result = subprocess.run(
                    ["pipx", "upgrade", "sqlbench"],
                    capture_output=True, text=True,
                    stdin=subprocess.DEVNULL, timeout=120)
                if result.returncode == 0:
                    self._upgrade_result = (True, "SQLBench has been upgraded.\nPlease restart to use the new version.")
                else:
                    error = result.stderr or result.stdout or "Unknown error"
                    self._upgrade_result = (False, f"Failed to upgrade:\n{error}")
            except subprocess.TimeoutExpired:
                self._upgrade_result = (False, "Upgrade timed out. Please upgrade manually:\n\npipx upgrade sqlbench")
            except FileNotFoundError:
                self._upgrade_result = (False, "pipx not found. Please upgrade manually:\n\npipx upgrade sqlbench")
            except Exception as e:
                self._upgrade_result = (False, f"Failed to upgrade:\n{e}")

        def poll_result():
            result = self._upgrade_result
            if result is None:
                QTimer.singleShot(500, poll_result)
                return
            success, message = result
            self.status_bar.showMessage("Upgrade complete" if success else "Upgrade failed", 3000)
            if success:
                result = QMessageBox.question(
                    self, "Upgrade Complete",
                    "SQLBench has been upgraded.\n\nWould you like to restart now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if result == QMessageBox.StandardButton.Yes:
                    self._restart_app()
            else:
                QMessageBox.warning(self, "Upgrade Failed", message)

        self.status_bar.showMessage("Upgrading SQLBench...")
        thread = threading.Thread(target=do_upgrade, daemon=True)
        thread.start()
        QTimer.singleShot(2000, poll_result)

    def _restart_app(self) -> None:
        """Restart the application."""
        import sys
        import os

        # Save window state
        self._save_state()

        # Start new process before closing
        if sys.argv[0].endswith('sqlbench') or 'sqlbench' in sys.argv[0]:
            subprocess.Popen([sys.argv[0]])
        else:
            subprocess.Popen([sys.executable, '-m', 'sqlbench'])

        self.close()
        os._exit(0)

    def set_status(self, message: str, timeout: int = 0) -> None:
        """Set status bar message."""
        self.status_bar.showMessage(message, timeout)

    def get_conn_info(self, name: str) -> Optional[Dict]:
        """Get connection info by name."""
        return self._conn_infos.get(name)

    def get_adapter(self, name: str) -> Optional[Any]:
        """Get adapter for a connection by name."""
        return self._adapters.get(name)
