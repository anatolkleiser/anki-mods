# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from tests.shared import getEmptyCol


def add_cards(col, deck_id, count):
    card_ids = []
    for i in range(count):
        note = col.newNote()
        note["Front"] = f"front {i}"
        col.add_note(note, deck_id)
        card_ids.append(note.cards()[0].id)
    return card_ids


def test_card_order_enabled_follows_backend_switch():
    col = getEmptyCol()
    did = col.decks.id("ordered")
    add_cards(col, did, 1)
    assert not col.decks.card_order_enabled(did)

    col.sched.set_deck_card_order_enabled(did, True)

    assert col.decks.card_order_enabled(did)


def test_card_order_enabled_survives_legacy_deck_save():
    col = getEmptyCol()
    did = col.decks.id("ordered")
    col.sched.set_deck_card_order_enabled(did, True)

    deck = col.decks.get(did)
    deck["desc"] = "changed elsewhere"
    col.decks.save(deck)

    assert col.decks.card_order_enabled(did)


def test_card_order_enabled_is_false_for_filtered_and_missing_decks():
    col = getEmptyCol()
    did = col.decks.id("ordered")
    add_cards(col, did, 1)
    filtered = col.decks.new_filtered("filtered")

    assert not col.decks.card_order_enabled(filtered)
    assert not col.decks.card_order_enabled(123456)


def test_find_cards_sorts_by_card_order_column():
    col = getEmptyCol()
    did = col.decks.id("ordered")
    first, second, third = add_cards(col, did, 3)
    col.sched.set_deck_card_order_enabled(did, True)

    col.sched.move_cards_in_deck_order(did, [third], target=first)

    column = next(c for c in col.all_browser_columns() if c.key == "cardOrder")
    assert list(col.find_cards("deck:ordered", order=column)) == [
        third,
        first,
        second,
    ]
    assert col.get_card(third).custom_data == '{"oi":1}'
