"""
SQL Tab Widget for SQLBench PyQt6 GUI.

Provides SQL editor with syntax highlighting and results display.
"""

import re
import time
from typing import Optional, Any, List, Tuple
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import (
    QFont,
    QTextCursor,
    QKeySequence,
    QShortcut,
    QAction,
    QColor,
    QIcon,
    QPainter,
    QPixmap,
    QPen,
    QPainterPath,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QLabel,
    QSpinBox,
    QCheckBox,
    QLineEdit,
    QPushButton,
    QToolButton,
    QComboBox,
    QMenu,
    QFileDialog,
    QMessageBox,
    QHeaderView,
    QAbstractItemView,
    QApplication,
    QFrame,
)

from ..syntax import SQLHighlighter
from ..theme import Theme
from ...database import get_setting, set_setting, _get_db, get_connection


def _make_icon(shape: str, color: str = "#ddd", size: int = 18) -> QIcon:
    """Create a simple painted icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    m = size  # shorthand

    if shape == "play":
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.moveTo(m * 0.2, m * 0.1)
        path.lineTo(m * 0.85, m * 0.5)
        path.lineTo(m * 0.2, m * 0.9)
        path.closeSubpath()
        p.drawPath(path)

    elif shape == "play_all":
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        path1 = QPainterPath()
        path1.moveTo(m * 0.1, m * 0.15)
        path1.lineTo(m * 0.5, m * 0.5)
        path1.lineTo(m * 0.1, m * 0.85)
        path1.closeSubpath()
        p.drawPath(path1)
        path2 = QPainterPath()
        path2.moveTo(m * 0.45, m * 0.15)
        path2.lineTo(m * 0.85, m * 0.5)
        path2.lineTo(m * 0.45, m * 0.85)
        path2.closeSubpath()
        p.drawPath(path2)

    elif shape == "stop":
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(int(m * 0.2), int(m * 0.2), int(m * 0.6), int(m * 0.6))

    elif shape == "save":
        pen = QPen(c, 1.5)
        p.setPen(pen)
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawRect(int(m * 0.1), int(m * 0.05), int(m * 0.8), int(m * 0.9))
        p.drawRect(int(m * 0.3), int(m * 0.05), int(m * 0.35), int(m * 0.3))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRect(int(m * 0.25), int(m * 0.55), int(m * 0.5), int(m * 0.3))

    elif shape == "open":
        pen = QPen(c, 1.5)
        p.setPen(pen)
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawRect(int(m * 0.05), int(m * 0.3), int(m * 0.9), int(m * 0.6))
        p.drawLine(int(m * 0.05), int(m * 0.3), int(m * 0.05), int(m * 0.15))
        p.drawLine(int(m * 0.05), int(m * 0.15), int(m * 0.4), int(m * 0.15))
        p.drawLine(int(m * 0.4), int(m * 0.15), int(m * 0.5), int(m * 0.3))

    elif shape == "clear":
        pen = QPen(c, 2.0)
        p.setPen(pen)
        p.drawLine(int(m * 0.2), int(m * 0.2), int(m * 0.8), int(m * 0.8))
        p.drawLine(int(m * 0.8), int(m * 0.2), int(m * 0.2), int(m * 0.8))

    elif shape == "format":
        pen = QPen(c, 1.5)
        p.setPen(pen)
        p.drawLine(int(m * 0.1), int(m * 0.2), int(m * 0.9), int(m * 0.2))
        p.drawLine(int(m * 0.25), int(m * 0.4), int(m * 0.9), int(m * 0.4))
        p.drawLine(int(m * 0.25), int(m * 0.6), int(m * 0.9), int(m * 0.6))
        p.drawLine(int(m * 0.1), int(m * 0.8), int(m * 0.9), int(m * 0.8))

    p.end()
    return QIcon(pixmap)


class QueryWorker(QThread):
    """Background thread for query execution."""

    finished = pyqtSignal(object, object, float, float, int)  # results, description, exec_time, fetch_time, total_rows
    error = pyqtSignal(str)
    row_count = pyqtSignal(int)

    def __init__(self, conn_info: dict, sql: str, adapter: Any = None,
                 limit: int = 1000, offset: int = 0,
                 fetch_all: bool = False, run_count: bool = True):
        super().__init__()
        self.conn_info = conn_info
        self.sql = sql
        self.adapter = adapter
        self.limit = limit
        self.offset = offset
        self.fetch_all = fetch_all
        self.run_count = run_count
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation."""
        self._cancelled = True

    @staticmethod
    def _has_limit_clause(sql_upper: str) -> bool:
        """Check if SQL already has a row limit clause."""
        return any(kw in sql_upper for kw in
                   ["FETCH FIRST", "FETCH NEXT", "LIMIT ", "OFFSET "])

    def run(self) -> None:
        """Execute query in background."""
        from ...adapters import connect_from_info
        conn = None
        try:
            conn = connect_from_info(self.adapter, self.conn_info)
            cursor = conn.cursor()

            sql_stripped = self.sql.strip()
            while sql_stripped.endswith(';'):
                sql_stripped = sql_stripped[:-1].strip()
            sql_upper = sql_stripped.upper()
            is_select = sql_upper.startswith("SELECT")

            # Run COUNT query first for SELECT statements
            total_rows = 0
            if (is_select and self.run_count and self.adapter
                    and not self._has_limit_clause(sql_upper)):
                try:
                    count_sql = self.adapter.get_count_sql(sql_stripped)
                    cursor.execute(count_sql)
                    total_rows = cursor.fetchone()[0]
                except Exception:
                    pass  # Count failed, continue without total
                if self._cancelled:
                    cursor.close()
                    return

            # Build paginated query for SELECT
            if (is_select and self.adapter and not self.fetch_all
                    and not self._has_limit_clause(sql_upper)):
                executed_sql = self.adapter.add_pagination(
                    sql_stripped, self.limit, self.offset)
            else:
                executed_sql = sql_stripped

            exec_start = time.time()
            cursor.execute(executed_sql)
            exec_time = time.time() - exec_start

            if self._cancelled:
                cursor.close()
                return

            fetch_start = time.time()

            if cursor.description:
                rows = cursor.fetchall()
                description = cursor.description
                if total_rows == 0:
                    total_rows = len(rows)
            else:
                rows = []
                description = None
                self.row_count.emit(cursor.rowcount)

            fetch_time = time.time() - fetch_start
            cursor.close()

            if not self._cancelled:
                self.finished.emit(rows, description, exec_time, fetch_time, total_rows)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


