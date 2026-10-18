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
