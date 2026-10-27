<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import * as tr from "@generated/ftl";
    import { getRange, getSelection } from "@tslib/cross-browser";
    import { getListItem } from "@tslib/dom";
    import { preventDefault } from "@tslib/events";
    import { getPlatformString, registerShortcut } from "@tslib/shortcuts";
    import { onMount } from "svelte";

    import ButtonGroup from "$lib/components/ButtonGroup.svelte";
    import ButtonGroupItem, {
        createProps,
        setSlotHostContext,
        updatePropsList,
    } from "$lib/components/ButtonGroupItem.svelte";
    import ButtonToolbar from "$lib/components/ButtonToolbar.svelte";
    import DynamicallySlottable from "$lib/components/DynamicallySlottable.svelte";
    import Icon from "$lib/components/Icon.svelte";
    import IconButton from "$lib/components/IconButton.svelte";
    import {
        indentIcon,
        justifyCenterIcon,
        justifyFullIcon,
        justifyLeftIcon,
        justifyRightIcon,
        listOptionsIcon,
        olIcon,
        outdentIcon,
        ulIcon,
    } from "$lib/components/icons";
    import Popover from "$lib/components/Popover.svelte";
    import WithFloating from "$lib/components/WithFloating.svelte";
    import { execCommand, removeEmptyLists, unwrapListItemBlocks } from "$lib/domlib";

    import { context } from "../NoteEditor.svelte";
    import { editingInputIsRichText } from "../rich-text-input";
    import CommandIconButton from "./CommandIconButton.svelte";

    export let api = {};

    // outside of lists, Chromium indents by wrapping the paragraph in a
    // margin-only <blockquote>, and outdent unwraps it again
    function changeIndent(command: "indent" | "outdent"): void {
        const root = document.activeElement?.shadowRoot;
        const selection = root && getSelection(root);
        const range = selection && getRange(selection);
        if (root && range) {
            // Chromium would indent a list item that wraps its content in a
            // <div> into a <blockquote> instead of nesting a list
            unwrapListItemBlocks(range, root);
            selection.removeAllRanges();
            selection.addRange(range);
        }
        execCommand(command);
        if (root) {
            removeEmptyLists(root);
        }
    }

    const outdentKeyCombination = "Control+Shift+M";
    function outdent() {
        changeIndent("outdent");
    }

    const indentKeyCombination = "Control+M";
    function indent() {
        changeIndent("indent");
    }

    onMount(() => {
        registerShortcut(onIndentKey, indentKeyCombination);
        registerShortcut((event: KeyboardEvent) => {
            if (disabled) {
                return;
            }
            preventDefault(event);
            outdent();
        }, outdentKeyCombination);
        // inside a list, Tab/Shift+Tab change the indentation; elsewhere they
        // keep moving between fields
        registerShortcut(indentWithTab("indent"), "Tab");
        registerShortcut(indentWithTab("outdent"), "Shift+Tab");
        registerShortcut((event: KeyboardEvent) => {
            if (disabled) {
                return;
            }
            preventDefault(event);
            execCommand("insertUnorderedList");
        }, "Control+Shift+L");
    });

    function onIndentKey(event: KeyboardEvent): void {
        if (disabled) {
            return;
        }
        preventDefault(event);
        indent();
    }

    function indentWithTab(command: "indent" | "outdent") {
        return (event: KeyboardEvent): void => {
            const root = document.activeElement?.shadowRoot;
            if (disabled || !root || !getListItem(root)) {
                return;
            }
            preventDefault(event);
            changeIndent(command);
        };
    }

    const { focusedInput } = context.get();

    $: disabled = !$focusedInput || !editingInputIsRichText($focusedInput);

    let showFloating = false;
    $: if (disabled) {
        showFloating = false;
    }

    const rtl = window.getComputedStyle(document.body).direction === "rtl";

    const justificationKeys = [
        "justifyLeft",
        "justifyCenter",
        "justifyRight",
        "justifyFull",
    ];

    const listKeys = ["insertUnorderedList", "insertOrderedList"];
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
            <CommandIconButton
                key="insertUnorderedList"
                tooltip={tr.editingUnorderedList()}
                shortcut="Control+,"
                modeVariantKeys={listKeys}
            >
                <Icon icon={ulIcon} />
            </CommandIconButton>
        </ButtonGroupItem>

        <ButtonGroupItem>
            <CommandIconButton
                key="insertOrderedList"
                tooltip={tr.editingOrderedList()}
                shortcut="Control+."
                modeVariantKeys={listKeys}
            >
                <Icon icon={olIcon} />
            </CommandIconButton>
        </ButtonGroupItem>

        <ButtonGroupItem>
            <WithFloating
                show={showFloating}
                inline
                on:close={() => (showFloating = false)}
                let:asReference
            >
                <span class="block-buttons" use:asReference>
                    <IconButton
                        tooltip={tr.editingAlignment()}
                        {disabled}
                        on:click={() => (showFloating = !showFloating)}
                    >
                        <Icon icon={listOptionsIcon} />
                    </IconButton>
                </span>

                <Popover slot="floating" --popover-padding-inline="0">
                    <ButtonToolbar wrap={false}>
                        <ButtonGroup>
                            <DynamicallySlottable
                                slotHost={ButtonGroupItem}
                                {createProps}
                                {updatePropsList}
                                {setSlotHostContext}
                                {api}
                            >
                                <ButtonGroupItem>
                                    <CommandIconButton
                                        key="justifyLeft"
                                        tooltip={tr.editingAlignLeft()}
                                        modeVariantKeys={justificationKeys}
                                    >
                                        <Icon icon={justifyLeftIcon} />
                                    </CommandIconButton>
                                </ButtonGroupItem>

                                <ButtonGroupItem>
                                    <CommandIconButton
                                        key="justifyCenter"
                                        tooltip={tr.editingCenter()}
                                        modeVariantKeys={justificationKeys}
                                    >
                                        <Icon icon={justifyCenterIcon} />
                                    </CommandIconButton>
                                </ButtonGroupItem>

                                <ButtonGroupItem>
                                    <CommandIconButton
                                        key="justifyRight"
                                        tooltip={tr.editingAlignRight()}
                                        modeVariantKeys={justificationKeys}
                                    >
                                        <Icon icon={justifyRightIcon} />
                                    </CommandIconButton>
                                </ButtonGroupItem>

                                <ButtonGroupItem>
                                    <CommandIconButton
                                        key="justifyFull"
                                        tooltip={tr.editingJustify()}
                                        modeVariantKeys={justificationKeys}
                                    >
                                        <Icon icon={justifyFullIcon} />
                                    </CommandIconButton>
                                </ButtonGroupItem>
                            </DynamicallySlottable>
                        </ButtonGroup>

                        <ButtonGroup>
                            <IconButton
                                tooltip="{tr.editingOutdent()} ({getPlatformString(
                                    outdentKeyCombination,
                                )})"
                                {disabled}
                                flipX={rtl}
                                on:click={outdent}
                                --border-left-radius="5px"
                                --border-right-radius="0px"
                            >
                                <Icon icon={outdentIcon} />
                            </IconButton>

                            <IconButton
                                tooltip="{tr.editingIndent()} ({getPlatformString(
                                    indentKeyCombination,
                                )})"
                                {disabled}
                                flipX={rtl}
                                on:click={indent}
                                --border-right-radius="5px"
                            >
                                <Icon icon={indentIcon} />
                            </IconButton>
                        </ButtonGroup>
                    </ButtonToolbar>
                </Popover>
            </WithFloating>
        </ButtonGroupItem>
    </DynamicallySlottable>
</ButtonGroup>

<style lang="scss">
    .block-buttons {
        line-height: 1;
    }
</style>
