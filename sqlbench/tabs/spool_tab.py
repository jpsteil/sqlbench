"""Spool file utility tab."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import subprocess
import tempfile
import platform


class SpoolTab:
    def __init__(self, parent, app, connection, conn_name, os_version):
        self.app = app
        self.connection = connection
        self.conn_name = conn_name
        self.os_version = os_version
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self._running = False
        self._current_spool_info = None  # Store spool file info for PDF export
        self._create_widgets()

    def _create_widgets(self):
        # Top controls
        ctrl_frame = ttk.Frame(self.frame)
        ctrl_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        ttk.Label(ctrl_frame, text="User:").pack(side=tk.LEFT, padx=(0, 5))
        self.user_entry = ttk.Entry(ctrl_frame, width=15)
        self.user_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.user_entry.insert(0, "*CURRENT")

        self.refresh_btn = ttk.Button(ctrl_frame, text="Refresh", command=self._refresh_spool_files)
        self.refresh_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame, text="View", command=self._view_spool_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame, text="Delete", command=self._delete_spool_files).pack(side=tk.LEFT, padx=2)

        # Connection info label
        ttk.Label(ctrl_frame, text=f"  [{self.conn_name}]").pack(side=tk.RIGHT, padx=5)

        # Paned window for list and viewer
        self.paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Spool file list
        list_frame = ttk.LabelFrame(self.paned, text="Spool Files")
        self.paned.add(list_frame, weight=1)

        columns = ("file", "user", "job", "filenumber", "status", "pages")
        self.spool_tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")

        self.spool_tree.heading("file", text="File")
        self.spool_tree.heading("user", text="User")
        self.spool_tree.heading("job", text="Job")
        self.spool_tree.heading("filenumber", text="File #")
        self.spool_tree.heading("status", text="Status")
        self.spool_tree.heading("pages", text="Pages")

        self.spool_tree.column("file", width=75, minwidth=50)
        self.spool_tree.column("user", width=50, minwidth=35)
        self.spool_tree.column("job", width=180, minwidth=100)
        self.spool_tree.column("filenumber", width=40, minwidth=30, anchor="e")
        self.spool_tree.column("status", width=45, minwidth=35)
        self.spool_tree.column("pages", width=40, minwidth=30, anchor="e")

        spool_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.spool_tree.yview)
        self.spool_tree.configure(yscrollcommand=spool_scroll.set)

        spool_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.spool_tree.pack(fill=tk.BOTH, expand=True)

        self.spool_tree.bind("<Double-1>", lambda e: self._view_spool_file())
        self.spool_tree.bind("<Button-3>", self._show_spool_context_menu)

        # Context menu for spool list
        self.spool_context_menu = tk.Menu(self.spool_tree, tearoff=0)
        self.spool_context_menu.add_command(label="View", command=self._view_spool_file)
        self.spool_context_menu.add_command(label="Delete", command=self._delete_spool_files)

        # Viewer area
        viewer_frame = ttk.LabelFrame(self.paned, text="Viewer")
        self.paned.add(viewer_frame, weight=2)

        # Viewer button bar
        viewer_btn_frame = ttk.Frame(viewer_frame)
        viewer_btn_frame.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)

        self.save_pdf_btn = ttk.Button(viewer_btn_frame, text="Save PDF", command=self._save_pdf, state=tk.DISABLED)
        self.save_pdf_btn.pack(side=tk.LEFT, padx=2)
        self.print_btn = ttk.Button(viewer_btn_frame, text="Print", command=self._print_spool, state=tk.DISABLED)
        self.print_btn.pack(side=tk.LEFT, padx=2)

        # Search frame on the right
        search_frame = ttk.Frame(viewer_btn_frame)
        search_frame.pack(side=tk.RIGHT, padx=5)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 2))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=20)
        self.search_entry.pack(side=tk.LEFT, padx=2)
        self.search_entry.bind("<Return>", lambda e: self._search_next())
        self.search_entry.bind("<Shift-Return>", lambda e: self._search_prev())

        self.search_prev_btn = ttk.Button(search_frame, text="<", width=2, command=self._search_prev)
        self.search_prev_btn.pack(side=tk.LEFT, padx=1)
        self.search_next_btn = ttk.Button(search_frame, text=">", width=2, command=self._search_next)
        self.search_next_btn.pack(side=tk.LEFT, padx=1)

        self._search_matches = []
        self._search_index = -1
        self._last_search = ""

        self.viewer_text = tk.Text(viewer_frame, wrap=tk.NONE, font=("Courier", 10))
        viewer_scroll_y = ttk.Scrollbar(viewer_frame, orient=tk.VERTICAL, command=self.viewer_text.yview)
        viewer_scroll_x = ttk.Scrollbar(viewer_frame, orient=tk.HORIZONTAL, command=self.viewer_text.xview)
        self.viewer_text.configure(yscrollcommand=viewer_scroll_y.set, xscrollcommand=viewer_scroll_x.set)

        viewer_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        viewer_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.viewer_text.pack(fill=tk.BOTH, expand=True)

        # Configure search highlight tag
        self.viewer_text.tag_configure("search_highlight", background="#FFFF00", foreground="#000000")
        self.viewer_text.tag_configure("search_current", background="#FF8C00", foreground="#000000")

        # Create context menu for viewer text
        self._create_viewer_context_menu()

    def _set_running(self, running):
        """Update UI state for running/not running."""
        self._running = running
        if running:
            self.refresh_btn.config(state=tk.DISABLED)
            self.app.root.config(cursor="watch")
        else:
            self.refresh_btn.config(state=tk.NORMAL)
            self.app.root.config(cursor="")

    def _refresh_spool_files(self):
        if self._running:
            return

        user = self.user_entry.get().strip().upper() or "*CURRENT"
        self.user_entry.delete(0, tk.END)
        self.user_entry.insert(0, user)

        # Clear current list
        self.spool_tree.delete(*self.spool_tree.get_children())

        self._set_running(True)
        self.app.statusbar.config(text=f"Loading spool files from {self.conn_name}...")

        thread = threading.Thread(target=self._fetch_spool_files, args=(user,), daemon=True)
        thread.start()

    def _fetch_spool_files(self, user):
        """Fetch spool files in background thread."""
        try:
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
            rows = cursor.fetchall()
            cursor.close()

            self.app.root.after(0, self._display_spool_files, rows, user)
        except Exception as e:
            self.app.root.after(0, self._spool_error, str(e))
        finally:
            self.app.root.after(0, self._set_running, False)

    def _display_spool_files(self, rows, user):
        """Display spool files in treeview (called from main thread)."""
        for row in rows:
            clean_row = tuple(str(v) if v is not None else "" for v in row)
            self.spool_tree.insert("", tk.END, values=clean_row)
        self.app.statusbar.config(text=f"Loaded {len(rows)} spool files for {user} on {self.conn_name}")

    def _spool_error(self, error):
        """Handle spool file errors."""
        messagebox.showerror("Error", error)

    def _show_spool_context_menu(self, event):
        """Show context menu for spool file list."""
        # Select the item under cursor
        item = self.spool_tree.identify_row(event.y)
        if item:
            # Add to selection if not already selected
            if item not in self.spool_tree.selection():
                self.spool_tree.selection_set(item)
            self.spool_context_menu.tk_popup(event.x_root, event.y_root, 0)

    def _view_spool_file(self):
        selection = self.spool_tree.selection()
        if not selection:
            messagebox.showinfo("Select", "Please select a spool file to view.")
            return

        item = self.spool_tree.item(selection[0])
        values = item["values"]
        file_name = values[0]
        qualified_job = values[2]  # Already in "number/user/name" format
        file_number = values[3]

        # Parse job name from qualified job (format: number/user/name)
        job_parts = qualified_job.split("/")
        job_name = job_parts[2] if len(job_parts) == 3 else qualified_job

        # Show loading feedback
        self.app.statusbar.config(text=f"Loading spool file {file_name}...")
        self.viewer_text.delete("1.0", tk.END)
        self.viewer_text.insert("1.0", "Loading...")
        self.app.root.config(cursor="watch")
        self.app.root.update()

        try:
            cursor = self.connection.cursor()

            # Get spool file attributes for proper page formatting
            attr_sql = """
                SELECT PAGE_LENGTH, PAGE_WIDTH, LPI, CPI
                FROM QSYS2.OUTPUT_QUEUE_ENTRIES
                WHERE JOB_NAME = ?
                  AND SPOOLED_FILE_NAME = ?
                  AND FILE_NUMBER = ?
            """
            cursor.execute(attr_sql, (qualified_job, file_name, int(file_number)))
            attr_row = cursor.fetchone()

            page_length = 66  # Default
            page_width = 132  # Default
            if attr_row:
                page_length = attr_row[0] or 66
                page_width = attr_row[1] or 132

            # Save info for PDF export
            self._current_spool_info = {
                "file_name": file_name,
                "job_name": job_name,
                "qualified_job": qualified_job,
                "file_number": file_number,
                "page_length": page_length,
                "page_width": page_width
            }

            # Read spool file content using SYSTOOLS.SPOOLED_FILE_DATA
            sql = """
                SELECT SPOOLED_DATA
                FROM TABLE(SYSTOOLS.SPOOLED_FILE_DATA(
                    JOB_NAME => ?,
                    SPOOLED_FILE_NAME => ?,
                    SPOOLED_FILE_NUMBER => ?
                ))
            """
            cursor.execute(sql, (qualified_job, file_name, int(file_number)))

            self.viewer_text.delete("1.0", tk.END)

            # Store raw lines for PDF generation
            raw_lines = []
            for row in cursor.fetchall():
                line = row[0] if row[0] else ""
                # Clean control characters but keep printable ASCII and common chars
                clean_line = ''.join(c if (c.isprintable() or c in '\t') else ' ' for c in line)
                raw_lines.append(clean_line)
                self.viewer_text.insert(tk.END, clean_line + "\n")

            # Store lines in spool info for PDF
            self._current_spool_info["lines"] = raw_lines

            cursor.close()
            self._update_viewer_buttons()
            self.app.statusbar.config(text=f"Loaded spool file {file_name} ({page_width}x{page_length}, {len(raw_lines)} lines)")
        except Exception as e:
            self.viewer_text.delete("1.0", tk.END)
            self.app.statusbar.config(text="Failed to load spool file")
            messagebox.showerror("Error", f"Could not read spool file: {e}")
        finally:
            self.app.root.config(cursor="")

    def _delete_spool_files(self):
        """Delete selected spool files."""
        selection = self.spool_tree.selection()
        if not selection:
            messagebox.showinfo("Select", "Please select spool file(s) to delete.")
            return

        # Build list of files to delete
        files_to_delete = []
        for item_id in selection:
            item = self.spool_tree.item(item_id)
            values = item["values"]
            files_to_delete.append({
                "file_name": values[0],
                "job": values[2],
                "file_number": values[3]
            })

        # Confirmation
        count = len(files_to_delete)
        if count == 1:
            msg = f"Delete spool file '{files_to_delete[0]['file_name']}'?"
        else:
            msg = f"Delete {count} selected spool files?"

        if not messagebox.askyesno("Confirm Delete", msg):
            return

        # Delete in background thread
        self._set_running(True)
        self.app.statusbar.config(text=f"Deleting {count} spool file(s)...")
        thread = threading.Thread(target=self._do_delete_spool_files, args=(files_to_delete,), daemon=True)
        thread.start()

    def _do_delete_spool_files(self, files_to_delete):
        """Delete spool files in background thread."""
        deleted = 0
        errors = []

        try:
            cursor = self.connection.cursor()

            for f in files_to_delete:
                try:
                    # Parse job name (format: number/user/name)
                    job_parts = f["job"].split("/")
                    if len(job_parts) == 3:
                        job_number, job_user, job_name = job_parts
                    else:
                        job_name = f["job"]
                        job_user = "*N"
                        job_number = "*N"

                    # Build DLTSPLF command
                    cmd = f"DLTSPLF FILE({f['file_name']}) JOB({job_number}/{job_user}/{job_name}) SPLNBR({f['file_number']})"

                    cursor.execute("CALL QSYS2.QCMDEXC(?)", (cmd,))
                    deleted += 1
                except Exception as e:
                    errors.append(f"{f['file_name']}: {e}")

            cursor.close()
        except Exception as e:
            errors.append(str(e))

        # Update UI on main thread
        self.app.root.after(0, self._delete_complete, deleted, errors)

    def _delete_complete(self, deleted, errors):
        """Handle delete completion on main thread."""
        self._set_running(False)

        if errors:
            error_msg = "\n".join(errors[:5])  # Show first 5 errors
            if len(errors) > 5:
                error_msg += f"\n... and {len(errors) - 5} more errors"
            messagebox.showerror("Delete Errors", f"Deleted {deleted} file(s).\n\nErrors:\n{error_msg}")
        else:
            self.app.statusbar.config(text=f"Deleted {deleted} spool file(s) from {self.conn_name}")

        # Refresh list
        self._refresh_spool_files()

    def _save_pdf(self):
        """Save spool file as PDF using IBM i native PDF generation."""
        if not self._current_spool_info:
            messagebox.showwarning("No Spool File", "Please view a spool file first.")
            return

        file_name = self._current_spool_info.get("file_name")
        qualified_job = self._current_spool_info.get("qualified_job")
        file_number = self._current_spool_info.get("file_number")
        job_name = self._current_spool_info.get("job_name", "spool")

        if not all([file_name, qualified_job, file_number]):
            messagebox.showerror("Error", "Missing spool file information.")
            return

        # Ask user where to save
        default_name = f"{job_name}_{file_number}.pdf"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialfile=default_name
        )

        if not file_path:
            return

        def on_success(pdf_path):
            self.save_pdf_btn.config(state=tk.NORMAL)
            self.print_btn.config(state=tk.NORMAL)
            self.app.statusbar.config(text=f"Saved PDF: {pdf_path}")
            if messagebox.askyesno("Saved", f"PDF saved to:\n{pdf_path}\n\nOpen the PDF now?"):
                self._open_file(pdf_path)

        def on_error(error):
            self.save_pdf_btn.config(state=tk.NORMAL)
            self.print_btn.config(state=tk.NORMAL)
            self.app.statusbar.config(text="PDF generation failed")
            messagebox.showerror("Error", f"PDF generation failed:\n{error}")

        # Disable buttons and show progress
        self.save_pdf_btn.config(state=tk.DISABLED)
        self.print_btn.config(state=tk.DISABLED)

        self._generate_native_pdf(file_path, on_success, on_error)

    def _generate_native_pdf(self, output_path, on_success, on_error):
        """Generate PDF using IBM i native CPYSPLF with WSCST(*PDF).

        Args:
            output_path: Local file path to save PDF
            on_success: Callback function(file_path) on success
            on_error: Callback function(error_message) on error
        """
        file_name = self._current_spool_info.get("file_name")
        qualified_job = self._current_spool_info.get("qualified_job")
        file_number = self._current_spool_info.get("file_number")

        # Parse job parts (format: number/user/name)
        job_parts = qualified_job.split("/")
        if len(job_parts) != 3:
            self.app.root.after(0, on_error, f"Invalid job name format: {qualified_job}")
            return

        job_number, job_user, job_name_part = job_parts

        # Generate a unique temp file name on IFS
        import time
        temp_ifs_path = f"/tmp/sqlbench_pdf_{job_number}_{int(time.time())}.pdf"

        # Show progress with animated dots
        self._pdf_progress_active = True
        self._pdf_progress_dots = 0

        def update_progress():
            if self._pdf_progress_active:
                self._pdf_progress_dots = (self._pdf_progress_dots + 1) % 4
                dots = "." * self._pdf_progress_dots
                self.app.statusbar.config(text=f"Generating PDF{dots}")
                self.app.root.after(300, update_progress)

        self.app.root.after(0, update_progress)

        def do_generate():
            try:
                cursor = self.connection.cursor()

                # Step 1: Generate PDF on IFS using CPYSPLF with WSCST(*PDF)
                cpysplf_cmd = (
                    f"CPYSPLF FILE({file_name}) TOFILE(*TOSTMF) "
                    f"JOB({job_number}/{job_user}/{job_name_part}) SPLNBR({file_number}) "
                    f"TOSTMF('{temp_ifs_path}') WSCST(*PDF)"
                )

                try:
                    cursor.execute("CALL QSYS2.QCMDEXC(?)", (cpysplf_cmd,))
                    self.connection.commit()
                except Exception as e:
                    self._pdf_progress_active = False
                    self.app.root.after(0, on_error, f"CPYSPLF failed: {e}")
                    return

                # Step 2: Read the PDF from IFS using base64 encoding to avoid binary issues
                try:
                    import base64

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
                        self._pdf_progress_active = False
                        self.app.root.after(0, on_error, "Failed to read PDF from IFS - no data")
                        return

                except Exception as e:
                    self._pdf_progress_active = False
                    self.app.root.after(0, on_error, f"Failed to read PDF: {e}")
                    return

                # Step 3: Clean up temp file on IFS
                try:
                    rmf_cmd = f"RMVLNK OBJLNK('{temp_ifs_path}')"
                    cursor.execute("CALL QSYS2.QCMDEXC(?)", (rmf_cmd,))
                    self.connection.commit()
                except Exception:
                    pass  # Ignore cleanup errors

                cursor.close()

                # Step 4: Write to local file
                with open(output_path, 'wb') as f:
                    f.write(pdf_data)

                self._pdf_progress_active = False
                self.app.root.after(0, on_success, output_path)

            except Exception as e:
                self._pdf_progress_active = False
                self.app.root.after(0, on_error, str(e))

        # Run in background thread
        thread = threading.Thread(target=do_generate, daemon=True)
        thread.start()

    def _open_file(self, file_path):
        """Open file with system default application."""
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", file_path], check=True)
            elif system == "Windows":
                import os
                os.startfile(file_path)
            else:  # Linux and others
                subprocess.run(["xdg-open", file_path], check=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file: {e}")

    def _update_viewer_buttons(self):
        """Enable/disable viewer buttons based on content."""
        content = self.viewer_text.get("1.0", tk.END).strip()
        state = tk.NORMAL if content else tk.DISABLED
        self.save_pdf_btn.config(state=state)
        self.print_btn.config(state=state)

    def _print_spool(self):
        """Print the current viewer content."""
        content = self.viewer_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Empty", "No spool file content to print.")
            return

        # Show print dialog
        self._show_print_dialog(content)

    def _get_printers(self):
        """Get list of available printers."""
        printers = []
        default = None
        system = platform.system()
        try:
            if system in ("Linux", "Darwin"):
                # Use lpstat to get printer list
                result = subprocess.run(["lpstat", "-a"], capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line:
                            # Format: "printer_name accepting requests..."
                            printer = line.split()[0]
                            printers.append(printer)
                # Get default printer
                result = subprocess.run(["lpstat", "-d"], capture_output=True, text=True)
                if result.returncode == 0 and ":" in result.stdout:
                    default = result.stdout.split(":")[1].strip()
            elif system == "Windows":
                # Use PowerShell to get printers (more reliable than wmic)
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
                    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line.strip():
                            printers.append(line.strip())
                # Get default printer
                result = subprocess.run(
                    ["powershell", "-Command", "(Get-WmiObject -Query \"SELECT * FROM Win32_Printer WHERE Default=$true\").Name"],
                    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                if result.returncode == 0 and result.stdout.strip():
                    default = result.stdout.strip()
        except Exception:
            pass
        return printers, default

    def _show_print_dialog(self, content):
        """Show a print dialog to select printer."""
        printers, default = self._get_printers()

        dialog = tk.Toplevel(self.frame)
        dialog.title("Print")
        dialog.geometry("350x200")
        dialog.transient(self.frame.winfo_toplevel())
        dialog.grab_set()

        # Apply dark mode if enabled
        is_dark = self.app.dark_mode_var.get()
        if is_dark:
            dialog.configure(bg="#2b2b2b")

        # Printer selection
        ttk.Label(dialog, text="Select Printer:").pack(anchor=tk.W, padx=10, pady=(10, 5))

        printer_var = tk.StringVar()
        if printers:
            printer_combo = ttk.Combobox(dialog, textvariable=printer_var, values=printers, state="readonly", width=40)
            printer_combo.pack(padx=10, pady=5)
            if default and default in printers:
                printer_combo.set(default)
            elif printers:
                printer_combo.set(printers[0])
        else:
            ttk.Label(dialog, text="No printers found. Using system default.").pack(padx=10, pady=5)

        # Copies
        copies_frame = ttk.Frame(dialog)
        copies_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(copies_frame, text="Copies:").pack(side=tk.LEFT)
        copies_var = tk.StringVar(value="1")
        copies_spin = ttk.Spinbox(copies_frame, from_=1, to=99, width=5, textvariable=copies_var)
        copies_spin.pack(side=tk.LEFT, padx=5)

        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=20)

        def do_print():
            dialog.destroy()
            self._send_to_printer(content, printer_var.get() if printers else None, int(copies_var.get()))

        ttk.Button(btn_frame, text="Print", command=do_print).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def _send_to_printer(self, content, printer, copies):
        """Send content to the specified printer by generating a native PDF first."""
        if not self._current_spool_info:
            messagebox.showerror("Error", "No spool file information available.")
            return

        # Generate PDF to temp file, then print
        temp_path = tempfile.mktemp(suffix='.pdf')

        def on_success(pdf_path):
            self.save_pdf_btn.config(state=tk.NORMAL)
            self.print_btn.config(state=tk.NORMAL)
            try:
                system = platform.system()
                if system in ("Linux", "Darwin"):
                    cmd = ["lp", "-n", str(copies)]
                    if printer:
                        cmd.extend(["-d", printer])
                    cmd.append(pdf_path)
                    subprocess.run(cmd, check=True)
                    self.app.statusbar.config(text=f"Sent to printer: {printer or 'default'}")
                elif system == "Windows":
                    import os
                    for _ in range(copies):
                        os.startfile(pdf_path, "print")
                    self.app.statusbar.config(text=f"Sent to printer: {printer or 'default'}")
            except FileNotFoundError:
                messagebox.showerror("Error", "Print command not found.\nEnsure CUPS (Linux/Mac) is available.")
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Error", f"Print failed: {e}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not print: {e}")

        def on_error(error):
            self.save_pdf_btn.config(state=tk.NORMAL)
            self.print_btn.config(state=tk.NORMAL)
            self.app.statusbar.config(text="Print failed - PDF generation error")
            messagebox.showerror("Error", f"Could not generate PDF for printing:\n{error}")

        # Disable buttons during PDF generation
        self.save_pdf_btn.config(state=tk.DISABLED)
        self.print_btn.config(state=tk.DISABLED)

        self._generate_native_pdf(temp_path, on_success, on_error)

    def _create_viewer_context_menu(self):
        """Create right-click context menu for viewer text."""
        self.viewer_context_menu = tk.Menu(self.viewer_text, tearoff=0)
        self.viewer_context_menu.add_command(label="Select All", command=self._select_all, accelerator="Ctrl+A")
        self.viewer_context_menu.add_separator()
        self.viewer_context_menu.add_command(label="Cut", command=self._cut, accelerator="Ctrl+X")
        self.viewer_context_menu.add_command(label="Copy", command=self._copy, accelerator="Ctrl+C")

        self.viewer_text.bind("<Button-3>", self._show_context_menu)
        self.viewer_text.bind("<Control-a>", lambda e: self._select_all())
        self.viewer_text.bind("<Control-A>", lambda e: self._select_all())

    def _show_context_menu(self, event):
        """Show context menu at mouse position."""
        self.viewer_context_menu.tk_popup(event.x_root, event.y_root, 0)

    def _select_all(self):
        """Select all text in viewer."""
        self.viewer_text.tag_add("sel", "1.0", "end-1c")
        self.viewer_text.mark_set("insert", "end-1c")
        return "break"

    def _cut(self):
        """Cut selected text to clipboard."""
        try:
            selected = self.viewer_text.get("sel.first", "sel.last")
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(selected)
            self.viewer_text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass  # No selection

    def _copy(self):
        """Copy selected text to clipboard."""
        try:
            selected = self.viewer_text.get("sel.first", "sel.last")
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(selected)
        except tk.TclError:
            pass  # No selection

    def _search_next(self):
        """Find next occurrence of search term."""
        search_term = self.search_var.get()
        if not search_term:
            return

        # If search term changed, find all matches
        if not self._search_matches or self._last_search != search_term:
            self._find_all_matches(search_term)
            self._last_search = search_term

        if not self._search_matches:
            self.app.statusbar.config(text=f"'{search_term}' not found")
            return

        # Move to next match
        self._search_index = (self._search_index + 1) % len(self._search_matches)
        self._highlight_current_match()

    def _search_prev(self):
        """Find previous occurrence of search term."""
        search_term = self.search_var.get()
        if not search_term:
            return

        # If search term changed, find all matches
        if not self._search_matches or self._last_search != search_term:
            self._find_all_matches(search_term)
            self._last_search = search_term

        if not self._search_matches:
            self.app.statusbar.config(text=f"'{search_term}' not found")
            return

        # Move to previous match
        self._search_index = (self._search_index - 1) % len(self._search_matches)
        self._highlight_current_match()

    def _find_all_matches(self, search_term):
        """Find all matches in the text."""
        self._search_matches = []
        self._search_index = -1

        # Remove existing highlights
        self.viewer_text.tag_remove("search_highlight", "1.0", tk.END)
        self.viewer_text.tag_remove("search_current", "1.0", tk.END)

        if not search_term:
            return

        # Search through text (case insensitive)
        start_pos = "1.0"
        search_term_lower = search_term.lower()

        while True:
            pos = self.viewer_text.search(search_term, start_pos, stopindex=tk.END, nocase=True)
            if not pos:
                break

            end_pos = f"{pos}+{len(search_term)}c"
            self._search_matches.append((pos, end_pos))
            self.viewer_text.tag_add("search_highlight", pos, end_pos)
            start_pos = end_pos

    def _highlight_current_match(self):
        """Highlight the current match and scroll to it."""
        if not self._search_matches or self._search_index < 0:
            return

        # Remove previous current highlight
        self.viewer_text.tag_remove("search_current", "1.0", tk.END)

        # Apply current highlight
        pos, end_pos = self._search_matches[self._search_index]
        self.viewer_text.tag_add("search_current", pos, end_pos)

        # Scroll to match
        self.viewer_text.see(pos)
        self.viewer_text.mark_set("insert", pos)

        # Update status
        self.app.statusbar.config(
            text=f"Match {self._search_index + 1} of {len(self._search_matches)}"
        )

    def apply_theme(self):
        """Apply current theme to viewer components."""
        is_dark = self.app.dark_mode_var.get()

        if is_dark:
            text_bg = "#313335"
            text_fg = "#a9b7c6"
            select_bg = "#214283"
            menu_bg = "#2b2b2b"
            search_highlight = "#614900"
            search_current = "#8B4000"
        else:
            text_bg = "#ffffff"
            text_fg = "#000000"
            select_bg = "#0078d4"
            menu_bg = "#f0f0f0"
            search_highlight = "#FFFF00"
            search_current = "#FF8C00"

        self.viewer_text.configure(bg=text_bg, fg=text_fg, insertbackground=text_fg,
                                  selectbackground=select_bg, selectforeground=text_fg)
        self.viewer_text.tag_configure("search_highlight", background=search_highlight,
                                       foreground="#ffffff" if is_dark else "#000000")
        self.viewer_text.tag_configure("search_current", background=search_current,
                                       foreground="#ffffff" if is_dark else "#000000")
        self.viewer_context_menu.configure(bg=menu_bg, fg=text_fg,
                                          activebackground=select_bg, activeforeground=text_fg)

    def get_user(self):
        """Get current user filter."""
        return self.user_entry.get().strip()

    def set_user(self, user):
        """Set user filter."""
        self.user_entry.delete(0, tk.END)
        self.user_entry.insert(0, user)
