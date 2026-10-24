# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from aqt import colors
from aqt.qt import *
from aqt.theme import theme_manager
from aqt.utils import tooltip, tr

if TYPE_CHECKING:
    from aqt.browser.table.table import Table

CARD_ORDER_COLUMN = "cardOrder"

# distance from the top or bottom of the table at which a drag scrolls it
_SCROLL_MARGIN = 24


def drop_target(moving: set[int], gap: int, row_count: int) -> tuple[int, bool] | None:
    """Where rows dropped into the gap before row `gap` end up: next to the
    returned row, after it if the flag is set. None if the drop changes nothing.
    """
    others = [row for row in range(row_count) if row not in moving]
    before = [row for row in others if row < gap]
    after = [row for row in others if row >= gap]
    new_order = before + sorted(moving) + after
    if new_order == list(range(row_count)):
        return None
    if after:
        return after[0], False
    return before[-1], True


class CardOrderDrag(QObject):
    """Lets the user drag rows of the table with Cmd (Ctrl on other platforms)
    held, to change the custom order of a deck's cards. A Cmd click without
    dragging still toggles the row's selection."""

    def __init__(self, table: Table, view: QTableView) -> None:
        super().__init__(view)
        self._table = table
        self._view = view
        viewport = view.viewport()
        assert viewport is not None
        self._viewport = viewport
        self._press_pos: QPoint | None = None
        self._press_global_pos = QPointF()
        self._press_modifiers = Qt.KeyboardModifier.NoModifier
        self._press_row = -1
        self._dragging = False
        # set while a press is handed on to the view
        self._replaying = False
        self._rows: set[int] = set()
        self._last_pos = QPoint()
        self._indicator = QFrame(viewport)
        self._indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._indicator.hide()
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(50)
        qconnect(self._scroll_timer.timeout, self._auto_scroll)
        viewport.installEventFilter(self)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if obj is not self._viewport or event is None or self._replaying:
            return False
        if event.type() == QEvent.Type.MouseButtonPress:
            return self._on_press(cast(QMouseEvent, event))
        if event.type() == QEvent.Type.MouseMove:
            return self._on_move(cast(QMouseEvent, event))
        if event.type() == QEvent.Type.MouseButtonRelease:
            return self._on_release(cast(QMouseEvent, event))
        if event.type() == QEvent.Type.MouseButtonDblClick:
            return self._press_pos is not None
        return False

    def _on_press(self, event: QMouseEvent) -> bool:
        if self._press_pos is not None:
            # the release of the last press went elsewhere, eg to a menu
            self._reset()
        modifiers = event.modifiers()
        if (
            event.button() != Qt.MouseButton.LeftButton
            or not modifiers & Qt.KeyboardModifier.ControlModifier
            or modifiers & Qt.KeyboardModifier.ShiftModifier
            or self._table.card_order_deck_id() is None
        ):
            return False
        pos = event.position().toPoint()
        row = self._view.rowAt(pos.y())
        if row < 0:
            return False
        self._press_pos = pos
        self._press_global_pos = event.globalPosition()
        self._press_modifiers = modifiers
        self._press_row = row
        return True

    def _on_move(self, event: QMouseEvent) -> bool:
        if self._press_pos is None:
            return False
        if not event.buttons() & Qt.MouseButton.LeftButton:
            self._reset()
            return False
        pos = event.position().toPoint()
        if not self._dragging:
            distance = (pos - self._press_pos).manhattanLength()
            if distance < QApplication.startDragDistance():
                return True
            if not self._table.is_sorted_by_card_order():
                tooltip(tr.browsing_card_order_sort_first(), parent=self._view)
                # let the view do its usual Cmd-drag selection instead
                self._replay_press()
                return False
            self._start_drag()
        self._last_pos = pos
        self._update_indicator()
        near_edge = (
            pos.y() < _SCROLL_MARGIN
            or pos.y() > self._viewport.height() - _SCROLL_MARGIN
        )
        if near_edge:
            self._scroll_timer.start()
        else:
            self._scroll_timer.stop()
        return True

    def _on_release(self, event: QMouseEvent) -> bool:
        if self._press_pos is None:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return True
        if self._dragging:
            rows = self._rows
            gap = self._gap_at(event.position().toPoint())
            self._reset()
            if target := drop_target(rows, gap, self._table.len()):
                self._table.move_rows_in_card_order(sorted(rows), *target)
            return True
        # a click without a drag: let the view handle the press it didn't see,
        # followed by this release
        self._replay_press()
        return False

    def _replay_press(self) -> None:
        assert self._press_pos is not None
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(self._press_pos),
            self._press_global_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            self._press_modifiers,
        )
        self._reset()
        self._replaying = True
        try:
            QApplication.sendEvent(self._viewport, press)
        finally:
            self._replaying = False

    def _start_drag(self) -> None:
        self._dragging = True
        selection_model = self._view.selectionModel()
        assert selection_model is not None
        if selection_model.isRowSelected(self._press_row):
            self._rows = set(self._table.selected_rows())
        else:
            self._table.select_rows_for_drag([self._press_row])
            self._rows = {self._press_row}
        self._indicator.setStyleSheet(
            f"background: {theme_manager.var(colors.BORDER_FOCUS)};"
        )
        self._viewport.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _reset(self) -> None:
        self._press_pos = None
        self._press_row = -1
        self._dragging = False
        self._rows = set()
        self._scroll_timer.stop()
        self._indicator.hide()
        self._viewport.unsetCursor()

    def _gap_at(self, pos: QPoint) -> int:
        """The row before which rows dropped at pos would be placed."""
        y = min(max(pos.y(), 0), self._viewport.height() - 1)
        row = self._view.rowAt(y)
        if row < 0:
            return self._table.len()
        middle = self._view.rowViewportPosition(row) + self._view.rowHeight(row) // 2
        return row if pos.y() < middle else row + 1

    def _update_indicator(self) -> None:
        count = self._table.len()
        if not count:
            self._indicator.hide()
            return
        gap = self._gap_at(self._last_pos)
        if gap < count:
            y = self._view.rowViewportPosition(gap)
        else:
            y = self._view.rowViewportPosition(count - 1) + self._view.rowHeight(
                count - 1
            )
        # keep the line visible at the very top and bottom
        y = min(max(y - 1, 0), self._viewport.height() - 2)
        self._indicator.setGeometry(0, y, self._viewport.width(), 2)
        self._indicator.show()
        self._indicator.raise_()

    def _auto_scroll(self) -> None:
        scroll_bar = self._view.verticalScrollBar()
        if scroll_bar is None:
            return
        step = max(self._view.rowHeight(0), 1)
        if self._last_pos.y() < _SCROLL_MARGIN:
            scroll_bar.setValue(scroll_bar.value() - step)
        elif self._last_pos.y() > self._viewport.height() - _SCROLL_MARGIN:
            scroll_bar.setValue(scroll_bar.value() + step)
        self._update_indicator()
