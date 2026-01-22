"""
Database type icons for SQLBench PyQt6 GUI.

Provides programmatically generated icons for different database types.
"""

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont


def get_db_icon(db_type: str, size: int = 16) -> QIcon:
    """Get an icon for a database type."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Color and text based on database type
    colors = {
        'ibmi': '#4a90d9',      # Blue for IBM i
        'mysql': '#00758f',     # MySQL teal
        'postgresql': '#336791', # PostgreSQL blue
    }
    labels = {
        'ibmi': 'i',
        'mysql': 'M',
        'postgresql': 'P',
    }

    color = QColor(colors.get(db_type, '#888888'))
    label = labels.get(db_type, '?')

    # Draw circle background
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)

    # Draw text
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Arial", size // 2, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, label)

    painter.end()

    return QIcon(pixmap)


def get_node_icon(node_type: str, size: int = 16) -> QIcon:
    """Get an icon for a tree node type."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    colors = {
        'schema': '#6b8e23',     # Olive green
        'table': '#cd853f',      # Peru/tan
        'view': '#9370db',       # Purple
        'column': '#708090',     # Slate gray
    }
    labels = {
        'schema': 'S',
        'table': 'T',
        'view': 'V',
        'column': 'C',
    }

    color = QColor(colors.get(node_type, '#888888'))
    label = labels.get(node_type, '?')

    # Draw rounded rect background
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)

    # Draw text
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Arial", size // 2 - 1, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, label)

    painter.end()

    return QIcon(pixmap)
