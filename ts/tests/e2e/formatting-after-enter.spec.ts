// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Formatting carried over to a new line (content-editable.ts
 * keepFormatAfterLineBreak, surround.ts)
 *
 * Pressing Enter at the end of formatted text puts the line break inside the
 * formatting element but the caret after it. Text typed on the new line must
 * keep the formatting, and the toolbar must show it as active.
 */

import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { editableField } from "./helpers";

// like a person typing; with no delay at all, the selectionchange of a typed
// character can cancel a format toggled right after it
const delay = 30;

function button(page: Page, name: string) {
    return page.locator(`button[title^="${name}"]`);
}

test("bold switched on and typed is kept after Enter", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press("ControlOrMeta+B");
    await page.keyboard.type("ab", { delay });
    await page.keyboard.press("Enter");

    await expect(button(page, "Bold")).toHaveClass(/active/);
    await page.keyboard.type("c", { delay });
    await expect(field.locator("b")).toHaveText(["abc"]);
});

test("bold and italic are both kept after Enter", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press("ControlOrMeta+B");
    await page.keyboard.press("ControlOrMeta+I");
    await page.keyboard.type("ab", { delay });
    await page.keyboard.press("Enter");

    await expect(button(page, "Bold")).toHaveClass(/active/);
    await expect(button(page, "Italic")).toHaveClass(/active/);
    await page.keyboard.type("c", { delay });
    await expect(field.locator("b").filter({ hasText: "c" })).toHaveCount(1);
    await expect(field.locator("i").filter({ hasText: "c" })).toHaveCount(1);
});

test("Enter over a bold selection shows bold as active", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.type("ab", { delay });
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.press("ControlOrMeta+B");
    await page.keyboard.press("Enter");

    await expect(button(page, "Bold")).toHaveClass(/active/);
    await page.keyboard.type("c", { delay });
    await expect(field.locator("b")).toHaveText("c");
});

test("bold can be turned off right after Enter", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press("ControlOrMeta+B");
    await page.keyboard.type("ab", { delay });
    await page.keyboard.press("Enter");
    await page.keyboard.press("ControlOrMeta+B");

    await expect(button(page, "Bold")).not.toHaveClass(/active/);
    await page.keyboard.type("c", { delay });
    await expect(field.locator("b")).toHaveText(["ab"]);
    await expect(field).toHaveText("abc");
});

test("bold can still be turned off while typing", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.type("x ", { delay });
    await page.keyboard.press("ControlOrMeta+B");
    await page.keyboard.type("ab", { delay });
    await page.waitForTimeout(delay);
    await page.keyboard.press("ControlOrMeta+B");
    await page.keyboard.type(" y", { delay });

    await expect(field.locator("b")).toHaveText("ab");
});

test("formatting from inline styles is kept after Enter", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await field.evaluate((el) => {
        el.innerHTML = "<span style=\"font-weight: bold; text-decoration: underline\">ab</span><br>";
        const text = el.querySelector("span")!.firstChild!;
        (el.getRootNode() as Document).getSelection()!.collapse(text, 2);
    });
    await page.keyboard.press("Enter");

    await expect(button(page, "Bold")).toHaveClass(/active/);
    await expect(button(page, "Underline")).toHaveClass(/active/);
    await page.keyboard.type("c", { delay });
    const typed = field.getByText("c", { exact: true });
    await expect(typed).toHaveCSS("font-weight", "700");
    await expect(typed).toHaveCSS("text-decoration-line", "underline");
});
