// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** Changes closer together than this are merged into one undo step */
const MERGE_INTERVAL_MS = 1000;
/** A merged undo step never spans more than this */
const MAX_MERGE_SPAN_MS = 5000;
const MAX_STACK_SIZE = 200;

/**
 * Snapshot-based undo history for the content of a single field.
 * Consecutive changes made in quick succession (e.g. typing a word) are
 * merged into a single step.
 */
export class UndoStack {
    private stack: string[];
    private index = 0;
    private lastChange = -Infinity;
    private mergeStart = -Infinity;
    private mergeable = false;

    constructor(
        initial = "",
        private readonly now: () => number = Date.now,
    ) {
        this.stack = [initial];
    }

    get current(): string {
        return this.stack[this.index];
    }

    get canUndo(): boolean {
        return this.index > 0;
    }

    get canRedo(): boolean {
        return this.index < this.stack.length - 1;
    }

    /** Discards the history, e.g. when a different note is loaded. */
    reset(value: string): void {
        this.stack = [value];
        this.index = 0;
        this.breakMerge();
    }

    /**
     * Updates the current state without creating an undo step, e.g. for
     * changes that were not made by the user.
     */
    replaceCurrent(value: string): void {
        this.stack[this.index] = value;
    }

    /** Ensures the next change starts a new undo step. */
    breakMerge(): void {
        this.mergeable = false;
    }

    /** Records a user change. Returns whether the history changed. */
    record(value: string): boolean {
        if (value === this.current) {
            return false;
        }

        const now = this.now();
        const merge = this.mergeable
            && !this.canRedo
            && this.index > 0
            && now - this.lastChange < MERGE_INTERVAL_MS
            && now - this.mergeStart < MAX_MERGE_SPAN_MS;

        this.stack.length = this.index + 1;
        if (merge) {
            this.stack[this.index] = value;
        } else {
            this.stack.push(value);
            this.index++;
            this.mergeStart = now;
            if (this.stack.length > MAX_STACK_SIZE) {
                this.stack.shift();
                this.index--;
            }
        }

        this.lastChange = now;
        this.mergeable = true;
        return true;
    }

    /** Returns the restored content, or null if there is nothing to undo. */
    undo(): string | null {
        if (!this.canUndo) {
            return null;
        }
        this.index--;
        this.breakMerge();
        return this.current;
    }

    /** Returns the restored content, or null if there is nothing to redo. */
    redo(): string | null {
        if (!this.canRedo) {
            return null;
        }
        this.index++;
        this.breakMerge();
        return this.current;
    }
}

/**
 * Where to put the caret after the text changed from `before` to `after`:
 * at the end of the part that differs.
 */
export function caretOffsetAfterChange(before: string, after: string): number {
    const maxCommon = Math.min(before.length, after.length);
    let prefix = 0;
    while (prefix < maxCommon && before[prefix] === after[prefix]) {
        prefix++;
    }
    let suffix = 0;
    while (
        suffix < maxCommon - prefix
        && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
    ) {
        suffix++;
    }
    return after.length - suffix;
}
