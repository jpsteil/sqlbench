"""
Spool Tab Widget for SQLBench PyQt6 GUI.

Provides IBM i spool file viewing functionality.
"""

import subprocess
import platform
import tempfile
from typing import Optional, Any, List
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QTableWidget,
    QTableWidgetItem,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QFileDialog,
    QMenu,
    QDialog,
    QComboBox,
    QSpinBox,
    QDialogButtonBox,
    QFormLayout,
    QApplication,
)


class SpoolWorker(QThread):
    """Background thread for spool file operations."""

    files_loaded = pyqtSignal(list)
    content_loaded = pyqtSignal(str, dict)  # content, spool_info
    delete_complete = pyqtSignal(int, list)  # deleted_count, errors
    pdf_complete = pyqtSignal(str)  # output_path
    error = pyqtSignal(str)

    def __init__(self, conn_info: dict, adapter: Any, operation: str, **kwargs):
        super().__init__()
        self.conn_info = conn_info
        self.adapter = adapter
        self.connection = None
        self.operation = operation
        self.kwargs = kwargs

    def run(self) -> None:
        """Execute operation in background."""
        from ...adapters import connect_from_info
        try:
            self.connection = connect_from_info(self.adapter, self.conn_info)
            if self.operation == "list":
                self._list_spool_files()
            elif self.operation == "view":
                self._view_spool_file()
            elif self.operation == "delete":
                self._delete_spool_files()
            elif self.operation == "pdf":
                self._generate_pdf()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if self.connection:
                try:
                    self.connection.close()
                except Exception:
                    pass

    def _list_spool_files(self) -> None:
        """List spool files for user."""
        user = self.kwargs.get("user", "*CURRENT")
        cursor = self.connection.cursor()

        sql = """
            SELECT
                SPOOLED_FILE_NAME,
                USER_NAME,
                JOB_NAME,
                FILE_NUMBER,
                STATUS,
                TOTAL_PAGES
            FROM QSYS2.OUTPUT_QUEUE_ENTRIES
            WHERE USER_NAME = CASE WHEN ? = '*CURRENT' THEN USER ELSE ? END
            ORDER BY CREATE_TIMESTAMP DESC
            FETCH FIRST 100 ROWS ONLY
        """
        cursor.execute(sql, (user, user))
        files = cursor.fetchall()
        cursor.close()

        self.files_loaded.emit(files)

    def _view_spool_file(self) -> None:
        """View spool file content."""
        file_name = self.kwargs.get("file_name")
        qualified_job = self.kwargs.get("qualified_job")
        file_number = self.kwargs.get("file_number")

        cursor = self.connection.cursor()

        # Get spool file attributes
        attr_sql = """
            SELECT PAGE_LENGTH, PAGE_WIDTH, LPI, CPI
            FROM QSYS2.OUTPUT_QUEUE_ENTRIES
            WHERE JOB_NAME = ?
              AND SPOOLED_FILE_NAME = ?
              AND FILE_NUMBER = ?
        """
        cursor.execute(attr_sql, (qualified_job, file_name, int(file_number)))
        attr_row = cursor.fetchone()

        page_length = 66
        page_width = 132
        if attr_row:
            page_length = attr_row[0] or 66
            page_width = attr_row[1] or 132

        # Read spool file content
        sql = """
            SELECT SPOOLED_DATA
            FROM TABLE(SYSTOOLS.SPOOLED_FILE_DATA(
                JOB_NAME => ?,
                SPOOLED_FILE_NAME => ?,
                SPOOLED_FILE_NUMBER => ?
            ))
        """
        cursor.execute(sql, (qualified_job, file_name, int(file_number)))

        lines = []
        for row in cursor.fetchall():
            line = row[0] if row[0] else ""
            clean_line = ''.join(c if (c.isprintable() or c in '\t') else ' ' for c in line)
            lines.append(clean_line)

        cursor.close()

        spool_info = {
            "file_name": file_name,
            "qualified_job": qualified_job,
            "file_number": file_number,
            "page_length": page_length,
            "page_width": page_width,
            "lines": lines
        }

        self.content_loaded.emit("\n".join(lines), spool_info)

    def _delete_spool_files(self) -> None:
        """Delete spool files."""
        files_to_delete = self.kwargs.get("files", [])
        deleted = 0
        errors = []

        cursor = self.connection.cursor()

        for f in files_to_delete:
            try:
                job_parts = f["job"].split("/")
                if len(job_parts) == 3:
                    job_number, job_user, job_name = job_parts
                else:
                    job_name = f["job"]
                    job_user = "*N"
                    job_number = "*N"

                cmd = f"DLTSPLF FILE({f['file_name']}) JOB({job_number}/{job_user}/{job_name}) SPLNBR({f['file_number']})"
                cursor.execute("CALL QSYS2.QCMDEXC(?)", (cmd,))
                deleted += 1
            except Exception as e:
                errors.append(f"{f['file_name']}: {e}")

        cursor.close()
        self.delete_complete.emit(deleted, errors)

    def _generate_pdf(self) -> None:
        """Generate PDF using IBM i native CPYSPLF."""
        import time
        import base64

        file_name = self.kwargs.get("file_name")
        qualified_job = self.kwargs.get("qualified_job")
        file_number = self.kwargs.get("file_number")
        output_path = self.kwargs.get("output_path")

        job_parts = qualified_job.split("/")
        if len(job_parts) != 3:
            self.error.emit(f"Invalid job name format: {qualified_job}")
            return

        job_number, job_user, job_name_part = job_parts
        temp_ifs_path = f"/tmp/sqlbench_pdf_{job_number}_{int(time.time())}.pdf"

        cursor = self.connection.cursor()

        # Generate PDF on IFS
        cpysplf_cmd = (
            f"CPYSPLF FILE({file_name}) TOFILE(*TOSTMF) "
            f"JOB({job_number}/{job_user}/{job_name_part}) SPLNBR({file_number}) "
            f"TOSTMF('{temp_ifs_path}') WSCST(*PDF)"
        )

        try:
            cursor.execute("CALL QSYS2.QCMDEXC(?)", (cpysplf_cmd,))
            self.connection.commit()
        except Exception as e:
            self.error.emit(f"CPYSPLF failed: {e}")
            return

        # Read PDF from IFS
        try:
            cursor.execute(
                """SELECT BASE64_ENCODE(GET_BLOB_FROM_FILE(?))
                   FROM SYSIBM.SYSDUMMY1""",
                (temp_ifs_path,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                base64_data = row[0]
                if isinstance(base64_data, bytes):
                    base64_data = base64_data.decode('ascii')
                base64_data = base64_data.replace('\n', '').replace('\r', '').replace(' ', '')
                pdf_data = base64.b64decode(base64_data)
            else:
                self.error.emit("Failed to read PDF from IFS - no data")
                return
        except Exception as e:
            self.error.emit(f"Failed to read PDF: {e}")
            return

        # Clean up temp file
        try:
            rmf_cmd = f"RMVLNK OBJLNK('{temp_ifs_path}')"
            cursor.execute("CALL QSYS2.QCMDEXC(?)", (rmf_cmd,))
            self.connection.commit()
        except Exception:
            pass

        cursor.close()

        # Write to local file
        with open(output_path, 'wb') as f:
            f.write(pdf_data)

        self.pdf_complete.emit(output_path)


class SpoolTab(QWidget):
    """Tab widget for IBM i spool file management."""

    def __init__(self, connection_name: str, conn_info: dict,
                 adapter: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.connection_name = connection_name
        self.conn_info = conn_info
        self.adapter = adapter
        self._worker: Optional[SpoolWorker] = None
        self._search_matches: List[int] = []
        self._current_match: int = -1
        self._current_spool_info: Optional[dict] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        self._create_toolbar()
        layout.addWidget(self.toolbar)

        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(3)

        # Left: Spool file list
        self.file_list = self._create_file_list()
        self.splitter.addWidget(self.file_list)

        # Right: Viewer
        self.viewer = self._create_viewer()
        self.splitter.addWidget(self.viewer)

        # Set initial sizes
        self.splitter.setSizes([400, 600])

        layout.addWidget(self.splitter)

    def _create_toolbar(self) -> None:
        """Create the toolbar."""
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)

        # User field
        self.toolbar.addWidget(QLabel("User:"))
        self.user_input = QLineEdit("*CURRENT")
        self.user_input.setFixedWidth(120)
        self.user_input.returnPressed.connect(self.refresh_files)
        self.toolbar.addWidget(self.user_input)

        self.toolbar.addSeparator()

        # Buttons
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_files)
        self.toolbar.addWidget(self.btn_refresh)

        self.btn_view = QPushButton("View")
        self.btn_view.clicked.connect(self.view_selected)
        self.toolbar.addWidget(self.btn_view)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.delete_selected)
        self.toolbar.addWidget(self.btn_delete)

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

    def _create_file_list(self) -> QWidget:
        """Create the spool file list."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "File", "User", "Job", "File #", "Status", "Pages"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self.view_selected)

        # Context menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)

        return container

    def _create_viewer(self) -> QWidget:
        """Create the spool file viewer."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Viewer toolbar
        viewer_toolbar = QFrame()
        toolbar_layout = QHBoxLayout(viewer_toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)

        self.btn_save_pdf = QPushButton("Save PDF")
        self.btn_save_pdf.setEnabled(False)
        self.btn_save_pdf.clicked.connect(self.save_as_pdf)
        toolbar_layout.addWidget(self.btn_save_pdf)

        self.btn_print = QPushButton("Print")
        self.btn_print.setEnabled(False)
        self.btn_print.clicked.connect(self.print_file)
        toolbar_layout.addWidget(self.btn_print)

        toolbar_layout.addStretch()

        # Search
        toolbar_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setFixedWidth(150)
        self.search_input.returnPressed.connect(self._search_next)
        self.search_input.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.search_input)

        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedWidth(28)
        self.btn_prev.clicked.connect(self._search_prev)
        toolbar_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton(">")
        self.btn_next.setFixedWidth(28)
        self.btn_next.clicked.connect(self._search_next)
        toolbar_layout.addWidget(self.btn_next)

        layout.addWidget(viewer_toolbar)

        # Content viewer
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setFont(QFont("JetBrains Mono", 10))
        self.content.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.content.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.content.customContextMenuRequested.connect(self._show_viewer_context_menu)
        layout.addWidget(self.content)

        # Status
        self.viewer_status = QLabel("")
        self.viewer_status.setProperty("subheading", True)
        self.viewer_status.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.viewer_status)

        return container

    def _show_context_menu(self, pos) -> None:
        """Show context menu."""
        menu = QMenu(self)
        menu.addAction("View", self.view_selected)
        menu.addAction("Delete", self.delete_selected)
        menu.exec(self.table.mapToGlobal(pos))

    def _show_viewer_context_menu(self, pos) -> None:
        """Show viewer context menu."""
        menu = QMenu(self)
        menu.addAction("Select All", self.content.selectAll)
        menu.addSeparator()
        menu.addAction("Copy", self.content.copy)
        menu.exec(self.content.mapToGlobal(pos))

    def refresh_files(self) -> None:
        """Refresh the spool file list."""
        user = self.user_input.text().strip().upper() or "*CURRENT"
        self.user_input.setText(user)

        self.table.setRowCount(0)
        self.btn_refresh.setEnabled(False)

        self._worker = SpoolWorker(
            self.conn_info,
            self.adapter,
            "list",
            user=user
        )
        self._worker.files_loaded.connect(self._on_files_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_files_loaded(self, files: List) -> None:
        """Handle files loaded."""
        self.btn_refresh.setEnabled(True)
        self.table.setRowCount(len(files))

        for i, file in enumerate(files):
            for j, value in enumerate(file):
                self.table.setItem(i, j, QTableWidgetItem(str(value or "")))

        self.table.resizeColumnsToContents()
        self.viewer_status.setText(f"Loaded {len(files)} spool file(s)")

    def _on_error(self, error: str) -> None:
        """Handle error."""
        self.btn_refresh.setEnabled(True)
        self.btn_save_pdf.setEnabled(True)
        self.btn_print.setEnabled(True)
        QMessageBox.critical(self, "Error", error)

    def view_selected(self) -> None:
        """View the selected spool file."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Select", "Please select a spool file to view.")
            return

        row = rows[0].row()
        file_name = self.table.item(row, 0).text()
        qualified_job = self.table.item(row, 2).text()
        file_number = self.table.item(row, 3).text()

        self.content.setPlainText("Loading...")
        self.btn_save_pdf.setEnabled(False)
        self.btn_print.setEnabled(False)

        self._worker = SpoolWorker(
            self.conn_info,
            self.adapter,
            "view",
            file_name=file_name,
            qualified_job=qualified_job,
            file_number=file_number
        )
        self._worker.content_loaded.connect(self._on_content_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_content_loaded(self, content: str, spool_info: dict) -> None:
        """Handle content loaded."""
        self._current_spool_info = spool_info
        self.content.setPlainText(content)
        self.btn_save_pdf.setEnabled(True)
        self.btn_print.setEnabled(True)

        page_width = spool_info.get("page_width", 132)
        page_length = spool_info.get("page_length", 66)
        lines = len(spool_info.get("lines", []))
        self.viewer_status.setText(f"{spool_info['file_name']} ({page_width}x{page_length}, {lines} lines)")

    def delete_selected(self) -> None:
        """Delete selected spool files."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Select", "Please select spool file(s) to delete.")
            return

        files_to_delete = []
        for row_idx in rows:
            row = row_idx.row()
            files_to_delete.append({
                "file_name": self.table.item(row, 0).text(),
                "job": self.table.item(row, 2).text(),
                "file_number": self.table.item(row, 3).text()
            })

        count = len(files_to_delete)
        msg = f"Delete {count} spool file(s)?" if count > 1 else f"Delete spool file '{files_to_delete[0]['file_name']}'?"

        result = QMessageBox.question(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self.btn_refresh.setEnabled(False)

        self._worker = SpoolWorker(
            self.conn_info,
            self.adapter,
            "delete",
            files=files_to_delete
        )
        self._worker.delete_complete.connect(self._on_delete_complete)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_delete_complete(self, deleted: int, errors: List[str]) -> None:
        """Handle delete completion."""
        self.btn_refresh.setEnabled(True)

        if errors:
            error_msg = "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n... and {len(errors) - 5} more errors"
            QMessageBox.warning(
                self,
                "Delete Errors",
                f"Deleted {deleted} file(s).\n\nErrors:\n{error_msg}"
            )
        else:
            self.viewer_status.setText(f"Deleted {deleted} spool file(s)")

        self.refresh_files()

    def save_as_pdf(self) -> None:
        """Save spool file as PDF."""
        if not self._current_spool_info:
            QMessageBox.warning(self, "No Spool File", "Please view a spool file first.")
            return

        file_name = self._current_spool_info.get("file_name", "spool")
        file_number = self._current_spool_info.get("file_number", "0")

        default_name = f"{file_name}_{file_number}.pdf"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save as PDF",
            default_name,
            "PDF Files (*.pdf)"
        )
        if not filename:
            return

        self.btn_save_pdf.setEnabled(False)
        self.btn_print.setEnabled(False)
        self.viewer_status.setText("Generating PDF...")

        self._worker = SpoolWorker(
            self.conn_info,
            self.adapter,
            "pdf",
            file_name=self._current_spool_info["file_name"],
            qualified_job=self._current_spool_info["qualified_job"],
            file_number=self._current_spool_info["file_number"],
            output_path=filename
        )
        self._worker.pdf_complete.connect(self._on_pdf_complete)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_pdf_complete(self, output_path: str) -> None:
        """Handle PDF generation complete."""
        self.btn_save_pdf.setEnabled(True)
        self.btn_print.setEnabled(True)
        self.viewer_status.setText(f"Saved: {output_path}")

        result = QMessageBox.question(
            self,
            "Saved",
            f"PDF saved to:\n{output_path}\n\nOpen the PDF now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if result == QMessageBox.StandardButton.Yes:
            self._open_file(output_path)

    def _open_file(self, file_path: str) -> None:
        """Open file with system default application."""
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", file_path], check=True)
            elif system == "Windows":
                import os
                os.startfile(file_path)
            else:
                subprocess.run(["xdg-open", file_path], check=True)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open file: {e}")

    def print_file(self) -> None:
        """Print the spool file."""
        if not self._current_spool_info:
            QMessageBox.warning(self, "No Spool File", "Please view a spool file first.")
            return

        # Create print dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Print")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout(dialog)

        # Printer selection
        form = QFormLayout()

        self.printer_combo = QComboBox()
        printers, default = self._get_printers()
        if printers:
            self.printer_combo.addItems(printers)
            if default and default in printers:
                self.printer_combo.setCurrentText(default)
        else:
            self.printer_combo.addItem("(System Default)")
        form.addRow("Printer:", self.printer_combo)

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(1)
        form.addRow("Copies:", self.copies_spin)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            printer = self.printer_combo.currentText() if printers else None
            copies = self.copies_spin.value()
            self._send_to_printer(printer, copies)

    def _get_printers(self):
        """Get list of available printers."""
        printers = []
        default = None
        system = platform.system()
        try:
            if system in ("Linux", "Darwin"):
                result = subprocess.run(["lpstat", "-a"], capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line:
                            printer = line.split()[0]
                            printers.append(printer)
                result = subprocess.run(["lpstat", "-d"], capture_output=True, text=True)
                if result.returncode == 0 and ":" in result.stdout:
                    default = result.stdout.split(":")[1].strip()
            elif system == "Windows":
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line.strip():
                            printers.append(line.strip())
        except Exception:
            pass
        return printers, default

    def _send_to_printer(self, printer: Optional[str], copies: int) -> None:
        """Send to printer by generating PDF first."""
        temp_path = tempfile.mktemp(suffix='.pdf')

        self.btn_save_pdf.setEnabled(False)
        self.btn_print.setEnabled(False)
        self.viewer_status.setText("Generating PDF for printing...")

        self._print_printer = printer
        self._print_copies = copies
        self._print_temp_path = temp_path

        self._worker = SpoolWorker(
            self.conn_info,
            self.adapter,
            "pdf",
            file_name=self._current_spool_info["file_name"],
            qualified_job=self._current_spool_info["qualified_job"],
            file_number=self._current_spool_info["file_number"],
            output_path=temp_path
        )
        self._worker.pdf_complete.connect(self._on_print_pdf_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_print_pdf_ready(self, pdf_path: str) -> None:
        """Handle PDF ready for printing."""
        self.btn_save_pdf.setEnabled(True)
        self.btn_print.setEnabled(True)

        try:
            system = platform.system()
            if system in ("Linux", "Darwin"):
                cmd = ["lp", "-n", str(self._print_copies)]
                if self._print_printer:
                    cmd.extend(["-d", self._print_printer])
                cmd.append(pdf_path)
                subprocess.run(cmd, check=True)
                self.viewer_status.setText(f"Sent to printer: {self._print_printer or 'default'}")
            elif system == "Windows":
                import os
                for _ in range(self._print_copies):
                    os.startfile(pdf_path, "print")
                self.viewer_status.setText(f"Sent to printer: {self._print_printer or 'default'}")
        except Exception as e:
            QMessageBox.warning(self, "Print Error", f"Could not print: {e}")

    def _on_search_changed(self, text: str) -> None:
        """Handle search text changed."""
        if not text:
            self._search_matches = []
            self._current_match = -1
            self.viewer_status.setText("")

    def _search_next(self) -> None:
        """Find next search match."""
        text = self.search_input.text()
        if not text:
            return

        content = self.content.toPlainText()
        cursor = self.content.textCursor()
        pos = cursor.position()

        self._update_search_matches(text, content)

        if not self._search_matches:
            self.viewer_status.setText("No matches found")
            return

        # Find next occurrence
        next_pos = content.lower().find(text.lower(), pos)
        if next_pos == -1:
            next_pos = content.lower().find(text.lower())

        if next_pos >= 0:
            cursor.setPosition(next_pos)
            cursor.setPosition(next_pos + len(text), cursor.MoveMode.KeepAnchor)
            self.content.setTextCursor(cursor)
            self.content.centerCursor()

            self._current_match = self._search_matches.index(next_pos) if next_pos in self._search_matches else 0
            self._update_search_status()

    def _search_prev(self) -> None:
        """Find previous search match."""
        text = self.search_input.text()
        if not text:
            return

        content = self.content.toPlainText()
        cursor = self.content.textCursor()
        pos = cursor.position() - len(text) - 1

        self._update_search_matches(text, content)

        if not self._search_matches:
            self.viewer_status.setText("No matches found")
            return

        prev_pos = content.lower().rfind(text.lower(), 0, max(0, pos))
        if prev_pos == -1:
            prev_pos = content.lower().rfind(text.lower())

        if prev_pos >= 0:
            cursor.setPosition(prev_pos)
            cursor.setPosition(prev_pos + len(text), cursor.MoveMode.KeepAnchor)
            self.content.setTextCursor(cursor)
            self.content.centerCursor()

            self._current_match = self._search_matches.index(prev_pos) if prev_pos in self._search_matches else 0
            self._update_search_status()

    def _update_search_matches(self, text: str, content: str) -> None:
        """Build list of all search match positions."""
        self._search_matches = []
        text_lower = text.lower()
        content_lower = content.lower()
        pos = 0
        while True:
            pos = content_lower.find(text_lower, pos)
            if pos == -1:
                break
            self._search_matches.append(pos)
            pos += 1

    def _update_search_status(self) -> None:
        """Update status with match count."""
        if self._search_matches:
            self.viewer_status.setText(f"Match {self._current_match + 1} of {len(self._search_matches)}")
        else:
            self.viewer_status.setText("No matches")

    def get_user(self) -> str:
        """Get current user filter."""
        return self.user_input.text().strip()

    def set_user(self, user: str) -> None:
        """Set user filter."""
        self.user_input.setText(user)

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._worker and self._worker.isRunning():
            self._worker.wait()
