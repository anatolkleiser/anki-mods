# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Keyboard shortcuts that can be changed in the preferences.

Each shortcut has an id and its default key sequences. Changed shortcuts are
stored with the other shared settings via ProfileManager.shortcuts(); an empty
string disables a shortcut. Answer keys keep using their own setting.

Editor shortcuts are registered in TypeScript (ts/lib/tslib/shortcuts.ts), and
are remapped there by their default key combination.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aqt
from anki.utils import is_mac
from aqt.qt import QAction, QKeySequence, QWebEngineScript
from aqt.utils import shortcut, tr


class ShortcutContext(Enum):
    MAIN_WINDOW = "main_window"
    MAIN_MENU = "main_menu"
    DECK_OVERVIEW = "deck_overview"
    REVIEWER = "reviewer"
    BROWSER = "browser"
    PREVIEWER = "previewer"
    CARD_LAYOUT = "card_layout"
    EDITOR = "editor"

    def label(self) -> str:
        return {
            ShortcutContext.MAIN_WINDOW: tr.preferences_shortcuts_context_main_window,
            ShortcutContext.MAIN_MENU: tr.preferences_shortcuts_context_main_menu,
            ShortcutContext.DECK_OVERVIEW: tr.preferences_shortcuts_context_overview,
            ShortcutContext.REVIEWER: tr.preferences_review,
            ShortcutContext.BROWSER: tr.qt_misc_browse,
            ShortcutContext.PREVIEWER: tr.preferences_shortcuts_context_previewer,
            ShortcutContext.CARD_LAYOUT: tr.preferences_shortcuts_context_card_layout,
            ShortcutContext.EDITOR: tr.preferences_editing,
        }[self]()


@dataclass
class Shortcut:
    id: str
    context: ShortcutContext
    label: Callable[[], str]
    defaults: tuple[str, ...]
    # name of the QAction on the window's form, if defined in a .ui file
    action: str | None = None
    # key combination as written in the TypeScript code, for editor shortcuts
    web_default: str | None = None
    # ease, for the answer keys
    answer: int | None = None
    # further key combinations bound in TypeScript, active by default only
    web_extra: tuple[str, ...] = ()


_shortcuts: dict[str, Shortcut] = {}


def all_shortcuts() -> list[Shortcut]:
    return list(_shortcuts.values())


def get(id: str) -> Shortcut:
    return _shortcuts[id]


# Reading and writing settings
######################################################################


def keys(id: str) -> list[str]:
    """The key sequences currently bound to a shortcut; empty if disabled."""
    sc = _shortcuts[id]
    if sc.answer is not None:
        answer_key = aqt.mw.pm.get_answer_key(sc.answer)
        return [answer_key] if answer_key else []
    changed = aqt.mw.pm.shortcuts()
    if id in changed:
        return [changed[id]] if changed[id] else []
    return list(sc.defaults)


def key(id: str) -> str:
    """The first key sequence bound to a shortcut, or an empty string."""
    return next(iter(keys(id)), "")


def display(id: str) -> str:
    return ", ".join(shortcut(k) for k in keys(id))


def tooltip(id: str) -> str:
    return tr.actions_shortcut_key(val=display(id)) if keys(id) else ""


def is_default(id: str) -> bool:
    return keys(id) == list(_shortcuts[id].defaults)


def set_keys(id: str, value: str | None) -> None:
    """Change a shortcut. None restores the default, and an empty string
    disables it."""
    sc = _shortcuts[id]
    if value is None:
        value = sc.defaults[0] if sc.answer is not None else None
    if sc.answer is not None:
        aqt.mw.pm.set_answer_key(sc.answer, value or "")
        return
    if value is not None and [value] == list(sc.defaults):
        value = None
    aqt.mw.pm.set_shortcut(id, value)


# Applying shortcuts
######################################################################


def bind(id: str, fn: Callable) -> list[tuple[str, Callable]]:
    """(key, fn) pairs for mw.applyShortcuts()."""
    return [(k, fn) for k in keys(id)]


def bind_all(pairs: Iterable[tuple[str, Callable]]) -> list[tuple[str, Callable]]:
    return [binding for id, fn in pairs for binding in bind(id, fn)]


def apply_to_action(action: QAction, id: str) -> None:
    action.setShortcuts([QKeySequence(k) for k in keys(id)])


def apply_to_form(form: Any, context: ShortcutContext) -> None:
    """Apply shortcuts to the QActions of a form created from a .ui file."""
    for sc in _shortcuts.values():
        if sc.context == context and sc.action:
            apply_to_action(getattr(form, sc.action), sc.id)