class ScriptWorker(QThread):
    """Background thread for executing multiple SQL statements."""

    all_finished = pyqtSignal(list, float)  # results_list, total_time
    error = pyqtSignal(str)

    def __init__(self, conn_info: dict, adapter: Any, statements: List[str]):
        super().__init__()
        self.conn_info = conn_info
        self.adapter = adapter
        self.statements = statements
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation."""
        self._cancelled = True

    def run(self) -> None:
        """Execute all statements sequentially."""
        from ...adapters import connect_from_info
        conn = None
        try:
            conn = connect_from_info(self.adapter, self.conn_info)
            results = []
            total_start = time.time()

            for i, stmt in enumerate(self.statements):
                if self._cancelled:
                    break

                stmt_stripped = stmt.strip()
                if not stmt_stripped:
                    continue
                while stmt_stripped.endswith(';'):
                    stmt_stripped = stmt_stripped[:-1].strip()
                if not stmt_stripped:
                    continue

                result = {
                    "stmt": i + 1,
                    "sql": stmt_stripped[:200] + ('...' if len(stmt_stripped) > 200 else ''),
                    "full_sql": stmt_stripped,
                    "status": "",
                    "time": 0.0,
                    "row_count": 0,
                    "success": True,
                    "error": None,
                }

                try:
                    cursor = conn.cursor()
                    start = time.time()
                    cursor.execute(stmt_stripped)
                    elapsed = time.time() - start

                    if cursor.description:
                        rows = cursor.fetchall()
                        result["row_count"] = len(rows)
                        result["status"] = f"{len(rows)} row(s) returned"
                    else:
                        rc = cursor.rowcount if cursor.rowcount >= 0 else 0
                        result["row_count"] = rc
                        sql_upper = stmt_stripped.upper()
                        if sql_upper.startswith("INSERT"):
                            result["status"] = f"{rc} row(s) inserted"
                        elif sql_upper.startswith("UPDATE"):
                            result["status"] = f"{rc} row(s) updated"
                        elif sql_upper.startswith("DELETE"):
                            result["status"] = f"{rc} row(s) deleted"
                        else:
                            result["status"] = f"OK ({rc} row(s) affected)"
                        try:
                            conn.commit()
                        except Exception:
                            pass

                    result["time"] = elapsed
                    cursor.close()

                except Exception as e:
                    result["success"] = False
                    result["status"] = "ERROR"
                    result["error"] = str(e)
                    result["time"] = time.time() - start
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                results.append(result)

            total_time = time.time() - total_start

            if not self._cancelled:
                self.all_finished.emit(results, total_time)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


class SQLEditor(QPlainTextEdit):
    """SQL code editor with syntax highlighting."""

    execute_requested = pyqtSignal()
    execute_all_requested = pyqtSignal()
    find_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Setup font
        self._font_size = int(get_setting("font_size", "12"))
        font = QFont("JetBrains Mono", self._font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # Setup highlighter
        self.highlighter = SQLHighlighter(self.document())

        # Configure editor
        self.setTabStopDistance(40)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Shortcuts
        self._setup_shortcuts()

    def _show_context_menu(self, pos) -> None:
        """Show context menu."""
        menu = QMenu(self)

        undo_action = menu.addAction("Undo", self.undo, QKeySequence("Ctrl+Z"))
        undo_action.setEnabled(self.document().isUndoAvailable())
        redo_action = menu.addAction("Redo", self.redo, QKeySequence("Ctrl+Y"))
        redo_action.setEnabled(self.document().isRedoAvailable())
        menu.addSeparator()
        menu.addAction("Cut", self.cut, QKeySequence("Ctrl+X"))
        menu.addAction("Copy", self.copy, QKeySequence("Ctrl+C"))
        menu.addAction("Paste", self.paste, QKeySequence("Ctrl+V"))
        menu.addSeparator()
        menu.addAction("Select All", self.selectAll, QKeySequence("Ctrl+A"))
        menu.addSeparator()
        menu.addAction("Find...", self.find_requested.emit, QKeySequence("Ctrl+F"))

        menu.exec(self.mapToGlobal(pos))

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts."""
        # F5 - Execute
        shortcut_exec = QShortcut(QKeySequence("F5"), self)
        shortcut_exec.activated.connect(self.execute_requested.emit)

        # Ctrl+F5 - Execute All
        shortcut_exec_all = QShortcut(QKeySequence("Ctrl+F5"), self)
        shortcut_exec_all.activated.connect(self.execute_all_requested.emit)

        # Ctrl+Z - Undo
        shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        shortcut_undo.activated.connect(self.undo)

        # Ctrl+Y or Ctrl+Shift+Z - Redo
        shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        shortcut_redo.activated.connect(self.redo)
        shortcut_redo2 = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        shortcut_redo2.activated.connect(self.redo)

    def update_theme(self) -> None:
        """Update colors when theme changes."""
        self.highlighter.update_theme()

    def set_font_size(self, size: int) -> None:
        """Set the editor font size."""
        self._font_size = size
        font = self.font()
        font.setPointSize(size)
        self.setFont(font)

    def get_statement_at_cursor(self) -> str:
        """Get the SQL statement at the current cursor position."""
        text = self.toPlainText()
        cursor_pos = self.textCursor().position()

        if not text.strip():
            return ""

        # Find statement boundaries (semicolons not in strings)
        statements = self._split_statements(text)

        # Find which statement contains the cursor
        pos = 0
        for stmt in statements:
            stmt_end = pos + len(stmt)
            if pos <= cursor_pos <= stmt_end:
                return stmt.strip().rstrip(';').strip()
            pos = stmt_end

        # Default to last statement
        if statements:
            return statements[-1].strip().rstrip(';').strip()

        return text.strip()

    def _split_statements(self, text: str) -> List[str]:
        """Split SQL text into statements, respecting string literals."""
        statements = []
        current = []
        in_string = False
        i = 0

        while i < len(text):
            char = text[i]

            if char == "'" and not in_string:
                in_string = True
                current.append(char)
            elif char == "'" and in_string:
                # Check for escaped quote
                if i + 1 < len(text) and text[i + 1] == "'":
                    current.append("''")
                    i += 1
                else:
                    in_string = False
                    current.append(char)
            elif char == ';' and not in_string:
                current.append(char)
                statements.append(''.join(current))
                current = []
            else:
                current.append(char)

            i += 1

        if current:
            statements.append(''.join(current))

        return statements


