"""SQLite database for storing connections and saved queries."""

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).parent / "iutil.db"
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            # Check if we need to migrate old connections table
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='connections'")
            if cursor.fetchone():
                # Check existing columns
                cursor = conn.execute("PRAGMA table_info(connections)")
                columns = [row[1] for row in cursor.fetchall()]

                # Migration: add new columns if needed
                needs_migration = 'db_type' not in columns or 'id' not in columns

                if needs_migration:
                    conn.execute("ALTER TABLE connections RENAME TO connections_old")
                    conn.execute("""
                        CREATE TABLE connections (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL UNIQUE,
                            db_type TEXT NOT NULL DEFAULT 'ibmi',
                            host TEXT NOT NULL,
                            port INTEGER,
                            database TEXT,
                            user TEXT NOT NULL,
                            password TEXT NOT NULL
                        )
                    """)
                    # Migrate data - existing connections become IBM i type
                    if 'id' in columns:
                        conn.execute("""
                            INSERT INTO connections (id, name, db_type, host, user, password)
                            SELECT id, name, 'ibmi', host, user, password FROM connections_old
                        """)
                    else:
                        conn.execute("""
                            INSERT INTO connections (name, db_type, host, user, password)
                            SELECT name, 'ibmi', host, user, password FROM connections_old
                        """)
                    conn.execute("DROP TABLE connections_old")
            else:
                conn.execute("""
                    CREATE TABLE connections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        db_type TEXT NOT NULL DEFAULT 'ibmi',
                        host TEXT NOT NULL,
                        port INTEGER,
                        database TEXT,
                        user TEXT NOT NULL,
                        password TEXT NOT NULL
                    )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    sql TEXT NOT NULL,
                    connection_name TEXT,
                    db_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migration: add db_type column if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(saved_queries)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'db_type' not in columns:
                conn.execute("ALTER TABLE saved_queries ADD COLUMN db_type TEXT")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_tabs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tab_type TEXT NOT NULL,
                    connection_name TEXT NOT NULL,
                    tab_data TEXT,
                    tab_order INTEGER
                )
            """)
            conn.commit()

    # Connection methods
    def get_connections(self):
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, name, db_type, host, port, database, user FROM connections ORDER BY name"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_connection(self, name):
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, name, db_type, host, port, database, user, password FROM connections WHERE name = ?",
                (name,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_connection_by_id(self, conn_id):
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, name, db_type, host, port, database, user, password FROM connections WHERE id = ?",
                (conn_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_connection(self, name, db_type, host, port, database, user, password, conn_id=None):
        with self._get_conn() as conn:
            if conn_id:
                # Update existing connection
                conn.execute(
                    """UPDATE connections SET name = ?, db_type = ?, host = ?, port = ?,
                       database = ?, user = ?, password = ? WHERE id = ?""",
                    (name, db_type, host, port, database, user, password, conn_id)
                )
            else:
                # Insert new connection
                conn.execute(
                    """INSERT INTO connections (name, db_type, host, port, database, user, password)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, db_type, host, port, database, user, password)
                )
            conn.commit()

    def delete_connection(self, conn_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
            conn.commit()

    # Saved query methods
    def get_saved_queries(self, db_type=None):
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            if db_type:
                cursor = conn.execute(
                    "SELECT id, name, sql, connection_name, db_type FROM saved_queries WHERE db_type = ? OR db_type IS NULL ORDER BY name",
                    (db_type,)
                )
            else:
                cursor = conn.execute(
                    "SELECT id, name, sql, connection_name, db_type FROM saved_queries ORDER BY name"
                )
            return [dict(row) for row in cursor.fetchall()]

    def save_query(self, name, sql, connection_name=None, db_type=None):
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO saved_queries (name, sql, connection_name, db_type)
                   VALUES (?, ?, ?, ?)""",
                (name, sql, connection_name, db_type)
            )
            conn.commit()

    def delete_query(self, query_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM saved_queries WHERE id = ?", (query_id,))
            conn.commit()

    # Tab state methods
    def save_tabs(self, tabs):
        """Save tab state. tabs is a list of dicts with type, connection, data."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM saved_tabs")
            for i, tab in enumerate(tabs):
                conn.execute(
                    "INSERT INTO saved_tabs (tab_type, connection_name, tab_data, tab_order) VALUES (?, ?, ?, ?)",
                    (tab["type"], tab["connection"], tab.get("data", ""), i)
                )
            conn.commit()

    def get_saved_tabs(self):
        """Get saved tab state."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT tab_type, connection_name, tab_data FROM saved_tabs ORDER BY tab_order"
            )
            return [dict(row) for row in cursor.fetchall()]

    # Settings methods
    def get_setting(self, key, default=None):
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key, value):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
            conn.commit()
