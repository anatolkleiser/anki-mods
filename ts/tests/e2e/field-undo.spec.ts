// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Per-field undo stack (undo-stack.ts, NoteEditor.svelte)
 *
 * Typing in a field creates undo steps; changes in quick succession are merged
 * into one step. Undo/redo are available via the keyboard shortcuts and the
 * toolbar buttons, and only ever affect the focused field.
 *
 * Outside of the Add window, saving a field makes Qt report the change back to
 * the editor (webview.py on_operation_did_execute), which reloads the note.
 * That reload must keep the history; loading a different note must clear it.
 */

import { expect, test } from "./fixtures";
import { addNote, editableField, isRpcResponse, loadNote, openInBrowserEditor } from "./helpers";

// longer than MERGE_INTERVAL_MS, so that the next change starts a new step
const STEP_PAUSE_MS = 1_200;

test("keyboard undo/redo restores earlier field content", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.type("hello");
    await page.waitForTimeout(STEP_PAUSE_MS);
    await page.keyboard.type(" world");
    await expect(field).toHaveText("hello world");

    await page.keyboard.press("ControlOrMeta+z");
    await expect(field).toHaveText("hello");

    await page.keyboard.press("ControlOrMeta+z");
    await expect(field).toHaveText("");

    await page.keyboard.press("ControlOrMeta+Shift+z");
    await expect(field).toHaveText("hello");

    // typing continues at the restored caret position
    await page.keyboard.type("!");
    await expect(field).toHaveText("hello!");
});

test("undo pressed in quick succession is not dropped", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    for (const word of ["one", " two", " three"]) {
        await page.keyboard.type(word);
        await page.waitForTimeout(STEP_PAUSE_MS);
    }

    for (let i = 0; i < 3; i++) {
        await page.keyboard.press("ControlOrMeta+z");
    }
    await expect(field).toHaveText("");
});

test("toolbar buttons undo and redo, and are disabled when unavailable", async ({ editor: page }) => {
    const undoButton = page.getByTitle(/^Undo/);
    const redoButton = page.getByTitle(/^Redo/);
    const field = editableField(page, 0);
    await field.click();
    await expect(undoButton).toBeDisabled();

    await page.keyboard.type("abc");
    await expect(undoButton).toBeEnabled();
    await expect(redoButton).toBeDisabled();

    await undoButton.click();
    await expect(field).toHaveText("");
    await expect(undoButton).toBeDisabled();
    await expect(redoButton).toBeEnabled();

    await redoButton.click();
    await expect(field).toHaveText("abc");
});

test("undo only affects the focused field", async ({ editor: page }) => {
    const first = editableField(page, 0);
    const second = editableField(page, 1);
    await first.click();
    await page.keyboard.type("front");
    await second.click();
    await page.keyboard.type("back");

    await page.keyboard.press("ControlOrMeta+z");
    await expect(second).toHaveText("");
    await expect(first).toHaveText("front");

    await first.click();
    await page.keyboard.press("ControlOrMeta+z");
    await expect(first).toHaveText("");
});

test("the history survives the browser reloading the note after saving it", async ({ editor: page }) => {
    const note = await addNote(page, "original");
    await openInBrowserEditor(page, note);
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press("End");

    const saved = page.waitForResponse(isRpcResponse("updateNotes"));
    await page.keyboard.type(" edited");
    await saved;
    const reloaded = page.waitForResponse(isRpcResponse("getNote"));
    await page.evaluate(() => (globalThis as any).anki.onOperationDidExecute({ noteText: true }));
    await reloaded;

    await page.keyboard.press("ControlOrMeta+z");
    await expect(field).toHaveText("original");
});

test("loading a different note clears the history", async ({ editor: page }) => {
    const first = await addNote(page, "first");
    const second = await addNote(page, "second");
    await openInBrowserEditor(page, first);
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press("End");
    await page.keyboard.type(" edited");

    await loadNote(page, second);
    await field.click();

    await expect(page.getByTitle(/^Undo/)).toBeDisabled();
    await page.keyboard.press("ControlOrMeta+z");
    await expect(field).toHaveText("second");
});
