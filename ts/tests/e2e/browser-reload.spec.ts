// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Reloading the note in the browser editor (NoteEditor.svelte reloadNote)
 *
 * Outside of the Add window, saving a field makes Qt report the change back to
 * the editor (webview.py on_operation_did_execute), which reloads the note.
 * This happens while the user is typing, so it must not move the caret.
 */

import { expect, test } from "./fixtures";
import { addNote, editableField, isRpcResponse, openInBrowserEditor } from "./helpers";

test("the caret stays put when the note is reloaded after saving", async ({ editor: page }) => {
    const note = await addNote(page, "world");
    await openInBrowserEditor(page, note);
    const field = editableField(page, 0);
    // the start of the text; Home does not move the caret on macOS
    await field.click({ position: { x: 1, y: 5 } });

    const saved = page.waitForResponse(isRpcResponse("updateNotes"));
    await page.keyboard.type("hello ");
    await saved;
    // what onOperationDidExecute({ noteText: true }) calls, but awaitable
    await page.evaluate(() => (window as any).reloadNote());
    // focusing after a load is deferred to the next tick
    await page.evaluate(() => new Promise(requestAnimationFrame));

    await page.keyboard.type("there ");
    await expect(field).toHaveText("hello there world");
});

test("loading and reloading a note does not save it", async ({ editor: page }) => {
    const note = await addNote(page, "hello");
    let saves = 0;
    page.on("response", async (resp) => {
        if (isRpcResponse("updateNotes")(resp)) {
            saves++;
            // what webview.py on_operation_did_execute triggers after a save
            await page.evaluate(() => (globalThis as any).anki.onOperationDidExecute({ noteText: true }));
        }
    });
    await openInBrowserEditor(page, note);
    await editableField(page, 0).click();
    await page.evaluate(() => (window as any).reloadNote());
    // longer than the save delay
    await page.waitForTimeout(1_500);
    expect(saves).toBe(0);

    // a change is still saved, once
    await page.keyboard.type("!");
    await page.waitForTimeout(1_500);
    expect(saves).toBe(1);
});

test("a newly shown note focuses the requested field even if loaded again", async ({ editor: page }) => {
    const first = await addNote(page, "one");
    const second = await addNote(page, "two");
    await openInBrowserEditor(page, first);
    await editableField(page, 1).click();

    // what the browser does after adding a note: the first load asks for the
    // first field, and further loads of the same note, which cancel it, don't
    await page.evaluate(({ noteId, notetypeId }) => {
        const args = { nid: noteId, notetypeId, initial: true };
        (window as any).loadNote({ ...args, focusTo: 0 });
        (window as any).loadNote({ ...args, focusTo: null });
    }, second);

    await expect(editableField(page, 0)).toHaveText("two");
    await expect(editableField(page, 0)).toBeFocused();
});
