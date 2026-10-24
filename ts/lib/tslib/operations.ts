// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { OpChanges } from "@generated/anki/collection_pb";

type OperationHandler = (changes: Partial<OpChanges>) => void | Promise<void>;
const handlers: OperationHandler[] = [];

export function registerOperationHandler(handler: OperationHandler): void {
    handlers.push(handler);
}

/** Resolves once every handler has finished reacting to the changes. */
async function onOperationDidExecute(changes: Partial<OpChanges>): Promise<void> {
    await Promise.all(handlers.map((handler) => handler(changes)));
}

globalThis.anki = globalThis.anki || {};
globalThis.anki.onOperationDidExecute = onOperationDidExecute;
