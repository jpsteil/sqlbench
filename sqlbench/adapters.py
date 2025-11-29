"""Database adapters for different database types."""

import os
from abc import ABC, abstractmethod
from pathlib import Path


def _setup_ibm_db_environment():
    """Set up environment variables for ibm_db if clidriver is installed."""
    if os.environ.get("IBM_DB_HOME"):
        return  # Already configured

    # Check common install locations
    clidriver_paths = [
        Path.home() / "db2drivers" / "clidriver",
        Path("/opt/ibm/db2/clidriver"),
        Path("/opt/clidriver"),
    ]

    for cli_path in clidriver_paths:
        if (cli_path / "lib").exists():
            os.environ["IBM_DB_HOME"] = str(cli_path)
            lib_path = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = f"{cli_path}/lib:{lib_path}"
            break


# Set up ibm_db environment before any imports
_setup_ibm_db_environment()


class DBAdapter(ABC):
    """Base class for database adapters."""

    db_type = "base"
    display_name = "Base"
    default_port = None
    requires_database = False
    supports_spool = False
    required_module = None  # Module name to import for this adapter
    install_hint = None  # pip install hint for missing dependency

    @classmethod
    def is_available(cls):
        """Check if the required module for this adapter is installed."""
        if cls.required_module is None:
            return True
        try:
            __import__(cls.required_module)
            return True
        except ImportError:
            return False

    @abstractmethod
    def connect(self, host, user, password, port=None, database=None):
        """Connect to the database and return a connection object."""
        pass

    @abstractmethod
    def get_version(self, conn):
        """Get the database version string."""
        pass

    def add_pagination(self, sql, limit, offset=0):
        """Add pagination to a SQL statement. Default uses LIMIT/OFFSET."""
        sql_stripped = sql.strip()
        while sql_stripped.endswith(';'):
            sql_stripped = sql_stripped[:-1].strip()

        if offset > 0:
            return f"{sql_stripped} LIMIT {limit} OFFSET {offset}"
        return f"{sql_stripped} LIMIT {limit}"

    def get_count_sql(self, sql):
        """Wrap SQL in COUNT(*) to get total rows."""
        sql_stripped = sql.strip()
        while sql_stripped.endswith(';'):
            sql_stripped = sql_stripped[:-1].strip()
        return f"SELECT COUNT(*) FROM ({sql_stripped}) AS count_query"

    @abstractmethod
    def get_columns_query(self, tables):
        """Get SQL to retrieve column metadata for given tables."""
        pass

    @abstractmethod
    def get_tables_query(self):
        """Get SQL to retrieve list of tables."""
        pass

    def is_numeric_type(self, type_code):
        """Check if a type_code represents a numeric type."""
        from decimal import Decimal
        # Default: check for Python numeric types (works for pyodbc)
        return type_code in (int, float, Decimal)

    def get_column_display_size(self, col_info):
        """Extract best display size from cursor description tuple.

        col_info format varies by driver but generally:
        (name, type_code, display_size, internal_size, precision, scale, null_ok)
        """
        if not col_info or len(col_info) < 5:
            return 10

        display_size = col_info[2] or 0
        internal_size = col_info[3] or 0
        precision = col_info[4] or 0

        return display_size or internal_size or precision or 10

    def get_select_limit_query(self, table_ref, limit):
        """Get a SELECT query with row limit for a table."""
        return f"SELECT * FROM {table_ref} LIMIT {limit}"

    def get_version_query(self):
        """Get the SQL to retrieve database version."""
        return "SELECT VERSION()"


