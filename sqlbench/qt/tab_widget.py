"""
Tab Container Widget for SQLBench PyQt6 GUI.

Provides tabbed interface with close buttons, drag-and-drop reordering,
and context menu support.
"""

from typing import Optional, Dict
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QMimeData
from PyQt6.QtGui import QMouseEvent, QDrag, QAction
from PyQt6.QtWidgets import (
    QTabWidget,
    QTabBar,
    QWidget,
    QMenu,
    QStyle,
    QStyleOptionTab,
    QPushButton,
    QHBoxLayout,
)


class DraggableTabBar(QTabBar):
    """Tab bar with drag-and-drop reordering and close buttons."""

    tab_close_requested = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._drag_start_pos: Optional[QPoint] = None
        self._drag_index: int = -1

        self.setMovable(True)
        self.setTabsClosable(True)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)
        self.setDocumentMode(True)

        # Connect close button signal
        self.tabCloseRequested.connect(self.tab_close_requested.emit)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for drag start."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_index = self.tabAt(event.pos())
        elif event.button() == Qt.MouseButton.MiddleButton:
            # Middle-click to close
            index = self.tabAt(event.pos())
            if index >= 0:
                self.tab_close_requested.emit(index)
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for drag operation."""
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release."""
        self._drag_start_pos = None
        self._drag_index = -1
        super().mouseReleaseEvent(event)


class TabContainer(QTabWidget):
    """Container for SQL and Spool tabs with close buttons and reordering."""

    tab_closed = pyqtSignal(int)  # index

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Use custom tab bar
        self._tab_bar = DraggableTabBar(self)
        self.setTabBar(self._tab_bar)

        # Track tab titles for duplicate naming
        self._tab_counts: Dict[str, int] = {}

        # Connect signals
        self._tab_bar.tab_close_requested.connect(self._close_tab)

        # Setup context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Styling
        self.setDocumentMode(True)

    def add_tab(self, widget: QWidget, title: str) -> int:
        """Add a new tab with proper naming."""
        # Handle duplicate titles
        base_title = title
        if base_title in self._tab_counts:
            self._tab_counts[base_title] += 1
            title = f"{base_title} ({self._tab_counts[base_title]})"
        else:
            self._tab_counts[base_title] = 1

        index = self.addTab(widget, title)
        self.setCurrentIndex(index)

        # Store base title for later
        widget.setProperty("base_title", base_title)

        return index

    def _close_tab(self, index: int) -> None:
        """Close tab at index."""
        if index < 0 or index >= self.count():
            return

        widget = self.widget(index)
        if widget:
            # Check if tab has unsaved changes
            if hasattr(widget, 'has_unsaved_changes') and widget.has_unsaved_changes():
                from PyQt6.QtWidgets import QMessageBox
                result = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "This tab has unsaved changes. Close anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if result == QMessageBox.StandardButton.No:
                    return

            # Clean up
            if hasattr(widget, 'cleanup'):
                widget.cleanup()

            # Update tab counts
            base_title = widget.property("base_title")
            if base_title and base_title in self._tab_counts:
                self._tab_counts[base_title] -= 1
                if self._tab_counts[base_title] == 0:
                    del self._tab_counts[base_title]

        self.removeTab(index)
        self.tab_closed.emit(index)

    def _show_context_menu(self, pos: QPoint) -> None:
        """Show context menu for tab."""
        index = self._tab_bar.tabAt(pos)
        if index < 0:
            return

        menu = QMenu(self)

        close_action = QAction("Close Tab", self)
        close_action.triggered.connect(lambda: self._close_tab(index))
        menu.addAction(close_action)

        close_others = QAction("Close Other Tabs", self)
        close_others.triggered.connect(lambda: self._close_other_tabs(index))
        close_others.setEnabled(self.count() > 1)
        menu.addAction(close_others)

        close_all = QAction("Close All Tabs", self)
        close_all.triggered.connect(self._close_all_tabs)
        menu.addAction(close_all)

        menu.exec(self.mapToGlobal(pos))

    def _close_other_tabs(self, keep_index: int) -> None:
        """Close all tabs except the specified one."""
        # Close tabs from end to avoid index shifting issues
        for i in range(self.count() - 1, -1, -1):
            if i != keep_index:
                self._close_tab(i)

    def _close_all_tabs(self) -> None:
        """Close all tabs."""
        for i in range(self.count() - 1, -1, -1):
            self._close_tab(i)

    def get_tabs_by_connection(self, connection_name: str) -> list:
        """Get all tabs for a specific connection."""
        tabs = []
        for i in range(self.count()):
            widget = self.widget(i)
            if hasattr(widget, 'connection_name'):
                if widget.connection_name == connection_name:
                    tabs.append((i, widget))
        return tabs

    def close_tabs_for_connection(self, connection_name: str) -> None:
        """Close all tabs for a specific connection."""
        tabs = self.get_tabs_by_connection(connection_name)
        for index, _ in reversed(tabs):
            self._close_tab(index)
