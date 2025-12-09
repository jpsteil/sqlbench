"""Main application window."""

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from sqlbench.database import Database
from sqlbench.adapters import get_adapter, ADAPTERS
from sqlbench.version import __version__
from sqlbench.tabs.sql_tab import SQLTab
from sqlbench.tabs.spool_tab import SpoolTab
from sqlbench.dialogs.connection_dialog import ConnectionDialog
from sqlbench.dialogs.regex_builder_dialog import RegexBuilderDialog


class SQLBenchApp:
    def __init__(self):
        # Set className for proper window manager integration (Linux/X11)
        # This makes the app show as "SQLBench" in window lists and match the .desktop file
        self.root = tk.Tk(className="sqlbench")
        self.root.title(f"SQLBench v{__version__}")

        # Hide window during setup to prevent visual flash during layout restoration
        self.root.withdraw()

        # Set window icon
        self._set_window_icon()

        self.db = Database()
        self.connections = {}  # name -> {conn, adapter, db_type, version, info}
        self.tab_count = 0
        self._loading_tables = set()  # Track connections currently loading tables
        self._loading_fields = set()  # Track tables currently loading fields
        self._connecting = set()  # Track connections currently being established
        self._pending_tabs = {}  # Tabs to restore after connection: conn_name -> [tab_info, ...]

        self._restore_geometry()
        self._create_menu()
        self._create_main_layout()
        self._create_statusbar()

        # Apply theme and font size
        self._apply_theme()
        self._apply_font_size()

        # Re-attach menu after theme (workaround for intermittent menu issue)
        self.root.config(menu=self.menubar)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Check window visibility after UI is set up
        self.root.after(50, self._ensure_visible_on_screen)

        # Restore last connection and tabs after UI is ready
        self.root.after(100, self._restore_session)

        # Check for updates in background
        self.root.after(500, self._check_for_updates)

    def _set_window_icon(self):
        """Set the window icon from the bundled PNG."""
        try:
            from pathlib import Path
            icon_path = Path(__file__).parent / "resources" / "sqlbench.png"
            if icon_path.exists():
                icon = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, icon)
                # Keep a reference to prevent garbage collection
                self._icon = icon
        except Exception:
            pass  # Silently fail if icon cannot be loaded

    def _load_db_icons(self):
        """Load database type icons for the connection tree."""
        from pathlib import Path
        self._db_icons = {}
        icon_map = {
            "ibmi": "db_ibmi.png",
            "mysql": "db_mysql.png",
            "postgresql": "db_postgresql.png",
            "unknown": "db_unknown.png",
        }
        resources = Path(__file__).parent / "resources"
        for db_type, filename in icon_map.items():
            try:
                icon_path = resources / filename
                if icon_path.exists():
                    self._db_icons[db_type] = tk.PhotoImage(file=str(icon_path))
            except Exception:
                pass

    def _create_menu(self):
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        # File menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=file_menu)

        self.dark_mode_var = tk.BooleanVar(value=self.db.get_setting("dark_mode", "0") == "1")
        file_menu.add_checkbutton(label="Dark Mode", variable=self.dark_mode_var,
                                  command=self._toggle_dark_mode)
        file_menu.add_command(label="Settings...", command=self._show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Reset Layout", command=self._reset_layout)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        # Load font size setting
        self.font_size = int(self.db.get_setting("font_size", "10"))

        # Help menu
        help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _create_main_layout(self):
        # Main paned window: left (connections) | right (tabs)
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - Connections
        conn_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(conn_frame, weight=0)

        # Connections header
        ttk.Label(conn_frame, text="Connections", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W, padx=2, pady=(2, 0))

        # Filter entry
        filter_frame = ttk.Frame(conn_frame)
        filter_frame.pack(fill=tk.X, padx=2, pady=2)
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self._on_filter_change)
        self.filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var, width=15)
        self.filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        ttk.Button(filter_frame, text="AI", width=3, command=self._open_regex_builder).pack(side=tk.LEFT, padx=(2, 0))

        # Store loaded tables for filtering
        self._loaded_tables = {}  # conn_name -> list of (schema, table_name, table_type)

        # Load database type icons
        self._load_db_icons()

        # Connection tree
        self.conn_tree = ttk.Treeview(conn_frame, show="tree", selectmode="browse")
        conn_scroll = ttk.Scrollbar(conn_frame, orient=tk.VERTICAL, command=self.conn_tree.yview)
        self.conn_tree.configure(yscrollcommand=conn_scroll.set)

        conn_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.conn_tree.pack(fill=tk.BOTH, expand=True)

        # Buttons below connection list
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.pack(fill=tk.X, padx=2, pady=2)
        ttk.Button(btn_frame, text="+", width=3, command=self._new_connection).pack(side=tk.LEFT, padx=1)
        ttk.Button(btn_frame, text="-", width=3, command=self._delete_connection).pack(side=tk.LEFT, padx=1)

        # Right-click context menu
        self.conn_menu = tk.Menu(self.root, tearoff=0)
        self.conn_menu.add_command(label="Connect", command=self._connect_selected)
        self.conn_menu.add_command(label="Disconnect", command=self._disconnect_selected)
        self.conn_menu.add_separator()
        self.conn_menu.add_command(label="New SQL", command=self._new_sql_tab)
        self.conn_menu.add_command(label="New Spool Files", command=self._new_spool_tab)
        self.conn_menu.add_separator()
        self.conn_menu.add_command(label="Show First 1000 Rows", command=self._show_first_1000_rows)
        self.conn_menu.add_separator()
        self.conn_menu.add_command(label="New Connection...", command=self._new_connection)
        self.conn_menu.add_command(label="Edit...", command=self._edit_connection)
        self.conn_menu.add_command(label="Delete", command=self._delete_connection)

        self.conn_tree.bind("<Button-3>", self._show_conn_menu)
        self.conn_tree.bind("<Double-1>", self._on_tree_double_click)
        self.conn_tree.bind("<<TreeviewOpen>>", self._on_tree_expand)

        # Keyboard navigation for connection tree
        self.conn_tree.bind("<Right>", self._on_tree_right_arrow)
        self.conn_tree.bind("<Left>", self._on_tree_left_arrow)
        self.conn_tree.bind("<space>", self._on_tree_space)
        self.conn_tree.bind("<Return>", self._on_tree_space)

        # Dismiss menu when clicking elsewhere
        self.root.bind("<Button-1>", self._dismiss_menus)

        # SQL tab keyboard shortcuts
        self.root.bind("<F5>", self._run_active_sql_query)
        self.root.bind("<Control-F5>", self._run_active_sql_script)
        self.root.bind("<Escape>", self._cancel_active_sql_query)
        self.root.bind("<Control-s>", self._save_active_sql_query)
        self.root.bind("<Control-S>", self._save_active_sql_query)
        self.root.bind("<Control-o>", self._load_active_sql_query)
        self.root.bind("<Control-O>", self._load_active_sql_query)

        # Right panel - Notebook for tabs
        self._create_closeable_notebook_style()
        self.notebook = ttk.Notebook(self.main_paned)
        self.main_paned.add(self.notebook, weight=1)

        # Enable tab closing via middle-click and right-click menu
        self.notebook.bind("<Button-2>", self._close_tab_middle_click)  # Middle click
        self.notebook.bind("<Button-3>", self._show_tab_menu)  # Right click

        # Enable tab drag-and-drop reordering
        self._drag_start_index = None
        self.notebook.bind("<Button-1>", self._tab_drag_start)
        self.notebook.bind("<B1-Motion>", self._tab_drag_motion)
        self.notebook.bind("<ButtonRelease-1>", self._tab_drag_end)

        # Tab context menu
        self.tab_menu = tk.Menu(self.root, tearoff=0)
        self.tab_menu.add_command(label="Close Tab", command=self._close_current_tab)

        self._refresh_connections()

    def _create_closeable_notebook_style(self):
        """Create a notebook style with close button character in tab names."""
        style = ttk.Style()

        # Use clam theme as base for consistent cross-platform look
        if "clam" in style.theme_names():
            style.theme_use("clam")

    def _create_statusbar(self):
        self.statusbar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def _refresh_connections(self):
        """Refresh the connection tree."""
        self.conn_tree.delete(*self.conn_tree.get_children())
        for conn in self.db.get_connections():
            name = conn["name"]
            db_type = conn.get("db_type", "ibmi")

            # Get icon for database type
            icon = self._db_icons.get(db_type) or self._db_icons.get("unknown")

            # Show connected status
            status = " (connected)" if name in self.connections else ""
            if icon:
                node_id = self.conn_tree.insert("", tk.END, iid=name, text=f"  {name}{status}", image=icon)
            else:
                node_id = self.conn_tree.insert("", tk.END, iid=name, text=f"{name}{status}")

            # Add placeholder child so connection can be expanded (if connected)
            if name in self.connections:
                # Check if tables already loaded
                if not self.conn_tree.get_children(node_id):
                    self.conn_tree.insert(node_id, tk.END, iid=f"{name}::loading", text="Loading...")

    def _on_tree_double_click(self, event):
        """Handle double-click on tree item - toggle open/closed state."""
        try:
            item = self.conn_tree.identify_row(event.y)
            if not item:
                return "break"

            # Skip loading/error placeholder nodes and fields
            if "::loading" in item or "::error" in item or "::field_" in item:
                return "break"

            # Toggle open/closed state
            is_open = self.conn_tree.item(item, "open")
            if is_open:
                self.conn_tree.item(item, open=False)
            else:
                # For connections not yet connected, connect first
                if "::" not in item and item not in self.connections:
                    self._connect_selected()
                else:
                    self.conn_tree.item(item, open=True)
                    # Manually trigger expand logic since <<TreeviewOpen>> may not fire
                    self._handle_node_expand(item)
        except Exception:
            pass  # Don't let tree errors crash the app

        return "break"  # Prevent default double-click behavior

    def _handle_node_expand(self, item):
        """Handle expansion of a node - load tables or fields if needed."""
        try:
            children = self.conn_tree.get_children(item)
            if not children:
                return

            first_child = children[0]

            # Connection node - load tables
            if "::" not in item and item in self.connections:
                if first_child.endswith("::loading"):
                    self._load_tables_for_connection(item)

            # Table node - load fields
            elif first_child.endswith("::fields_loading"):
                conn_name = item.split("::")[0]
                table_ref = item.split("::", 1)[1] if "::" in item else None
                if conn_name in self.connections and table_ref and "." in table_ref:
                    self._load_fields_for_table(conn_name, item, table_ref)
        except Exception:
            pass

    def _on_tree_expand(self, event):
        """Handle tree node expansion via arrow click."""
        item = self.conn_tree.focus()
        if item:
            self._handle_node_expand(item)

    def _on_tree_right_arrow(self, event):
        """Handle right arrow: expand if closed, move to first child if open."""
        item = self.conn_tree.focus()
        if not item:
            return

        # Skip placeholder nodes
        if "::loading" in item or "::error" in item or "::field_" in item:
            return

        is_open = self.conn_tree.item(item, "open")
        children = self.conn_tree.get_children(item)

        if not is_open and children:
            # Node is closed and has children - expand it
            self.conn_tree.item(item, open=True)
            self._handle_node_expand(item)
        elif is_open and children:
            # Node is open - move to first child
            first_child = children[0]
            # Skip loading/error placeholders
            if "::loading" not in first_child and "::error" not in first_child:
                self.conn_tree.focus(first_child)
                self.conn_tree.selection_set(first_child)
        elif not children:
            # No children - for unconnected connections, try to connect
            if "::" not in item and item not in self.connections:
                self._connect_selected()

        return "break"

    def _on_tree_left_arrow(self, event):
        """Handle left arrow: collapse if open, move to parent if closed."""
        item = self.conn_tree.focus()
        if not item:
            return

        # Skip placeholder nodes
        if "::loading" in item or "::error" in item or "::field_" in item:
            return

        is_open = self.conn_tree.item(item, "open")

        if is_open:
            # Node is open - collapse it
            self.conn_tree.item(item, open=False)
        else:
            # Node is closed - move to parent
            parent = self.conn_tree.parent(item)
            if parent:
                self.conn_tree.focus(parent)
                self.conn_tree.selection_set(parent)

        return "break"

    def _on_tree_space(self, event):
        """Handle space/enter: toggle expand/collapse."""
        item = self.conn_tree.focus()
        if not item:
            return

        # Skip placeholder nodes
        if "::loading" in item or "::error" in item or "::field_" in item:
            return "break"

        is_open = self.conn_tree.item(item, "open")
        children = self.conn_tree.get_children(item)

        if children:
            # Toggle open/closed
            if is_open:
                self.conn_tree.item(item, open=False)
            else:
                self.conn_tree.item(item, open=True)
                self._handle_node_expand(item)
        elif "::" not in item and item not in self.connections:
            # Unconnected connection node with no children - connect
            self._connect_selected()

        return "break"

    def _load_tables_for_connection(self, conn_name):
        """Load tables for a connection."""
        if conn_name not in self.connections:
            return

        # Prevent concurrent loading
        if conn_name in self._loading_tables:
            return
        self._loading_tables.add(conn_name)

        conn_data = self.connections[conn_name]
        adapter = conn_data["adapter"]
        db_conn = conn_data["conn"]

        def load_tables():
            try:
                cursor = db_conn.cursor()
                cursor.execute(adapter.get_tables_query())
                tables = cursor.fetchall()
                cursor.close()
                # Update UI on main thread
                self.root.after(0, lambda: self._on_tables_loaded(conn_name, tables))
            except Exception as e:
                self.root.after(0, lambda: self._on_tables_load_error(conn_name, str(e)))

        # Run in background thread
        import threading
        thread = threading.Thread(target=load_tables, daemon=True)
        thread.start()

    def _on_tables_loaded(self, conn_name, tables):
        """Handle tables loaded - runs on main thread."""
        self._loading_tables.discard(conn_name)
        self._populate_tables(conn_name, tables)

    def _on_tables_load_error(self, conn_name, error):
        """Handle tables load error - runs on main thread."""
        self._loading_tables.discard(conn_name)
        self._tables_load_error(conn_name, error)

    def _populate_tables(self, conn_name, tables):
        """Populate the tree with tables."""
        # Store tables for filtering
        self._loaded_tables[conn_name] = list(tables)

        # Apply current filter
        self._display_filtered_tables(conn_name)

    def _display_filtered_tables(self, conn_name):
        """Display tables for a connection, applying the current filter."""
        if conn_name not in self._loaded_tables:
            return

        # Remove existing children
        for child in self.conn_tree.get_children(conn_name):
            self.conn_tree.delete(child)

        tables = self._loaded_tables[conn_name]
        filter_text = self.filter_var.get().strip()

        # Try to compile as regex, fall back to literal match if invalid
        filter_regex = None
        if filter_text:
            try:
                filter_regex = re.compile(filter_text, re.IGNORECASE)
            except re.error:
                # Invalid regex - treat as literal string match
                filter_regex = None

        # Group tables by schema, applying filter
        schemas = {}
        for row in tables:
            schema, table_name, table_type = row[0], row[1], row[2]

            # Apply filter to table name or schema name
            if filter_text:
                if filter_regex:
                    # Use regex search
                    if not filter_regex.search(table_name) and not filter_regex.search(schema):
                        continue
                else:
                    # Fall back to literal case-insensitive match
                    filter_upper = filter_text.upper()
                    if filter_upper not in table_name.upper() and filter_upper not in schema.upper():
                        continue

            if schema not in schemas:
                schemas[schema] = []
            schemas[schema].append((table_name, table_type))

        # Add schema nodes and tables
        for schema in sorted(schemas.keys()):
            schema_id = f"{conn_name}::{schema}"
            table_count = len(schemas[schema])
            self.conn_tree.insert(conn_name, tk.END, iid=schema_id, text=f"[S] {schema} ({table_count})")

            for table_name, table_type in sorted(schemas[schema]):
                type_char = "V" if table_type in ("VIEW", "V") else "T"
                table_id = f"{conn_name}::{schema}.{table_name}"
                self.conn_tree.insert(schema_id, tk.END, iid=table_id, text=f"[{type_char}] {table_name}")
                # Add placeholder for fields
                self.conn_tree.insert(table_id, tk.END, iid=f"{table_id}::fields_loading", text="Loading...")

        # Auto-expand connection if filter is active
        if filter_text and schemas:
            self.conn_tree.item(conn_name, open=True)
            for schema in schemas.keys():
                self.conn_tree.item(f"{conn_name}::{schema}", open=True)

    def _on_filter_change(self, *args):
        """Handle filter text change."""
        # Reapply filter to all loaded connections
        for conn_name in self._loaded_tables:
            self._display_filtered_tables(conn_name)

    def _open_regex_builder(self):
        """Open the AI regex builder dialog."""
        def on_regex_generated(regex):
            self.filter_var.set(regex)

        RegexBuilderDialog(self.root, callback=on_regex_generated)

    def _tables_load_error(self, conn_name, error):
        """Handle error loading tables."""
        # Remove loading placeholder
        for child in self.conn_tree.get_children(conn_name):
            self.conn_tree.delete(child)

        self.conn_tree.insert(conn_name, tk.END, iid=f"{conn_name}::error", text=f"Error: {error[:50]}")

    def _load_fields_for_table(self, conn_name, table_node_id, table_ref):
        """Load fields for a table."""
        if conn_name not in self.connections:
            return

        # Prevent concurrent loading
        if table_node_id in self._loading_fields:
            return
        self._loading_fields.add(table_node_id)

        conn_data = self.connections[conn_name]
        adapter = conn_data["adapter"]
        db_conn = conn_data["conn"]

        def load_fields():
            try:
                columns_query = adapter.get_columns_query([table_ref])
                if not columns_query:
                    self.root.after(0, lambda: self._on_fields_error(table_node_id, "Not supported"))
                    return

                cursor = db_conn.cursor()
                cursor.execute(columns_query)
                fields = cursor.fetchall()
                cursor.close()
                # Update UI on main thread
                self.root.after(0, lambda: self._on_fields_loaded(table_node_id, fields))
            except Exception as e:
                self.root.after(0, lambda: self._on_fields_error(table_node_id, str(e)))

        # Run in background thread
        import threading
        thread = threading.Thread(target=load_fields, daemon=True)
        thread.start()

    def _on_fields_loaded(self, table_node_id, fields):
        """Handle fields loaded - runs on main thread."""
        self._loading_fields.discard(table_node_id)
        self._populate_fields(table_node_id, fields)

    def _on_fields_error(self, table_node_id, error):
        """Handle fields load error - runs on main thread."""
        self._loading_fields.discard(table_node_id)
        self._fields_load_error(table_node_id, error)

    def _populate_fields(self, table_node_id, fields):
        """Populate the tree with fields."""
        # Remove loading placeholder
        for child in self.conn_tree.get_children(table_node_id):
            self.conn_tree.delete(child)

        # Update table node text with field count
        current_text = self.conn_tree.item(table_node_id, "text")
        # Remove old count if present
        if " (" in current_text and current_text.endswith(")"):
            # Check if it's a field count (not type indicator)
            last_paren = current_text.rfind(" (")
            if last_paren > 3:  # After "[T] "
                current_text = current_text[:last_paren]
        self.conn_tree.item(table_node_id, text=f"{current_text} ({len(fields)})")

        # Fields format from adapter: (schema, table, column_name, data_type, length, scale)
        for i, row in enumerate(fields):
            col_name = row[2]
            data_type = row[3]
            length = row[4]
            scale = row[5]

            # Build type string
            if length and scale:
                type_str = f"{data_type}({length},{scale})"
            elif length:
                type_str = f"{data_type}({length})"
            else:
                type_str = str(data_type)

            field_id = f"{table_node_id}::field_{i}"
            self.conn_tree.insert(table_node_id, tk.END, iid=field_id, text=f"{col_name} ({type_str})")

    def _fields_load_error(self, table_node_id, error):
        """Handle error loading fields."""
        # Remove loading placeholder
        for child in self.conn_tree.get_children(table_node_id):
            self.conn_tree.delete(child)

        self.conn_tree.insert(table_node_id, tk.END, iid=f"{table_node_id}::error", text=f"Error: {error[:40]}")

    def _dismiss_menus(self, event=None):
        """Dismiss any open context menus."""
        try:
            self.conn_menu.unpost()
            self.tab_menu.unpost()
        except Exception:
            pass

    def _run_active_sql_query(self, event=None):
        """Run query on the currently active SQL tab."""
        try:
            selected = self.notebook.select()
            if not selected:
                return
            tab_frame = self.notebook.nametowidget(selected)
            if hasattr(tab_frame, 'sql_tab'):
                tab_frame.sql_tab._run_query()
        except Exception:
            pass

    def _run_active_sql_script(self, event=None):
        """Run all statements on the currently active SQL tab."""
        try:
            selected = self.notebook.select()
            if not selected:
                return
            tab_frame = self.notebook.nametowidget(selected)
            if hasattr(tab_frame, 'sql_tab'):
                tab_frame.sql_tab._run_script()
        except Exception:
            pass

    def _cancel_active_sql_query(self, event=None):
        """Cancel query on the currently active SQL tab."""
        try:
            selected = self.notebook.select()
            if not selected:
                return
            tab_frame = self.notebook.nametowidget(selected)
            if hasattr(tab_frame, 'sql_tab'):
                tab_frame.sql_tab._cancel_query()
        except Exception:
            pass

    def _save_active_sql_query(self, event=None):
        """Save query from the currently active SQL tab."""
        try:
            selected = self.notebook.select()
            if not selected:
                return
            tab_frame = self.notebook.nametowidget(selected)
            if hasattr(tab_frame, 'sql_tab'):
                tab_frame.sql_tab._save_query()
                return "break"  # Prevent default Ctrl+S behavior
        except Exception:
            pass

    def _load_active_sql_query(self, event=None):
        """Load query into the currently active SQL tab."""
        try:
            selected = self.notebook.select()
            if not selected:
                return
            tab_frame = self.notebook.nametowidget(selected)
            if hasattr(tab_frame, 'sql_tab'):
                tab_frame.sql_tab._load_query()
                return "break"  # Prevent default Ctrl+O behavior
        except Exception:
            pass

    def _show_conn_menu(self, event):
        """Show context menu on right-click."""
        item = self.conn_tree.identify_row(event.y)
        if item:
            self.conn_tree.selection_set(item)

            # Get connection name (handle table/schema selections)
            conn_name = item.split("::")[0] if "::" in item else item

            # Enable/disable menu items based on connection state
            is_connected = conn_name in self.connections
            supports_spool = False
            if is_connected:
                supports_spool = self.connections[conn_name]["adapter"].supports_spool

            # Check if clicked on a table (format: conn_name::schema.table)
            is_table = "::" in item and "." in item.split("::", 1)[1]

            self.conn_menu.entryconfig("Connect", state=tk.DISABLED if is_connected else tk.NORMAL)
            self.conn_menu.entryconfig("Disconnect", state=tk.NORMAL if is_connected else tk.DISABLED)
            self.conn_menu.entryconfig("New SQL", state=tk.NORMAL if is_connected else tk.DISABLED)
            self.conn_menu.entryconfig("New Spool Files", state=tk.NORMAL if is_connected and supports_spool else tk.DISABLED)
            self.conn_menu.entryconfig("Show First 1000 Rows", state=tk.NORMAL if is_connected and is_table else tk.DISABLED)
            self.conn_menu.post(event.x_root, event.y_root)

    def _show_first_1000_rows(self):
        """Show first 1000 rows of the selected table."""
        selection = self.conn_tree.selection()
        if not selection:
            return

        item = selection[0]
        if "::" not in item:
            return

        conn_name = item.split("::")[0]
        table_ref = item.split("::", 1)[1]

        # table_ref is schema.table
        if "." not in table_ref:
            return

        if conn_name not in self.connections:
            return

        conn_data = self.connections[conn_name]
        adapter = conn_data["adapter"]

        # Build query with appropriate LIMIT syntax
        sql = adapter.get_select_limit_query(table_ref, 1000)

        # Select the connection and create a new SQL tab
        self.conn_tree.selection_set(conn_name)
        self._new_sql_tab(initial_sql=sql)

        # Execute the query
        self.root.after(100, self._run_active_sql_query)

    def _get_selected_connection(self):
        """Get the currently selected connection name."""
        selection = self.conn_tree.selection()
        if not selection:
            return None
        item = selection[0]
        # Handle table/schema selections (format: "conn_name::schema.table")
        if "::" in item:
            return item.split("::")[0]
        return item

    def _connect_selected(self):
        """Connect to the selected connection (async)."""
        name = self._get_selected_connection()
        if not name or name in self.connections:
            return

        # Check if already connecting
        if name in self._connecting:
            return
        self._connecting.add(name)

        conn_info = self.db.get_connection(name)
        if not conn_info:
            self._connecting.discard(name)
            return

        # Check if adapter is available
        db_type = conn_info.get("db_type", "ibmi")
        adapter_cls = ADAPTERS.get(db_type)
        if adapter_cls and not adapter_cls.is_available():
            hint = adapter_cls.install_hint or f"Install {db_type} driver"
            self.statusbar.config(text=f"{adapter_cls.display_name} driver not installed. {hint}")
            self._connecting.discard(name)
            return

        self.statusbar.config(text=f"Connecting to {name}...")

        def do_connect():
            try:
                adapter = get_adapter(db_type)

                db_conn = adapter.connect(
                    host=conn_info['host'],
                    user=conn_info['user'],
                    password=conn_info['password'],
                    port=conn_info.get('port'),
                    database=conn_info.get('database')
                )
                version = adapter.get_version(db_conn)

                self.root.after(0, lambda: self._on_connected(name, db_conn, adapter, db_type, version, conn_info))
            except Exception as e:
                self.root.after(0, lambda: self._on_connect_error(name, str(e)))

        import threading
        thread = threading.Thread(target=do_connect, daemon=True)
        thread.start()

    def _on_connected(self, name, db_conn, adapter, db_type, version, conn_info):
        """Handle successful connection (main thread)."""
        self._connecting.discard(name)

        self.connections[name] = {
            "conn": db_conn,
            "adapter": adapter,
            "db_type": db_type,
            "version": version,
            "info": conn_info
        }

        self._refresh_connections()
        self.db.set_setting("last_connection", name)
        version_str = f" v{version}" if version else ""
        self.statusbar.config(text=f"Connected to {name}{version_str}")

        # Restore any pending tabs for this connection
        if name in self._pending_tabs:
            self.conn_tree.selection_set(name)
            for tab in self._pending_tabs[name]:
                if tab["tab_type"] == "sql":
                    self._new_sql_tab(initial_sql=tab.get("tab_data", ""))
                elif tab["tab_type"] == "spool":
                    self._new_spool_tab(initial_user=tab.get("tab_data", "*CURRENT"))
            del self._pending_tabs[name]

            # Select the first tab and restore layout
            if self.notebook.tabs():
                self.notebook.select(0)
            self.root.after(100, self._restore_layout)

    def _on_connect_error(self, name, error):
        """Handle connection error (main thread)."""
        self._connecting.discard(name)
        # Remove any pending tabs for this failed connection
        self._pending_tabs.pop(name, None)
        self.statusbar.config(text=f"Connection to {name} failed")
        tk.messagebox.showerror("Connection Error", f"{name}: {error}")

    def _disconnect_selected(self):
        """Disconnect the selected connection."""
        name = self._get_selected_connection()
        if not name or name not in self.connections:
            return

        self.connections[name]["conn"].close()
        del self.connections[name]
        self._refresh_connections()
        self.statusbar.config(text=f"Disconnected from {name}")


    def _count_tabs(self, conn_name, tab_type):
        """Count existing tabs of a given type for a connection."""
        count = 0
        for tab_id in self.notebook.tabs():
            try:
                tab_frame = self.notebook.nametowidget(tab_id)
                if getattr(tab_frame, "conn_name", None) == conn_name and \
                   getattr(tab_frame, "tab_type", None) == tab_type:
                    count += 1
            except Exception:
                pass
        return count

    def _new_sql_tab(self, initial_sql=""):
        """Create a new SQL tab for the selected connection."""
        name = self._get_selected_connection()
        if not name or name not in self.connections:
            return

        self.tab_count += 1
        conn_data = self.connections[name]

        # Create tab frame with close capability
        tab_frame = ttk.Frame(self.notebook)
        sql_tab = SQLTab(
            tab_frame, self, conn_data["conn"], name,
            conn_data["version"], conn_data["adapter"]
        )

        # Set initial SQL if provided
        if initial_sql:
            sql_tab.set_sql(initial_sql)

        # Generate tab title with number if duplicates exist
        existing_count = self._count_tabs(name, "sql")
        if existing_count > 0:
            tab_title = f"{name} SQL ({existing_count})"
        else:
            tab_title = f"{name} SQL"

        # Get icon for database type
        db_type = conn_data.get("db_type", "ibmi")
        icon = self._db_icons.get(db_type)
        if icon:
            self.notebook.add(tab_frame, text=tab_title, image=icon, compound=tk.LEFT)
        else:
            self.notebook.add(tab_frame, text=tab_title)
        self.notebook.select(tab_frame)

        # Store reference for cleanup
        tab_frame.sql_tab = sql_tab
        tab_frame.conn_name = name
        tab_frame.tab_type = "sql"

        # Apply theme to new widgets
        self._apply_theme_to_widgets()

    def _new_spool_tab(self, initial_user="*CURRENT"):
        """Create a new Spool Files tab for the selected connection (IBM i only)."""
        name = self._get_selected_connection()
        if not name or name not in self.connections:
            return

        conn_data = self.connections[name]

        # Spool files only available for IBM i
        if not conn_data["adapter"].supports_spool:
            tk.messagebox.showinfo("Not Available", "Spool files are only available for IBM i connections.")
            return

        self.tab_count += 1

        tab_frame = ttk.Frame(self.notebook)
        spool_tab = SpoolTab(tab_frame, self, conn_data["conn"], name, conn_data["version"])

        # Set initial user if provided
        if initial_user and initial_user != "*CURRENT":
            spool_tab.set_user(initial_user)

        # Generate tab title with number if duplicates exist
        existing_count = self._count_tabs(name, "spool")
        if existing_count > 0:
            tab_title = f"{name} SPLF ({existing_count})"
        else:
            tab_title = f"{name} SPLF"

        # Get icon for database type (spool is IBM i only, but get from conn_data for consistency)
        db_type = conn_data.get("db_type", "ibmi")
        icon = self._db_icons.get(db_type)
        if icon:
            self.notebook.add(tab_frame, text=tab_title, image=icon, compound=tk.LEFT)
        else:
            self.notebook.add(tab_frame, text=tab_title)
        self.notebook.select(tab_frame)

        tab_frame.spool_tab = spool_tab
        tab_frame.conn_name = name
        tab_frame.tab_type = "spool"

        # Apply theme to new widgets
        self._apply_theme_to_widgets()

    def _close_tab(self, tab_frame):
        """Close a tab."""
        try:
            self.notebook.forget(tab_frame)
        except Exception:
            pass

    def _close_tab_middle_click(self, event):
        """Close tab on middle click."""
        try:
            clicked_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if clicked_tab != "":
                tab_frame = self.notebook.nametowidget(self.notebook.tabs()[int(clicked_tab)])
                self._close_tab(tab_frame)
        except Exception:
            pass

    def _show_tab_menu(self, event):
        """Show context menu on tab right-click."""
        try:
            clicked_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if clicked_tab != "":
                self.notebook.select(int(clicked_tab))
                self.tab_menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def _close_current_tab(self):
        """Close the currently selected tab."""
        try:
            current = self.notebook.select()
            if current:
                self.notebook.forget(current)
        except Exception:
            pass

    def _tab_drag_start(self, event):
        """Start dragging a tab."""
        try:
            clicked_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if clicked_tab != "":
                self._drag_start_index = int(clicked_tab)
            else:
                self._drag_start_index = None
        except Exception:
            self._drag_start_index = None

    def _tab_drag_motion(self, event):
        """Handle tab drag motion."""
        if self._drag_start_index is None:
            return

        try:
            target_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if target_tab == "" or int(target_tab) == self._drag_start_index:
                return

            target_index = int(target_tab)
            tabs = self.notebook.tabs()

            # Move the tab
            tab_to_move = tabs[self._drag_start_index]
            self.notebook.insert(target_index, tab_to_move)
            self._drag_start_index = target_index
        except Exception:
            pass

    def _tab_drag_end(self, event):
        """End tab dragging."""
        self._drag_start_index = None

    def _new_connection(self):
        """Show dialog to create new connection."""
        dialog = ConnectionDialog(self.root, self.db, app=self)
        self.root.wait_window(dialog.top)
        self._refresh_connections()

    def _edit_connection(self):
        """Edit the selected connection."""
        old_name = self._get_selected_connection()
        if old_name:
            dialog = ConnectionDialog(self.root, self.db, edit_name=old_name, app=self)
            self.root.wait_window(dialog.top)
            self._refresh_connections()
            self._update_tab_names(old_name)

    def _update_tab_names(self, old_name):
        """Update tab names if connection was renamed."""
        # Check if the old_name still exists - if not, it was renamed
        conn = self.db.get_connection(old_name)
        if conn:
            # Name didn't change
            return

        # Find the new name by checking what connection was just edited
        if old_name not in self.connections:
            return

        # Get the host from our active connection
        conn_data = self.connections[old_name]
        old_host = conn_data.get("info", {}).get("host", "")

        # Look for connection with same host (the renamed one)
        new_name = None
        for c in self.db.get_connections():
            full_conn = self.db.get_connection(c["name"])
            if full_conn and full_conn["host"] == old_host:
                new_name = c["name"]
                break

        if not new_name or new_name == old_name:
            return

        # Update the connections dict
        self.connections[new_name] = self.connections.pop(old_name)

        # Update all tabs with the old connection name
        for tab_id in self.notebook.tabs():
            tab_frame = self.notebook.nametowidget(tab_id)
            if getattr(tab_frame, "conn_name", None) == old_name:
                tab_frame.conn_name = new_name
                tab_type = getattr(tab_frame, "tab_type", "")
                # Preserve any existing number suffix
                current_text = self.notebook.tab(tab_frame, "text")
                suffix = ""
                if "(" in current_text and current_text.endswith(")"):
                    suffix = " " + current_text[current_text.rfind("("):]
                if tab_type == "sql":
                    self.notebook.tab(tab_frame, text=f"{new_name} SQL{suffix}")
                elif tab_type == "spool":
                    self.notebook.tab(tab_frame, text=f"{new_name} SPLF{suffix}")

        # Update connection tree display
        self._refresh_connections()
        # Re-mark as connected
        for item in self.conn_tree.get_children():
            if self.conn_tree.item(item, "text") == new_name:
                self.conn_tree.item(item, values=("(connected)",))
                break

        # Update last_connection setting if it was the renamed one
        if self.db.get_setting("last_connection") == old_name:
            self.db.set_setting("last_connection", new_name)

        # Save tabs immediately to persist the name change
        self._save_tabs()

    def _delete_connection(self):
        """Delete the selected connection."""
        name = self._get_selected_connection()
        if not name:
            return

        if name in self.connections:
            tk.messagebox.showwarning("Connected", "Disconnect before deleting.")
            return

        if tk.messagebox.askyesno("Confirm Delete", f"Delete connection '{name}'?"):
            conn = self.db.get_connection(name)
            if conn:
                self.db.delete_connection(conn["id"])
            self._refresh_connections()

    def _install_launcher(self):
        """Install desktop launcher for the current OS."""
        from sqlbench.launcher import create_launcher
        try:
            success = create_launcher()
            if success:
                tk.messagebox.showinfo(
                    "Launcher Installed",
                    "Desktop launcher installed successfully.\n\n"
                    "You may need to log out and back in for it to appear in your application menu."
                )
            else:
                tk.messagebox.showwarning(
                    "Installation Failed",
                    "Could not install desktop launcher for this operating system."
                )
        except Exception as e:
            tk.messagebox.showerror("Error", f"Failed to install launcher:\n{e}")

    def _remove_launcher(self):
        """Remove desktop launcher for the current OS."""
        from sqlbench.launcher import remove_launcher
        try:
            success = remove_launcher()
            if success:
                tk.messagebox.showinfo(
                    "Launcher Removed",
                    "Desktop launcher removed successfully."
                )
            else:
                tk.messagebox.showinfo(
                    "No Launcher Found",
                    "No desktop launcher was found to remove."
                )
        except Exception as e:
            tk.messagebox.showerror("Error", f"Failed to remove launcher:\n{e}")

    def _check_for_updates(self):
        """Check for updates in background."""
        from sqlbench.version import check_for_updates, __version__

        def on_update_check(has_update, latest_version):
            if has_update:
                self.root.after(0, lambda: self._show_update_dialog(latest_version))

        check_for_updates(on_update_check)

    def _show_update_dialog(self, latest_version):
        """Show update available dialog."""
        from sqlbench.version import __version__

        result = tk.messagebox.askyesno(
            "Update Available",
            f"A new version of SQLBench is available.\n\n"
            f"Installed: {__version__}\n"
            f"Latest: {latest_version}\n\n"
            f"Would you like to upgrade now?\n\n"
            f"(This will run: pipx upgrade sqlbench)"
        )

        if result:
            self._run_upgrade()

    def _run_upgrade(self):
        """Run pipx upgrade in background."""
        import subprocess
        import threading

        def do_upgrade():
            try:
                result = subprocess.run(
                    ["pipx", "upgrade", "sqlbench"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self.root.after(0, self._show_restart_dialog)
                else:
                    error = result.stderr or result.stdout or "Unknown error"
                    self.root.after(0, lambda: tk.messagebox.showerror(
                        "Upgrade Failed",
                        f"Failed to upgrade:\n{error}"
                    ))
            except FileNotFoundError:
                self.root.after(0, lambda: tk.messagebox.showerror(
                    "Upgrade Failed",
                    "pipx not found. Please upgrade manually:\n\n"
                    "pipx upgrade sqlbench"
                ))
            except Exception as e:
                self.root.after(0, lambda: tk.messagebox.showerror(
                    "Upgrade Failed",
                    f"Failed to upgrade:\n{e}"
                ))

        self.statusbar.config(text="Upgrading SQLBench...")
        thread = threading.Thread(target=do_upgrade, daemon=True)
        thread.start()

    def _show_about(self):
        from sqlbench.version import __version__
        tk.messagebox.showinfo("About", f"SQLBench v{__version__}\nMulti-database SQL Workbench")

    def _show_restart_dialog(self, message="SQLBench has been upgraded.\n\nWould you like to restart now?"):
        """Show a dialog asking if user wants to restart."""
        result = tk.messagebox.askyesno(
            "Upgrade Complete",
            message
        )
        if result:
            self._restart_app()

    def _restart_app(self):
        """Restart the application."""
        import sys
        import os
        import subprocess

        # Save current state before restart
        self._save_geometry()
        self._save_active_tab()

        # Close connections gracefully
        for name in list(self.connections.keys()):
            try:
                self.connections[name]['conn'].close()
            except Exception:
                pass

        # Start new process BEFORE destroying the window
        if sys.argv[0].endswith('sqlbench') or 'sqlbench' in sys.argv[0]:
            # Running via entry point script (e.g., pipx)
            subprocess.Popen([sys.argv[0]])
        else:
            # Running via python -m sqlbench
            subprocess.Popen([sys.executable, '-m', 'sqlbench'])

        # Now destroy and exit
        self.root.destroy()
        os._exit(0)

    def _show_settings(self):
        """Show settings dialog."""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.transient(self.root)
        settings_win.grab_set()

        # Center on parent
        settings_win.geometry("350x200")
        settings_win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 350) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        settings_win.geometry(f"+{x}+{y}")

        # Apply dark mode
        is_dark = self.dark_mode_var.get()
        if is_dark:
            settings_win.configure(bg="#2b2b2b")
            fg = "#a9b7c6"
            entry_bg = "#313335"
        else:
            fg = "#000000"
            entry_bg = "#ffffff"

        # Font size setting
        font_frame = ttk.Frame(settings_win)
        font_frame.pack(fill=tk.X, padx=20, pady=(20, 10))

        ttk.Label(font_frame, text="Font Size:").pack(side=tk.LEFT)

        font_size_var = tk.StringVar(value=str(self.font_size))
        font_spin = ttk.Spinbox(font_frame, from_=6, to=24, width=5,
                                textvariable=font_size_var)
        font_spin.pack(side=tk.LEFT, padx=(10, 0))

        # Desktop launcher
        launcher_frame = ttk.Frame(settings_win)
        launcher_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(launcher_frame, text="Desktop:").pack(side=tk.LEFT)
        ttk.Button(launcher_frame, text="Install Launcher",
                   command=self._install_launcher).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(launcher_frame, text="Remove Launcher",
                   command=self._remove_launcher).pack(side=tk.LEFT, padx=(5, 0))

        # Buttons
        btn_frame = ttk.Frame(settings_win)
        btn_frame.pack(fill=tk.X, padx=20, pady=10)

        def apply_settings():
            try:
                new_size = int(font_size_var.get())
                if 6 <= new_size <= 24:
                    self.font_size = new_size
                    self.db.set_setting("font_size", str(new_size))
                    self._apply_font_size()
                    settings_win.destroy()
                else:
                    tk.messagebox.showwarning("Invalid", "Font size must be between 6 and 24")
            except ValueError:
                tk.messagebox.showwarning("Invalid", "Please enter a valid number")

        def cancel():
            settings_win.destroy()

        ttk.Button(btn_frame, text="OK", command=apply_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=cancel).pack(side=tk.RIGHT)

        # Escape to close
        settings_win.bind("<Escape>", lambda e: settings_win.destroy())
        settings_win.bind("<Return>", lambda e: apply_settings())

    def _apply_font_size(self):
        """Apply font size to all UI elements globally."""
        # Update all named fonts in tkinter
        for font_name in ["TkDefaultFont", "TkTextFont", "TkMenuFont",
                          "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
                          "TkIconFont", "TkTooltipFont"]:
            try:
                font = tkfont.nametofont(font_name)
                font.configure(size=self.font_size)
            except Exception:
                pass

        # Update fixed font separately (for code/SQL)
        try:
            fixed_font = tkfont.nametofont("TkFixedFont")
            fixed_font.configure(size=self.font_size)
        except Exception:
            pass

        # Update ttk style for Treeview
        style = ttk.Style()
        rowheight = int(self.font_size * 1.8)  # Scale row height with font
        style.configure("Treeview", rowheight=rowheight)

        # Update SQL tab widgets and scale column widths
        scale = self.font_size / 10.0  # Base scale factor
        for tab_id in self.notebook.tabs():
            try:
                tab_frame = self.notebook.nametowidget(tab_id)
                if hasattr(tab_frame, 'sql_tab'):
                    sql_tab = tab_frame.sql_tab
                    sql_tab.scale_columns(scale)
                    # Update stats text font
                    if hasattr(sql_tab, 'stats_text'):
                        sql_tab.stats_text.configure(font=("Courier", self.font_size))
            except Exception:
                pass

        self.statusbar.config(text=f"Font size set to {self.font_size}")

    def _toggle_dark_mode(self):
        """Toggle dark mode on/off."""
        is_dark = self.dark_mode_var.get()
        self.db.set_setting("dark_mode", "1" if is_dark else "0")
        self._apply_theme()

    def _apply_theme(self):
        """Apply light or dark theme."""
        is_dark = self.dark_mode_var.get()
        style = ttk.Style()

        if is_dark:
            # Darcula-inspired dark theme
            bg = "#2b2b2b"
            fg = "#a9b7c6"
            bg_light = "#313335"
            bg_dark = "#1e1e1e"
            select_bg = "#214283"
            border = "#3c3f41"

            style.theme_use("clam")

            style.configure(".", background=bg, foreground=fg, fieldbackground=bg_light,
                           troughcolor=bg_dark, bordercolor=border, lightcolor=bg_light,
                           darkcolor=bg_dark, insertcolor=fg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TLabelframe", background=bg, foreground=fg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg)
            style.configure("TButton", background=bg_light, foreground=fg)
            style.configure("TEntry", fieldbackground=bg_light, foreground=fg, insertcolor=fg)
            style.configure("TCombobox", fieldbackground=bg_light, foreground=fg)
            style.configure("TNotebook", background=bg, foreground=fg, tabmargins=[2, 5, 2, 0])
            style.configure("TNotebook.Tab", background="#3c3f41", foreground="#777777", padding=[10, 4],
                           borderwidth=1, focusthickness=0)
            style.configure("TPanedwindow", background=bg)
            style.configure("Sash", sashthickness=6, gripcount=0)
            style.configure("TScrollbar", background="#5a5a5a", troughcolor=bg, arrowcolor="#6e6e6e",
                           bordercolor=bg, lightcolor="#5a5a5a", darkcolor="#5a5a5a")
            style.map("TScrollbar", background=[("pressed", "#6e6e6e"), ("active", "#6e6e6e")],
                      lightcolor=[("pressed", "#6e6e6e"), ("active", "#6e6e6e")],
                      darkcolor=[("pressed", "#6e6e6e"), ("active", "#6e6e6e")])
            style.configure("Treeview", background=bg_light, foreground=fg, fieldbackground=bg_light)
            style.configure("Treeview.Heading", background=bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TSpinbox", fieldbackground=bg_light, foreground=fg)
            style.configure("TMenubutton", background=bg_light, foreground=fg)

            style.map("TButton", background=[("active", bg_light)])
            style.map("TNotebook.Tab", background=[("selected", bg_light), ("active", "#454545")],
                      foreground=[("selected", fg)],
                      padding=[("selected", [10, 4]), ("!selected", [10, 2])])
            style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", fg)])
            style.map("TCombobox", fieldbackground=[("readonly", bg_light)])
            style.map("TCheckbutton", background=[("active", bg)])
            style.map("TMenubutton", background=[("active", bg_light)])

            self.root.configure(bg=bg)
        else:
            # Light theme
            style.theme_use("clam")

            bg = "#d9d9d9"
            fg = "#000000"
            bg_light = "#ffffff"
            select_bg = "#4a6984"
            border = "#9e9e9e"

            style.configure(".", background=bg, foreground=fg, fieldbackground=bg_light,
                           troughcolor="#c3c3c3", bordercolor=border,
                           lightcolor="#ededed", darkcolor="#cfcfcf", insertcolor=fg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TLabelframe", background=bg, foreground=fg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg)
            style.configure("TButton", background="#e1e1e1", foreground=fg)
            style.configure("TEntry", fieldbackground=bg_light, foreground=fg, insertcolor=fg)
            style.configure("TCombobox", fieldbackground=bg_light, foreground=fg)
            style.configure("TNotebook", background=bg, foreground=fg, tabmargins=[2, 5, 2, 0])
            style.configure("TNotebook.Tab", background="#d0d0d0", foreground="#666666", padding=[10, 4],
                           borderwidth=1, focusthickness=0)
            style.configure("TPanedwindow", background=bg)
            # Reset scrollbar to default light theme colors
            style.configure("TScrollbar", background="#c3c3c3", troughcolor="#e6e6e6",
                           arrowcolor="#5a5a5a", bordercolor=border,
                           lightcolor="#ededed", darkcolor="#cfcfcf")
            style.map("TScrollbar", background=[("pressed", "#a0a0a0"), ("active", "#b0b0b0")],
                      lightcolor=[("pressed", "#a0a0a0"), ("active", "#b0b0b0")],
                      darkcolor=[("pressed", "#a0a0a0"), ("active", "#b0b0b0")])
            style.configure("Treeview", background=bg_light, foreground=fg, fieldbackground=bg_light)
            style.configure("Treeview.Heading", background=bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TSpinbox", fieldbackground=bg_light, foreground=fg)
            style.configure("TMenubutton", background="#e1e1e1", foreground=fg)

            style.map("TButton", background=[("active", "#ececec")])
            style.map("TNotebook.Tab", background=[("selected", "#ffffff"), ("active", "#e0e0e0")],
                      foreground=[("selected", "#000000")],
                      padding=[("selected", [10, 4]), ("!selected", [10, 2])])
            style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", "#ffffff")])
            style.map("TCombobox", fieldbackground=[("readonly", bg_light)])
            style.map("TCheckbutton", background=[("active", bg)])
            style.map("TMenubutton", background=[("active", "#ececec")])

            self.root.configure(bg=bg)

        # Apply to non-ttk widgets
        self._apply_theme_to_widgets()

        # Apply to tab-specific components
        self._apply_theme_to_tabs()

        # Re-apply menu to ensure it's visible after theme change
        if hasattr(self, 'menubar'):
            self.root.config(menu=self.menubar)

    def _apply_theme_to_widgets(self):
        """Apply theme to non-ttk widgets (Text, Listbox, Menu)."""
        is_dark = self.dark_mode_var.get()

        if is_dark:
            bg = "#2b2b2b"
            fg = "#a9b7c6"
            text_bg = "#313335"
            select_bg = "#214283"
        else:
            bg = "#f0f0f0"
            fg = "#000000"
            text_bg = "#ffffff"
            select_bg = "#0078d4"

        self._configure_widgets_recursive(self.root, text_bg, fg, select_bg, bg)

    def _configure_widgets_recursive(self, widget, bg, fg, select_bg, menu_bg):
        """Recursively configure non-ttk widgets."""
        widget_class = widget.winfo_class()

        try:
            if widget_class == "Text":
                widget.configure(bg=bg, fg=fg, insertbackground=fg,
                               selectbackground=select_bg, selectforeground=fg)
            elif widget_class == "Listbox":
                widget.configure(bg=bg, fg=fg,
                               selectbackground=select_bg, selectforeground=fg)
            elif widget_class == "Menu":
                widget.configure(bg=menu_bg, fg=fg,
                               activebackground=select_bg, activeforeground=fg)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._configure_widgets_recursive(child, bg, fg, select_bg, menu_bg)

    def _apply_theme_to_tabs(self):
        """Apply theme to tab-specific components (search highlights, etc.)."""
        for tab_id in self.notebook.tabs():
            try:
                tab_frame = self.notebook.nametowidget(tab_id)
                # Call apply_theme on SQL tabs (for syntax highlighting and search)
                if hasattr(tab_frame, 'sql_tab') and hasattr(tab_frame.sql_tab, 'apply_theme'):
                    tab_frame.sql_tab.apply_theme()
                # Call apply_theme on Spool tabs (for search highlights)
                if hasattr(tab_frame, 'spool_tab') and hasattr(tab_frame.spool_tab, 'apply_theme'):
                    tab_frame.spool_tab.apply_theme()
            except Exception:
                pass

    def _restore_session(self):
        """Restore connections and tabs from last session (non-blocking)."""
        # Get saved tabs to know which connections to restore
        saved_tabs = self.db.get_saved_tabs()

        # Group tabs by connection
        tabs_by_conn = {}
        for tab in saved_tabs:
            conn_name = tab["connection_name"]
            if conn_name not in tabs_by_conn:
                tabs_by_conn[conn_name] = []
            tabs_by_conn[conn_name].append(tab)

        connections_needed = set(tabs_by_conn.keys())

        # Also restore last connection if set
        last_conn = self.db.get_setting("last_connection")
        if last_conn:
            connections_needed.add(last_conn)

        # Connect to needed connections (async)
        available = [c["name"] for c in self.db.get_connections()]
        connecting_count = 0
        for conn_name in connections_needed:
            if conn_name in available and conn_name not in self.connections:
                # Queue pending tabs for this connection
                if conn_name in tabs_by_conn:
                    self._pending_tabs[conn_name] = tabs_by_conn[conn_name]

                self.conn_tree.selection_set(conn_name)
                self._connect_selected()
                connecting_count += 1

        if connecting_count > 0:
            self.statusbar.config(text=f"Restoring {connecting_count} connection(s)...")
        else:
            # No connections to wait for, restore layout now
            self.root.after(100, self._restore_layout)

    def _restore_geometry(self):
        """Restore window geometry from saved settings."""
        default_geometry = "1200x800"
        saved = self.db.get_setting("window_geometry", default_geometry)

        try:
            self.root.geometry(saved)
        except Exception:
            self.root.geometry(default_geometry)

    def _ensure_visible_on_screen(self):
        """Ensure window is visible on screen, reposition if needed."""
        default_geometry = "1200x800"
        try:
            if not self._is_visible_on_screen():
                self.root.geometry(default_geometry)
                self._center_window()
        except Exception:
            pass

    def _is_visible_on_screen(self):
        """Check if window position seems reasonable.

        Only reset if window is clearly off-screen (negative coords or way past
        primary screen). This allows windows on secondary monitors to be preserved.
        """
        x = self.root.winfo_x()
        y = self.root.winfo_y()

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        # Only consider off-screen if clearly beyond reasonable bounds
        # Allow 3x screen size to accommodate multi-monitor setups
        max_x = screen_w * 3
        max_y = screen_h * 2

        # Window is visible if not clearly off-screen
        return x > -500 and y > -100 and x < max_x and y < max_y

    def _center_window(self):
        """Center window on screen."""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _save_geometry(self):
        """Save current window geometry."""
        geometry = self.root.geometry()
        self.db.set_setting("window_geometry", geometry)

    def _save_layout(self):
        """Save paned window sash positions as ratios for reliable restore."""
        try:
            # Main paned window (connections | tabs) - horizontal, save as ratio of width
            sash_pos = self.main_paned.sashpos(0)
            pane_width = self.main_paned.winfo_width()
            if pane_width > 100:
                ratio = sash_pos / pane_width
                self.db.set_setting("layout_main_ratio", f"{ratio:.4f}")
        except Exception:
            pass

        # Save tab-level layouts as ratios
        for tab_id in self.notebook.tabs():
            try:
                tab_frame = self.notebook.nametowidget(tab_id)
                if hasattr(tab_frame, 'sql_tab') and hasattr(tab_frame.sql_tab, 'paned'):
                    sash_pos = tab_frame.sql_tab.paned.sashpos(0)
                    pane_height = tab_frame.sql_tab.paned.winfo_height()
                    if pane_height > 100:
                        ratio = sash_pos / pane_height
                        self.db.set_setting("layout_sql_ratio", f"{ratio:.4f}")
                    break  # Only need one SQL tab's position
            except Exception:
                pass

        for tab_id in self.notebook.tabs():
            try:
                tab_frame = self.notebook.nametowidget(tab_id)
                if hasattr(tab_frame, 'spool_tab') and hasattr(tab_frame.spool_tab, 'paned'):
                    sash_pos = tab_frame.spool_tab.paned.sashpos(0)
                    pane_width = tab_frame.spool_tab.paned.winfo_width()
                    if pane_width > 100:
                        ratio = sash_pos / pane_width
                        self.db.set_setting("layout_spool_ratio", f"{ratio:.4f}")
                    break  # Only need one spool tab's position
            except Exception:
                pass

    def _restore_layout(self):
        """Restore paned window sash positions from saved ratios."""
        self.root.update_idletasks()

        # Restore main paned (connections | tabs) from ratio
        try:
            ratio_str = self.db.get_setting("layout_main_ratio")
            if ratio_str:
                ratio = float(ratio_str)
                pane_width = self.main_paned.winfo_width()
                if pane_width > 100 and 0.05 <= ratio <= 0.95:
                    sash_pos = int(ratio * pane_width)
                    self.main_paned.sashpos(0, sash_pos)
        except Exception:
            pass

        # Restore SQL tab sash from ratio
        sql_ratio_str = self.db.get_setting("layout_sql_ratio")
        spool_ratio_str = self.db.get_setting("layout_spool_ratio")

        for tab_id in self.notebook.tabs():
            try:
                tab_frame = self.notebook.nametowidget(tab_id)
                if sql_ratio_str and hasattr(tab_frame, 'sql_tab') and hasattr(tab_frame.sql_tab, 'paned'):
                    ratio = float(sql_ratio_str)
                    pane_height = tab_frame.sql_tab.paned.winfo_height()
                    if pane_height > 100 and 0.1 <= ratio <= 0.9:
                        sash_pos = int(ratio * pane_height)
                        tab_frame.sql_tab.paned.sashpos(0, sash_pos)
                elif spool_ratio_str and hasattr(tab_frame, 'spool_tab') and hasattr(tab_frame.spool_tab, 'paned'):
                    ratio = float(spool_ratio_str)
                    pane_width = tab_frame.spool_tab.paned.winfo_width()
                    if pane_width > 100 and 0.1 <= ratio <= 0.9:
                        sash_pos = int(ratio * pane_width)
                        tab_frame.spool_tab.paned.sashpos(0, sash_pos)
            except Exception:
                pass

        # Restore the last active tab
        self._restore_active_tab()

        # Show window after a short delay to let layout settle
        self.root.after(50, self.root.deiconify)

    def _reset_layout(self):
        """Reset layout to defaults."""
        # Clear saved layout settings (both old and new format)
        self.db.set_setting("layout_main_sash", "")
        self.db.set_setting("layout_sql_sash", "")
        self.db.set_setting("layout_spool_sash", "")
        self.db.set_setting("layout_main_ratio", "")
        self.db.set_setting("layout_sql_ratio", "")
        self.db.set_setting("layout_spool_ratio", "")

        # Reset font size to default
        self.font_size = 10
        self.db.set_setting("font_size", "10")
        self._apply_font_size()

        # Reset main paned to default (connections panel ~200px)
        self.root.update_idletasks()
        try:
            self.main_paned.sashpos(0, 200)
        except Exception:
            pass

        # Reset any open tab layouts - need to select each tab for sash to apply
        current_tab = self.notebook.select()
        for tab_id in self.notebook.tabs():
            try:
                self.notebook.select(tab_id)
                self.root.update_idletasks()
                tab_frame = self.notebook.nametowidget(tab_id)
                if hasattr(tab_frame, 'sql_tab') and hasattr(tab_frame.sql_tab, 'paned'):
                    # SQL tab: vertical split, 50/50
                    paned_height = tab_frame.sql_tab.paned.winfo_height()
                    tab_frame.sql_tab.paned.sashpos(0, paned_height // 2)
                elif hasattr(tab_frame, 'spool_tab') and hasattr(tab_frame.spool_tab, 'paned'):
                    # Spool tab: horizontal split, 50/50
                    paned_width = tab_frame.spool_tab.paned.winfo_width()
                    tab_frame.spool_tab.paned.sashpos(0, paned_width // 2)
            except Exception:
                pass
        # Restore original tab selection
        if current_tab:
            self.notebook.select(current_tab)

        self.statusbar.config(text="Layout reset to defaults")

    def _on_close(self):
        """Handle window close event."""
        self._save_geometry()
        self._save_layout()
        self._save_tabs()
        self._save_active_tab()
        # Close all connections
        for name, data in self.connections.items():
            try:
                data["conn"].close()
            except Exception:
                pass
        self.root.destroy()

    def _save_tabs(self):
        """Save current tab state."""
        tabs = []
        for tab_id in self.notebook.tabs():
            try:
                tab_frame = self.notebook.nametowidget(tab_id)
                tab_type = getattr(tab_frame, "tab_type", None)
                conn_name = getattr(tab_frame, "conn_name", None)

                if tab_type and conn_name:
                    data = ""
                    if tab_type == "sql" and hasattr(tab_frame, "sql_tab"):
                        data = tab_frame.sql_tab.get_sql()
                    elif tab_type == "spool" and hasattr(tab_frame, "spool_tab"):
                        data = tab_frame.spool_tab.get_user()

                    tabs.append({
                        "type": tab_type,
                        "connection": conn_name,
                        "data": data
                    })
            except Exception:
                pass

        self.db.save_tabs(tabs)

    def _save_active_tab(self):
        """Save the currently active tab index."""
        try:
            current_tab = self.notebook.select()
            if current_tab:
                tabs = self.notebook.tabs()
                for idx, tab_id in enumerate(tabs):
                    if tab_id == current_tab:
                        self.db.set_setting("last_active_tab", str(idx))
                        return
        except Exception:
            pass

    def _restore_active_tab(self):
        """Restore the last active tab."""
        try:
            last_tab_idx = self.db.get_setting("last_active_tab")
            if last_tab_idx is not None:
                idx = int(last_tab_idx)
                tabs = self.notebook.tabs()
                if 0 <= idx < len(tabs):
                    self.notebook.select(tabs[idx])
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def main():
    """Entry point for SQLBench."""
    app = SQLBenchApp()
    app.run()


if __name__ == "__main__":
    main()
