# SQLBench GUI Feature Inventory for PyQt Migration

---

## PANE 1: CONNECTION TREE (Left Panel)

**Treeview showing connections with drill-down hierarchy:**
- Connection level → Schema level → Table/View level → Column level
- Database type icons (IBM i, MySQL, PostgreSQL) at connection level
- "(connected)" status indicator after connected connection names
- Format: `[S] schema_name (count)` for schemas
- Format: `[T] table_name` or `[V] view_name` for tables/views
- Format: `column_name (type(length,scale))` for columns

**Filter bar at top:**
- Text entry with real-time filtering as you type
- Filters tables by name or schema (case-insensitive)
- Supports regex patterns or literal strings
- "AI" button opens dialog to generate regex from natural language description
- Auto-expands schema nodes when filter is active to show matches

**AI Regex Builder dialog:**
- Text input for describing what to match (e.g., "tables starting with CUST")
- Backend selector: Claude CLI, Anthropic API, OpenAI API, or Ollama (local)
- Auto-detects available backends and API keys
- Shows generated regex with Copy and Use buttons

**Keyboard navigation:**
- Right arrow: expand node or move to first child
- Left arrow: collapse node or move to parent
- Space/Enter: toggle expand/collapse
- Auto-connects if pressing expand on disconnected connection

**Right-click context menu:**
- Connect / Disconnect (based on current state)
- New SQL (opens SQL tab for this connection)
- New Spool Files (IBM i only)
- Show First 1000 Rows (when table selected - runs SELECT with LIMIT)
- New Connection...
- Edit...
- Delete

**Buttons below tree:**
- "+" button: create new connection
- "-" button: delete selected connection

**Double-click behavior:**
- On connection: connect if disconnected, toggle expand if connected
- On other nodes: toggle expand/collapse

---

## PANE 2: TAB CONTAINER (Right Panel)

**Tab bar features:**
- Dynamic tab creation/deletion
- Tab titles: `[connection_name] SQL` or `[connection_name] SQL (2)` for duplicates
- Database type icon on each tab
- X button on each tab to close it
- Middle-click to close tab
- Right-click context menu with "Close Tab"
- Drag-and-drop to reorder tabs

---

## PANE 2A: SQL TAB

### Toolbar

| Button | Shortcut | Behavior |
|--------|----------|----------|
| Execute | F5 | Runs the single statement at cursor position |
| Execute Script | Ctrl+F5 | Runs all statements in editor sequentially |
| Cancel | Esc | Cancels running query (disabled when idle) |
| Save Query | Ctrl+S | Save editor contents to .sql file |
| Load Query | Ctrl+O | Load .sql file into editor |
| Clear | - | Clears editor contents |
| Format | Ctrl+Shift+F | Formats SQL with proper indentation |

- Connection name label on far right

### SQL Editor

**Text editing:**
- Multi-line code editor with unlimited undo/redo
- Fixed-width font, configurable size (6-24pt)
- No word wrap

**Syntax highlighting (debounced 150ms):**
- Keywords (SELECT, FROM, WHERE, etc.) - orange/blue bold
- Functions (COUNT, SUM, COALESCE, etc.) - yellow/brown
- Strings (single-quoted) - green
- Comments (-- and /* */) - gray italic
- Numbers - blue/teal
- Different color schemes for dark/light mode

**Statement detection:**
- Semicolon-delimited statements
- Ignores semicolons inside string literals
- Cursor position determines which statement Execute runs

**Right-click context menu:**
- Select All (Ctrl+A)
- Cut (Ctrl+X)
- Copy (Ctrl+C)
- Paste (Ctrl+V)

### Results Sub-tabs

#### RESULTS Tab

**Pagination controls (top left):**
- First/Prev/Next/Last page buttons (◀◀ ◀ ▶ ▶▶)
- Disabled when no results

**Export dropdown "Save To":**
- Copy to Clipboard
- Excel (.xlsx)
- CSV (.csv)
- JSON (.json)

**Edit controls (appear only when edits pending):**
- Save Changes button - generates and runs UPDATE statements
- Discard button - reverts all edits

**Search box (top right):**
- Text entry to search within visible results
- Previous/Next buttons to navigate matches

**Settings (top right):**
- Rows per page spinbox (100-10000, default 1000)
- "Show All" checkbox (caps at 10000)

**Results grid:**
- Column headers with click-to-sort (▲/▼ indicators)
- Auto-sized columns based on content
- Right-aligned numbers, left-aligned text
- Horizontal and vertical scrollbars

