"""Connection management dialog."""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import threading

from sqlbench.adapters import get_adapter_choices, get_adapter, get_unavailable_adapters, ADAPTERS


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

    def _create_widgets(self):
        # Left side - list
        list_frame = ttk.Frame(self.top)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)

        self.conn_listbox = tk.Listbox(list_frame, width=25,
                                        bg=self.list_bg, fg=self.fg,
                                        selectbackground=self.select_bg,
                                        selectforeground=self.select_fg,
                                        highlightthickness=0)
        self.conn_listbox.pack(fill=tk.BOTH, expand=True)
        self.conn_listbox.bind("<<ListboxSelect>>", self._on_select)

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
        self.conn_listbox.delete(0, tk.END)
        self._connections = self.db.get_connections()
        available_types = {choice[0] for choice in get_adapter_choices()}
        for conn in self._connections:
            # Show type indicator
            db_type = conn.get("db_type", "ibmi")
            type_indicator = {"ibmi": "[i]", "ibmi_db": "[I]", "mysql": "[M]", "postgresql": "[P]"}.get(db_type, "[?]")
            # Mark unavailable connections
            if db_type not in available_types:
                type_indicator = "[!]"
            self.conn_listbox.insert(tk.END, f"{type_indicator} {conn['name']}")

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

    def _on_select(self, event):
        selection = self.conn_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < len(self._connections):
            conn = self._connections[idx]
            self._current_id = conn["id"]
            # Fetch full connection with password
            full_conn = self.db.get_connection_by_id(conn["id"])
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

        self.db.save_connection(name, db_type, host, port, database, user, password, conn_id=self._current_id)
        self._refresh_list()
        messagebox.showinfo("Saved", f"Connection '{name}' saved.", parent=self.top)

    def _delete(self):
        selection = self.conn_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < len(self._connections):
            conn = self._connections[idx]
            if messagebox.askyesno("Confirm Delete", f"Delete connection '{conn['name']}'?", parent=self.top):
                self.db.delete_connection(conn["id"])
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

        def install_clidriver(log_status):
            """Download and install IBM Db2 clidriver for ibm_db."""
            import platform
            import tarfile
            import urllib.request
            from pathlib import Path

            # Determine platform and download URL
            system = platform.system().lower()
            machine = platform.machine().lower()

            if system == "linux" and machine in ("x86_64", "amd64"):
                url = "https://public.dhe.ibm.com/ibmdl/export/pub/software/data/db2/drivers/odbc_cli/linuxx64_odbc_cli.tar.gz"
            elif system == "linux" and machine in ("aarch64", "arm64"):
                url = "https://public.dhe.ibm.com/ibmdl/export/pub/software/data/db2/drivers/odbc_cli/linuxarm64_odbc_cli.tar.gz"
            elif system == "darwin" and machine in ("x86_64", "amd64"):
                url = "https://public.dhe.ibm.com/ibmdl/export/pub/software/data/db2/drivers/odbc_cli/macos64_odbc_cli.tar.gz"
            elif system == "darwin" and machine == "arm64":
                # M1/M2 Mac - use x86_64 version with Rosetta or native if available
                url = "https://public.dhe.ibm.com/ibmdl/export/pub/software/data/db2/drivers/odbc_cli/macos64_odbc_cli.tar.gz"
            elif system == "windows":
                log_status("  Windows: Please download clidriver manually from IBM")
                return False
            else:
                log_status(f"  Unsupported platform: {system}/{machine}")
                return False

            # Set up paths
            home = Path.home()
            driver_dir = home / "db2drivers"
            clidriver_path = driver_dir / "clidriver"
            tar_file = driver_dir / "odbc_cli.tar.gz"

            # Check if already installed
            if (clidriver_path / "lib").exists():
                log_status("  clidriver already installed")
                return True

            try:
                # Create directory
                driver_dir.mkdir(parents=True, exist_ok=True)

                # Download
                log_status("  Downloading clidriver (~100MB)...")
                urllib.request.urlretrieve(url, tar_file)

                # Extract
                log_status("  Extracting...")
                with tarfile.open(tar_file, "r:gz") as tar:
                    tar.extractall(path=driver_dir)

                # Clean up tar file
                tar_file.unlink()

                # Set environment variable hint
                log_status("  clidriver installed to ~/db2drivers/clidriver")

                # Update environment for current process
                import os
                cli_path = str(clidriver_path)
                os.environ["IBM_DB_HOME"] = cli_path
                lib_path = os.environ.get("LD_LIBRARY_PATH", "")
                os.environ["LD_LIBRARY_PATH"] = f"{cli_path}/lib:{lib_path}"

                # Add to shell config
                shell_config = home / ".bashrc"
                if not shell_config.exists():
                    shell_config = home / ".profile"

                config_lines = [
                    f'\n# IBM Db2 clidriver (added by SQLBench)',
                    f'export IBM_DB_HOME=~/db2drivers/clidriver',
                    f'export LD_LIBRARY_PATH=$IBM_DB_HOME/lib:$LD_LIBRARY_PATH',
                ]

                # Check if already in config
                try:
                    existing = shell_config.read_text() if shell_config.exists() else ""
                    if "IBM_DB_HOME" not in existing:
                        with open(shell_config, "a") as f:
                            f.write("\n".join(config_lines) + "\n")
                        log_status(f"  Added environment vars to {shell_config.name}")
                except Exception:
                    log_status("  Note: Add IBM_DB_HOME to your shell config manually")

                return True

            except Exception as e:
                log_status(f"  clidriver install failed: {e}")
                return False

        def do_install():
            install_btn.config(state=tk.DISABLED)
            selected = [db_type for db_type, var in check_vars.items() if var.get()]
            if not selected:
                log_status("No drivers selected.")
                install_btn.config(state=tk.NORMAL)
                return

            python = sys.executable
            for db_type in selected:
                extra = {"ibmi": "ibmi", "ibmi_db": "ibmi-db", "mysql": "mysql", "postgresql": "postgresql"}.get(db_type)
                if extra:
                    # Special handling for ibm_db - need clidriver first
                    if db_type == "ibmi_db":
                        log_status("Installing IBM clidriver...")
                        if not install_clidriver(log_status):
                            log_status("  Skipping ibm_db (clidriver required)")
                            continue

                    # Map db_type to actual pip package
                    packages = {
                        "ibmi": "pyodbc",
                        "ibmi_db": "ibm_db",
                        "mysql": "mysql-connector-python",
                        "postgresql": "psycopg2-binary",
                    }
                    package = packages.get(db_type, extra)
                    log_status(f"Installing {package}...")
                    try:
                        # Set up environment - inherit current env and add IBM_DB_HOME if needed
                        env = os.environ.copy()
                        if db_type == "ibmi_db":
                            cli_path = Path.home() / "db2drivers" / "clidriver"
                            if cli_path.exists():
                                env["IBM_DB_HOME"] = str(cli_path)

                        result = subprocess.run(
                            [python, "-m", "pip", "install", package],
                            capture_output=True, text=True, timeout=180, env=env
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

            log_status("\nDone! Please restart SQLBench to use new drivers.")
            install_btn.config(state=tk.NORMAL)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        install_btn = ttk.Button(btn_frame, text="Install Selected", command=lambda: threading.Thread(target=do_install, daemon=True).start())
        install_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
