# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Playing a deck's cards in the custom order the user gave them in the browser.

A session runs in a filtered deck that doesn't reschedule, so answers don't
change the cards' scheduling. The filtered deck is removed again when the
user stops reviewing.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import aqt
from anki.cards import Card
from anki.collection import Collection, OpChanges, OpChangesWithId, SearchNode
from anki.decks import DeckId, FilteredDeckConfig
from anki.lang import without_unicode_isolation
from aqt.errors import show_exception
from aqt.operations import CollectionOp
from aqt.utils import tr

if TYPE_CHECKING:
    from aqt.main import MainWindowState

# maps the id of a deck being played in order to the id of its filtered deck
SESSIONS_KEY = "cardOrderSessions"
# key of a card's order index in its custom data
CARD_ORDER_KEY = "oi"

_DECK_SEARCH = re.compile(r'^"?deck:(.+?)"?$')
# deck names that searches treat as keywords
_SPECIAL_DECK_NAMES = ("current", "filtered")

# set while a session's filtered deck is being built
_starting = False
# the filtered deck of the session being reviewed
_session_deck_id: DeckId | None = None


def deck_for_search(col: Collection, search: str) -> DeckId | None:
    """The normal deck shown by a normalized search for a single deck, like the
    ones the sidebar makes. None for any other search."""
    if search == col.build_search_string(SearchNode(deck="current")):
        did = col.decks.get_current_id()
        deck = col.decks.get(did, default=False)
        if not deck or deck["dyn"] or deck["name"].lower() in _SPECIAL_DECK_NAMES:
            return None
        return did
    if not (match := _DECK_SEARCH.match(search)):
        return None
    name = re.sub(r"\\(.)", r"\1", match.group(1))
    if name.lower() in _SPECIAL_DECK_NAMES:
        return None
    deck = col.decks.by_name(name)
    if not deck or deck["dyn"]:
        return None
    # guard against misreading escapes
    if col.build_search_string(SearchNode(deck=name)) != search:
        return None
    return DeckId(deck["id"])


def card_order_index(card: Card) -> int | None:
    try:
        custom_data = json.loads(card.custom_data or "{}")
    except ValueError:
        return None
    index = custom_data.get(CARD_ORDER_KEY) if isinstance(custom_data, dict) else None
    return index if isinstance(index, int) else None


def session_search(col: Collection, deck_id: DeckId, from_index: int | None) -> str:
    """The deck's cards and its children's, from the given order index on, and
    cards that have no index yet, which come last."""
    deck_ids = ",".join(str(did) for did in col.decks.deck_and_child_ids(deck_id))
    search = f"did:{deck_ids}"
    if from_index is not None:
        search += (
            f" (prop:cdn:{CARD_ORDER_KEY}>={from_index} OR -has-cd:{CARD_ORDER_KEY})"
        )
    return search


