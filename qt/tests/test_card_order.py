# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from anki.collection import Collection, SearchNode
from aqt.browser.table.card_order import CARD_ORDER_COLUMN, CardOrderDrag, drop_target
from aqt.browser.table.state import CardState
from aqt.browser.table.table import Table
from aqt.card_order import card_order_index, deck_for_search, session_search


@pytest.fixture
def col(tmp_path):
    col = Collection(str(tmp_path / "collection.anki2"))
    yield col
    col.close(downgrade=False)


def deck_search(col: Collection, name: str) -> str:
    return col.build_search_string(SearchNode(deck=name))


@pytest.mark.parametrize(
    "name", ["Japanese", "Lang::Japanese verbs", "a_b*c", 'quote " and \\ slash']
)
def test_deck_for_search_finds_deck_of_sidebar_search(col, name):
    did = col.decks.id(name)

    assert deck_for_search(col, deck_search(col, name)) == did


def test_deck_for_search_maps_current_deck_search(col):
    did = col.decks.id("current one")
    col.decks.select(did)

    assert deck_for_search(col, deck_search(col, "current")) == did


@pytest.mark.parametrize(
    "search", ["deck:Japan*", "deck:Japanese is:new", "Japanese", ""]
)
def test_deck_for_search_ignores_other_searches(col, search):
    col.decks.id("Japanese")

    assert deck_for_search(col, col.build_search_string(search)) is None


def test_deck_for_search_ignores_filtered_decks(col):
    col.decks.new_filtered("my filtered deck")

    assert deck_for_search(col, deck_search(col, "my filtered deck")) is None


@pytest.mark.parametrize("name", ["filtered", "Current"])
def test_deck_for_search_ignores_decks_named_like_search_keywords(col, name):
    col.decks.id(name)

    assert deck_for_search(col, deck_search(col, name)) is None


def add_cards(col: Collection, deck_id, count: int) -> list:
    card_ids = []
    for i in range(count):
        note = col.newNote()
        note["Front"] = f"front {i}"
        col.add_note(note, deck_id)
        card_ids.append(note.cards()[0].id)
    return card_ids


def test_session_search_from_index_finds_later_and_unnumbered_cards(col):
    did = col.decks.id("ordered")
    child = col.decks.id("ordered::child")
    first, second = add_cards(col, did, 2)
    in_child = add_cards(col, child, 1)[0]
    col.sched.set_deck_card_order_enabled(did, True)
    added_later = add_cards(col, did, 1)[0]
    elsewhere = add_cards(col, col.decks.id("other"), 1)[0]

    found = set(col.find_cards(session_search(col, did, from_index=2)))

    assert found == {second, in_child, added_later}
    assert elsewhere not in set(col.find_cards(session_search(col, did, None)))
    assert first in set(col.find_cards(session_search(col, did, None)))


@pytest.mark.parametrize(
    ("custom_data", "expected"),
    [
        ('{"oi":3}', 3),
        ('{"oi":3,"x":1}', 3),
        ("", None),
        ('{"oi":"3"}', None),
        ("[1]", None),
    ],
)
def test_card_order_index_reads_custom_data(custom_data, expected):
    card = SimpleNamespace(custom_data=custom_data)

    assert card_order_index(card) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("moving", "gap", "expected"),
    [
        ({3}, 1, (1, False)),
        ({0}, 4, (4, False)),
        ({1, 3}, 0, (0, False)),
        ({0, 2}, 5, (4, True)),
    ],
)
def test_drop_target_places_rows_next_to_unmoved_row(moving, gap, expected):
    assert drop_target(moving, gap, 5) == expected


@pytest.mark.parametrize(
    ("moving", "gap"), [({2}, 2), ({2}, 3), ({1, 2}, 1), ({1, 2}, 3), ({4}, 5)]
)
def test_drop_target_is_none_when_rows_stay_in_place(moving, gap):
    assert drop_target(moving, gap, 5) is None


def prepare_card_order(col: Collection, state: CardState, deck_id) -> bool:
    table = SimpleNamespace(col=col, _card_order_deck_id=deck_id)
    return Table._prepare_card_order(table, state)  # type: ignore[arg-type]


def test_entering_ordered_deck_sorts_by_order_column(col):
    state = CardState(col)
    state.sort_column = "noteFld"
    state.sort_backwards = True

    changed = prepare_card_order(col, state, col.decks.id("ordered"))

    assert changed
    assert CARD_ORDER_COLUMN in state.active_columns
    assert (state.sort_column, state.sort_backwards) == (CARD_ORDER_COLUMN, False)


def test_staying_in_ordered_deck_keeps_users_sorting(col):
    state = CardState(col)
    did = col.decks.id("ordered")
    prepare_card_order(col, state, did)
    state.sort_column = "cardDue"

    changed = prepare_card_order(col, state, did)

    assert not changed
    assert state.sort_column == "cardDue"


