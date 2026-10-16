// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { getSelection } from "@tslib/cross-browser";

function placeCaret(node: Node, range: Range): void {
    const selection = getSelection(node)!;
    selection.removeAllRanges();
    selection.addRange(range);
}

export function placeCaretBefore(node: Node): void {
    const range = new Range();
    range.setStartBefore(node);
    range.collapse(true);

    placeCaret(node, range);
}

export function placeCaretAfter(node: Node): void {
    const range = new Range();
    range.setStartAfter(node);
    range.collapse(true);

    placeCaret(node, range);
}

export function placeCaretAfterContent(node: Node): void {
    const range = new Range();
    range.selectNodeContents(node);
    range.collapse(false);

    placeCaret(node, range);
}

/**
 * Places the caret after the `offset`-th character of the text inside `root`.
 */
export function placeCaretAtTextOffset(root: Node, offset: number): void {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let remaining = offset;
    let node: Node | null;

    while ((node = walker.nextNode())) {
        const length = node.textContent?.length ?? 0;
        if (remaining <= length) {
            const range = new Range();
            range.setStart(node, remaining);
            range.collapse(true);
            placeCaret(root, range);
            return;
        }
        remaining -= length;
    }

    placeCaretAfterContent(root);
}
