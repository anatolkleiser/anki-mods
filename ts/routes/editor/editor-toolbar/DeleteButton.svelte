<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import * as tr from "@generated/ftl";
    import { bridgeCommand } from "@tslib/bridgecommand";
    import { getPlatformString } from "@tslib/shortcuts";

    import ButtonGroup from "$lib/components/ButtonGroup.svelte";
    import ButtonGroupItem, {
        createProps,
        setSlotHostContext,
        updatePropsList,
    } from "$lib/components/ButtonGroupItem.svelte";
    import DynamicallySlottable from "$lib/components/DynamicallySlottable.svelte";
    import Icon from "$lib/components/Icon.svelte";
    import IconButton from "$lib/components/IconButton.svelte";
    import { mdiDeleteOutline } from "$lib/components/icons";

    export let api = {};

    // the shortcut itself is registered by the browser window
    const keyCombination = "Control+Shift+Backspace";
</script>

<ButtonGroup>
    <DynamicallySlottable
        slotHost={ButtonGroupItem}
        {createProps}
        {updatePropsList}
        {setSlotHostContext}
        {api}
    >
        <ButtonGroupItem>
            <IconButton
                tooltip="{tr.actionsDelete()} ({getPlatformString(keyCombination)})"
                iconSize={70}
                on:click={() => bridgeCommand("delete_note")}
            >
                <Icon icon={mdiDeleteOutline} />
            </IconButton>
        </ButtonGroupItem>
    </DynamicallySlottable>
</ButtonGroup>
