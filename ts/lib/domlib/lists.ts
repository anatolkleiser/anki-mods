// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { nodeIsElement } from "@tslib/dom";

/**
 * Chromium's indent/outdent commands only nest or unnest a list item when
 * the block around the caret is the <li> itself. A list item that wraps its
 * content in a <div>, as pasted content often does, is instead indented into
 * a margin-only <blockquote> inside the item.
 *
 * Unwraps such sole <div> wrappers from the list items the range touches, so
 * the commands nest a real list. The range is moved along with the unwrapped
 * content, as a live range would otherwise collapse to the start of the item.
 */
export function unwrapListItemBlocks(range: Range, root: ParentNode): void {
    const start = { node: range.startContainer, offset: range.startOffset };
    const end = { node: range.endContainer, offset: range.endOffset };

    // unwrapping moves the live range, so pick the items first
    const listItems = [...root.querySelectorAll("li")].filter((listItem) => range.intersectsNode(listItem));

    for (const listItem of listItems) {
        let wrapper = soleBlockWrapper(listItem);
        while (wrapper) {
            for (const boundary of [start, end]) {
                if (boundary.node === wrapper) {
                    // the wrapper is the item's only child, so offsets carry over
                    boundary.node = listItem;
                }
            }
            wrapper.replaceWith(...wrapper.childNodes);
            wrapper = soleBlockWrapper(listItem);
        }
    }

    range.setStart(start.node, start.offset);
    range.setEnd(end.node, end.offset);
}

function soleBlockWrapper(listItem: HTMLLIElement): HTMLDivElement | null {
    const only = listItem.childNodes.length === 1 ? listItem.firstChild : null;
    if (only && nodeIsElement(only) && only.tagName === "DIV" && only.attributes.length === 0) {
        return only as HTMLDivElement;
    }
    return null;
}

/**
 * Deleting a nested list item leaves the lists that wrapped it behind.
 * Removes lists that contain no items and no text, innermost first.
 */
export function removeEmptyLists(root: ParentNode): void {
    const lists = [...root.querySelectorAll("ul, ol")].reverse();
    for (const list of lists) {
        if (!list.querySelector("li") && !list.textContent?.trim()) {
            list.remove();
        }
    }
}