def test_leaving_ordered_deck_restores_sorting_and_hides_column(col):
    state = CardState(col)
    state.sort_column = "noteFld"
    state.sort_backwards = True
    prepare_card_order(col, state, col.decks.id("ordered"))

    changed = prepare_card_order(col, state, None)

    assert changed
    assert CARD_ORDER_COLUMN not in state.active_columns
    assert (state.sort_column, state.sort_backwards) == ("noteFld", True)
    # a later visit starts from the restored sorting again
    assert CardState(col).sort_column == "noteFld"


class FakeTable:
    """The parts of the browser table that the drag handler uses."""

    def __init__(self, view, sorted_by_order: bool = True) -> None:
        self.view = view
        self.sorted_by_order = sorted_by_order
        self.moves: list[tuple[list[int], int, bool]] = []

    def card_order_deck_id(self):
        return 1

    def is_sorted_by_card_order(self) -> bool:
        return self.sorted_by_order

    def len(self) -> int:
        return self.view.model().rowCount()

    def selected_rows(self) -> list[int]:
        return sorted(i.row() for i in self.view.selectionModel().selectedRows())

    def select_rows_for_drag(self, rows: list[int]) -> None:
        self.view.selectRow(rows[0])

    def move_rows_in_card_order(self, rows, target_row, insert_after) -> None:
        self.moves.append((rows, target_row, insert_after))


@pytest.fixture
def table_view(qapp):
    from aqt.qt import QAbstractItemView, QStandardItem, QStandardItemModel, QTableView

    model = QStandardItemModel(5, 1)
    for row in range(5):
        model.setItem(row, 0, QStandardItem(f"card {row}"))
    view = QTableView()
    view.setModel(model)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    view.resize(300, 400)
    view.show()
    yield view
    view.close()


def mouse(view, kind, row, button=None, buttons=None, cmd=True, y_offset=0):
    from aqt.qt import QApplication, QEvent, QMouseEvent, QPointF, Qt

    viewport = view.viewport()
    pos = view.visualRect(view.model().index(row, 0)).center()
    pos.setY(pos.y() + y_offset)
    left = Qt.MouseButton.LeftButton
    event = QMouseEvent(
        getattr(QEvent.Type, kind),
        QPointF(pos),
        QPointF(viewport.mapToGlobal(pos)),
        button or left,
        buttons if buttons is not None else left,
        Qt.KeyboardModifier.ControlModifier if cmd else Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, event)


def drag(view, from_row, to_row, y_offset=0):
    from aqt.qt import Qt

    mouse(view, "MouseButtonPress", from_row)
    mouse(view, "MouseMove", from_row, y_offset=-12)
    mouse(view, "MouseMove", to_row, y_offset=y_offset)
    mouse(view, "MouseButtonRelease", to_row, buttons=Qt.MouseButton.NoButton)


def test_cmd_drag_moves_row_before_drop_row(table_view):
    table = FakeTable(table_view)
    CardOrderDrag(table, table_view)  # type: ignore[arg-type]

    drag(table_view, 4, 1, y_offset=-5)

    assert table.moves == [([4], 1, False)]


def test_cmd_click_without_drag_toggles_selection_like_qt(table_view):
    from aqt.qt import Qt

    table = FakeTable(table_view)
    CardOrderDrag(table, table_view)  # type: ignore[arg-type]
    table_view.selectRow(0)

    mouse(table_view, "MouseButtonPress", 2)
    mouse(table_view, "MouseButtonRelease", 2, buttons=Qt.MouseButton.NoButton)
    # shift click extends from the cmd-clicked row, as without the handler
    mouse(table_view, "MouseButtonPress", 3, cmd=False)
    mouse(table_view, "MouseButtonRelease", 3, buttons=Qt.MouseButton.NoButton)

    assert table.moves == []
    assert table.selected_rows() == [3]


def test_drag_whose_release_was_lost_is_forgotten(table_view):
    from aqt.qt import Qt

    table = FakeTable(table_view)
    CardOrderDrag(table, table_view)  # type: ignore[arg-type]
    mouse(table_view, "MouseButtonPress", 4)
    mouse(table_view, "MouseMove", 4, y_offset=-12)
    mouse(table_view, "MouseMove", 1)

    # eg a context menu took the release; the next plain click is just a click
    mouse(table_view, "MouseButtonPress", 2, cmd=False)
    mouse(
        table_view, "MouseButtonRelease", 2, cmd=False, buttons=Qt.MouseButton.NoButton
    )

    assert table.moves == []
    assert table.selected_rows() == [2]


def test_refused_drag_selects_rows_like_qt(table_view):
    table = FakeTable(table_view, sorted_by_order=False)
    CardOrderDrag(table, table_view)  # type: ignore[arg-type]
    table_view.selectRow(0)

    with (
        patch("aqt.browser.table.card_order.tooltip") as tooltip,
        patch("aqt.browser.table.card_order.tr"),
    ):
        drag(table_view, 4, 1)

    tooltip.assert_called_once()
    assert table.moves == []
    # Qt's own Cmd-drag adds the dragged-over rows to the selection
    assert table.selected_rows() == [0, 1, 2, 3, 4]
