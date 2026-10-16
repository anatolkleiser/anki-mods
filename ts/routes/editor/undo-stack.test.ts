// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, test } from "vitest";

import { caretOffsetAfterChange, UndoStack } from "./undo-stack";

function stackWithClock(initial = ""): [UndoStack, (ms: number) => void] {
    let time = 0;
    const stack = new UndoStack(initial, () => time);
    return [stack, (ms: number) => (time += ms)];
}

describe("UndoStack", () => {
    test("undo and redo walk through separate changes", () => {
        const [stack, advance] = stackWithClock("a");
        stack.record("ab");
        advance(2000);
        stack.record("abc");

        expect(stack.undo()).toBe("ab");
        expect(stack.undo()).toBe("a");
        expect(stack.undo()).toBeNull();
        expect(stack.redo()).toBe("ab");
        expect(stack.redo()).toBe("abc");
        expect(stack.redo()).toBeNull();
    });

    test("quick successive changes are undone as one step", () => {
        const [stack, advance] = stackWithClock("");
        for (const text of ["h", "he", "hel", "hell", "hello"]) {
            stack.record(text);
            advance(100);
        }

        expect(stack.undo()).toBe("");
        expect(stack.canUndo).toBe(false);
    });

    test("a long burst of typing is split into several steps", () => {
        const [stack, advance] = stackWithClock("");
        let text = "";
        for (let i = 0; i < 70; i++) {
            text += "x";
            stack.record(text);
            advance(100);
        }

        expect(stack.undo()!.length).toBeGreaterThan(0);
    });

    test("a change after undo discards the redo history", () => {
        const [stack] = stackWithClock("a");
        stack.record("ab");
        stack.undo();
        stack.record("ac");

        expect(stack.canRedo).toBe(false);
        expect(stack.undo()).toBe("a");
    });

    test("a change right after undo is not merged into the restored step", () => {
        const [stack, advance] = stackWithClock("a");
        stack.record("ab");
        advance(2000);
        stack.record("abc");
        stack.undo();
        stack.record("abd");

        expect(stack.undo()).toBe("ab");
    });

    test("recording unchanged content does not add a step", () => {
        const [stack] = stackWithClock("a");

        expect(stack.record("a")).toBe(false);
        expect(stack.canUndo).toBe(false);
    });

    test("reset discards the history", () => {
        const [stack] = stackWithClock("a");
        stack.record("ab");
        stack.reset("other note");

        expect(stack.canUndo).toBe(false);
        expect(stack.current).toBe("other note");
    });

    test("replaceCurrent updates the state without adding a step", () => {
        const [stack] = stackWithClock("a");
        stack.record("<b>a</b>");
        stack.replaceCurrent("<b>a</b><br>");

        expect(stack.undo()).toBe("a");
        expect(stack.redo()).toBe("<b>a</b><br>");
    });

    test("the oldest steps are dropped beyond the limit", () => {
        const [stack, advance] = stackWithClock("0");
        for (let i = 1; i <= 250; i++) {
            stack.record(String(i));
            advance(2000);
        }
        let last: string | null = null;
        while (stack.canUndo) {
            last = stack.undo();
        }

        expect(last).toBe("51");
    });
});

describe("caretOffsetAfterChange", () => {
    test.each([
        ["undoing an insertion puts the caret where it was", "hello world", "hello", 5],
        ["redoing an insertion puts the caret after it", "hello", "hello world", 11],
        ["a replacement puts the caret after the new text", "a cat sat", "a dog sat", 5],
        ["a change at the start", "xabc", "abc", 0],
        ["identical text puts the caret at the end", "abc", "abc", 3],
        ["repeated characters", "aaa", "aaaa", 4],
    ])("%s", (_, before, after, expected) => {
        expect(caretOffsetAfterChange(before, after)).toBe(expected);
    });
});
