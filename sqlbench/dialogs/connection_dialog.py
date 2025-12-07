"""Connection management dialog."""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import threading

from sqlbench.adapters import get_adapter_choices, get_adapter, get_unavailable_adapters, ADAPTERS


def _get_resource_path(filename):
    """Get the path to a resource file."""
    return Path(__file__).parent.parent / "resources" / filename


class ConnectionDialog:
    def __init__(self, parent, db, edit_name=None, app=None):
        self.db = db
        self.edit_name = edit_name
        self.app = app
        self._current_id = None  # Track current connection ID
        self._connections = []   # Store connections with IDs
        self.top = tk.Toplevel(parent)
        self.top.title("Connection" if edit_name else "Manage Connections")
        self.top.geometry("720x500")
        self.top.transient(parent)
        self.top.grab_set()

        # Apply theme
        self._apply_theme()

        self._create_widgets()
        self._refresh_list()

        # If editing specific connection, load it
        if edit_name:
            self._load_connection_by_name(edit_name)

        # ESC to close
        self.top.bind("<Escape>", lambda e: self.top.destroy())

    def _apply_theme(self):
        """Apply dark/light theme colors."""
        is_dark = self.app.dark_mode_var.get() if self.app else False
        if is_dark:
            self.bg = "#2b2b2b"
            self.fg = "#a9b7c6"
            self.list_bg = "#313335"
            self.select_bg = "#214283"
            self.select_fg = "#a9b7c6"
            self.status_fg = "#a9b7c6"  # For "Testing..." message
        else:
            self.bg = "#f0f0f0"
            self.fg = "#000000"
            self.list_bg = "#ffffff"
            self.select_bg = "#0078d4"
            self.select_fg = "#ffffff"
            self.status_fg = "#000000"

        self.top.configure(bg=self.bg)

    def _load_db_icons(self):
        """Load database type icons."""
        self._db_icons = {}
        icon_map = {
            "ibmi": "db_ibmi.png",
            "mysql": "db_mysql.png",
            "postgresql": "db_postgresql.png",
            "unknown": "db_unknown.png",
        }
        for db_type, filename in icon_map.items():
            try:
                icon_path = _get_resource_path(filename)
                if icon_path.exists():
                    self._db_icons[db_type] = tk.PhotoImage(file=str(icon_path))
            except Exception:
                pass

    def _create_widgets(self):
        # Load database icons
        self._load_db_icons()

        # Left side - list
        list_frame = ttk.Frame(self.top)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)

        # Use Treeview instead of Listbox to support icons
        self.conn_tree = ttk.Treeview(list_frame, selectmode="browse", show="tree")
        self.conn_tree.column("#0", width=180)
        self.conn_tree.pack(fill=tk.BOTH, expand=True)
        self.conn_tree.bind("<<TreeviewSelect>>", self._on_select)

        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="New", command=self._new).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete).pack(side=tk.LEFT, padx=2)

        # Right side - details
        detail_frame = ttk.LabelFrame(self.top, text="Connection Details")
        detail_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Configure column weights so entries expand
        detail_frame.columnconfigure(1, weight=1)

        row = 0

        # Name
        ttk.Label(detail_frame, text="Name:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.name_entry = ttk.Entry(detail_frame, width=40)
        self.name_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        row += 1

        # Database Type
        ttk.Label(detail_frame, text="Type:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.db_type_var = tk.StringVar(value="ibmi")
        available_choices = get_adapter_choices()
        self.db_type_combo = ttk.Combobox(
            detail_frame,
            textvariable=self.db_type_var,
            values=[choice[1] for choice in available_choices],
            state="readonly",
            width=37
        )
        self.db_type_combo.grid(row=row, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        self.db_type_combo.bind("<<ComboboxSelected>>", self._on_type_change)
        # Map display names to db_type keys (available only)
        self._type_map = {choice[1]: choice[0] for choice in available_choices}
        self._type_map_reverse = {choice[0]: choice[1] for choice in available_choices}
        # Set default to first available adapter
        if available_choices:
            self.db_type_combo.set(available_choices[0][1])
        row += 1

        # Show unavailable adapters with install button
        unavailable = get_unavailable_adapters()
        if unavailable:
            unavail_frame = ttk.Frame(detail_frame)
            unavail_frame.grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=5, pady=2)
            unavail_text = "Unavailable: " + ", ".join(f"{name}" for _, name, _ in unavailable)
            ttk.Label(unavail_frame, text=unavail_text, foreground="gray").pack(side=tk.LEFT)
            ttk.Button(
                unavail_frame, text="Install...", width=8,
                command=lambda: self._show_install_dialog(unavailable)
            ).pack(side=tk.LEFT, padx=(10, 0))
            row += 1

        # Host
        ttk.Label(detail_frame, text="Host:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.host_entry = ttk.Entry(detail_frame, width=40)
        self.host_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        row += 1

        # Port
        self.port_label = ttk.Label(detail_frame, text="Port:")
        self.port_label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.port_entry = ttk.Entry(detail_frame, width=10)
        self.port_entry.grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)
        row += 1

        # Database
        self.database_label = ttk.Label(detail_frame, text="Database:")
        self.database_label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.database_entry = ttk.Entry(detail_frame, width=40)
        self.database_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        row += 1

        # User
        ttk.Label(detail_frame, text="User:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.user_entry = ttk.Entry(detail_frame, width=40)
        self.user_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        row += 1

        # Password
        ttk.Label(detail_frame, text="Password:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        self.pass_entry = ttk.Entry(detail_frame, width=40, show="*")
        self.pass_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        row += 1

        # Production checkbox
        self.is_production_var = tk.BooleanVar(value=False)
        self.production_check = ttk.Checkbutton(
            detail_frame, text="Production (confirm before data changes)",
            variable=self.is_production_var
        )
        self.production_check.grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        row += 1

        # Duplicate protection checkbox
        self.duplicate_protection_var = tk.BooleanVar(value=False)
        self.duplicate_check = ttk.Checkbutton(
            detail_frame, text="Duplicate protection (warn on repeated statements)",
            variable=self.duplicate_protection_var
        )
        self.duplicate_check.grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        row += 1

        # Test and Save buttons
        btn_frame = ttk.Frame(detail_frame)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=20)

        self.test_btn = ttk.Button(btn_frame, text="Test", command=self._test)
        self.test_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=5)

        # Status label for test results (with word wrap)
        self.test_status = ttk.Label(detail_frame, text="", wraplength=350)
        self.test_status.grid(row=row + 1, column=0, columnspan=3, padx=10, pady=5)

        # Initial visibility based on default type
        self._update_field_visibility()

    def _on_type_change(self, event=None):
        """Handle database type change."""
        self._update_field_visibility()

    def _update_field_visibility(self):
        """Show/hide fields based on database type."""
        display_name = self.db_type_combo.get()
        db_type = self._type_map.get(display_name, "ibmi")
        adapter = get_adapter(db_type)

        # Show/hide port field
        if adapter.default_port:
            self.port_label.grid()
            self.port_entry.grid()
            if not self.port_entry.get():
                self.port_entry.delete(0, tk.END)
                self.port_entry.insert(0, str(adapter.default_port))
        else:
            self.port_label.grid_remove()
            self.port_entry.grid_remove()

        # Show/hide database field
        if adapter.requires_database:
            self.database_label.grid()
            self.database_entry.grid()
        else:
            self.database_label.grid_remove()
            self.database_entry.grid_remove()

    def _refresh_list(self):
        # Clear existing items
        for item in self.conn_tree.get_children():
            self.conn_tree.delete(item)

        self._connections = self.db.get_connections()
        available_types = {choice[0] for choice in get_adapter_choices()}

        for conn in self._connections:
            db_type = conn.get("db_type", "ibmi")
            # Use unknown icon if adapter not available
            if db_type not in available_types:
                icon = self._db_icons.get("unknown")
            else:
                icon = self._db_icons.get(db_type) or self._db_icons.get("unknown")

            if icon:
                self.conn_tree.insert("", tk.END, text=conn["name"], image=icon, values=(conn["id"],))
            else:
                self.conn_tree.insert("", tk.END, text=conn["name"], values=(conn["id"],))

    def _load_connection_by_name(self, name):
        """Load a specific connection into the form by name."""
        conn = self.db.get_connection(name)
        if conn:
            self._current_id = conn["id"]
            self._fill_form(conn)

    def _fill_form(self, conn):
        """Fill the form with connection data."""
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, conn["name"])

        # Set database type - handle unavailable adapters
        db_type = conn.get("db_type", "ibmi")
        display_name = self._type_map_reverse.get(db_type)
        if display_name:
            self.db_type_combo.set(display_name)
            self._update_field_visibility()
        else:
            # Adapter not available - show warning and get install hint
            adapter_cls = ADAPTERS.get(db_type)
            if adapter_cls:
                hint = adapter_cls.install_hint or f"Install {db_type} driver"
                self.test_status.config(
                    text=f"{adapter_cls.display_name} driver not installed. {hint}",
                    foreground="orange"
                )
            # Still need to fill the form for display, use first available adapter for field visibility
            available_choices = get_adapter_choices()
            if available_choices:
                self.db_type_combo.set(available_choices[0][1])

        self.host_entry.delete(0, tk.END)
        self.host_entry.insert(0, conn["host"])

        self.port_entry.delete(0, tk.END)
        if conn.get("port"):
            self.port_entry.insert(0, str(conn["port"]))
        else:
            # Set default port for type
            adapter = get_adapter(db_type)
            if adapter.default_port:
                self.port_entry.insert(0, str(adapter.default_port))

        self.database_entry.delete(0, tk.END)
        if conn.get("database"):
            self.database_entry.insert(0, conn["database"])

        self.user_entry.delete(0, tk.END)
        self.user_entry.insert(0, conn["user"])

        self.pass_entry.delete(0, tk.END)
        self.pass_entry.insert(0, conn["password"])

        self.is_production_var.set(bool(conn.get("is_production", 0)))
        self.duplicate_protection_var.set(bool(conn.get("duplicate_protection", 0)))

    def _on_select(self, event):
        selection = self.conn_tree.selection()
        if not selection:
            return

        item = selection[0]
        values = self.conn_tree.item(item, "values")
        if values:
            conn_id = int(values[0])
            self._current_id = conn_id
            # Fetch full connection with password
            full_conn = self.db.get_connection_by_id(conn_id)
            if full_conn:
                self._fill_form(full_conn)

    def _new(self):
        self._current_id = None
        self.name_entry.delete(0, tk.END)
        # Set to first available adapter
        available_choices = get_adapter_choices()
        if available_choices:
            self.db_type_combo.set(available_choices[0][1])
        self._update_field_visibility()
        self.host_entry.delete(0, tk.END)
        self.port_entry.delete(0, tk.END)
        self.database_entry.delete(0, tk.END)
        self.user_entry.delete(0, tk.END)
        self.pass_entry.delete(0, tk.END)
        self.is_production_var.set(False)
        self.duplicate_protection_var.set(False)
        self.name_entry.focus()

    def _save(self):
        name = self.name_entry.get().strip()
        display_name = self.db_type_combo.get()
        db_type = self._type_map.get(display_name, "ibmi")
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        port = int(port_str) if port_str else None
        database = self.database_entry.get().strip() or None
        user = self.user_entry.get().strip()
        password = self.pass_entry.get()

        if not all([name, host, user]):
            messagebox.showwarning("Missing Fields", "Name, Host, and User are required.", parent=self.top)
            return

        # Validate required database for certain types
        adapter = get_adapter(db_type)
        if adapter.requires_database and not database:
            messagebox.showwarning("Missing Fields", "Database name is required for this connection type.", parent=self.top)
            return

        is_production = self.is_production_var.get()
        duplicate_protection = self.duplicate_protection_var.get()
        self.db.save_connection(name, db_type, host, port, database, user, password, conn_id=self._current_id, is_production=is_production, duplicate_protection=duplicate_protection)
        self._refresh_list()
        messagebox.showinfo("Saved", f"Connection '{name}' saved.", parent=self.top)

    def _delete(self):
        selection = self.conn_tree.selection()
        if not selection:
            return

        item = selection[0]
        conn_name = self.conn_tree.item(item, "text")
        values = self.conn_tree.item(item, "values")
        if values:
            conn_id = int(values[0])
            if messagebox.askyesno("Confirm Delete", f"Delete connection '{conn_name}'?", parent=self.top):
                self.db.delete_connection(conn_id)
                self._refresh_list()
                self._new()

    def _test(self):
        """Test the connection with current form values."""
        display_name = self.db_type_combo.get()
        db_type = self._type_map.get(display_name, "ibmi")
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        try:
            port = int(port_str) if port_str else None
        except ValueError:
            self.test_status.config(text="Port must be a number", foreground="red")
            return
        database = self.database_entry.get().strip() or None
        user = self.user_entry.get().strip()
        password = self.pass_entry.get()

        if not all([host, user]):
            self.test_status.config(text="Host and User are required", foreground="red")
            return

        adapter = get_adapter(db_type)

        # Use default port if not specified
        if port is None and adapter.default_port:
            port = adapter.default_port
        if adapter.requires_database and not database:
            self.test_status.config(text="Database name required", foreground="red")
            return

        # Disable test button and show testing status
        self.test_btn.config(state=tk.DISABLED)
        self.test_status.config(text="Testing connection...", foreground=self.status_fg)
        self.top.update()

        # Run test in background thread
        def do_test():
            try:
                conn = adapter.connect(host, user, password, port, database)
                # Try a simple query to verify connection
                cursor = conn.cursor()
                cursor.execute(adapter.get_version_query())
                version = cursor.fetchone()[0] if cursor.description else "Connected"
                cursor.close()
                conn.close()
                self.top.after(0, self._test_success, str(version)[:50])
            except Exception as e:
                self.top.after(0, self._test_failure, str(e))

        thread = threading.Thread(target=do_test, daemon=True)
        thread.start()

    def _test_success(self, version):
        """Handle successful connection test."""
        self.test_btn.config(state=tk.NORMAL)
        self.test_status.config(text=f"Success! {version}", foreground="green")

    def _test_failure(self, error):
        """Handle failed connection test."""
        self.test_btn.config(state=tk.NORMAL)
        print(f"Connection test failed: {error}")  # Debug output
        self.test_status.config(text=f"Failed: {error}", foreground="red")

    def _show_install_dialog(self, unavailable):
        """Show dialog to install missing database drivers."""
        import subprocess
        import sys

        dialog = tk.Toplevel(self.top)
        dialog.title("Install Database Drivers")
        dialog.geometry("400x380")
        dialog.transient(self.top)
        dialog.grab_set()

        # Apply theme
        if self.app and self.app.dark_mode_var.get():
            dialog.configure(bg="#2b2b2b")

        ttk.Label(dialog, text="Select drivers to install:").pack(pady=(10, 5))

        # Create checkboxes for each unavailable driver
        check_vars = {}
        for db_type, name, hint in unavailable:
            var = tk.BooleanVar(value=True)
            check_vars[db_type] = var
            frame = ttk.Frame(dialog)
            frame.pack(fill=tk.X, padx=20, pady=2)
            ttk.Checkbutton(frame, text=name, variable=var).pack(side=tk.LEFT)
            ttk.Label(frame, text=f"({hint})", foreground="gray").pack(side=tk.LEFT, padx=(5, 0))

        # Status area
        status_text = tk.Text(dialog, height=8, width=45, state=tk.DISABLED)
        status_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        def log_status(msg):
            status_text.config(state=tk.NORMAL)
            status_text.insert(tk.END, msg + "\n")
            status_text.see(tk.END)
            status_text.config(state=tk.DISABLED)
            dialog.update()

        def do_install():
            install_btn.config(state=tk.DISABLED)
            selected = [db_type for db_type, var in check_vars.items() if var.get()]
            if not selected:
                log_status("No drivers selected.")
                install_btn.config(state=tk.NORMAL)
                return

            python = sys.executable
            for db_type in selected:
                extra = {"ibmi": "ibmi", "mysql": "mysql", "postgresql": "postgresql"}.get(db_type)
                if extra:
                    # Map db_type to actual pip package
                    packages = {
                        "ibmi": "pyodbc",
                        "mysql": "mysql-connector-python",
                        "postgresql": "psycopg2-binary",
                    }
                    package = packages.get(db_type, extra)
                    log_status(f"Installing {package}...")
                    try:
                        result = subprocess.run(
                            [python, "-m", "pip", "install", package],
                            capture_output=True, text=True, timeout=180
                        )
                        if result.returncode == 0:
                            log_status(f"  {extra}: OK")
                        else:
                            log_status(f"  {extra}: FAILED")
                            log_status(result.stderr[:200] if result.stderr else "Unknown error")
                    except subprocess.TimeoutExpired:
                        log_status(f"  {extra}: TIMEOUT")
                    except Exception as e:
                        log_status(f"  {extra}: ERROR - {e}")

            log_status("\nDone!")
            install_btn.config(state=tk.NORMAL)
            # Ask user if they want to restart
            dialog.after(0, ask_restart)

        def ask_restart():
            result = messagebox.askyesno(
                "Installation Complete",
                "Drivers installed successfully.\n\nWould you like to restart now?",
                parent=dialog
            )
            if result:
                dialog.destroy()
                if self.app:
                    self.app._restart_app()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        install_btn = ttk.Button(btn_frame, text="Install Selected", command=lambda: threading.Thread(target=do_install, daemon=True).start())
        install_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