class IBMiAdapter(DBAdapter):
    """Adapter for IBM i (AS/400) via ODBC."""

    db_type = "ibmi"
    display_name = "IBM i"
    default_port = None  # ODBC handles this
    requires_database = False
    supports_spool = True
    required_module = "pyodbc"
    install_hint = "pip install sqlbench[ibmi]"

    def connect(self, host, user, password, port=None, database=None):
        import pyodbc
        conn_str = (
            f"DRIVER={{IBM i Access ODBC Driver}};"
            f"SYSTEM={host};"
            f"UID={user};"
            f"PWD={password};"
        )
        return pyodbc.connect(conn_str)

    def get_version(self, conn):
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT OS_VERSION, OS_RELEASE FROM SYSIBMADM.ENV_SYS_INFO")
            row = cursor.fetchone()
            cursor.close()
            if row:
                return f"{row[0]}.{row[1]}"
        except Exception:
            pass
        return None

    def add_pagination(self, sql, limit, offset=0):
        """IBM i uses OFFSET/FETCH syntax."""
        sql_stripped = sql.strip()
        while sql_stripped.endswith(';'):
            sql_stripped = sql_stripped[:-1].strip()

        if offset > 0:
            return f"{sql_stripped} OFFSET {offset} ROWS FETCH FIRST {limit} ROWS ONLY"
        return f"{sql_stripped} FETCH FIRST {limit} ROWS ONLY"

    def get_select_limit_query(self, table_ref, limit):
        """Get a SELECT query with row limit for IBM i."""
        return f"SELECT * FROM {table_ref} FETCH FIRST {limit} ROWS ONLY"

    def get_version_query(self):
        """Get the SQL to retrieve IBM i version."""
        return "SELECT OS_VERSION || '.' || OS_RELEASE FROM SYSIBMADM.ENV_SYS_INFO"

    def get_columns_query(self, tables):
        if not tables:
            return None

        table_conditions = []
        for table in tables:
            if '.' in table:
                schema, tbl = table.split('.', 1)
                table_conditions.append(
                    f"(TABLE_SCHEMA = '{schema.upper()}' AND TABLE_NAME = '{tbl.upper()}')"
                )
            else:
                table_conditions.append(f"TABLE_NAME = '{table.upper()}'")

        where_clause = " OR ".join(table_conditions)
        return f"""
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, LENGTH, NUMERIC_SCALE
            FROM QSYS2.SYSCOLUMNS
            WHERE {where_clause}
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """

    def get_tables_query(self):
        """Get tables from IBM i - returns schema, table_name, table_type."""
        return """
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM QSYS2.SYSTABLES
            WHERE TABLE_TYPE IN ('T', 'P', 'V')
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """


class IBMiDBAdapter(DBAdapter):
    """Adapter for IBM i (AS/400) via ibm_db (native CLI driver)."""

    db_type = "ibmi_db"
    display_name = "IBM i (ibm_db)"
    default_port = 446  # DRDA port
    requires_database = False
    supports_spool = True
    required_module = "ibm_db"
    install_hint = "pip install sqlbench[ibmi-db]"

    def connect(self, host, user, password, port=None, database=None):
        import ibm_db_dbi

        # Build connection string for IBM i
        # DATABASE can be *LOCAL or the RDB name
        db_name = database if database else "*LOCAL"
        port_num = port if port else 446

        conn_str = (
            f"DATABASE={db_name};"
            f"HOSTNAME={host};"
            f"PORT={port_num};"
            f"PROTOCOL=TCPIP;"
            f"UID={user};"
            f"PWD={password};"
        )

        # ibm_db_dbi provides DB-API 2.0 compliant interface
        return ibm_db_dbi.connect(conn_str, "", "")

    def get_version(self, conn):
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT OS_VERSION, OS_RELEASE FROM SYSIBMADM.ENV_SYS_INFO")
            row = cursor.fetchone()
            cursor.close()
            if row:
                return f"{row[0]}.{row[1]}"
        except Exception:
            pass
        return None

    def add_pagination(self, sql, limit, offset=0):
        """IBM i uses OFFSET/FETCH syntax."""
        sql_stripped = sql.strip()
        while sql_stripped.endswith(';'):
            sql_stripped = sql_stripped[:-1].strip()

        if offset > 0:
            return f"{sql_stripped} OFFSET {offset} ROWS FETCH FIRST {limit} ROWS ONLY"
        return f"{sql_stripped} FETCH FIRST {limit} ROWS ONLY"

    def get_select_limit_query(self, table_ref, limit):
        """Get a SELECT query with row limit for IBM i."""
        return f"SELECT * FROM {table_ref} FETCH FIRST {limit} ROWS ONLY"

    def get_version_query(self):
        """Get the SQL to retrieve IBM i version."""
        return "SELECT OS_VERSION || '.' || OS_RELEASE FROM SYSIBMADM.ENV_SYS_INFO"

    def get_columns_query(self, tables):
        if not tables:
            return None

        table_conditions = []
        for table in tables:
            if '.' in table:
                schema, tbl = table.split('.', 1)
                table_conditions.append(
                    f"(TABLE_SCHEMA = '{schema.upper()}' AND TABLE_NAME = '{tbl.upper()}')"
                )
            else:
                table_conditions.append(f"TABLE_NAME = '{table.upper()}'")

        where_clause = " OR ".join(table_conditions)
        return f"""
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, LENGTH, NUMERIC_SCALE
            FROM QSYS2.SYSCOLUMNS
            WHERE {where_clause}
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """

    def get_tables_query(self):
        """Get tables from IBM i - returns schema, table_name, table_type."""
        return """
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM QSYS2.SYSTABLES
            WHERE TABLE_TYPE IN ('T', 'P', 'V')
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """

    def is_numeric_type(self, type_code):
        """Check if a type_code represents a numeric type for ibm_db."""
        # ibm_db uses type codes similar to CLI
        # Check for Python numeric types as fallback
        from decimal import Decimal
        if isinstance(type_code, type):
            return type_code in (int, float, Decimal)
        # ibm_db type codes for numeric: various integer constants
        return False


