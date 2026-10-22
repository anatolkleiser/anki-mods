// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { bridgeCommand } from "@tslib/bridgecommand";
import { getRange, getSelection } from "@tslib/cross-browser";
import { elementIsBlock, nodeIsElement } from "@tslib/dom";
import { on, preventDefault } from "@tslib/events";
import { isApplePlatform } from "@tslib/platform";
import { registerShortcut, registerUnmappedShortcut } from "@tslib/shortcuts";
import type { Callback } from "@tslib/typing";

import { execCommand, queryCommandState } from "$lib/domlib/content-editable";
import type { SelectionLocation } from "$lib/domlib/location";
import { restoreSelection, saveSelection } from "$lib/domlib/location";
import { placeCaretAfterContent } from "$lib/domlib/place-caret";
import { HandlerList } from "$lib/sveltelib/handler-list";

/**
 * Workaround: If you try to invoke an IME after calling
 * `placeCaretAfterContent` on a cE element, the IME will immediately
 * end and the input character will be duplicated
 */
function safePlaceCaretAfterContent(editable: HTMLElement): void {
    placeCaretAfterContent(editable);
    restoreSelection(editable, saveSelection(editable)!);
}

function restoreCaret(element: HTMLElement, location: SelectionLocation | null): void {
    if (!location) {
        return safePlaceCaretAfterContent(element);
    }

    try {
        restoreSelection(element, location);
    } catch {
        safePlaceCaretAfterContent(element);
    }
}

type SetupFocusHandlerAction = (element: HTMLElement) => { destroy(): void };

export interface FocusHandlerAPI {
    /**
     * Prevent the automatic caret restoration, that happens upon field focus
     */
    flushCaret(): void;
    /**
     * Executed upon focus event of editable.
     */
    focus: HandlerList<{ event: FocusEvent }>;
    /**
     * Executed upon blur event of editable.
     */
    blur: HandlerList<{ event: FocusEvent }>;
}

export function useFocusHandler(): [FocusHandlerAPI, SetupFocusHandlerAction] {
    let latestLocation: SelectionLocation | null = null;
    let offFocus: Callback | null;
    let offPointerDown: Callback | null;
    let flush = false;

    function flushCaret(): void {
        flush = true;
    }

    const focus = new HandlerList<{ event: FocusEvent }>();
    const blur = new HandlerList<{ event: FocusEvent }>();

    function prepareFocusHandling(
        editable: HTMLElement,
        location: SelectionLocation | null = null,
    ): void {
        latestLocation = location;

        offFocus?.();
        offFocus = on(
            editable,
            "focus",
            (event: FocusEvent): void => {
                if (flush) {
                    flush = false;
                } else {
                    restoreCaret(event.currentTarget as HTMLElement, latestLocation);
                }

                focus.dispatch({ event });
            },
            { once: true },
        );

        offPointerDown?.();
        offPointerDown = on(
            editable,
            "pointerdown",
            () => {
                offFocus?.();
                offFocus = null;
            },
            { once: true },
        );
    }

    /**
     * Must execute before DOMMirror.
     */
    function onBlur(this: HTMLElement, event: FocusEvent): void {
        prepareFocusHandling(this, saveSelection(this));
        blur.dispatch({ event });
    }

    function setupFocusHandler(editable: HTMLElement): { destroy(): void } {
        prepareFocusHandling(editable);
        const off = on(editable, "blur", onBlur);

        return {
            destroy() {
                off();
                offFocus?.();
                offPointerDown?.();
            },
        };
    }

    return [
        {
            flushCaret,
            focus,
            blur,
        },
        setupFocusHandler,
    ];
}

if (isApplePlatform()) {
    registerShortcut(() => bridgeCommand("paste"), "Control+Shift+V");
}

/** The formatting of element that Chromium can apply as typing style */
function typingStyleCommands(element: Element): string[] {
    const style = getComputedStyle(element);
    const commands: string[] = [];
    if (Number(style.fontWeight) >= 600) {
        commands.push("bold");
    }
    if (style.fontStyle === "italic" || style.fontStyle === "oblique") {
        commands.push("italic");
    }
    // text decoration and vertical alignment are not inherited
    if (style.textDecorationLine.includes("underline")) {
        commands.push("underline");
    }
    if (style.textDecorationLine.includes("line-through")) {
        commands.push("strikethrough");
    }
    if (style.verticalAlign === "sub") {
        commands.push("subscript");
    } else if (style.verticalAlign === "super") {
        commands.push("superscript");
    }
    return commands;
}

function isInlineContainer(node: Node | null): node is Element {
    return Boolean(
        node
            && nodeIsElement(node)
            && node.tagName !== "BR"
            && node.hasChildNodes()
            && !elementIsBlock(node),
    );
}

/**
 * When Enter is pressed at the end of formatted text, Chromium puts the line
 * break inside the formatting elements (e.g. <b>text<br></b>), but the caret
 * after them, and it can't be moved back inside. Whether typed text is still
 * formatted then depends on whether Chromium remembered the formatting, so
 * make sure it does.
 */
export function keepFormatAfterLineBreak(editable: HTMLElement): { destroy(): void } {
    function onInput(event: Event): void {
        const { inputType } = event as InputEvent;
        if (inputType !== "insertLineBreak" && inputType !== "insertParagraph") {
            return;
        }
        const selection = getSelection(editable);
        // selection.isCollapsed is unreliable in shadow roots
        const range = selection && getRange(selection);
        if (!range?.collapsed || !nodeIsElement(range.startContainer)) {
            return;
        }
        const commands = new Set<string>();
        let element: Node | null = range.startContainer.childNodes[range.startOffset - 1] ?? null;
        while (isInlineContainer(element)) {
            typingStyleCommands(element).forEach((command) => commands.add(command));
            const last = element.lastChild;
            if (last && nodeIsElement(last) && last.tagName === "BR") {
                for (const command of commands) {
                    if (!queryCommandState(command)) {
                        execCommand(command);
                    }
                }
                return;
            }
            element = last;
        }
    }

    return { destroy: on(editable, "input", onInput) };
}

export function preventBuiltinShortcuts(editable: HTMLElement): void {
    for (const keyCombination of ["Control+B", "Control+U", "Control+I"]) {
        // block Chromium's built-in formatting even if the toolbar buttons
        // were given different shortcuts
        registerUnmappedShortcut(preventDefault, keyCombination, { target: editable });
    }
}

declare global {
    interface Selection {
        modify(s: string, t: string, u: string): void;
    }
}

// Fix inverted Ctrl+right/left handling in RTL fields
export function fixRTLKeyboardNav(editable: HTMLElement): void {
    editable.addEventListener("keydown", (evt: KeyboardEvent) => {
        if (window.getComputedStyle(editable).direction === "rtl") {
            const selection = getSelection(editable)!;
            let granularity = "character";
            let alter = "move";
            if (evt.ctrlKey) {
                granularity = "word";
            }
            if (evt.shiftKey) {
                alter = "extend";
            }
            if (evt.code === "ArrowRight") {
                selection.modify(alter, "right", granularity);
                evt.preventDefault();
                return;
            } else if (evt.code === "ArrowLeft") {
                selection.modify(alter, "left", granularity);
                evt.preventDefault();
                return;
            }
        }
    });
}

/** API */

export interface ContentEditableAPI {
    /**
     * Can be used to turn off the caret restoring functionality of
     * the ContentEditable. Can be used when you want to set the caret
     * yourself.
     */
    focusHandler: FocusHandlerAPI;
}