def learn_in_order(
    *, mw: aqt.AnkiQt, deck_id: DeckId, from_index: int | None = None
) -> None:
    """Build a filtered deck that plays the deck's cards in their custom order
    without rescheduling them, and start reviewing it. With from_index, start
    with the card that has it."""
    global _starting
    if _starting:
        return
    col = mw.col
    deck = col.decks.get(deck_id)
    assert deck is not None
    sessions: dict[str, int] = col.get_config(SESSIONS_KEY, {})
    existing = DeckId(sessions.get(str(deck_id), 0))
    if existing and not (col.decks.get(existing, default=False) or {}).get("dyn"):
        existing = DeckId(0)

    filtered = col.sched.get_or_create_filtered_deck(deck_id=existing)
    # a top-level deck, so it doesn't count towards the limits of any parent
    filtered.name = without_unicode_isolation(
        tr.studying_in_order_deck_name(deck=deck["name"].replace("::", " - "))
    )
    config = filtered.config
    config.reschedule = False
    config.preview_again_secs = 60
    config.preview_hard_secs = 600
    config.preview_good_secs = 0
    del config.search_terms[:]
    config.search_terms.append(
        FilteredDeckConfig.SearchTerm(
            search=session_search(col, deck_id, from_index),
            limit=99999,
            order=FilteredDeckConfig.SearchTerm.CARD_ORDER,
        )
    )

    other_session_decks = [
        DeckId(did)
        for home, did in sessions.items()
        if home != str(deck_id) and _is_filtered_deck(col, DeckId(did))
    ]

    def op(col: Collection) -> OpChangesWithId:
        if not other_session_decks:
            return col.sched.add_or_update_filtered_deck(filtered)
        # the other session holds cards this one may need
        undo_entry = col.add_custom_undo_entry(tr.studying_learn_in_order())
        col.decks.remove(other_session_decks)
        out = col.sched.add_or_update_filtered_deck(filtered)
        col.merge_undo_entries(undo_entry)
        return out

    def on_success(out: OpChangesWithId) -> None:
        global _starting, _session_deck_id
        _starting = False
        _session_deck_id = DeckId(out.id)
        col.set_config(SESSIONS_KEY, {str(deck_id): out.id})
        col.startTimebox()
        mw.moveToState("review")
        # it may have been started from the browser
        mw.activateWindow()
        mw.raise_()

    def on_failure(err: Exception) -> None:
        global _starting
        _starting = False
        show_exception(parent=mw, exception=err)

    _starting = True
    # the reviewer is shown by on_success, so it needn't refresh after the op
    CollectionOp(mw, op).success(on_success).failure(on_failure).run_in_background(
        initiator=mw.reviewer
    )


def _is_filtered_deck(col: Collection, did: DeckId) -> bool:
    return bool((col.decks.get(did, default=False) or {}).get("dyn"))


def end_sessions(col: Collection) -> OpChanges:
    """Remove the filtered decks of all sessions, returning their cards, and
    select the deck that was being played. A single undo step."""
    global _session_deck_id
    _session_deck_id = None
    sessions: dict[str, int] = col.get_config(SESSIONS_KEY, {})
    session_decks = [
        DeckId(did) for did in sessions.values() if _is_filtered_deck(col, DeckId(did))
    ]
    if not session_decks:
        # eg an undo removed them; nothing to undo here
        return col.set_config(SESSIONS_KEY, {})
    current = col.decks.get_current_id()
    undo_entry = col.add_custom_undo_entry(tr.studying_learn_in_order())
    col.remove_config(SESSIONS_KEY)
    for home, filtered in sessions.items():
        if filtered == current and col.decks.get(DeckId(int(home)), default=False):
            col.decks.select(DeckId(int(home)))
    col.decks.remove(session_decks)
    return col.merge_undo_entries(undo_entry)


def _has_sessions() -> bool:
    from aqt import mw

    return bool(mw and mw.col and mw.col.get_config(SESSIONS_KEY, {}))


def on_state_did_change(new_state: MainWindowState, old_state: MainWindowState) -> None:
    "End sessions the user has left."
    from aqt import mw

    if new_state in ("review", "resetRequired", "profileManager") or not mw:
        return
    if _has_sessions():
        CollectionOp(mw, end_sessions).run_in_background()


def on_profile_will_close() -> None:
    "End sessions before the collection is closed and synced."
    from aqt import mw

    if mw and _has_sessions():
        end_sessions(mw.col)
        if mw.state == "review":
            # the close may still be cancelled, eg by an unsaved Add window
            mw.moveToState("overview")


def on_operation_did_execute(changes: OpChanges, handler: object | None) -> None:
    "Leave the reviewer if an undo has removed the session's filtered deck."
    from aqt import mw

    if not mw or mw.state != "review" or not changes.deck or not _session_deck_id:
        return
    if mw.col.decks.get_current_id() != _session_deck_id or not _is_filtered_deck(
        mw.col, _session_deck_id
    ):
        mw.moveToState("overview")
