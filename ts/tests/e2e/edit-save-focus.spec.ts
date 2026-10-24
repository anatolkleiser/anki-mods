// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * When editing an existing note, the editor saves each field after a short
 * pause in typing. Qt then reports that save back to the editor webview as an
 * operation that changed note text (webview.py on_operation_did_execute). The
 * editor must recognise its own save there, rather than reloading the note and
 * moving focus to the field it was originally opened with.
 */

import { Empty } from "@generated/anki/generic_pb";
import { AddNoteRequest, AddNoteResponse, Note, NoteId, UpdateNotesRequest } from "@generated/anki/notes_pb";
import { NotetypeId, NotetypeNames } from "@generated/anki/notetypes_pb";

import { expect, test } from "./fixtures";
import { callRpc, editableField, isRpcResponse } from "./helpers";

async function addBasicNote(page): Promise<{ nid: bigint; ntid: bigint }> {
    const names = NotetypeNames.fromBinary(
        await callRpc(page, "getNotetypeNames", new Empty()),
    );
    const ntid = names.entries.find((entry) => entry.name === "Basic")?.id;
    if (ntid === undefined) {
        throw new Error("Expected stock Basic notetype in e2e profile");
    }
    const note = Note.fromBinary(
        await callRpc(page, "newNote", new NotetypeId({ ntid })),
    );
    note.fields = ["front", ""];
    const response = AddNoteResponse.fromBinary(
        await callRpc(page, "addNote", new AddNoteRequest({ note, deckId: 1n })),
    );
    return { nid: response.noteId, ntid };
}

async function openInEditCurrent(page): Promise<bigint> {
    await page.addInitScript(() => {
        (window as any).bridgeCommand = (): void => {
            // there is no Qt side to receive bridge commands
        };
    });
    // EditCurrent (editcurrent.py) opens the editor focused on the first field.
    await page.goto("/editor/?mode=current", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => typeof (window as any).loadNote === "function", {
        timeout: 15_000,
    });
    const { nid, ntid } = await addBasicNote(page);
    await page.evaluate(
        ({ nid, ntid }) =>
            (window as any).loadNote({
                nid: BigInt(nid),
                notetypeId: BigInt(ntid),
                focusTo: 0,
                initial: true,
            }),
        { nid: nid.toString(), ntid: ntid.toString() },
    );
    return nid;
}

/** What Qt evaluates in the webview once an operation has changed note text. */
async function reportNoteTextChange(page): Promise<void> {
    await page.evaluate(() => (globalThis as any).anki.onOperationDidExecute({ noteText: true }));
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)));
}

test("saving a field keeps focus and caret in that field", async ({ page }) => {
    await openInEditCurrent(page);

    const back = editableField(page, 1);
    await back.click();
    const saved = page.waitForResponse(isRpcResponse("updateNotes"), { timeout: 10_000 });
    await page.keyboard.type("world");
    // put the caret before "world" ("Home" does nothing on macOS)
    for (let i = 0; i < "world".length; i++) {
        await page.keyboard.press("ArrowLeft");
    }
    await saved;
    await reportNoteTextChange(page);

    await page.keyboard.type("hello ");
    await expect(back).toHaveText("hello world");
    await expect(editableField(page, 0)).toHaveText("front");
});

test("a change made elsewhere is still loaded", async ({ page }) => {
    const nid = await openInEditCurrent(page);
    await expect(editableField(page, 0)).toHaveText("front");

    const note = Note.fromBinary(await callRpc(page, "getNote", new NoteId({ nid })));
    // change a field other than the focused one
    note.fields = ["front", "changed elsewhere"];
    await callRpc(page, "updateNotes", new UpdateNotesRequest({ notes: [note] }));
    await reportNoteTextChange(page);

    await expect(editableField(page, 1)).toHaveText("changed elsewhere");
});
