"""
SQL Syntax Highlighter for PyQt6.

Provides professional syntax highlighting for SQL code with support
for keywords, functions, strings, comments, and numbers.
"""

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)

from .theme import Theme


# SQL keywords to highlight
SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL",
    "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "FULL", "CROSS", "ON",
    "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC", "LIMIT", "OFFSET",
    "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
    "CREATE", "TABLE", "INDEX", "VIEW", "DROP", "ALTER", "ADD", "COLUMN",
    "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "CONSTRAINT", "UNIQUE",
    "DEFAULT", "CHECK", "CASCADE", "RESTRICT",
    "UNION", "ALL", "DISTINCT", "AS",
    "CASE", "WHEN", "THEN", "ELSE", "END",
    "LIKE", "BETWEEN", "EXISTS", "ANY", "SOME",
    "FETCH", "FIRST", "NEXT", "ROWS", "ONLY",
    "WITH", "RECURSIVE", "OVER", "PARTITION", "ROW_NUMBER", "RANK",
    "TRUE", "FALSE",
    "BEGIN", "COMMIT", "ROLLBACK", "TRANSACTION",
    "TRUNCATE", "GRANT", "REVOKE",
    "CALL", "DECLARE", "CURSOR", "FOR",
    "IF", "THEN", "ELSE", "ELSEIF", "ENDIF",
    "WHILE", "DO", "LOOP", "REPEAT", "UNTIL",
    "RETURN", "RETURNS", "PROCEDURE", "FUNCTION",
    "EXCEPT", "INTERSECT", "NATURAL",
}

# SQL functions to highlight
SQL_FUNCTIONS = {
    # Aggregate
    "COUNT", "SUM", "AVG", "MIN", "MAX",
    # Math
    "ABS", "ROUND", "FLOOR", "CEIL", "CEILING", "MOD", "POWER", "SQRT",
    # Null handling
    "COALESCE", "NULLIF", "IFNULL", "NVL", "NVL2", "ISNULL",
    # Type conversion
    "CAST", "CONVERT", "TRY_CAST", "TRY_CONVERT",
    # String
    "UPPER", "LOWER", "TRIM", "LTRIM", "RTRIM", "LENGTH", "LEN",
    "SUBSTR", "SUBSTRING", "CONCAT", "REPLACE", "INSTR", "LOCATE",
    "POSITION", "LEFT", "RIGHT", "LPAD", "RPAD", "REVERSE", "REPEAT",
    "CHARINDEX", "PATINDEX", "STUFF", "TRANSLATE", "ASCII", "CHAR",
    # Date/Time
    "DATE", "TIME", "TIMESTAMP", "YEAR", "MONTH", "DAY",
    "HOUR", "MINUTE", "SECOND", "NOW", "GETDATE", "SYSDATE",
    "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP",
    "DATEADD", "DATEDIFF", "EXTRACT", "TO_DATE", "TO_CHAR", "TO_NUMBER",
    "DATE_FORMAT", "STR_TO_DATE", "DATEPART", "DATENAME",
    # Window
    "DENSE_RANK", "NTILE", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
    "ROW_NUMBER", "RANK", "PERCENT_RANK", "CUME_DIST",
    # Aggregate string
    "LISTAGG", "STRING_AGG", "GROUP_CONCAT", "ARRAY_AGG",
    # JSON
    "JSON_VALUE", "JSON_QUERY", "JSON_OBJECT", "JSON_ARRAY",
    "JSON_EXTRACT", "JSON_SET", "JSON_INSERT", "JSON_REPLACE",
    # Conditional
    "IIF", "DECODE", "GREATEST", "LEAST",
}


class SQLHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for SQL code."""

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._build_rules()

    def _build_rules(self) -> None:
        """Build highlighting rules based on current theme."""
        colors = Theme.current()

        # Keyword format
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor(colors.keyword))
        self.keyword_format.setFontWeight(QFont.Weight.Bold)

        # Function format
        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor(colors.function))

        # String format
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor(colors.string))

        # Comment format
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor(colors.comment))
        self.comment_format.setFontItalic(True)

        # Number format
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor(colors.number))

        # Operator format
        self.operator_format = QTextCharFormat()
        self.operator_format.setForeground(QColor(colors.operator))

        # Build keyword pattern
        keyword_pattern = r"\b(" + "|".join(SQL_KEYWORDS) + r")\b"
        self.keyword_regex = QRegularExpression(keyword_pattern)
        self.keyword_regex.setPatternOptions(
            QRegularExpression.PatternOption.CaseInsensitiveOption
        )

        # Build function pattern
        function_pattern = r"\b(" + "|".join(SQL_FUNCTIONS) + r")\s*(?=\()"
        self.function_regex = QRegularExpression(function_pattern)
        self.function_regex.setPatternOptions(
            QRegularExpression.PatternOption.CaseInsensitiveOption
        )

        # Other patterns
        self.number_regex = QRegularExpression(r"\b\d+\.?\d*\b")
        self.single_line_comment_regex = QRegularExpression(r"--[^\n]*")
        self.operator_regex = QRegularExpression(r"[=<>!]+|[+\-*/%&|^~]")

    def update_theme(self) -> None:
        """Update colors when theme changes."""
        self._build_rules()
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        """Apply syntax highlighting to a block of text."""
        # Handle multi-line comments
        self._highlight_multiline_comments(text)

        # Skip further processing if we're in a multi-line comment
        if self.previousBlockState() == 1 and self.currentBlockState() == 1:
            return

        # Keywords
        match_iterator = self.keyword_regex.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            # Don't highlight if in string or comment
            if not self._in_string_or_comment(text, match.capturedStart()):
                self.setFormat(
                    match.capturedStart(),
                    match.capturedLength(),
                    self.keyword_format
                )

        # Functions
        match_iterator = self.function_regex.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            if not self._in_string_or_comment(text, match.capturedStart()):
                self.setFormat(
                    match.capturedStart(),
                    match.capturedLength(),
                    self.function_format
                )

        # Numbers
        match_iterator = self.number_regex.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            if not self._in_string_or_comment(text, match.capturedStart()):
                self.setFormat(
                    match.capturedStart(),
                    match.capturedLength(),
                    self.number_format
                )

        # Single-line comments
        match_iterator = self.single_line_comment_regex.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            # Make sure comment isn't inside a string
            if not self._in_string(text, match.capturedStart()):
                self.setFormat(
                    match.capturedStart(),
                    match.capturedLength(),
                    self.comment_format
                )

        # Strings (single quotes)
        self._highlight_strings(text)

    def _highlight_strings(self, text: str) -> None:
        """Highlight single-quoted strings, handling escapes."""
        in_string = False
        string_start = 0

        i = 0
        while i < len(text):
            if text[i] == "'":
                # Check for escaped quote
                if in_string and i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                elif in_string:
                    # End of string
                    self.setFormat(
                        string_start,
                        i - string_start + 1,
                        self.string_format
                    )
                    in_string = False
                else:
                    # Start of string
                    string_start = i
                    in_string = True
            i += 1

        # Handle unclosed string
        if in_string:
            self.setFormat(
                string_start,
                len(text) - string_start,
                self.string_format
            )

    def _highlight_multiline_comments(self, text: str) -> None:
        """Handle /* */ multi-line comments."""
        self.setCurrentBlockState(0)

        start_index = 0
        if self.previousBlockState() != 1:
            # Not in a comment, find start
            start_index = text.find("/*")

        while start_index >= 0:
            end_index = text.find("*/", start_index + 2)

            if end_index == -1:
                # Comment continues to next block
                self.setCurrentBlockState(1)
                comment_length = len(text) - start_index
            else:
                comment_length = end_index - start_index + 2

            self.setFormat(start_index, comment_length, self.comment_format)

            if end_index == -1:
                break

            start_index = text.find("/*", end_index + 2)

        # If previous block was in comment, highlight from start
        if self.previousBlockState() == 1:
            end_index = text.find("*/")
            if end_index == -1:
                self.setCurrentBlockState(1)
                self.setFormat(0, len(text), self.comment_format)
            else:
                self.setFormat(0, end_index + 2, self.comment_format)

    def _in_string(self, text: str, pos: int) -> bool:
        """Check if position is inside a string."""
        in_string = False
        i = 0
        while i < pos:
            if text[i] == "'":
                if in_string and i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                in_string = not in_string
            i += 1
        return in_string

    def _in_string_or_comment(self, text: str, pos: int) -> bool:
        """Check if position is inside a string or comment."""
        if self._in_string(text, pos):
            return True

        # Check for single-line comment before position
        comment_pos = text.find("--")
        if comment_pos != -1 and comment_pos < pos:
            if not self._in_string(text, comment_pos):
                return True

        # Check for multi-line comment
        if self.previousBlockState() == 1:
            end_pos = text.find("*/")
            if end_pos == -1 or pos < end_pos + 2:
                return True

        return False