def qt_to_web(sequence: str) -> str:
    """Convert a QKeySequence portable string to the format used by
    registerShortcut() in TypeScript."""
    replacements = {
        "Ctrl": "Control",
        "Del": "Delete",
        "Return": "Enter",
        "Esc": "Escape",
        "PgUp": "PageUp",
        "PgDown": "PageDown",
    }
    chords = []
    for chord in sequence.split(", "):
        # a trailing '+' is the plus key, not a separator
        parts = (
            chord[:-2].split("+") + ["+"] if chord.endswith("++") else chord.split("+")
        )
        chords.append("+".join(replacements.get(part, part) for part in parts))
    return ", ".join(chords)


def web_to_qt(combination: str) -> str:
    return (
        combination.replace("Control", "Ctrl")
        .replace("Enter", "Return")
        .replace("Delete", "Del")
    )


def editor_overrides() -> dict[str, str]:
    """Changed editor shortcuts, keyed by their default key combination.
    Additional default combinations are disabled once a shortcut is changed."""
    overrides: dict[str, str] = {}
    for sc in _shortcuts.values():
        if sc.web_default is None or is_default(sc.id):
            continue
        overrides[sc.web_default] = qt_to_web(key(sc.id))
        for extra in sc.web_extra:
            overrides[extra] = ""
    return overrides


def editor_script() -> QWebEngineScript:
    """Passes changed shortcuts to an editor page before it loads, so they
    are in place when its components register their shortcuts."""
    script = QWebEngineScript()
    script.setSourceCode(
        f"globalThis.shortcutOverrides = {json.dumps(editor_overrides())};"
    )
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setRunsOnSubFrames(False)
    return script


# Built-in shortcuts
######################################################################


def _accel(fn: Callable[[], str]) -> Callable[[], str]:
    "Label from a menu entry, without its accelerator marker."
    return lambda: fn().replace("&&", "\0").replace("&", "").replace("\0", "&")


def _flag_label(index: int) -> Callable[[], str]:
    return lambda: aqt.mw.flags.get_flag(index).label


_FLAG_ACTIONS = ("Red", "Orange", "Green", "Blue", "Pink", "Turquoise", "Purple")