**Inline cell editing (when available):**
- Enabled for single-table SELECTs with primary key visible
- Double-click cell to edit
- Tab/Shift+Tab to move between cells
- Enter to confirm, Escape to cancel
- Modified cells visually highlighted
- Tracks original vs new values for UPDATE generation

**Status bar:**
- "No results" or "Showing 1-1000 of 5432 row(s) (Page 1 of 6)"

#### FIELDS Tab

**Metadata grid showing column info:**
- Table name
- Column name
- Data type
- Display size
- Precision
- Scale
- Nullable (Yes/No)

#### STATISTICS Tab

**Read-only text display:**
- SQL statement that was executed
- Execution time (query + fetch)
- Row count and column count
- Total rows available vs displayed
- Query plan info (IBM i shows index usage)
- Full error message if query failed

#### LOG Tab

**Controls:**
- Refresh button
- Clear Log button (with confirmation)

**Query history grid:**
- Timestamp
- SQL (first 200 chars)
- Status (success/error)
- Duration in seconds
- Row count
- Error message

**Interactions:**
- Double-click: copies SQL back to editor
- Right-click: Copy SQL to Editor, Copy SQL to Clipboard
- Error rows highlighted red
- Keeps last 500 entries per connection

---

## PANE 2B: SPOOL TAB (IBM i only)

### Toolbar
- User field (default "*CURRENT")
- Refresh button - fetches spool file list for entered user
- View button - displays selected spool file content
- Delete button - deletes selected spool files
- Connection name label on right

### Left: Spool File List

**Grid columns:**
- File name
- User
- Job
- File #
- Status
- Pages

**Interactions:**
- Multi-select enabled
- Double-click to view
- Right-click menu: View, Delete

### Right: Spool Viewer

**Toolbar:**
- Save PDF button (disabled until file loaded)
- Print button (disabled until file loaded)
- Search box with Previous/Next navigation

**Text viewer:**
- Fixed-width font display
- Horizontal and vertical scrollbars
- Search highlighting (yellow for matches, orange for current)
- Status shows "Match X of Y"

**Right-click menu:**
- Select All
- Cut
- Copy

---

## DIALOG: CONNECTION EDITOR

**Left panel - connection list:**
- Treeview of saved connections with database type icons
- New/Delete buttons below

**Right panel - connection form:**

| Field | Notes |
|-------|-------|
| Name | Connection identifier |
| Type | Dropdown of available database adapters |
| Host | Server hostname/IP |
| Port | Port number (hidden for IBM i) |
| Database | Database name (hidden for IBM i) |
| User | Username |
| Password | Masked password field |
| Production | Checkbox - requires confirmation before destructive queries |
| Duplicate Protection | Checkbox - warns if same UPDATE/DELETE run twice |

**Buttons:**
- Test - tests connection, shows success (green) or failure (red)
- Save - saves connection to database

**Driver installation:**
- Unavailable adapters shown with "Install..." button
- Opens sub-dialog with pip install progress

---

## DIALOG: SETTINGS

- Font Size: spinbox (6-24pt)
- Desktop Launcher: Install/Remove buttons for .desktop file
- OK/Cancel buttons
- Escape to close, Enter to apply

---

## GLOBAL FEATURES

### Status Bar (bottom of window)
- Query status messages
- Connection status
- Row counts
- "Connecting...", "Loading..." progress
- "[Editable]" indicator for editable results

### Dark/Light Mode
- Toggle in File menu (persisted)
- Complete color scheme change for all widgets
- Syntax highlighting colors adapt to mode

### Window State Persistence
- Window size and position
- Sash positions (saved as ratios)
- Last active connection and tab
- Font size
- Dark mode preference
- Tab contents (SQL text, spool user)

### Query Safety Features

**Production mode (per connection):**
- Confirmation dialog before UPDATE/DELETE/DROP/TRUNCATE
- Shows statement type and first 100 chars

**Duplicate protection (per connection):**
- Tracks last 10 destructive statements
- Warns if same normalized SQL run again
- Prevents accidental double-execution

### Error Handling
- Auto-reconnect on connection loss
- PostgreSQL transaction rollback on error
- Full error display in Statistics tab
- All queries logged to database

---

## KEYBOARD SHORTCUTS SUMMARY

| Shortcut | Action |
|----------|--------|
| F5 | Execute statement at cursor |
| Ctrl+F5 | Execute all statements |
| Esc | Cancel running query |
| Ctrl+S | Save query to file |
| Ctrl+O | Load query from file |
| Ctrl+Shift+F | Format SQL |
| Ctrl+A | Select all |
| Ctrl+X/C/V | Cut/Copy/Paste |