class MySQLAdapter(DBAdapter):
    """Adapter for MySQL."""

    db_type = "mysql"
    display_name = "MySQL"
    default_port = 3306
    requires_database = True
    supports_spool = False
    required_module = "mysql.connector"
    install_hint = "pip install sqlbench[mysql]"

    def connect(self, host, user, password, port=None, database=None):
        import mysql.connector
        config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database or '',
        }
        if port:
            config['port'] = int(port)
        return mysql.connector.connect(**config)

    def get_version(self, conn):
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
            cursor.close()
            if row:
                return row[0]
        except Exception:
            pass
        return None

    def get_columns_query(self, tables):
        if not tables:
            return None

        table_conditions = []
        for table in tables:
            if '.' in table:
                schema, tbl = table.split('.', 1)
                table_conditions.append(
                    f"(TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{tbl}')"
                )
            else:
                table_conditions.append(f"TABLE_NAME = '{table}'")

        where_clause = " OR ".join(table_conditions)
        return f"""
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE,
                   CHARACTER_MAXIMUM_LENGTH AS LENGTH, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE {where_clause}
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """

    def get_tables_query(self):
        """Get tables from MySQL - returns schema, table_name, table_type."""
        return """
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """

    def is_numeric_type(self, type_code):
        """Check if a type_code represents a numeric type for MySQL."""
        # mysql-connector-python uses FieldType constants
        # Numeric field types: TINY, SHORT, LONG, FLOAT, DOUBLE, LONGLONG, INT24, DECIMAL, NEWDECIMAL
        try:
            from mysql.connector import FieldType
            numeric_types = {
                FieldType.TINY, FieldType.SHORT, FieldType.LONG,
                FieldType.FLOAT, FieldType.DOUBLE, FieldType.LONGLONG,
                FieldType.INT24, FieldType.DECIMAL, FieldType.NEWDECIMAL
            }
            return type_code in numeric_types
        except (ImportError, AttributeError):
            # Fallback to checking if it's a Python numeric type
            from decimal import Decimal
            return type_code in (int, float, Decimal)

    def get_column_display_size(self, col_info):
        """Extract display size for MySQL - use internal_size as it's more reliable."""
        if not col_info or len(col_info) < 5:
            return 10

        # MySQL: (name, type_code, display_size, internal_size, precision, scale, null_ok, flags, charset)
        # internal_size (index 3) is usually populated
        internal_size = col_info[3] or 0
        display_size = col_info[2] or 0
        precision = col_info[4] or 0

        # For MySQL, internal_size is often the best indicator
        size = internal_size or display_size or precision
        # Cap at reasonable max for display purposes
        return min(size, 255) if size > 0 else 20


