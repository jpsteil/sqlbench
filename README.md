# SQLBench

A multi-database SQL workbench with support for IBM i (AS/400), MySQL, and PostgreSQL.

## Features

- Connect to multiple databases simultaneously
- Browse schemas, tables, and columns
- Execute SQL queries with syntax highlighting
- Export results to CSV, Excel, and PDF
- Save and manage database connections
- Right-click context menus for quick actions

## Supported Databases

- **IBM i (AS/400)** - via ODBC
- **MySQL** - via mysql-connector-python
- **PostgreSQL** - via psycopg2

## Installation

```bash
# Clone the repository
git clone https://github.com/jsteil/sqlbench.git
cd sqlbench

# Install dependencies
make install
```

## Usage

```bash
make run
```

## Requirements

- Python 3.8+
- tkinter (usually included with Python)
- For IBM i: IBM i Access ODBC Driver

## License

MIT