def _register_builtin() -> None:
    C = ShortcutContext

    def add(
        id: str,
        context: ShortcutContext,
        label: Callable[[], str],
        *defaults: str,
        action: str | None = None,
        web: str | None = None,
        answer: int | None = None,
        web_extra: tuple[str, ...] = (),
    ) -> None:
        _shortcuts[id] = Shortcut(
            id, context, label, defaults, action, web, answer, web_extra
        )

    # main window, active in every state
    add("main.debug_console", C.MAIN_WINDOW, tr.qt_misc_debug_console, "Ctrl+:")
    add("main.decks", C.MAIN_WINDOW, tr.actions_decks, "D")
    add("main.study", C.MAIN_WINDOW, tr.studying_study_now, "S")
    add("main.add", C.MAIN_WINDOW, tr.actions_add, "A")
    add("main.browse", C.MAIN_WINDOW, tr.qt_misc_browse, "B")
    add("main.stats", C.MAIN_WINDOW, tr.qt_misc_stats, "T", "Shift+T")
    add("main.sync", C.MAIN_WINDOW, tr.qt_misc_sync, "Y")
    add(
        "main.full_screen",
        C.MAIN_WINDOW,
        _accel(tr.qt_accel_full_screen),
        "Ctrl+Meta+F" if is_mac else "F11",
    )

    # main window menus (defaults from main.ui)
    for name, label, default in (
        ("actionExit", tr.qt_accel_exit, "Ctrl+Q"),
        ("actionPreferences", tr.qt_accel_preferences, "Ctrl+P"),
        ("actionUndo", tr.qt_accel_undo, "Ctrl+Z"),
        ("actionRedo", tr.qt_accel_redo, "Ctrl+Shift+Z"),
        ("actionDocumentation", tr.qt_accel_guide, "F1"),
        ("actionSwitchProfile", tr.qt_accel_switch_profile, "Ctrl+Shift+P"),
        ("actionImport", tr.qt_accel_import, "Ctrl+Shift+I"),
        ("actionExport", tr.qt_accel_export, "Ctrl+E"),
        ("actionStudyDeck", tr.qt_misc_study_deck, "/"),
        ("actionCreateFiltered", tr.qt_misc_create_filtered_deck, "F"),
        ("actionNoteTypes", tr.qt_misc_manage_note_types, "Ctrl+Shift+N"),
        ("actionAdd_ons", tr.qt_misc_addons, "Ctrl+Shift+A"),
        ("actionEmptyCards", tr.qt_misc_empty_cards, ""),
        ("actionZoomIn", tr.qt_accel_zoom_in, ""),
        ("actionZoomOut", tr.qt_accel_zoom_out, ""),
        ("actionResetZoom", tr.qt_accel_reset_zoom, "Ctrl+0"),
    ):
        add(
            f"menu.{name}",
            C.MAIN_MENU,
            _accel(label),
            *filter(None, [default]),
            action=name,
        )

    # deck overview
    add("overview.options", C.DECK_OVERVIEW, tr.actions_options, "O")
    add("overview.rebuild", C.DECK_OVERVIEW, tr.actions_rebuild, "R")
    add("overview.empty", C.DECK_OVERVIEW, tr.studying_empty, "E")
    add("overview.custom_study", C.DECK_OVERVIEW, tr.actions_custom_study, "C")
    add("overview.unbury", C.DECK_OVERVIEW, tr.studying_unbury, "U")

    # reviewer
    add(
        "reviewer.show_answer",
        C.REVIEWER,
        tr.studying_show_answer,
        "Space",
        "Return",
        "Enter",
    )
    for ease, label in (
        (1, tr.studying_again),
        (2, tr.studying_hard),
        (3, tr.studying_good),
        (4, tr.studying_easy),
    ):
        add(f"reviewer.answer{ease}", C.REVIEWER, label, str(ease), answer=ease)
    add("reviewer.edit", C.REVIEWER, tr.studying_edit, "E")
    add("reviewer.more", C.REVIEWER, tr.studying_more, "M")
    add("reviewer.undo", C.REVIEWER, tr.undo_undo, "U")
    add("reviewer.replay_audio", C.REVIEWER, tr.actions_replay_audio, "R", "F5")
    add("reviewer.pause_audio", C.REVIEWER, tr.studying_pause_audio, "5")
    add("reviewer.seek_backward", C.REVIEWER, tr.studying_audio_5s, "6")
    add("reviewer.seek_forward", C.REVIEWER, tr.studying_audio_and5s, "7")
    add("reviewer.record_voice", C.REVIEWER, tr.studying_record_own_voice, "Shift+V")
    add("reviewer.replay_voice", C.REVIEWER, tr.studying_replay_own_voice, "V")
    for index in range(1, 8):
        add(f"reviewer.flag{index}", C.REVIEWER, _flag_label(index), f"Ctrl+{index}")
    add("reviewer.mark_note", C.REVIEWER, tr.studying_mark_note, "*")
    add("reviewer.bury_card", C.REVIEWER, tr.studying_bury_card, "-")
    add("reviewer.bury_note", C.REVIEWER, tr.studying_bury_note, "=")
    add("reviewer.suspend_card", C.REVIEWER, tr.actions_suspend_card, "@")
    add("reviewer.suspend_note", C.REVIEWER, tr.studying_suspend_note, "!")
    add("reviewer.forget", C.REVIEWER, tr.actions_forget_card, "Ctrl+Alt+N")
    add("reviewer.set_due_date", C.REVIEWER, tr.actions_set_due_date, "Ctrl+Shift+D")
    add("reviewer.create_copy", C.REVIEWER, tr.actions_create_copy, "Ctrl+Alt+E")
    add(
        "reviewer.delete_note",
        C.REVIEWER,
        tr.studying_delete_note,
        "Ctrl+Backspace" if is_mac else "Ctrl+Del",
    )
    add("reviewer.options", C.REVIEWER, tr.actions_options, "O")
    add("reviewer.card_info", C.REVIEWER, tr.actions_card_info, "I")
    add(
        "reviewer.previous_card_info",
        C.REVIEWER,
        tr.actions_previous_card_info,
        "Ctrl+Alt+I",
    )
    add("reviewer.auto_advance", C.REVIEWER, tr.actions_auto_advance, "Shift+A")

    # browser (defaults from browser.ui unless noted)
    for name, label, defaults in (
        ("actionUndo", tr.qt_accel_undo, ("Ctrl+Z",)),
        ("actionRedo", tr.qt_accel_redo, ("Ctrl+Shift+Z",)),
        ("actionSelectAll", tr.qt_accel_select_all, ("Ctrl+Alt+A",)),
        ("actionSelectNotes", tr.qt_accel_select_notes, ()),
        ("actionInvertSelection", tr.qt_accel_invert_selection, ("Ctrl+Alt+S",)),
        ("action_toggle_mode", tr.browsing_toggle_showing_cards_notes, ("Ctrl+Alt+T",)),
        ("actionFind", tr.qt_accel_find, ("Ctrl+F",)),
        ("actionSidebarFilter", tr.qt_accel_filter, ("Ctrl+Shift+F",)),
        ("actionFindReplace", tr.qt_accel_find_and_replace, ("Ctrl+Alt+F",)),
        ("actionFindDuplicates", tr.qt_accel_find_duplicates, ()),
        ("actionNote", tr.qt_accel_note, ("Ctrl+Shift+N",)),
        ("actionCardList", tr.browsing_card_list, ("Ctrl+Shift+L",)),
        ("actionSidebar", tr.browsing_sidebar, ("Ctrl+Shift+R",)),
        ("actionToggleSidebar", tr.qt_accel_toggle_sidebar, ()),
        ("actionPreviousCard", tr.qt_accel_previous_card, ("Ctrl+P",)),
        ("actionNextCard", tr.qt_accel_next_card, ("Ctrl+N",)),
        ("actionFirstCard", tr.browsing_first_card, ("Home",)),
        ("actionLastCard", tr.browsing_last_card, ("End",)),
        ("actionAdd", tr.browsing_add_notes, ("Ctrl+E",)),
        ("actionCopy", tr.actions_create_copy, ("Ctrl+Alt+E",)),
        ("actionDelete", tr.actions_delete, ("Ctrl+Del",)),
        ("actionAdd_Tags", tr.browsing_add_tags2, ("Ctrl+Shift+A",)),
        ("actionRemove_Tags", tr.browsing_remove_tags, ("Ctrl+Alt+Shift+A",)),
        ("actionClear_Unused_Tags", tr.browsing_clear_unused_tags, ()),
        ("actionToggle_Mark", tr.browsing_toggle_mark, ("Ctrl+K",)),
        ("actionChangeModel", tr.browsing_change_note_type2, ("Ctrl+Shift+M",)),
        ("actionManage_Note_Types", tr.browsing_manage_note_types, ()),
        ("actionExport", tr.qt_accel_export_notes, ("Ctrl+Shift+E",)),
        ("actionChange_Deck", tr.browsing_change_deck2, ("Ctrl+D",)),
        ("action_Info", tr.qt_accel_info, ("Ctrl+Shift+I",)),
        ("actionReposition", tr.browsing_reposition, ("Ctrl+Shift+S",)),
        ("action_set_due_date", tr.qt_accel_set_due_date, ("Ctrl+Shift+D",)),
        ("action_grade_now", tr.actions_grade_now, ("Ctrl+Shift+G",)),
        ("action_forget", tr.qt_accel_forget, ("Ctrl+Alt+N",)),
        ("actionToggle_Suspend", tr.browsing_toggle_suspend, ("Ctrl+J",)),
        ("action_toggle_bury", tr.browsing_toggle_bury, ("Ctrl+Shift+J",)),
        (
            "actionCreateFilteredDeck",
            tr.qt_misc_create_filtered_deck,
            ("Ctrl+G", "Ctrl+Alt+G"),
        ),
        ("actionZoomIn", tr.qt_accel_zoom_editor_in, ()),
        ("actionZoomOut", tr.qt_accel_zoom_editor_out, ()),
        ("actionResetZoom", tr.qt_accel_reset_zoom, ("Ctrl+0",)),
        ("actionGuide", tr.qt_accel_guide, ("F1",)),
        ("actionClose", tr.actions_close, ("Ctrl+W",)),
    ):
        add(
            f"browser.{name}",
            C.BROWSER,
            _accel(label),
            *defaults,
            action=name,
        )
    for index, colour in enumerate(_FLAG_ACTIONS, start=1):
        name = f"action{colour}_Flag"
        add(
            f"browser.{name}",
            C.BROWSER,
            _flag_label(index),
            f"Ctrl+{index}",
            action=name,
        )
    add(
        "browser.add_note_to_deck",
        C.BROWSER,
        tr.actions_add,
        "Ctrl+N",
    )
    add(
        "browser.delete_notes",
        C.BROWSER,
        tr.browsing_delete_notes,
        "Ctrl+Shift+Backspace",
        # shown on the editor's delete button
        web="Control+Shift+Backspace",
    )
    add(
        "browser.toggle_preview",
        C.BROWSER,
        tr.actions_preview,
        "Ctrl+Shift+P",
    )

    # card preview window
    add(
        "previewer.close",
        C.PREVIEWER,
        tr.actions_close,
        "Ctrl+Shift+P",
    )
    add("previewer.previous", C.PREVIEWER, _accel(tr.qt_accel_previous_card), "Left")
    add("previewer.next", C.PREVIEWER, _accel(tr.qt_accel_next_card), "Right")
    add("previewer.replay_audio", C.PREVIEWER, tr.actions_replay_audio, "R")
    add("previewer.back_side_only", C.PREVIEWER, tr.qt_misc_back_side_only, "B")

    # card layout window
    add("clayout.front", C.CARD_LAYOUT, tr.card_templates_front_template, "Ctrl+1")
    add("clayout.back", C.CARD_LAYOUT, tr.card_templates_back_template, "Ctrl+2")
    add("clayout.styling", C.CARD_LAYOUT, tr.card_templates_template_styling, "Ctrl+3")
    add(
        "clayout.previous_card_type",
        C.CARD_LAYOUT,
        tr.preferences_shortcuts_previous_card_type,
        "F3",
    )
    add(
        "clayout.next_card_type",
        C.CARD_LAYOUT,
        tr.preferences_shortcuts_next_card_type,
        "F4",
    )
    add("clayout.save", C.CARD_LAYOUT, tr.actions_save, "Ctrl+Return")

    # inside a list, Tab/Shift+Tab also change the indentation
    editor_extra_keys = {"indent": ("Tab",), "outdent": ("Shift+Tab",)}

    # editor (in the add, edit and browser windows)
    for id, label, web in (
        ("bold", tr.editing_bold_text, "Control+B"),
        ("italic", tr.editing_italic_text, "Control+I"),
        ("underline", tr.editing_underline_text, "Control+U"),
        ("superscript", tr.editing_superscript, "Control+="),
        ("subscript", tr.editing_subscript, "Control+Shift+="),
        ("remove_formatting", tr.editing_remove_formatting, "Control+R"),
        ("text_color", tr.editing_text_color, "F7"),
        ("change_color", tr.editing_change_color, "F8"),
        ("unordered_list", tr.editing_unordered_list, "Control+,"),
        ("ordered_list", tr.editing_ordered_list, "Control+."),
        ("toggle_list", tr.preferences_shortcuts_toggle_list, "Control+Shift+L"),
        ("indent", tr.editing_indent, "Control+M"),
        ("outdent", tr.editing_outdent, "Control+Shift+M"),
        ("cloze", tr.editing_cloze_deletion, "Control+Shift+C"),
        ("cloze_same", tr.editing_cloze_deletion_repeat, "Control+Alt+Shift+C"),
        ("mathjax_inline", tr.editing_mathjax_inline, "Control+Alt+M, M"),
        ("mathjax_block", tr.editing_mathjax_block, "Control+Alt+M, E"),
        ("mathjax_chemistry", tr.editing_mathjax_chemistry, "Control+Alt+M, C"),
        ("latex", tr.editing_latex, "Control+T, T"),
        ("latex_equation", tr.editing_latex_equation, "Control+T, E"),
        ("latex_math_env", tr.editing_latex_math_env, "Control+T, M"),
        ("attach", tr.editing_attach_picturesaudiovideo, "F3"),
        ("record_audio", tr.editing_record_audio, "F5"),
        ("toggle_html", tr.editing_toggle_html_editor, "Control+Shift+X"),
        ("toggle_sticky", tr.editing_toggle_sticky, "F9"),
        ("toggle_sticky_all", tr.preferences_shortcuts_toggle_sticky_all, "Shift+F9"),
        ("tags", tr.editing_tags, "Control+Shift+T"),
        ("cards", tr.editing_customize_card_templates, "Control+L"),
        ("notetype", tr.notetypes_choose_note_type, "Control+N"),
        ("deck", tr.decks_choose_deck, "Control+D"),
        ("preview", tr.actions_preview, "Control+Shift+P"),
        ("add_or_close", tr.preferences_shortcuts_add_or_close, "Control+Enter"),
        (
            "history",
            tr.adding_history,
            "Control+Shift+H" if is_mac else "Control+H",
        ),
        ("help", tr.actions_help, "F1"),
    ):
        extra = editor_extra_keys.get(id, ())
        add(
            f"editor.{id}",
            C.EDITOR,
            label,
            web_to_qt(web),
            *(web_to_qt(k) for k in extra),
            web=web,
            web_extra=extra,
        )


_register_builtin()
