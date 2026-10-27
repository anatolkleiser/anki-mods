// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
// @vitest-environment jsdom

import { describe, expect, test } from "vitest";

import { removeEmptyLists, unwrapListItemBlocks } from "./lists";

function body(html: string): HTMLElement {
    const element = document.createElement("div");
    element.innerHTML = html;
    return element;
}

function caretAtEndOf(node: Node): Range {
    const range = new Range();
    range.selectNodeContents(node);
    range.collapse(false);
    return range;
}

describe("unwrapListItemBlocks", () => {
    test("a sole div wrapper is removed from the item with the caret", () => {
        const root = body("<ul><li><div>one</div></li><li><div>two</div></li></ul>");
        const range = caretAtEndOf(root.querySelector("li:last-child div")!);

        unwrapListItemBlocks(range, root);

        expect(root.innerHTML).toBe("<ul><li><div>one</div></li><li>two</li></ul>");
    });

    test("nested div wrappers are all removed", () => {
        const root = body("<ul><li><div><div>one</div></div></li></ul>");
        const range = caretAtEndOf(root.querySelector("li div div")!);

        unwrapListItemBlocks(range, root);

        expect(root.innerHTML).toBe("<ul><li>one</li></ul>");
    });

    test("every item the selection spans is unwrapped", () => {
        const root = body("<ul><li><div>one</div></li><li><div>two</div></li><li><div>three</div></li></ul>");
        const items = root.querySelectorAll("li");
        const range = new Range();
        range.setStart(items[0].querySelector("div")!.firstChild!, 1);
        range.setEnd(items[1].querySelector("div")!.firstChild!, 1);

        unwrapListItemBlocks(range, root);

        expect(root.innerHTML).toBe("<ul><li>one</li><li>two</li><li><div>three</div></li></ul>");
    });

    test("the caret stays in the unwrapped text", () => {
        const root = body("<ul><li><div>one</div></li></ul>");
        const text = root.querySelector("li div")!.firstChild!;
        const range = new Range();
        range.setStart(text, 2);
        range.collapse(true);

        unwrapListItemBlocks(range, root);

        expect(range.startContainer).toBe(text);
        expect(range.startOffset).toBe(2);
        expect(text.parentElement!.tagName).toBe("LI");
    });

    test("a caret placed on the wrapper itself moves to the item", () => {
        const root = body("<ul><li><div><br></div></li></ul>");
        const listItem = root.querySelector("li")!;
        const range = new Range();
        range.setStart(listItem.firstChild!, 0);
        range.collapse(true);

        unwrapListItemBlocks(range, root);

        expect(root.innerHTML).toBe("<ul><li><br></li></ul>");
        expect(range.startContainer).toBe(listItem);
        expect(range.startOffset).toBe(0);
    });

    test("an item with several lines is left alone", () => {
        const root = body("<ul><li><div>one</div><div>two</div></li></ul>");
        const range = caretAtEndOf(root.querySelector("li div")!);

        unwrapListItemBlocks(range, root);

        expect(root.innerHTML).toBe("<ul><li><div>one</div><div>two</div></li></ul>");
    });

    test("a div with attributes is left alone", () => {
        const root = body("<ul><li><div class=\"note\">one</div></li></ul>");
        const range = caretAtEndOf(root.querySelector("li div")!);

        unwrapListItemBlocks(range, root);

        expect(root.innerHTML).toBe("<ul><li><div class=\"note\">one</div></li></ul>");
    });
});

describe("removeEmptyLists", () => {
    test("nested lists without items are removed, including their wrapper", () => {
        const root = body("<ul><li>one</li></ul><div><ul><ul><ul></ul></ul></ul></div>");

        removeEmptyLists(root);

        expect(root.innerHTML).toBe("<ul><li>one</li></ul><div></div>");
    });

    test("empty lists nested inside a list with items are removed", () => {
        const root = body("<ul><li>one</li><ul><ul></ul></ul><li>two</li></ul>");

        removeEmptyLists(root);

        expect(root.innerHTML).toBe("<ul><li>one</li><li>two</li></ul>");
    });

    test("lists with an item, even an empty one, are kept", () => {
        const root = body("<ul><li>one</li><ul><li><br></li></ul></ul>");

        removeEmptyLists(root);

        expect(root.innerHTML).toBe("<ul><li>one</li><ul><li><br></li></ul></ul>");
    });

    test("lists holding text outside an item are kept", () => {
        const root = body("<ul>stray</ul>");

        removeEmptyLists(root);

        expect(root.innerHTML).toBe("<ul>stray</ul>");
    });
});
