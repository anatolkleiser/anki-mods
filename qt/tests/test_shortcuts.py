# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from aqt import shortcuts
from aqt.profiles import ProfileManager


@pytest.fixture
def mw() -> Iterator[MagicMock]:
    mw = MagicMock()
    mw.pm = ProfileManager.__new__(ProfileManager)
    mw.pm.meta = {}
    with patch.object(shortcuts.aqt, "mw", mw):
        yield mw


def test_keys_returns_defaults_when_not_changed(mw: MagicMock) -> None:
    assert shortcuts.keys("reviewer.replay_audio") == ["R", "F5"]
    assert shortcuts.is_default("reviewer.replay_audio")


def test_set_keys_replaces_all_default_keys(mw: MagicMock) -> None:
    shortcuts.set_keys("reviewer.replay_audio", "Ctrl+R")

    assert shortcuts.keys("reviewer.replay_audio") == ["Ctrl+R"]
    assert mw.pm.shortcuts() == {"reviewer.replay_audio": "Ctrl+R"}


def test_set_keys_disables_shortcut_when_empty(mw: MagicMock) -> None:
    shortcuts.set_keys("main.sync", "")

    assert shortcuts.keys("main.sync") == []
    assert shortcuts.key("main.sync") == ""
    assert shortcuts.bind("main.sync", print) == []


def test_set_keys_forgets_change_when_reset_or_set_to_default(
    mw: MagicMock,
) -> None:
    mw.pm.meta["shortcuts"] = {"main.sync": "Ctrl+Y", "main.add": "N"}

    shortcuts.set_keys("main.sync", None)
    shortcuts.set_keys("main.add", "A")

    assert mw.pm.shortcuts() == {}
    assert shortcuts.keys("main.sync") == ["Y"]


def test_answer_keys_use_existing_answer_key_setting(mw: MagicMock) -> None:
    shortcuts.set_keys("reviewer.answer1", "J")

    assert mw.pm.get_answer_key(1) == "J"
    assert shortcuts.keys("reviewer.answer1") == ["J"]
    assert mw.pm.shortcuts() == {}


def test_answer_key_reset_restores_number(mw: MagicMock) -> None:
    mw.pm.set_answer_key(2, "K")

    shortcuts.set_keys("reviewer.answer2", None)

    assert mw.pm.get_answer_key(2) == "2"


@pytest.mark.parametrize(
    "qt, web",
    [
        ("Ctrl+Shift+B", "Control+Shift+B"),
        ("Ctrl+Return", "Control+Enter"),
        ("Ctrl+Del", "Control+Delete"),
        ("Ctrl+M, M", "Control+M, M"),
        ("Meta+Alt+F7", "Meta+Alt+F7"),
        ("Ctrl++", "Control++"),
    ],
)
def test_qt_to_web_converts_key_names(qt: str, web: str) -> None:
    assert shortcuts.qt_to_web(qt) == web


def test_builtin_editor_defaults_round_trip_to_typescript_format() -> None:
    for shortcut in shortcuts.all_shortcuts():
        if shortcut.web_default is not None:
            assert shortcuts.qt_to_web(shortcut.defaults[0]) == shortcut.web_default


def test_editor_overrides_contains_only_changed_editor_shortcuts(
    mw: MagicMock,
) -> None:
    shortcuts.set_keys("editor.bold", "Ctrl+Shift+B")
    shortcuts.set_keys("main.sync", "Ctrl+Y")

    assert shortcuts.editor_overrides() == {"Control+B": "Control+Shift+B"}


def test_indent_keys_include_tab_by_default(mw: MagicMock) -> None:
    assert shortcuts.keys("editor.indent") == ["Ctrl+Shift+.", "Tab"]
    assert shortcuts.keys("editor.outdent") == ["Ctrl+Shift+,", "Shift+Tab"]
    assert shortcuts.editor_overrides() == {}


def test_editor_overrides_disables_tab_when_indent_changed(mw: MagicMock) -> None:
    shortcuts.set_keys("editor.indent", "Ctrl+]")

    assert shortcuts.editor_overrides() == {"Control+Shift+.": "Control+]", "Tab": ""}
