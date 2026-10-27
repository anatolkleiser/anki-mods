// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * A note deleted while open in the browser editor (NoteEditor.svelte
 * noteWasDeleted)
 *
 * Qt reports the deletion as a text change (editor.py NewEditorWebView
 * on_operation_did_execute), which would otherwise make the editor request the
 * note to see whether it needs reloading, and then to reload it. Python calls
 * noteWasDeleted() first, so the editor must not request the note any more.
 */

import { expect, test } from "./fixtures";
import { addNote, editableField, isRpc, openInBrowserEditor } from "./helpers";

test("a deleted note is neither checked nor reloaded", async ({ editor: page }) => {
    const note = await addNote(page, "doomed");
    await openInBrowserEditor(page, note);
    const requests: string[] = [];
    page.on("request", (request) => {
        if (isRpc("getNote")(request)) {
            requests.push(request.url());
        }
    });

    await page.evaluate(() => (window as any).noteWasDeleted());
    await page.evaluate(() => (globalThis as any).anki.onOperationDidExecute({ noteText: true }));
    // give a wrongly scheduled reload time to start
    await page.waitForTimeout(100);

    expect(requests).toEqual([]);
});

test("another note can be loaded after a deletion", async ({ editor: page }) => {
    const doomed = await addNote(page, "doomed");
    const survivor = await addNote(page, "survivor");
    await openInBrowserEditor(page, doomed);

    await page.evaluate(() => (window as any).noteWasDeleted());
    await page.evaluate(
        (args) => (window as any).loadNote({ ...args, initial: true }),
        { nid: survivor.noteId, notetypeId: survivor.notetypeId },
    );

    await expect(editableField(page, 0)).toHaveText("survivor");
});
