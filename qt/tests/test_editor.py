# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

from anki.collection import OpChanges
from anki.errors import NotFoundError
from anki.notes import NoteId
from aqt.editor import NewEditor, NewEditorWebView
from aqt.webview import AnkiWebView


def make_editor_web_view(nid: NoteId | None) -> NewEditorWebView:
    web = cast(NewEditorWebView, MagicMock(spec=NewEditorWebView))
    web.editor = MagicMock(spec=NewEditor)
    web.editor.nid = nid
    web.editor.mw = MagicMock()
    return web


@patch.object(AnkiWebView, "on_operation_did_execute")
def test_text_change_for_deleted_note_tells_editor_before_forwarding(
    super_on_operation_did_execute: MagicMock,
) -> None:
    web = make_editor_web_view(NoteId(1))
    web._note_was_deleted.return_value = True  # type: ignore[attr-defined]
    changes = OpChanges(note_text=True)

    NewEditorWebView.on_operation_did_execute(web, changes, None)

    web.editor.on_note_deleted.assert_called_once_with()
    super_on_operation_did_execute.assert_called_once_with(changes, None)


@patch.object(AnkiWebView, "on_operation_did_execute")
def test_text_change_for_existing_note_is_only_forwarded(
    super_on_operation_did_execute: MagicMock,
) -> None:
    web = make_editor_web_view(NoteId(1))
    web._note_was_deleted.return_value = False  # type: ignore[attr-defined]
    changes = OpChanges(note_text=True)

    NewEditorWebView.on_operation_did_execute(web, changes, None)

    web.editor.on_note_deleted.assert_not_called()
    super_on_operation_did_execute.assert_called_once_with(changes, None)


@patch.object(AnkiWebView, "on_operation_did_execute")
def test_change_without_text_does_not_look_up_the_note(
    super_on_operation_did_execute: MagicMock,
) -> None:
    web = make_editor_web_view(NoteId(1))
    changes = OpChanges(card=True)

    NewEditorWebView.on_operation_did_execute(web, changes, None)

    web._note_was_deleted.assert_not_called()  # type: ignore[attr-defined]
    web.editor.on_note_deleted.assert_not_called()
    super_on_operation_did_execute.assert_called_once_with(changes, None)


def test_note_was_deleted_when_the_collection_no_longer_has_it() -> None:
    web = make_editor_web_view(NoteId(1))
    web.editor.mw.col.get_note.side_effect = NotFoundError(
        "no such note", None, None, None
    )

    assert NewEditorWebView._note_was_deleted(web) is True
    web.editor.mw.col.get_note.assert_called_once_with(NoteId(1))


def test_note_was_not_deleted_when_the_collection_has_it() -> None:
    web = make_editor_web_view(NoteId(1))

    assert NewEditorWebView._note_was_deleted(web) is False


def test_note_was_not_deleted_without_a_note() -> None:
    web = make_editor_web_view(None)

    assert NewEditorWebView._note_was_deleted(web) is False
    web.editor.mw.col.get_note.assert_not_called()


def test_on_note_deleted_forgets_the_note_and_tells_the_page() -> None:
    editor = cast(NewEditor, MagicMock(spec=NewEditor))
    editor.nid = NoteId(1)
    editor.web = MagicMock()

    NewEditor.on_note_deleted(editor)

    assert editor.nid is None
    editor.web.eval.assert_called_once_with("noteWasDeleted();")
