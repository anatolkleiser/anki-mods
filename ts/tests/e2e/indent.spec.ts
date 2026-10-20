// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Indent/outdent shortcuts (BlockButtons.svelte)
 *
 * Inside lists they nest/unnest list items; elsewhere they indent the current
 * paragraph. Tab always indents; Shift+Tab outdents when there is something to
 * outdent, and otherwise moves focus to the previous field.
 */

import { expect, test } from "./fixtures";
import { editableField } from "./helpers";

const INDENT = "ControlOrMeta+Shift+Period";
const OUTDENT = "ControlOrMeta+Shift+Comma";

test("indent and outdent work on plain text", async ({ editor: page }) => {
    let dialogShown = false;
    page.on("dialog", (dialog) => {
        dialogShown = true;
        void dialog.dismiss();
    });

    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.type("hello");

    await page.keyboard.press(INDENT);
    const blockquote = field.locator("blockquote");
    await expect(blockquote).toHaveText("hello");
    await expect(blockquote).toHaveCSS("margin-left", "40px");

    // typing continues inside the indented paragraph
    await page.keyboard.type("!");
    await expect(blockquote).toHaveText("hello!");

    await page.keyboard.press(OUTDENT);
    await expect(blockquote).toHaveCount(0);
    await expect(field).toHaveText("hello!");
    expect(dialogShown).toBe(false);
});

test("Tab and Shift+Tab nest and unnest list items", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press("ControlOrMeta+Shift+L");
    await page.keyboard.type("one");
    await page.keyboard.press("Enter");
    await page.keyboard.type("two");

    const nested = field.locator("ul ul > li");
    await page.keyboard.press("Tab");
    await expect(nested).toHaveText("two");
    // focus stays in the field
    await expect(field).toBeFocused();

    await page.keyboard.press("Shift+Tab");
    await expect(nested).toHaveCount(0);
    await expect(field.locator("ul > li")).toHaveText(["one", "two"]);
    await expect(field).toBeFocused();
});

test("Tab and Shift+Tab indent and outdent a paragraph", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.type("hello");

    const blockquote = field.locator("blockquote");
    await page.keyboard.press("Tab");
    await expect(blockquote).toHaveText("hello");
    await expect(field).toBeFocused();

    await page.keyboard.press("Shift+Tab");
    await expect(blockquote).toHaveCount(0);
    await expect(field).toHaveText("hello");
    await expect(field).toBeFocused();
});

test("Shift+Tab with nothing to outdent moves to the previous field", async ({ editor: page }) => {
    const first = editableField(page, 0);
    const second = editableField(page, 1);
    await second.click();
    await page.keyboard.type("hello");

    await page.keyboard.press("Shift+Tab");
    await expect(first).toBeFocused();
    await expect(second).toHaveText("hello");
});
