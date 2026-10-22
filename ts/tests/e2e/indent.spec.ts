// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Indent/outdent shortcuts (BlockButtons.svelte)
 *
 * Inside lists they nest/unnest list items; elsewhere they indent the current
 * paragraph. Tab/Shift+Tab only change the indentation inside lists, and
 * otherwise keep moving focus between fields.
 */

import { expect, test } from "./fixtures";
import { editableField } from "./helpers";

const INDENT = "ControlOrMeta+M";
const OUTDENT = "ControlOrMeta+Shift+M";

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

test("typing right after indenting does not trigger the MathJax chord", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press(INDENT);
    await page.keyboard.type("mec");

    await expect(field.locator("blockquote")).toHaveText("mec");
    await expect(field.locator("anki-mathjax")).toHaveCount(0);
});

test("MathJax chord uses Ctrl+Alt+M", async ({ editor: page }) => {
    const field = editableField(page, 0);
    await field.click();
    await page.keyboard.press("ControlOrMeta+Alt+M");
    await page.keyboard.press("M");

    await expect(field.locator("anki-mathjax")).toHaveCount(1);
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

test("Tab and Shift+Tab outside a list move between fields", async ({ editor: page }) => {
    const first = editableField(page, 0);
    const second = editableField(page, 1);
    await first.click();
    await page.keyboard.type("hello");

    await page.keyboard.press("Tab");
    await expect(second).toBeFocused();
    await expect(first.locator("blockquote")).toHaveCount(0);

    await page.keyboard.press("Shift+Tab");
    await expect(first).toBeFocused();
    await expect(first).toHaveText("hello");
});

test("Shift+Tab in an indented paragraph moves to the previous field", async ({ editor: page }) => {
    const first = editableField(page, 0);
    const second = editableField(page, 1);
    await second.click();
    await page.keyboard.type("hello");
    await page.keyboard.press(INDENT);

    await page.keyboard.press("Shift+Tab");
    await expect(first).toBeFocused();
    await expect(second.locator("blockquote")).toHaveText("hello");
});