class ResultsTable(QTableWidget):
    """Table widget for displaying query results."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Header setup
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().sectionDoubleClicked.connect(self._auto_fit_column)
        self.verticalHeader().setDefaultSectionSize(24)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos) -> None:
        """Show context menu."""
        menu = QMenu(self)
        menu.addAction("Copy", self._copy_selection, QKeySequence("Ctrl+C"))
        menu.addAction("Copy with Headers", self._copy_with_headers)
        menu.addSeparator()
        menu.addAction("Select All", self.selectAll, QKeySequence("Ctrl+A"))
        menu.exec(self.mapToGlobal(pos))

    def _copy_selection(self) -> None:
        """Copy selected cells to clipboard."""
        selection = self.selectedRanges()
        if not selection:
            return

        # Get min/max row and column
        rows = set()
        cols = set()
        for sel_range in selection:
            for row in range(sel_range.topRow(), sel_range.bottomRow() + 1):
                rows.add(row)
            for col in range(sel_range.leftColumn(), sel_range.rightColumn() + 1):
                cols.add(col)

        rows = sorted(rows)
        cols = sorted(cols)

        # Build tab-separated text
        lines = []
        for row in rows:
            row_data = []
            for col in cols:
                item = self.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))

        QApplication.clipboard().setText("\n".join(lines))

    def _copy_with_headers(self) -> None:
        """Copy selected cells with column headers."""
        selection = self.selectedRanges()
        if not selection:
            return

        # Get min/max row and column
        rows = set()
        cols = set()
        for sel_range in selection:
            for row in range(sel_range.topRow(), sel_range.bottomRow() + 1):
                rows.add(row)
            for col in range(sel_range.leftColumn(), sel_range.rightColumn() + 1):
                cols.add(col)

        rows = sorted(rows)
        cols = sorted(cols)

        # Header row
        headers = []
        for col in cols:
            header = self.horizontalHeaderItem(col)
            headers.append(header.text() if header else "")

        # Build tab-separated text
        lines = ["\t".join(headers)]
        for row in rows:
            row_data = []
            for col in cols:
                item = self.item(row, col)
                row_data.append(item.text() if item else "")
            lines.append("\t".join(row_data))

        QApplication.clipboard().setText("\n".join(lines))

    def _auto_fit_column(self, logical_index: int) -> None:
        """Auto-fit column width to content on header double-click."""
        header = self.horizontalHeaderItem(logical_index)
        header_text = header.text() if header else ""
        fm = self.fontMetrics()
        max_width = fm.horizontalAdvance(header_text) + 30

        for row in range(min(self.rowCount(), 1000)):
            item = self.item(row, logical_index)
            if item:
                text_width = fm.horizontalAdvance(item.text()) + 20
                max_width = max(max_width, text_width)

        self.setColumnWidth(logical_index, max(50, min(max_width, 600)))

    def load_results(self, rows: List[Tuple], description: Any) -> None:
        """Load query results into table."""
        self.clear()
        self.setSortingEnabled(False)

        if not description:
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        # Set up columns
        columns = [col[0] for col in description]
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)

        # Set up rows
        self.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value) if value is not None else "")

                # Right-align numbers
                if isinstance(value, (int, float)):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )

                self.setItem(row_idx, col_idx, item)

        # Resize columns to content
        self.resizeColumnsToContents()

        # Cap column widths
        for i in range(self.columnCount()):
            if self.columnWidth(i) > 300:
                self.setColumnWidth(i, 300)

        self.setSortingEnabled(True)


class SQLTab(QWidget):
    """Tab widget for SQL editing and execution."""

    def __init__(self, connection_name: str, conn_info: dict,
                 adapter: Any = None, db_type: str = '',
                 parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.connection_name = connection_name
        self.conn_info = conn_info
        self.adapter = adapter
        self.db_type = db_type
        self._worker: Optional[QueryWorker] = None
        self._script_worker: Optional[ScriptWorker] = None
        self._current_page = 1
        self._rows_per_page = 1000
        self._total_rows = 0
        self._last_sql = ""
        self._recent_destructive: List[str] = []  # Track last 10 destructive queries
        self._search_matches: List[Tuple[int, int]] = []  # (row, col) pairs
        self._current_search_idx = -1
        self._columns: List[str] = []
        self._editable = False
        self._edit_table: Optional[str] = None
        self._edit_schema: Optional[str] = None
        self._pk_columns: List[str] = []
        self._pk_indices: List[int] = []
        self._original_values: dict = {}  # row_index -> original row tuple
        self._modified_cells: dict = {}   # row_index -> {col_index: new_value}
        self._loading_results = False      # guard flag to ignore cellChanged during loads

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # SQL Editor (create before toolbar since toolbar references it)
        self.editor = SQLEditor()

        # Editor search bar (hidden by default)
        self.editor_search_bar = self._create_editor_search_bar()
        self.editor_search_bar.hide()

        # Toolbar
        self._create_toolbar()
        layout.addWidget(self.toolbar)

        # Main splitter (editor / results)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(3)

        # Editor container (editor + search bar)
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self.editor)
        editor_layout.addWidget(self.editor_search_bar)

        # Add editor container to splitter
        self.splitter.addWidget(editor_container)

        # Results area
        self.results_widget = self._create_results_widget()
        self.splitter.addWidget(self.results_widget)

        # Set initial sizes (40% editor, 60% results)
        self.splitter.setSizes([300, 500])

        layout.addWidget(self.splitter)

    def _create_toolbar(self) -> None:
        """Create the toolbar."""
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(24, 24))

        ic = "#ddd"  # icon color
        tb_style = Qt.ToolButtonStyle.ToolButtonTextUnderIcon

        def _tb(text, icon_name, icon_color=ic):
            btn = QToolButton()
            btn.setText(text)
            btn.setIcon(_make_icon(icon_name, icon_color, size=24))
            btn.setToolButtonStyle(tb_style)
            btn.setAutoRaise(True)
            return btn

        # Execute button
        self.btn_execute = _tb("Execute", "play", "#fff")
        self.btn_execute.setProperty("primary", True)
        self.btn_execute.setToolTip("Execute statement at cursor (F5)")
        self.btn_execute.clicked.connect(self.execute_query)
        self.toolbar.addWidget(self.btn_execute)

        # Execute Script button
        self.btn_execute_all = _tb("Script", "play_all")
        self.btn_execute_all.setToolTip("Execute all statements (Ctrl+F5)")
        self.btn_execute_all.clicked.connect(self.execute_all)
        self.toolbar.addWidget(self.btn_execute_all)

        # Cancel button
        self.btn_cancel = _tb("Cancel", "stop", "#fff")
        self.btn_cancel.setProperty("danger", True)
        self.btn_cancel.setToolTip("Cancel query (Esc)")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_query)
        self.toolbar.addWidget(self.btn_cancel)

        self.toolbar.addSeparator()

        # Save button
        self.btn_save = _tb("Save", "save")
        self.btn_save.setToolTip("Save query (Ctrl+S)")
        self.btn_save.clicked.connect(self.save_query)
        self.toolbar.addWidget(self.btn_save)

        # Load button
        self.btn_load = _tb("Load", "open")
        self.btn_load.setToolTip("Load query (Ctrl+O)")
        self.btn_load.clicked.connect(self.load_query)
        self.toolbar.addWidget(self.btn_load)

        # Clear button
        self.btn_clear = _tb("Clear", "clear")
        self.btn_clear.clicked.connect(self.editor.clear)
        self.toolbar.addWidget(self.btn_clear)

        self.toolbar.addSeparator()

        # Format button
        self.btn_format = _tb("Format", "format")
        self.btn_format.setToolTip("Format SQL (Ctrl+Shift+F)")
        self.btn_format.clicked.connect(self.format_sql)
        self.toolbar.addWidget(self.btn_format)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(),
                            spacer.sizePolicy().verticalPolicy())
        spacer.setMinimumWidth(20)
        self.toolbar.addWidget(spacer)

        # Stretch
        stretch = QWidget()
        stretch.setSizePolicy(
            stretch.sizePolicy().Policy.Expanding,
            stretch.sizePolicy().verticalPolicy()
        )
        self.toolbar.addWidget(stretch)

        # Connection label
        self.lbl_connection = QLabel(self.connection_name)
        self.lbl_connection.setProperty("subheading", True)
        self.toolbar.addWidget(self.lbl_connection)

    def _create_results_widget(self) -> QWidget:
        """Create the results area with tabs."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Results tab widget
        self.results_tabs = QTabWidget()
        self.results_tabs.setDocumentMode(True)

        # Results tab
        results_container = QWidget()
        results_layout = QVBoxLayout(results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)

        # Results controls
        controls = self._create_results_controls()
        results_layout.addWidget(controls)

        # Results table
        self.results_table = ResultsTable()
        results_layout.addWidget(self.results_table)

        # Status label
        self.results_status = QLabel("No results")
        self.results_status.setProperty("subheading", True)
        self.results_status.setContentsMargins(8, 4, 8, 4)
        results_layout.addWidget(self.results_status)

        self.results_tabs.addTab(results_container, "Results")

        # Fields tab
        self.fields_table = QTableWidget()
        self.fields_table.setColumnCount(7)
        self.fields_table.setHorizontalHeaderLabels([
            "Table", "Column", "Type", "Display Size",
            "Precision", "Scale", "Nullable"
        ])
        self.fields_table.horizontalHeader().setStretchLastSection(True)
        self.results_tabs.addTab(self.fields_table, "Fields")

        # Statistics tab
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setFont(QFont("JetBrains Mono", 11))
        self.results_tabs.addTab(self.stats_text, "Statistics")

        # Log tab
        log_container = self._create_log_tab()
        self.results_tabs.addTab(log_container, "Log")

        layout.addWidget(self.results_tabs)

        return widget

    def _create_results_controls(self) -> QWidget:
        """Create the results control bar."""
        controls = QFrame()
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Pagination buttons
        self.btn_first = QPushButton("◀◀")
        self.btn_first.setFixedWidth(36)
        self.btn_first.clicked.connect(lambda: self._go_to_page(1))
        layout.addWidget(self.btn_first)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(30)
        self.btn_prev.clicked.connect(lambda: self._go_to_page(self._current_page - 1))
        layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(30)
        self.btn_next.clicked.connect(lambda: self._go_to_page(self._current_page + 1))
        layout.addWidget(self.btn_next)

        self.btn_last = QPushButton("▶▶")
        self.btn_last.setFixedWidth(36)
        self.btn_last.clicked.connect(self._go_to_last_page)
        layout.addWidget(self.btn_last)

        layout.addSpacing(8)

        # Export dropdown
        self.btn_export = QPushButton("Save To ▾")
        export_menu = QMenu(self)
        export_menu.addAction("Copy to Clipboard", self._copy_to_clipboard)
        export_menu.addSeparator()
        export_menu.addAction("Excel (.xlsx)", lambda: self._export("xlsx"))
        export_menu.addAction("CSV (.csv)", lambda: self._export("csv"))
        export_menu.addAction("JSON (.json)", lambda: self._export("json"))
        self.btn_export.setMenu(export_menu)
        layout.addWidget(self.btn_export)

        # Save/Discard buttons (hidden until edits exist)
        self.btn_save_changes = QPushButton("Save Changes")
        self.btn_save_changes.setProperty("primary", True)
        self.btn_save_changes.clicked.connect(self._save_changes)
        self.btn_save_changes.hide()
        layout.addWidget(self.btn_save_changes)

        self.btn_discard_changes = QPushButton("Discard")
        self.btn_discard_changes.setProperty("danger", True)
        self.btn_discard_changes.clicked.connect(self._discard_changes)
        self.btn_discard_changes.hide()
        layout.addWidget(self.btn_discard_changes)

        layout.addStretch()

        # Search
        layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setFixedWidth(150)
        self.search_input.textChanged.connect(self._search_results)
        self.search_input.returnPressed.connect(self._search_next_result)
        layout.addWidget(self.search_input)

        self.btn_search_prev = QPushButton("<")
        self.btn_search_prev.setFixedWidth(28)
        self.btn_search_prev.clicked.connect(self._search_prev_result)
        layout.addWidget(self.btn_search_prev)

        self.btn_search_next = QPushButton(">")
        self.btn_search_next.setFixedWidth(28)
        self.btn_search_next.clicked.connect(self._search_next_result)
        layout.addWidget(self.btn_search_next)

        layout.addSpacing(16)

        # Rows per page
        layout.addWidget(QLabel("Rows:"))
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(100, 10000)
        self.spin_rows.setValue(1000)
        self.spin_rows.setSingleStep(100)
        self.spin_rows.valueChanged.connect(self._on_rows_changed)
        layout.addWidget(self.spin_rows)

        self.chk_show_all = QCheckBox("Show All")
        self.chk_show_all.stateChanged.connect(self._on_show_all_changed)
        layout.addWidget(self.chk_show_all)

        return controls

    def _create_editor_search_bar(self) -> QWidget:
        """Create the editor search bar."""
        bar = QFrame()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Find:"))

        self.editor_search_input = QLineEdit()
        self.editor_search_input.setFixedWidth(200)
        self.editor_search_input.returnPressed.connect(self._editor_search_next)
        self.editor_search_input.textChanged.connect(self._editor_search_highlight)
        layout.addWidget(self.editor_search_input)

        btn_prev = QPushButton("<")
        btn_prev.setFixedWidth(28)
        btn_prev.clicked.connect(self._editor_search_prev)
        layout.addWidget(btn_prev)

        btn_next = QPushButton(">")
        btn_next.setFixedWidth(28)
        btn_next.clicked.connect(self._editor_search_next)
        layout.addWidget(btn_next)

        self.editor_search_status = QLabel("")
        layout.addWidget(self.editor_search_status)

        layout.addStretch()

        btn_close = QPushButton("X")
        btn_close.setFixedWidth(26)
        btn_close.clicked.connect(self._hide_editor_search)
        layout.addWidget(btn_close)

        return bar

    def _toggle_editor_search(self) -> None:
        """Toggle editor search bar visibility."""
        if self.editor_search_bar.isVisible():
            self._hide_editor_search()
        else:
            self.editor_search_bar.show()
            self.editor_search_input.setFocus()
            self.editor_search_input.selectAll()

    def _hide_editor_search(self) -> None:
        """Hide editor search bar."""
        self.editor_search_bar.hide()
        self.editor.setFocus()
        # Clear search highlights
        self._editor_clear_highlights()

    def _editor_search_highlight(self, text: str) -> None:
        """Highlight all occurrences of search text in editor."""
        self._editor_clear_highlights()

        if not text:
            self.editor_search_status.setText("")
            return

        # Find all matches
        self._editor_search_positions = []
        content = self.editor.toPlainText()
        text_lower = text.lower()
        content_lower = content.lower()
        pos = 0

        while True:
            pos = content_lower.find(text_lower, pos)
            if pos == -1:
                break
            self._editor_search_positions.append(pos)
            pos += 1

        count = len(self._editor_search_positions)
        self.editor_search_status.setText(f"{count} match{'es' if count != 1 else ''}")

        if self._editor_search_positions:
            self._editor_search_idx = 0
            self._editor_goto_match()

    def _editor_search_next(self) -> None:
        """Go to next search match."""
        if not hasattr(self, '_editor_search_positions') or not self._editor_search_positions:
            return

        self._editor_search_idx = (self._editor_search_idx + 1) % len(self._editor_search_positions)
        self._editor_goto_match()

    def _editor_search_prev(self) -> None:
        """Go to previous search match."""
        if not hasattr(self, '_editor_search_positions') or not self._editor_search_positions:
            return

        self._editor_search_idx = (self._editor_search_idx - 1) % len(self._editor_search_positions)
        self._editor_goto_match()

    def _editor_goto_match(self) -> None:
        """Go to current match and highlight it."""
        if not hasattr(self, '_editor_search_positions') or not self._editor_search_positions:
            return

        pos = self._editor_search_positions[self._editor_search_idx]
        text_len = len(self.editor_search_input.text())

        cursor = self.editor.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + text_len, cursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()

        self.editor_search_status.setText(
            f"Match {self._editor_search_idx + 1} of {len(self._editor_search_positions)}"
        )

    def _editor_clear_highlights(self) -> None:
        """Clear editor search highlights."""
        self._editor_search_positions = []
        self._editor_search_idx = -1

    def _create_log_tab(self) -> QWidget:
        """Create the log tab."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Log controls
        controls = QFrame()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(8, 4, 8, 4)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_log)
        controls_layout.addWidget(btn_refresh)

        btn_clear = QPushButton("Clear Log")
        btn_clear.clicked.connect(self._clear_log)
        controls_layout.addWidget(btn_clear)

        controls_layout.addStretch()
        layout.addWidget(controls)

        # Log table
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(6)
        self.log_table.setHorizontalHeaderLabels([
            "Time", "SQL", "Status", "Duration", "Rows", "Error"
        ])
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.doubleClicked.connect(self._log_item_double_clicked)
        self.log_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_table.customContextMenuRequested.connect(self._show_log_context_menu)
        layout.addWidget(self.log_table)

        return container

    def _connect_signals(self) -> None:
        """Connect signals."""
        self.editor.execute_requested.connect(self.execute_query)
        self.editor.execute_all_requested.connect(self.execute_all)
        self.editor.find_requested.connect(self._toggle_editor_search)

        # Track cell edits (guarded by _loading_results flag)
        self.results_table.cellChanged.connect(self._on_cell_changed)

        # Double-click on results to open record viewer
        self.results_table.doubleClicked.connect(self._on_results_double_click)

        # Auto-refresh log when tab changes to Log
        self.results_tabs.currentChanged.connect(self._on_results_tab_changed)

        # Shortcuts
        shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut_save.activated.connect(self.save_query)

        shortcut_load = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut_load.activated.connect(self.load_query)

        shortcut_format = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        shortcut_format.activated.connect(self.format_sql)

        shortcut_cancel = QShortcut(QKeySequence("Escape"), self)
        shortcut_cancel.activated.connect(self.cancel_query)

        shortcut_find = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut_find.activated.connect(self._toggle_editor_search)

    def has_unsaved_changes(self) -> bool:
        """Check if this tab has unsaved cell edits."""
        return bool(self._modified_cells)

    def set_sql(self, sql: str) -> None:
        """Set the SQL text."""
        self.editor.setPlainText(sql)

    def execute_query(self) -> None:
        """Execute the statement at cursor."""
        sql = self.editor.get_statement_at_cursor()
        if not sql.strip():
            return

        self._run_query(sql)

    def execute_all(self) -> None:
        """Execute all statements as a script."""
        sql = self.editor.toPlainText().strip()
        if not sql:
            return

        statements = self.editor._split_statements(sql)
        statements = [s for s in statements if s.strip()]
        if not statements:
            return

        if self._worker and self._worker.isRunning():
            return

        self.btn_execute.setEnabled(False)
        self.btn_execute_all.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._set_status(f"Executing {len(statements)} statement(s)...")

        self._script_worker = ScriptWorker(self.conn_info, self.adapter, statements)
        self._script_worker.all_finished.connect(self._on_script_finished)
        self._script_worker.error.connect(self._on_query_error)
        self._script_worker.start()

    def _on_script_finished(self, results: List, total_time: float) -> None:
        """Handle script execution completion."""
        self._reset_buttons()

        # Log each statement
        db = _get_db()
        for r in results:
            try:
                db.log_query(
                    self.connection_name, r["full_sql"],
                    duration=r["time"],
                    row_count=r["row_count"],
                    status="success" if r["success"] else "error",
                    error_message=r.get("error")
                )
            except Exception:
                pass

        # Display results in table with script columns
        self._loading_results = True
        self.results_table.clear()
        self.results_table.setSortingEnabled(False)
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["#", "SQL", "Result", "Time"])
        self.results_table.setRowCount(len(results))

        for i, r in enumerate(results):
            self.results_table.setItem(i, 0, QTableWidgetItem(str(r["stmt"])))
            self.results_table.setItem(i, 1, QTableWidgetItem(r["sql"]))
            status_item = QTableWidgetItem(r["status"])
            if not r["success"]:
                status_item.setForeground(QColor(255, 80, 80))
            self.results_table.setItem(i, 2, status_item)
            self.results_table.setItem(i, 3, QTableWidgetItem(f"{r['time']:.3f}s"))

        self.results_table.resizeColumnsToContents()
        for col in range(self.results_table.columnCount()):
            if self.results_table.columnWidth(col) > 400:
                self.results_table.setColumnWidth(col, 400)
        self.results_table.setSortingEnabled(True)
        self._loading_results = False

        # Update statistics
        success = sum(1 for r in results if r["success"])
        errors = sum(1 for r in results if not r["success"])
        stats_lines = [
            "=" * 60,
            "SCRIPT EXECUTION RESULTS",
            "=" * 60,
            "",
            f"  Statements:  {len(results)}",
            f"  Success:     {success}",
            f"  Errors:      {errors}",
            f"  Total time:  {total_time:.3f} seconds",
        ]
        self.stats_text.setPlainText("\n".join(stats_lines))

        # Update status
        self.results_status.setText(
            f"Script: {success} succeeded, {errors} failed ({total_time:.3f}s)")
        self._set_status(
            f"Script completed: {len(results)} statement(s)")
        self.results_tabs.setCurrentIndex(0)

    def _run_query(self, sql: str) -> None:
        """Run a query in the background."""
        if self._worker and self._worker.isRunning():
            return

        # Check for destructive queries
        sql_upper = sql.strip().upper()
        is_destructive = any(sql_upper.startswith(kw) for kw in
                            ['UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER'])

        if is_destructive:
            # Get connection info for production/duplicate checks
            conn_info = get_connection(self.connection_name)

            # Production mode confirmation
            if conn_info and conn_info.get('is_production'):
                stmt_type = sql_upper.split()[0] if sql_upper else "QUERY"
                preview = sql[:100] + "..." if len(sql) > 100 else sql
                result = QMessageBox.warning(
                    self,
                    f"Production Database - {stmt_type}",
                    f"You are about to run a {stmt_type} on a PRODUCTION database.\n\n"
                    f"{preview}\n\n"
                    "Are you sure you want to continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if result != QMessageBox.StandardButton.Yes:
                    return

            # Duplicate protection
            if conn_info and conn_info.get('duplicate_protection'):
                # Normalize SQL for comparison (remove extra whitespace)
                normalized = ' '.join(sql.split())
                if normalized in self._recent_destructive:
                    result = QMessageBox.warning(
                        self,
                        "Duplicate Query Warning",
                        "This destructive query was recently executed.\n\n"
                        "Are you sure you want to run it again?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if result != QMessageBox.StandardButton.Yes:
                        return

                # Track this query
                self._recent_destructive.append(normalized)
                if len(self._recent_destructive) > 10:
                    self._recent_destructive.pop(0)

        self._last_sql = sql
        self._current_page = 1

        # Update UI
        self.btn_execute.setEnabled(False)
        self.btn_execute_all.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._set_status("Executing...")

        # Start worker
        self._worker = QueryWorker(
            self.conn_info, sql, self.adapter,
            self._rows_per_page, 0,
            self.chk_show_all.isChecked(), run_count=True
        )
        self._worker.finished.connect(self._on_query_finished)
        self._worker.error.connect(self._on_query_error)
        self._worker.start()

    def cancel_query(self) -> None:
        """Cancel the running query."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
            self._set_status("Query cancelled")
            self._reset_buttons()
        if self._script_worker and self._script_worker.isRunning():
            self._script_worker.cancel()
            self._script_worker.wait()
            self._set_status("Script cancelled")
            self._reset_buttons()

    def _on_query_finished(self, rows: List, description: Any,
                          exec_time: float, fetch_time: float,
                          total_rows: int = 0) -> None:
        """Handle query completion."""
        self._reset_buttons()

        # Log to database
        try:
            db = _get_db()
            db.log_query(
                self.connection_name,
                self._last_sql,
                duration=exec_time + fetch_time,
                row_count=len(rows) if rows else 0,
                status="success"
            )
        except Exception as e:
            print(f"Failed to log query: {e}")

        # Guard against false edits during programmatic table updates
        self._loading_results = True

        self.results_table.load_results(rows, description)
        self._total_rows = total_rows if total_rows > 0 else len(rows)

        # Store column names for editing
        self._columns = [col[0] for col in description] if description else []

        # Detect editability
        self._detect_editability(rows)

        # Update fields tab
        self._update_fields(description)

        # Get explain info and update statistics
        explain_info = self._get_explain_info(self._last_sql)
        self._update_statistics(exec_time, fetch_time, len(rows), description,
                               total_rows=self._total_rows, explain_info=explain_info)

        # Update status
        edit_status = " [Editable]" if self._editable else ""
        if rows:
            start = (self._current_page - 1) * self._rows_per_page + 1
            end = start + len(rows) - 1
            total_pages = max(1, (self._total_rows + self._rows_per_page - 1) // self._rows_per_page)
            self.results_status.setText(
                f"Showing {start:,}-{end:,} of {self._total_rows:,} row(s) "
                f"(Page {self._current_page} of {total_pages}){edit_status}"
            )
        else:
            self.results_status.setText("No results")

        # Update pagination buttons
        self._update_pagination_buttons()

        # Allow cellChanged tracking now that all loading is done
        self._loading_results = False

        # Update main status bar
        self._set_status(self.results_status.text())

        # Switch to results tab
        self.results_tabs.setCurrentIndex(0)

    def _on_query_error(self, error: str) -> None:
        """Handle query error."""
        self._reset_buttons()
        self._set_status(f"Error: {error}")

        # Log to database
        try:
            db = _get_db()
            db.log_query(
                self.connection_name,
                self._last_sql,
                status="error",
                error_message=error
            )
        except Exception:
            pass

        # Show in statistics
        self.stats_text.setPlainText(f"ERROR:\n{error}")
        self.results_tabs.setCurrentIndex(2)

    def _reset_buttons(self) -> None:
        """Reset button states."""
        self.btn_execute.setEnabled(True)
        self.btn_execute_all.setEnabled(True)
        self.btn_cancel.setEnabled(False)

    def _update_fields(self, description: Any) -> None:
        """Update the fields tab."""
        self.fields_table.setRowCount(0)
        if not description:
            return

        self.fields_table.setRowCount(len(description))
        for i, col in enumerate(description):
            self.fields_table.setItem(i, 0, QTableWidgetItem(""))  # Table
            self.fields_table.setItem(i, 1, QTableWidgetItem(col[0]))  # Name
            self.fields_table.setItem(i, 2, QTableWidgetItem(str(col[1])))  # Type
            self.fields_table.setItem(i, 3, QTableWidgetItem(str(col[2] or "")))
            self.fields_table.setItem(i, 4, QTableWidgetItem(str(col[4] or "")))
            self.fields_table.setItem(i, 5, QTableWidgetItem(str(col[5] or "")))
            self.fields_table.setItem(i, 6, QTableWidgetItem(
                "Yes" if col[6] else "No"
            ))

    def _update_statistics(self, exec_time: float, fetch_time: float,
                          row_count: int, description: Any,
                          total_rows: int = 0, explain_info: str = None) -> None:
        """Update the statistics tab."""
        lines = []
        lines.append("=" * 60)
        lines.append("QUERY EXECUTION STATISTICS")
        lines.append("=" * 60)
        lines.append("")
        lines.append("TIMING:")
        lines.append(f"  Execution time: {exec_time:.3f} seconds")
        lines.append(f"  Fetch time:     {fetch_time:.3f} seconds")
        lines.append(f"  Total time:     {exec_time + fetch_time:.3f} seconds")
        lines.append("")
        lines.append("RESULTS:")
        if total_rows > row_count:
            lines.append(f"  Rows fetched:   {row_count:,}")
            lines.append(f"  Total rows:     {total_rows:,}")
        else:
            lines.append(f"  Rows returned:  {row_count:,}")
        col_count = len(description) if description else 0
        lines.append(f"  Columns:        {col_count}")
        lines.append("")
        lines.append("QUERY:")
        lines.append("-" * 40)
        sql = self._last_sql
        lines.append(sql[:500] + ('...' if len(sql) > 500 else ''))
        if explain_info:
            lines.append("")
            lines.append("INDEX INFORMATION:")
            lines.append("-" * 40)
            lines.append(explain_info)
        self.stats_text.setPlainText("\n".join(lines))

    def _set_status(self, message: str) -> None:
        """Set status message."""
        main_window = self.window()
        if hasattr(main_window, 'set_status'):
            main_window.set_status(message)

    def _go_to_page(self, page: int) -> None:
        """Navigate to a specific page."""
        if not self._last_sql or self._total_rows == 0:
            return

        total_pages = max(1, (self._total_rows + self._rows_per_page - 1) // self._rows_per_page)
        page = max(1, min(page, total_pages))

        if page == self._current_page:
            return

        self._current_page = page
        offset = (page - 1) * self._rows_per_page

        # Re-run query with offset
        self._run_paginated_query(offset)

    def _go_to_last_page(self) -> None:
        """Navigate to the last page."""
        if self._total_rows > 0:
            total_pages = max(1, (self._total_rows + self._rows_per_page - 1) // self._rows_per_page)
            self._go_to_page(total_pages)

    def _run_paginated_query(self, offset: int) -> None:
        """Run query with pagination offset."""
        if self._worker and self._worker.isRunning():
            return

        self.btn_execute.setEnabled(False)
        self.btn_execute_all.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._set_status("Loading page...")

        self._worker = QueryWorker(
            self.conn_info, self._last_sql, self.adapter,
            self._rows_per_page, offset,
            fetch_all=False, run_count=False
        )
        self._worker.finished.connect(self._on_page_loaded)
        self._worker.error.connect(self._on_query_error)
        self._worker.start()

    def _on_page_loaded(self, rows: List, description: Any,
                        exec_time: float, fetch_time: float,
                        total_rows: int = 0) -> None:
        """Handle page load completion."""
        self._reset_buttons()

        self._loading_results = True
        self.results_table.load_results(rows, description)
        self._loading_results = False

        # Update status with pagination info
        start = (self._current_page - 1) * self._rows_per_page + 1
        end = start + len(rows) - 1
        total_pages = max(1, (self._total_rows + self._rows_per_page - 1) // self._rows_per_page)

        self.results_status.setText(
            f"Showing {start}-{end} of {self._total_rows} row(s) (Page {self._current_page} of {total_pages})"
        )

        # Update pagination button states
        self._update_pagination_buttons()

    def _on_rows_changed(self, value: int) -> None:
        """Handle rows per page change."""
        self._rows_per_page = value

    def _on_show_all_changed(self, state: int) -> None:
        """Handle show all checkbox change."""
        self.spin_rows.setEnabled(not self.chk_show_all.isChecked())

    def _update_pagination_buttons(self) -> None:
        """Update pagination button enabled states."""
        has_results = self._total_rows > 0
        total_pages = max(1, (self._total_rows + self._rows_per_page - 1) // self._rows_per_page) if has_results else 1

        self.btn_first.setEnabled(has_results and self._current_page > 1)
        self.btn_prev.setEnabled(has_results and self._current_page > 1)
        self.btn_next.setEnabled(has_results and self._current_page < total_pages)
        self.btn_last.setEnabled(has_results and self._current_page < total_pages)

    def _on_results_double_click(self, index) -> None:
        """Handle double-click on results table."""
        if not self._editable and self.results_table.rowCount() > 0:
            # Collect current results data
            columns = []
            for col in range(self.results_table.columnCount()):
                header = self.results_table.horizontalHeaderItem(col)
                columns.append(header.text() if header else "")

            rows = []
            for row in range(self.results_table.rowCount()):
                row_data = []
                for col in range(self.results_table.columnCount()):
                    item = self.results_table.item(row, col)
                    row_data.append(item.text() if item else "")
                rows.append(row_data)

            from ..dialogs.record_viewer_dialog import RecordViewerDialog
            dialog = RecordViewerDialog(self, columns, rows, index.row())
            dialog.navigate.connect(
                lambda idx: self.results_table.selectRow(idx))
            dialog.exec()

    def _copy_to_clipboard(self) -> None:
        """Copy results to clipboard."""

        rows = []
        # Header
        headers = []
        for col in range(self.results_table.columnCount()):
            headers.append(self.results_table.horizontalHeaderItem(col).text())
        rows.append("\t".join(headers))

        # Data
        for row in range(self.results_table.rowCount()):
            row_data = []
            for col in range(self.results_table.columnCount()):
                item = self.results_table.item(row, col)
                row_data.append(item.text() if item else "")
            rows.append("\t".join(row_data))

        QApplication.clipboard().setText("\n".join(rows))
        self._set_status("Copied to clipboard")

    def _export(self, format: str) -> None:
        """Export results to file."""
        if self.results_table.rowCount() == 0:
            QMessageBox.warning(self, "Export", "No results to export")
            return

        # Get filename
        extensions = {
            'xlsx': "Excel Files (*.xlsx)",
            'csv': "CSV Files (*.csv)",
            'json': "JSON Files (*.json)"
        }
        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export to {format.upper()}",
            "",
            extensions.get(format, "All Files (*)")
        )
        if not filename:
            return

        # Ensure extension
        if not filename.endswith(f".{format}"):
            filename += f".{format}"

        try:
            # Collect data
            headers = []
            for col in range(self.results_table.columnCount()):
                item = self.results_table.horizontalHeaderItem(col)
                headers.append(item.text() if item else f"Column{col}")

            rows = []
            for row in range(self.results_table.rowCount()):
                row_data = []
                for col in range(self.results_table.columnCount()):
                    item = self.results_table.item(row, col)
                    row_data.append(item.text() if item else "")
                rows.append(row_data)

            if format == 'csv':
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(rows)

            elif format == 'json':
                import json
                data = []
                for row in rows:
                    data.append(dict(zip(headers, row)))
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)

            elif format == 'xlsx':
                try:
                    import openpyxl
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.append(headers)
                    for row in rows:
                        ws.append(row)
                    wb.save(filename)
                except ImportError:
                    QMessageBox.warning(
                        self,
                        "Export Error",
                        "openpyxl module not installed.\nInstall with: pip install openpyxl"
                    )
                    return

            self._set_status(f"Exported to {filename}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")

    def _search_results(self, text: str) -> None:
        """Search within results and highlight matches."""
        # Clear previous highlighting
        self._search_matches = []
        self._current_search_idx = -1

        for row in range(self.results_table.rowCount()):
            for col in range(self.results_table.columnCount()):
                item = self.results_table.item(row, col)
                if item:
                    item.setBackground(QColor(0, 0, 0, 0))  # Transparent

        if not text:
            return

        text_lower = text.lower()

        # Find and highlight all matches
        for row in range(self.results_table.rowCount()):
            for col in range(self.results_table.columnCount()):
                item = self.results_table.item(row, col)
                if item and text_lower in item.text().lower():
                    item.setBackground(QColor(100, 100, 0))  # Yellow highlight
                    self._search_matches.append((row, col))

        # Select first match
        if self._search_matches:
            self._current_search_idx = 0
            self._highlight_current_match()

    def _search_next_result(self) -> None:
        """Navigate to next search match."""
        if not self._search_matches:
            return

        self._current_search_idx = (self._current_search_idx + 1) % len(self._search_matches)
        self._highlight_current_match()

    def _search_prev_result(self) -> None:
        """Navigate to previous search match."""
        if not self._search_matches:
            return

        self._current_search_idx = (self._current_search_idx - 1) % len(self._search_matches)
        self._highlight_current_match()

    def _highlight_current_match(self) -> None:
        """Highlight and scroll to current search match."""
        if self._current_search_idx < 0 or self._current_search_idx >= len(self._search_matches):
            return

        # Reset all to yellow
        for row, col in self._search_matches:
            item = self.results_table.item(row, col)
            if item:
                item.setBackground(QColor(100, 100, 0))

        # Highlight current in orange
        row, col = self._search_matches[self._current_search_idx]
        item = self.results_table.item(row, col)
        if item:
            item.setBackground(QColor(200, 100, 0))  # Orange for current
            self.results_table.scrollToItem(item)
            self.results_table.setCurrentCell(row, col)

    def _on_results_tab_changed(self, index: int) -> None:
        """Handle results tab change."""
        # Tab 3 is Log tab - auto refresh when selected
        if index == 3:
            self._refresh_log()

    def _refresh_log(self) -> None:
        """Refresh the query log."""
        try:
            db = _get_db()
            logs = db.get_query_log(self.connection_name, limit=500)

            self.log_table.setRowCount(len(logs))
            for i, log in enumerate(logs):
                self.log_table.setItem(i, 0, QTableWidgetItem(str(log.get('executed_at', ''))))

                # Store truncated SQL in display, full SQL in UserRole
                full_sql = log.get('sql', '')
                sql_item = QTableWidgetItem(full_sql[:200] + ('...' if len(full_sql) > 200 else ''))
                sql_item.setData(Qt.ItemDataRole.UserRole, full_sql)
                self.log_table.setItem(i, 1, sql_item)

                self.log_table.setItem(i, 2, QTableWidgetItem(log.get('status', '')))

                duration = log.get('duration')
                self.log_table.setItem(i, 3, QTableWidgetItem(f"{duration:.3f}s" if duration else ""))

                row_count = log.get('row_count')
                self.log_table.setItem(i, 4, QTableWidgetItem(str(row_count) if row_count is not None else ""))
                self.log_table.setItem(i, 5, QTableWidgetItem(log.get('error_message', '') or ""))

                # Highlight error rows
                if log.get('status') == 'error':
                    for j in range(6):
                        item = self.log_table.item(i, j)
                        if item:
                            item.setBackground(QColor(80, 40, 40))

            self.log_table.resizeColumnsToContents()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load log: {e}")

    def _clear_log(self) -> None:
        """Clear the query log."""
        result = QMessageBox.question(
            self,
            "Clear Log",
            "Are you sure you want to clear the query log?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if result == QMessageBox.StandardButton.Yes:
            try:
                db = _get_db()
                db.clear_query_log(self.connection_name)
                self.log_table.setRowCount(0)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to clear log: {e}")

    def _show_log_context_menu(self, pos) -> None:
        """Show context menu for log table."""
        row = self.log_table.rowAt(pos.y())
        if row < 0:
            return

        sql_item = self.log_table.item(row, 1)
        if not sql_item:
            return

        full_sql = sql_item.data(Qt.ItemDataRole.UserRole) or sql_item.text()

        menu = QMenu(self)
        menu.addAction("Copy SQL to Editor", lambda: self.editor.setPlainText(full_sql))
        menu.addAction("Copy SQL to Clipboard", lambda: QApplication.clipboard().setText(full_sql))
        menu.exec(self.log_table.mapToGlobal(pos))

    def _log_item_double_clicked(self, index) -> None:
        """Handle double-click on log item - copy full SQL to editor."""
        row = index.row()
        sql_item = self.log_table.item(row, 1)
        if sql_item:
            # Get full SQL from UserRole data
            full_sql = sql_item.data(Qt.ItemDataRole.UserRole)
            if full_sql:
                self.editor.setPlainText(full_sql)
            else:
                self.editor.setPlainText(sql_item.text())

    def save_query(self) -> None:
        """Save query to database."""
        from PyQt6.QtWidgets import QInputDialog
        sql = self.editor.toPlainText().strip()
        if not sql:
            return

        name, ok = QInputDialog.getText(
            self, "Save Query", "Query name:")
        if ok and name:
            try:
                db = _get_db()
                db.save_query(name, sql, self.connection_name, self.db_type)
                self._set_status(f"Saved query: {name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def load_query(self) -> None:
        """Load query from database."""
        from ..dialogs.query_manager_dialog import QueryManagerDialog
        dialog = QueryManagerDialog(self, self.db_type, self.connection_name)
        if dialog.exec() and dialog.selected_sql:
            self.editor.setPlainText(dialog.selected_sql)
            self._set_status("Query loaded")

    def format_sql(self) -> None:
        """Format the SQL in the editor."""
        try:
            import sqlparse
            sql = self.editor.toPlainText()
            formatted = sqlparse.format(
                sql,
                reindent=True,
                keyword_case='upper'
            )
            self.editor.setPlainText(formatted)
        except ImportError:
            QMessageBox.warning(
                self,
                "Format Error",
                "sqlparse module not available"
            )

    # ── Explain / Query Plan ─────────────────────────────────────

    def _get_explain_info(self, sql: str) -> Optional[str]:
        """Try to get query explain/plan information."""
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            return None
        if not self.adapter or self.db_type != "ibmi":
            return None

        from ...adapters import connect_from_info
        conn = None
        explain_data = []
        try:
            conn = connect_from_info(self.adapter, self.conn_info)
            explain_cursor = conn.cursor()
            try:
                explain_cursor.execute("CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')")
            except Exception:
                pass

            tables = self._extract_tables_from_sql(sql)
            for table in tables[:5]:
                try:
                    idx_cursor = conn.cursor()
                    idx_cursor.execute("""
                        SELECT INDEX_NAME, COLUMN_NAME, INDEX_TYPE, IS_UNIQUE
                        FROM QSYS2.SYSINDEXES I
                        JOIN QSYS2.SYSKEYS K ON I.INDEX_NAME = K.INDEX_NAME
                            AND I.INDEX_SCHEMA = K.INDEX_SCHEMA
                        WHERE I.TABLE_NAME = ?
                        ORDER BY I.INDEX_NAME, K.ORDINAL_POSITION
                        FETCH FIRST 20 ROWS ONLY
                    """, (table.upper(),))
                    indexes = idx_cursor.fetchall()
                    if indexes:
                        explain_data.append(f"\nIndexes on {table}:")
                        current_idx = None
                        for row in indexes:
                            idx_name, col_name, idx_type, is_unique = row
                            if idx_name != current_idx:
                                unique_str = "UNIQUE " if is_unique == 'Y' else ""
                                explain_data.append(f"  {unique_str}{idx_name} ({idx_type})")
                                current_idx = idx_name
                            explain_data.append(f"    - {col_name}")
                    idx_cursor.close()
                except Exception:
                    pass

            explain_cursor.close()
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return "\n".join(explain_data) if explain_data else None

    @staticmethod
    def _extract_tables_from_sql(sql: str) -> List[str]:
        """Extract table names from SQL (basic parsing)."""
        tables = []
        from_match = re.search(
            r'\bFROM\s+([A-Za-z0-9_.]+(?:/[A-Za-z0-9_]+)?)', sql, re.IGNORECASE)
        if from_match:
            table = from_match.group(1)
            if '/' in table:
                parts = table.split('/')
                table = f"{parts[0]}.{parts[1]}"
            tables.append(table)

        for match in re.findall(
                r'\bJOIN\s+([A-Za-z0-9_.]+(?:/[A-Za-z0-9_]+)?)', sql, re.IGNORECASE):
            if '/' in match:
                parts = match.split('/')
                match = f"{parts[0]}.{parts[1]}"
            tables.append(match)

        return tables

    # ── Inline Editing ──────────────────────────────────────────

    @staticmethod
    def _parse_single_table_select(sql: str):
        """Parse SQL to detect single-table SELECT. Returns (schema, table) or (None, None)."""
        sql_clean = sql.strip().rstrip(';')
        sql_upper = sql_clean.upper()

        if not sql_upper.startswith('SELECT'):
            return None, None

        for kw in (' JOIN ', ' INNER JOIN ', ' LEFT JOIN ', ' RIGHT JOIN ',
                    ' OUTER JOIN ', ' CROSS JOIN ', ' NATURAL JOIN '):
            if kw in sql_upper:
                return None, None

        if ' UNION ' in sql_upper or ' INTERSECT ' in sql_upper or ' EXCEPT ' in sql_upper:
            return None, None

        from_pos = sql_upper.find(' FROM ')
        if from_pos == -1:
            return None, None

        after_from = sql_upper[from_pos + 6:].lstrip()
        if after_from.startswith('('):
            return None, None

        from_match = re.search(
            r'\bFROM\s+(["\w]+(?:\.["\w]+)?)\s*(?:AS\s+\w+|\w+)?'
            r'(?:\s+WHERE|\s+ORDER|\s+GROUP|\s+HAVING|\s+LIMIT|\s+FETCH|\s*$)',
            sql_clean, re.IGNORECASE
        )
        if not from_match:
            from_match = re.search(r'\bFROM\s+(["\w]+(?:\.["\w]+)?)', sql_clean, re.IGNORECASE)
        if not from_match:
            return None, None

        table_ref = from_match.group(1)

        where_pos = sql_upper.find(' WHERE ', from_pos)
        order_pos = sql_upper.find(' ORDER ', from_pos)
        group_pos = sql_upper.find(' GROUP ', from_pos)
        end_pos = min(p for p in [where_pos, order_pos, group_pos, len(sql_upper)] if p > 0)
        from_clause = sql_upper[from_pos + 6:end_pos]
        if ',' in from_clause:
            return None, None

        if '.' in table_ref:
            parts = table_ref.split('.')
            return parts[0].strip('"').strip("'"), parts[1].strip('"').strip("'")
        return None, table_ref.strip('"').strip("'")

    def _detect_editability(self, rows) -> None:
        """Detect if results are editable and set up editing state."""
        self._editable = False
        self._edit_table = None
        self._edit_schema = None
        self._pk_columns = []
        self._pk_indices = []
        self._original_values = {}
        self._modified_cells = {}
        self.btn_save_changes.hide()
        self.btn_discard_changes.hide()

        if not self.adapter or not self._columns:
            self.results_table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            return

        schema, table = self._parse_single_table_select(self._last_sql)
        if not table:
            self.results_table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            return

        try:
            from ...adapters import connect_from_info
            pk_conn = connect_from_info(self.adapter, self.conn_info)
            try:
                pk_cols = self.adapter.get_primary_key_columns(
                    pk_conn, schema, table)
            finally:
                pk_conn.close()
        except Exception:
            pk_cols = []

        if not pk_cols:
            self.results_table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            return

        columns_upper = [c.upper() for c in self._columns]
        pk_indices = []
        for pk_col in pk_cols:
            try:
                idx = columns_upper.index(pk_col.upper())
                pk_indices.append(idx)
            except ValueError:
                self.results_table.setEditTriggers(
                    QAbstractItemView.EditTrigger.NoEditTriggers)
                return

        self._editable = True
        self._edit_table = table
        self._edit_schema = schema
        self._pk_columns = pk_cols
        self._pk_indices = pk_indices

        # Store original values
        for row_idx, row in enumerate(rows):
            self._original_values[row_idx] = tuple(
                str(v) if v is not None else "" for v in row)

        # Enable editing, but lock PK columns
        self.results_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked)
        for row_idx in range(self.results_table.rowCount()):
            for pk_idx in pk_indices:
                item = self.results_table.item(row_idx, pk_idx)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        # cellChanged is always connected; _loading_results flag guards against false edits

    def _on_cell_changed(self, row: int, col: int) -> None:
        """Track cell modifications."""
        if self._loading_results:
            return
        if not self._editable or col in self._pk_indices:
            return

        item = self.results_table.item(row, col)
        if not item:
            return

        new_value = item.text()
        original = self._original_values.get(row)
        if not original:
            return

        if new_value == original[col]:
            # Value reverted — remove from tracked changes
            if row in self._modified_cells:
                self._modified_cells[row].pop(col, None)
                if not self._modified_cells[row]:
                    del self._modified_cells[row]
                    # Remove highlight
                    for c in range(self.results_table.columnCount()):
                        it = self.results_table.item(row, c)
                        if it:
                            it.setBackground(QColor(0, 0, 0, 0))
        else:
            if row not in self._modified_cells:
                self._modified_cells[row] = {}
            self._modified_cells[row][col] = new_value
            # Highlight modified row
            for c in range(self.results_table.columnCount()):
                it = self.results_table.item(row, c)
                if it:
                    it.setBackground(QColor(100, 100, 0, 60))

        # Show/hide save buttons
        if self._modified_cells:
            self.btn_save_changes.show()
            self.btn_discard_changes.show()
        else:
            self.btn_save_changes.hide()
            self.btn_discard_changes.hide()

    def _save_changes(self) -> None:
        """Save all modified rows to the database."""
        if not self._modified_cells or not self._editable:
            return

        num_changes = len(self._modified_cells)
        conn_info = get_connection(self.connection_name)

        if conn_info and conn_info.get('is_production'):
            title = "Production Database"
            text = (f"This is a PRODUCTION connection.\n\n"
                    f"Save {num_changes} modified row(s) to '{self._edit_table}'?")
            icon = QMessageBox.Icon.Warning
        else:
            title = "Save Changes"
            text = f"Save {num_changes} modified row(s) to '{self._edit_table}'?"
            icon = QMessageBox.Icon.Question

        msg = QMessageBox(icon, title, text,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                          self.window())
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        from ...adapters import connect_from_info
        errors = []
        success_count = 0
        db = _get_db()
        conn = None

        try:
            conn = connect_from_info(self.adapter, self.conn_info)

            for row_idx, changes in list(self._modified_cells.items()):
                original = self._original_values.get(row_idx)
                if not original:
                    continue
                try:
                    sql, params = self._generate_update_sql(changes, original)
                    if sql:
                        cursor = conn.cursor()
                        start_time = time.time()
                        cursor.execute(sql, params)
                        conn.commit()
                        duration = time.time() - start_time
                        cursor.close()
                        success_count += 1

                        log_sql = self._format_sql_with_params(sql, params)
                        db.log_query(self.connection_name, log_sql, duration, 1, "success")

                        # Update original values
                        current = list(original)
                        for col_idx, val in changes.items():
                            current[col_idx] = val
                        self._original_values[row_idx] = tuple(current)

                        # Remove highlight
                        for c in range(self.results_table.columnCount()):
                            it = self.results_table.item(row_idx, c)
                            if it:
                                it.setBackground(QColor(0, 0, 0, 0))

                except Exception as e:
                    errors.append(f"Row {row_idx + 1}: {e}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        except Exception as e:
            errors.append(f"Connection error: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        if not errors:
            self._modified_cells = {}
        else:
            # Keep only failed rows
            self._modified_cells = {k: v for k, v in self._modified_cells.items()
                                    if any(f"Row {k + 1}:" in e for e in errors)}

        self.btn_save_changes.setVisible(bool(self._modified_cells))
        self.btn_discard_changes.setVisible(bool(self._modified_cells))

        if errors:
            QMessageBox.warning(
                self, "Save Errors",
                f"Saved {success_count} row(s).\n\nErrors:\n" + "\n".join(errors[:5]))
        else:
            self._set_status(f"Saved {success_count} row(s) to {self._edit_table}")

    def _discard_changes(self) -> None:
        """Discard all unsaved changes."""
        if not self._modified_cells:
            return

        msg = QMessageBox(QMessageBox.Icon.Question, "Discard Changes",
                          f"Discard {len(self._modified_cells)} modified row(s)?",
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                          self.window())
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        self._loading_results = True

        for row_idx in list(self._modified_cells.keys()):
            original = self._original_values.get(row_idx)
            if original:
                for col_idx in range(len(original)):
                    item = self.results_table.item(row_idx, col_idx)
                    if item:
                        item.setText(original[col_idx])
                        item.setBackground(QColor(0, 0, 0, 0))

        self._modified_cells = {}
        self.btn_save_changes.hide()
        self.btn_discard_changes.hide()
        self._set_status("Changes discarded")

        self._loading_results = False

    def _generate_update_sql(self, changes: dict, original_values: tuple):
        """Generate UPDATE SQL for a modified row."""
        if not changes or not original_values:
            return None, None

        set_parts = []
        set_params = []
        for col_num, new_value in changes.items():
            col_name = self._columns[col_num]
            set_parts.append(f"{col_name} = ?")
            set_params.append(None if new_value == "" else new_value)

        where_parts = []
        where_params = []
        for pk_idx in self._pk_indices:
            pk_col = self._columns[pk_idx]
            pk_value = original_values[pk_idx]
            where_parts.append(f"{pk_col} = ?")
            where_params.append(pk_value)

        table_ref = (f"{self._edit_schema}.{self._edit_table}"
                     if self._edit_schema else self._edit_table)
        sql = f"UPDATE {table_ref} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"

        if self.db_type in ('mysql', 'postgresql'):
            sql = sql.replace('?', '%s')

        return sql, set_params + where_params

    @staticmethod
    def _format_sql_with_params(sql: str, params) -> str:
        """Format SQL with parameter values substituted for logging."""
        result = sql
        for param in params:
            if param is None:
                val = "NULL"
            elif isinstance(param, (int, float)):
                val = str(param)
            else:
                val = f"'{str(param).replace(chr(39), chr(39)+chr(39))}'"
            if '%s' in result:
                result = result.replace('%s', val, 1)
            elif '?' in result:
                result = result.replace('?', val, 1)
        return result

    # ── End Inline Editing ────────────────────────────────────

    def update_theme(self) -> None:
        """Update theme colors."""
        self.editor.update_theme()

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
        if self._script_worker and self._script_worker.isRunning():
            self._script_worker.cancel()
            self._script_worker.wait()
