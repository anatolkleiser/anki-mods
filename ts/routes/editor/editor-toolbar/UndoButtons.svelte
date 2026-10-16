<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import * as tr from "@generated/ftl";
    import { getPlatformString } from "@tslib/shortcuts";

    import ButtonGroup from "$lib/components/ButtonGroup.svelte";
    import Icon from "$lib/components/Icon.svelte";
    import IconButton from "$lib/components/IconButton.svelte";
    import { mdiRedo, mdiUndo } from "$lib/components/icons";
    import Shortcut from "$lib/components/Shortcut.svelte";

    import { context } from "../NoteEditor.svelte";

    const undoKeyCombination = "Control+Z";
    const redoKeyCombination = "Control+Shift+Z";
    const alternativeRedoKeyCombination = "Control+Y";

    const { fieldUndo, focusedInput } = context.get();
</script>

<ButtonGroup>
    <IconButton
        tooltip="{tr.undoUndo()} ({getPlatformString(undoKeyCombination)})"
        disabled={!$fieldUndo.undoable}
        on:click={fieldUndo.undo}
        --border-left-radius="5px"
    >
        <Icon icon={mdiUndo} />
    </IconButton>

    <IconButton
        tooltip="{tr.undoRedo()} ({getPlatformString(redoKeyCombination)})"
        disabled={!$fieldUndo.redoable}
        on:click={fieldUndo.redo}
        --border-right-radius="5px"
    >
        <Icon icon={mdiRedo} />
    </IconButton>
</ButtonGroup>

<!-- outside of fields, e.g. in the tag editor, the browser's undo applies -->
{#if $focusedInput}
    <Shortcut keyCombination={undoKeyCombination} on:action={fieldUndo.undo} />
    <Shortcut keyCombination={redoKeyCombination} on:action={fieldUndo.redo} />
    <Shortcut
        keyCombination={alternativeRedoKeyCombination}
        on:action={fieldUndo.redo}
    />
{/if}