class PostgreSQLAdapter(DBAdapter):
    """Adapter for PostgreSQL."""

    db_type = "postgresql"
    display_name = "PostgreSQL"
    default_port = 5432
    requires_database = True
    supports_spool = False
    required_module = "psycopg2"
    install_hint = "pip install sqlbench[postgresql]"

    def connect(self, host, user, password, port=None, database=None):
        import psycopg2
        return psycopg2.connect(
            host=host,
            user=user,
            password=password,
            dbname=database or 'postgres',
            port=port or 5432
        )

    def get_version_query(self):
        return "SELECT version()"

    def get_version(self, conn):
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            row = cursor.fetchone()
            cursor.close()
            if row:
                # Extract just version number from full string
                version_str = row[0]
                if 'PostgreSQL' in version_str:
                    parts = version_str.split()
                    for i, p in enumerate(parts):
                        if p == 'PostgreSQL' and i + 1 < len(parts):
                            return parts[i + 1].rstrip(',')
                return version_str[:30]
        except Exception:
            pass
        return None

    def get_columns_query(self, tables):
        if not tables:
            return None

        table_conditions = []
        for table in tables:
            if '.' in table:
                schema, tbl = table.split('.', 1)
                table_conditions.append(
                    f"(table_schema = '{schema}' AND table_name = '{tbl}')"
                )
            else:
                table_conditions.append(f"table_name = '{table}'")

        where_clause = " OR ".join(table_conditions)
        return f"""
            SELECT table_schema, table_name, column_name, data_type,
                   character_maximum_length AS length, numeric_scale
            FROM information_schema.columns
            WHERE {where_clause}
            ORDER BY table_schema, table_name, ordinal_position
        """

    def get_tables_query(self):
        """Get tables from PostgreSQL - returns schema, table_name, table_type."""
        return """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """

    def is_numeric_type(self, type_code):
        """Check if a type_code represents a numeric type for PostgreSQL."""
        # psycopg2 uses OIDs for type_code
        # Common numeric OIDs: 20=int8, 21=int2, 23=int4, 700=float4, 701=float8, 1700=numeric
        numeric_oids = {20, 21, 23, 26, 700, 701, 790, 1700}
        if isinstance(type_code, int):
            return type_code in numeric_oids
        # Fallback
        from decimal import Decimal
        return type_code in (int, float, Decimal)

    def get_column_display_size(self, col_info):
        """Extract display size for PostgreSQL."""
        if not col_info or len(col_info) < 5:
            return 10

        # psycopg2: (name, type_code, display_size, internal_size, precision, scale, null_ok)
        # display_size is often None, internal_size is the storage size
        display_size = col_info[2] or 0
        internal_size = col_info[3] or 0
        precision = col_info[4] or 0

        # For text types, internal_size is -1 (unlimited)
        if internal_size < 0:
            return 50  # Default for text/varchar without limit

        size = display_size or precision or internal_size
        return min(size, 255) if size > 0 else 20


# Registry of available adapters
ADAPTERS = {
    'ibmi': IBMiAdapter,
    'ibmi_db': IBMiDBAdapter,
    'mysql': MySQLAdapter,
    'postgresql': PostgreSQLAdapter,
}


def get_adapter(db_type):
    """Get an adapter instance by type."""
    adapter_class = ADAPTERS.get(db_type)
    if adapter_class:
        return adapter_class()
    raise ValueError(f"Unknown database type: {db_type}")


def get_adapter_choices(include_unavailable=False):
    """Get list of (db_type, display_name) for UI.

    Args:
        include_unavailable: If True, include all adapters. If False, only include
                           adapters whose required modules are installed.
    """
    if include_unavailable:
        return [(key, cls.display_name) for key, cls in ADAPTERS.items()]
    return [(key, cls.display_name) for key, cls in ADAPTERS.items() if cls.is_available()]


def get_unavailable_adapters():
    """Get list of adapters that are not available due to missing dependencies.

    Returns list of (db_type, display_name, install_hint).
    """
    return [
        (key, cls.display_name, cls.install_hint)
        for key, cls in ADAPTERS.items()
        if not cls.is_available()
    ]
