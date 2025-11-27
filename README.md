# SQLBench

A multi-database SQL workbench with support for IBM i, MySQL, and PostgreSQL.

## Features

- Connect to multiple database types (IBM i, MySQL, PostgreSQL)
- Execute SQL queries with syntax highlighting
- View and navigate query results with pagination
- Auto-resize columns by double-clicking header separators
- Dark/light theme support
- Save and manage database connections
- SQL formatting

## Installation

```bash
pip install sqlbench
```

### Database-specific dependencies

Install the drivers for your database(s):

```bash
# MySQL support
pip install sqlbench[mysql]

# PostgreSQL support
pip install sqlbench[postgresql]

# IBM i support
pip install sqlbench[ibmi]

# All databases
pip install sqlbench[all]
```

## Usage

```bash
# Run the application
sqlbench

# Or via Python
python -m sqlbench
```

## Development

```bash
# Clone the repository
git clone https://github.com/jim/sqlbench.git
cd sqlbench

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[all,dev]"

# Run the application
sqlbench
```

## License

MIT
