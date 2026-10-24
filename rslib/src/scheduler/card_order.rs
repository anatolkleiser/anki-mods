// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! A custom order for the cards of a deck, which the user arranges in the
//! browser. The order index lives in the card's custom data, and the deck's
//! switch in its unknown legacy keys, so both survive syncing through clients
//! that know nothing about this feature.

use std::collections::HashSet;

use itertools::Itertools;
use serde_json::Map;
use serde_json::Value;

use crate::prelude::*;

/// Key of the order index in a card's custom data.
const CARD_ORDER_KEY: &str = "oi";
/// Key of the switch in a deck's legacy JSON.
const DECK_CARD_ORDER_KEY: &str = "cardOrder";

/// Sorts cards by their order index. Cards without one go last, in the order
/// they were added.
pub(crate) const CARD_ORDER_SQL: &str =
    "coalesce(extract_card_order(c.data), 4294967295) asc, n.id asc, c.ord asc";

/// Reads the order index from a card's custom data JSON.
pub(crate) fn order_index_from_custom_data(custom_data: &str) -> Option<u32> {
    let object: Map<String, Value> = serde_json::from_str(custom_data).ok()?;
    object
        .get(CARD_ORDER_KEY)?
        .as_u64()
        .and_then(|index| u32::try_from(index).ok())
}

impl Card {
    pub(crate) fn order_index(&self) -> Option<u32> {
        order_index_from_custom_data(&self.custom_data)
    }

    fn set_order_index(&mut self, index: Option<u32>) -> Result<()> {
        let mut object: Map<String, Value> = if self.custom_data.is_empty() {
            Map::new()
        } else {
            serde_json::from_str(&self.custom_data).or_invalid("custom data not an object")?
        };
        match index {
            Some(index) => object.insert(CARD_ORDER_KEY.into(), index.into()),
            None => object.remove(CARD_ORDER_KEY),
        };
        self.custom_data = if object.is_empty() {
            String::new()
        } else {
            serde_json::to_string(&object)?
        };
        if self.validate_custom_data().is_err() {
            invalid_input!(
                "card {} has too much custom data to keep its place in the deck's order",
                self.id
            );
        }
        Ok(())
    }

    /// When a card moves to a deck outside its custom order, its index means
    /// nothing there, so it is removed, which puts the card at the end of the
    /// new deck's order.
    pub(crate) fn forget_order_index_unless_staying_in(
        &mut self,
        old_root: Option<DeckId>,
        new_root: Option<DeckId>,
    ) -> Result<()> {
        if self.order_index().is_some() && (old_root.is_none() || old_root != new_root) {
            self.set_order_index(None)?;
        }
        Ok(())
    }

    fn order_key(&self) -> (bool, Option<u32>, NoteId, u16) {
        let index = self.order_index();
        (index.is_none(), index, self.note_id, self.template_idx)
    }
}

impl Deck {
    pub fn card_order_enabled(&self) -> bool {
        serde_json::from_slice::<Map<String, Value>>(&self.common.other)
            .ok()
            .and_then(|other| other.get(DECK_CARD_ORDER_KEY)?.as_bool())
            .unwrap_or_default()
    }

    fn set_card_order_enabled(&mut self, enabled: bool) -> Result<()> {
        let mut other: Map<String, Value> = if self.common.other.is_empty() {
            Map::new()
        } else {
            serde_json::from_slice(&self.common.other)?
        };
        if enabled {
            other.insert(DECK_CARD_ORDER_KEY.into(), true.into());
        } else {
            other.remove(DECK_CARD_ORDER_KEY);
        }
        self.common.other = if other.is_empty() {
            vec![]
        } else {
            serde_json::to_vec(&other)?
        };
        Ok(())
    }
}

impl Collection {
    /// Turns the custom card order of a normal deck on or off. Turning it on
    /// gives the deck's cards that have none an order index; turning it off
    /// keeps the indices, so the order comes back when it is turned on again.
    pub fn set_deck_card_order_enabled(
        &mut self,
        deck_id: DeckId,
        enabled: bool,
    ) -> Result<OpOutput<()>> {
        self.transact(Op::UpdateDeck, |col| {
            let original = col.storage.get_deck(deck_id)?.or_not_found(deck_id)?;
            require!(!original.is_filtered(), "filtered decks can't be ordered");
            let mut deck = original.clone();
            deck.set_card_order_enabled(enabled)?;
            col.update_deck_inner(&mut deck, original, col.usn()?)?;
            if enabled {
                col.reorder_deck_cards(&deck, &[], None, false)?;
            }
            Ok(())
        })
    }

    /// Moves `card_ids` next to `target`, keeping their relative order. Cards
    /// without an order index are placed at the end. Without a target in the
    /// deck, or without cards to move, only does the latter.
    pub fn move_cards_in_deck_order(
        &mut self,
        deck_id: DeckId,
        card_ids: &[CardId],
        target: Option<CardId>,
        insert_after: bool,
    ) -> Result<OpOutput<()>> {
        self.transact(Op::ReorderCards, |col| {
            let deck = col.storage.get_deck(deck_id)?.or_not_found(deck_id)?;
            require!(
                deck.card_order_enabled(),
                "card order is not enabled for this deck"
            );
            col.reorder_deck_cards(&deck, card_ids, target, insert_after)
        })
    }

    /// The outermost deck with a custom card order that contains the deck,
    /// which may be the deck itself. All cards below it share one order.
    pub(crate) fn card_order_root(&self, deck: &Deck) -> Result<Option<DeckId>> {
        let mut root = deck.card_order_enabled().then_some(deck.id);
        for parent in self.storage.parent_decks(deck)? {
            if parent.card_order_enabled() {
                root = Some(parent.id);
            }
        }
        Ok(root)
    }

    /// After a deck was renamed or moved, forget its cards' order indices if
    /// it now belongs to another custom order, so they go at the end of it.
    pub(crate) fn forget_order_indices_if_order_changed(
        &mut self,
        deck: &Deck,
        old_root: Option<DeckId>,
        usn: Usn,
    ) -> Result<()> {
        if self.card_order_root(deck)? == old_root {
            return Ok(());
        }
        for mut card in self.cards_in_order(deck)? {
            if card.order_index().is_some() {
                let original = card.clone();
                card.set_order_index(None)?;
                self.update_card_inner(&mut card, original, usn)?;
            }
        }
        Ok(())
    }

    /// A card added to a deck with a custom order goes at the end of it.
    pub(crate) fn place_new_card_in_order(&mut self, card: &mut Card) -> Result<()> {
        if card.order_index().is_some() {
            return Ok(());
        }
        let Some(deck) = self.get_deck(card.deck_id)? else {
            return Ok(());
        };
        let Some(root_id) = self.card_order_root(&deck)? else {
            return Ok(());
        };
        let root = self.storage.get_deck(root_id)?.or_not_found(root_id)?;
        let last = self.last_order_index(&root)?.unwrap_or(0);
        card.set_order_index(Some(last + 1))
    }

    /// The highest order index of the cards whose home is the deck or one of
    /// its children.
    fn last_order_index(&self, deck: &Deck) -> Result<Option<u32>> {
        let deck_ids = self.storage.deck_id_with_children(deck)?.iter().join(",");
        Ok(self.storage.db.query_row(
            &format!(
                "select max(extract_card_order(data)) from cards
                where (odid = 0 and did in ({deck_ids})) or odid in ({deck_ids})"
            ),
            [],
            |row| row.get(0),
        )?)
    }

    /// The cards whose home is the deck or one of its children, including
    /// those that are temporarily in a filtered deck, but not cards of other
    /// decks that a filtered child deck holds, in their custom order.
    fn cards_in_order(&mut self, deck: &Deck) -> Result<Vec<Card>> {
        let deck_ids = self.storage.deck_id_with_children(deck)?.iter().join(",");
        let card_ids: Vec<CardId> = self
            .storage
            .db
            .prepare(&format!(
                "select id from cards where (odid = 0 and did in ({deck_ids})) or odid in ({deck_ids})"
            ))?
            .query_and_then([], |row| row.get(0))?
            .collect::<rusqlite::Result<_>>()?;
        let mut cards = self.all_cards_for_ids(&card_ids, false)?;
        cards.sort_by_key(Card::order_key);
        Ok(cards)
    }

    /// Moves cards, then hands the deck's existing order indices back out in
    /// the new order, so only cards whose place changed are written, and the
    /// deck's cards keep their places within an ordered parent deck. Cards
    /// without an index get one after the last index of the whole ordered
    /// tree.
    fn reorder_deck_cards(
        &mut self,
        deck: &Deck,
        card_ids: &[CardId],
        target: Option<CardId>,
        insert_after: bool,
    ) -> Result<()> {
        let mut cards = self.cards_in_order(deck)?;
        let mut indices: Vec<u32> = cards.iter().filter_map(Card::order_index).collect();
        // indices of cards that came from another order may clash
        for i in 1..indices.len() {
            indices[i] = indices[i].max(indices[i - 1] + 1);
        }
        let missing = cards.len() - indices.len();
        if missing > 0 {
            let root_id = self.card_order_root(deck)?.unwrap_or(deck.id);
            let root = self.storage.get_deck(root_id)?.or_not_found(root_id)?;
            let last_in_tree = self.last_order_index(&root)?;
            let start = last_in_tree.max(indices.last().copied()).unwrap_or(0) + 1;
            indices.extend((start..).take(missing));
        }

        let to_move: HashSet<CardId> = card_ids.iter().copied().collect();
        let target = target.filter(|target| {
            !to_move.contains(target) && cards.iter().any(|card| card.id == *target)
        });
        if let Some(target) = target {
            let (moving, mut rest): (Vec<Card>, Vec<Card>) = cards
                .into_iter()
                .partition(|card| to_move.contains(&card.id));
            let target_pos = rest.iter().position(|card| card.id == target).unwrap();
            let insert_pos = target_pos + usize::from(insert_after);
            rest.splice(insert_pos..insert_pos, moving);
            cards = rest;
        }

        let usn = self.usn()?;
        for (mut card, index) in cards.into_iter().zip(indices) {
            if card.order_index() != Some(index) {
                let original = card.clone();
                card.set_order_index(Some(index))?;
                self.update_card_inner(&mut card, original, usn)?;
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::browser_table::Column;
    use crate::card::CardQueue;
    use crate::decks::FilteredSearchOrder;
    use crate::decks::FilteredSearchTerm;
    use crate::search::SearchNode;
    use crate::search::SortMode;
    use crate::tests::CardAdder;
    use crate::tests::DeckAdder;
    use crate::tests::NoteAdder;

    fn add_cards(col: &mut Collection, deck: DeckId, count: usize) -> Vec<CardId> {
        (0..count)
            .map(|i| {
                let note = NoteAdder::basic(col)
                    .fields(&[&format!("front {i}"), ""])
                    .deck(deck)
                    .add(col);
                col.storage.card_ids_of_notes(&[note.id]).unwrap()[0]
            })
            .collect()
    }

    fn order_of(col: &mut Collection, deck: DeckId) -> Vec<CardId> {
        let name = col.get_deck(deck).unwrap().unwrap().human_name();
        col.search_cards(
            SearchNode::from_deck_name(&name),
            SortMode::Custom(CARD_ORDER_SQL.into()),
        )
        .unwrap()
    }

    fn indices(col: &Collection, cards: &[CardId]) -> Vec<Option<u32>> {
        cards
            .iter()
            .map(|cid| col.storage.get_card(*cid).unwrap().unwrap().order_index())
            .collect()
    }

    fn ordered_deck(col: &mut Collection, count: usize) -> (DeckId, Vec<CardId>) {
        let deck = DeckAdder::new("ordered").add(col).id;
        let cards = add_cards(col, deck, count);
        col.set_deck_card_order_enabled(deck, true).unwrap();
        (deck, cards)
    }

    fn build_preview_deck(col: &mut Collection, search: &str) {
        let mut filtered = col.get_or_create_filtered_deck(DeckId(0)).unwrap();
        filtered.config.reschedule = false;
        filtered.config.search_terms = vec![FilteredSearchTerm {
            search: search.into(),
            limit: 100,
            order: FilteredSearchOrder::CardOrder as i32,
        }];
        col.add_or_update_filtered_deck(filtered).unwrap();
    }

    #[test]
    fn enabling_card_order_numbers_cards_in_order_added() {
        let mut col = Collection::new();
        let deck = DeckAdder::new("ordered").add(&mut col).id;
        let cards = add_cards(&mut col, deck, 3);

        col.set_deck_card_order_enabled(deck, true).unwrap();

        assert!(col.get_deck(deck).unwrap().unwrap().card_order_enabled());
        assert_eq!(indices(&col, &cards), [Some(1), Some(2), Some(3)]);
    }

    #[test]
    fn disabling_card_order_keeps_order_indices() {
        let mut col = Collection::new();
        let (deck, cards) = ordered_deck(&mut col, 2);
        col.move_cards_in_deck_order(deck, &[cards[1]], Some(cards[0]), false)
            .unwrap();

        col.set_deck_card_order_enabled(deck, false).unwrap();

        assert!(!col.get_deck(deck).unwrap().unwrap().card_order_enabled());
        assert_eq!(indices(&col, &cards), [Some(2), Some(1)]);
    }

    #[test]
    fn move_cards_in_deck_order_places_cards_before_target() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 5);

        col.move_cards_in_deck_order(deck, &[c[3], c[4]], Some(c[1]), false)
            .unwrap();

        let order = order_of(&mut col, deck);
        assert_eq!(order, [c[0], c[3], c[4], c[1], c[2]]);
        assert_eq!(
            indices(&col, &order),
            [Some(1), Some(2), Some(3), Some(4), Some(5)]
        );
    }

    #[test]
    fn move_cards_in_deck_order_places_cards_after_target() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 4);

        col.move_cards_in_deck_order(deck, &[c[0]], Some(c[3]), true)
            .unwrap();

        assert_eq!(order_of(&mut col, deck), [c[1], c[2], c[3], c[0]]);
    }

    #[test]
    fn move_cards_in_deck_order_keeps_relative_order_of_moved_cards() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 4);

        // passed out of order, but they keep the order they had
        col.move_cards_in_deck_order(deck, &[c[3], c[1]], Some(c[0]), false)
            .unwrap();

        assert_eq!(order_of(&mut col, deck), [c[1], c[3], c[0], c[2]]);
    }

    #[test]
    fn move_cards_in_deck_order_is_noop_when_target_is_moved() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 3);

        col.move_cards_in_deck_order(deck, &[c[0], c[1]], Some(c[1]), true)
            .unwrap();

        assert_eq!(order_of(&mut col, deck), c);
    }

    #[test]
    fn move_cards_in_deck_order_appends_cards_without_index() {
        let mut col = Collection::new();
        let (deck, mut c) = ordered_deck(&mut col, 2);
        c.extend(add_cards(&mut col, deck, 1));
        // eg added on another device by a client that doesn't number cards
        let mut card = col.storage.get_card(c[2]).unwrap().unwrap();
        card.custom_data.clear();
        col.update_cards_maybe_undoable(vec![card], false).unwrap();
        assert_eq!(indices(&col, &c), [Some(1), Some(2), None]);

        col.move_cards_in_deck_order(deck, &[], None, false)
            .unwrap();

        assert_eq!(indices(&col, &c), [Some(1), Some(2), Some(3)]);
    }

    #[test]
    fn move_cards_in_deck_order_includes_child_decks() {
        let mut col = Collection::new();
        let parent = DeckAdder::new("parent").add(&mut col).id;
        let child = DeckAdder::new("parent::child").add(&mut col).id;
        let parent_card = add_cards(&mut col, parent, 1)[0];
        let child_card = add_cards(&mut col, child, 1)[0];
        col.set_deck_card_order_enabled(parent, true).unwrap();

        col.move_cards_in_deck_order(parent, &[child_card], Some(parent_card), false)
            .unwrap();

        assert_eq!(order_of(&mut col, parent), [child_card, parent_card]);
    }

    #[test]
    fn move_cards_in_deck_order_preserves_other_custom_data() {
        let mut col = Collection::new();
        let deck = DeckAdder::new("ordered").add(&mut col).id;
        let cid = add_cards(&mut col, deck, 1)[0];
        let mut card = col.storage.get_card(cid).unwrap().unwrap();
        card.custom_data = r#"{"x":"y"}"#.into();
        col.update_cards_maybe_undoable(vec![card], false).unwrap();

        col.set_deck_card_order_enabled(deck, true).unwrap();

        let card = col.storage.get_card(cid).unwrap().unwrap();
        assert_eq!(card.custom_data, r#"{"oi":1,"x":"y"}"#);
    }

    #[test]
    fn move_cards_in_deck_order_fails_when_order_is_disabled() {
        let mut col = Collection::new();
        let deck = DeckAdder::new("unordered").add(&mut col).id;
        let c = add_cards(&mut col, deck, 2);

        let result = col.move_cards_in_deck_order(deck, &[c[1]], Some(c[0]), false);

        assert!(result.is_err());
        assert_eq!(indices(&col, &c), [None, None]);
    }

    #[test]
    fn reordering_can_be_undone() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 3);
        col.move_cards_in_deck_order(deck, &[c[2]], Some(c[0]), false)
            .unwrap();

        col.undo().unwrap();

        assert_eq!(order_of(&mut col, deck), c);
    }

    #[test]
    fn filtered_deck_with_card_order_plays_cards_in_custom_order() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 3);
        // a review card that isn't due yet still plays in its place
        col.set_due_date(&[c[2]], "5", None).unwrap();
        col.move_cards_in_deck_order(deck, &[c[2]], Some(c[0]), false)
            .unwrap();
        build_preview_deck(&mut col, "deck:ordered");

        let queued: Vec<CardId> = col
            .get_queued_cards(10, false)
            .unwrap()
            .cards
            .iter()
            .map(|queued| queued.card.id)
            .collect();

        assert_eq!(queued, [c[2], c[0], c[1]]);
    }

    #[test]
    fn browser_sorts_cards_and_notes_by_card_order() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 3);
        col.move_cards_in_deck_order(deck, &[c[2]], Some(c[0]), false)
            .unwrap();
        let nids: Vec<NoteId> = [c[2], c[0], c[1]]
            .iter()
            .map(|cid| col.storage.get_card(*cid).unwrap().unwrap().note_id)
            .collect();
        let sort = |reverse| SortMode::Builtin {
            column: Column::CardOrder,
            reverse,
        };

        assert_eq!(
            col.search_cards("deck:ordered", sort(false)).unwrap(),
            [c[2], c[0], c[1]]
        );
        assert_eq!(
            col.search_cards("deck:ordered", sort(true)).unwrap(),
            [c[1], c[0], c[2]]
        );
        assert_eq!(col.search_notes("deck:ordered", sort(false)).unwrap(), nids);
    }

    #[test]
    fn previewing_in_custom_order_shows_and_keeps_siblings_unburied() {
        let mut col = Collection::new();
        col.update_default_deck_config(|config| {
            config.bury_new = true;
            config.bury_reviews = true;
        });
        let deck = DeckAdder::new("ordered").add(&mut col).id;
        let siblings = CardAdder::new().siblings(2).deck(deck).add(&mut col);
        col.set_deck_card_order_enabled(deck, true).unwrap();
        build_preview_deck(&mut col, "deck:ordered");
        assert_eq!(col.get_queued_cards(10, false).unwrap().cards.len(), 2);

        col.answer_good();

        let second = col.storage.get_card(siblings[1].id).unwrap().unwrap();
        assert_ne!(second.queue, CardQueue::SchedBuried);
        assert_eq!(col.get_queued_cards(10, false).unwrap().cards.len(), 1);
    }

    #[test]
    fn ordering_a_child_deck_keeps_its_cards_places_in_the_parent_order() {
        let mut col = Collection::new();
        let parent = DeckAdder::new("parent").add(&mut col).id;
        let child = DeckAdder::new("parent::child").add(&mut col).id;
        let p = add_cards(&mut col, parent, 2);
        let c = add_cards(&mut col, child, 2);
        col.set_deck_card_order_enabled(parent, true).unwrap();
        col.move_cards_in_deck_order(parent, &[c[1]], Some(p[0]), false)
            .unwrap();
        assert_eq!(order_of(&mut col, parent), [c[1], p[0], p[1], c[0]]);

        col.set_deck_card_order_enabled(child, true).unwrap();
        col.move_cards_in_deck_order(child, &[c[0]], Some(c[1]), false)
            .unwrap();

        assert_eq!(order_of(&mut col, parent), [c[0], p[0], p[1], c[1]]);
    }

    #[test]
    fn cards_added_to_an_ordered_child_deck_go_after_the_whole_parent_order() {
        let mut col = Collection::new();
        let parent = DeckAdder::new("parent").add(&mut col).id;
        let child = DeckAdder::new("parent::child").add(&mut col).id;
        let p = add_cards(&mut col, parent, 1);
        let c = add_cards(&mut col, child, 1);
        col.set_deck_card_order_enabled(parent, true).unwrap();
        col.move_cards_in_deck_order(parent, &[c[0]], Some(p[0]), false)
            .unwrap();
        let added = add_cards(&mut col, child, 1);

        col.set_deck_card_order_enabled(child, true).unwrap();

        assert_eq!(
            indices(&col, &[c[0], p[0], added[0]]),
            [Some(1), Some(2), Some(3)]
        );
    }

    #[test]
    fn moving_cards_writes_only_cards_whose_place_changed() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 5);
        let note_of_third = col.storage.get_card(c[2]).unwrap().unwrap().note_id;
        col.remove_notes(&[note_of_third]).unwrap();

        col.move_cards_in_deck_order(deck, &[c[4]], Some(c[3]), false)
            .unwrap();

        // the gap left by the removed card stays, and the first cards keep
        // their indices
        assert_eq!(
            indices(&col, &[c[0], c[1], c[4], c[3]]),
            [Some(1), Some(2), Some(4), Some(5)]
        );
    }

    #[test]
    fn changing_deck_forgets_order_index_unless_staying_in_the_same_order() {
        let mut col = Collection::new();
        let (_, c) = ordered_deck(&mut col, 2);
        let child = DeckAdder::new("ordered::child").add(&mut col).id;
        let other = DeckAdder::new("other").add(&mut col).id;
        add_cards(&mut col, other, 1);
        col.set_deck_card_order_enabled(other, true).unwrap();

        col.set_deck(&[c[0]], child).unwrap();
        col.set_deck(&[c[1]], other).unwrap();

        assert_eq!(indices(&col, &c), [Some(1), None]);
        col.move_cards_in_deck_order(other, &[], None, false)
            .unwrap();
        assert_eq!(indices(&col, &[c[1]]), [Some(2)]);
    }

    #[test]
    fn moving_a_deck_into_another_order_puts_its_cards_at_the_end() {
        let mut col = Collection::new();
        let (parent, p) = ordered_deck(&mut col, 2);
        let other = DeckAdder::new("other").add(&mut col).id;
        let o = add_cards(&mut col, other, 2);
        col.set_deck_card_order_enabled(other, true).unwrap();

        col.reparent_decks(&[other], Some(parent)).unwrap();
        col.move_cards_in_deck_order(parent, &[], None, false)
            .unwrap();

        assert_eq!(order_of(&mut col, parent), [p[0], p[1], o[0], o[1]]);
    }

    #[test]
    fn renaming_a_deck_keeps_its_order() {
        let mut col = Collection::new();
        let (deck, c) = ordered_deck(&mut col, 2);
        col.move_cards_in_deck_order(deck, &[c[1]], Some(c[0]), false)
            .unwrap();
        let mut renamed = (*col.get_deck(deck).unwrap().unwrap()).clone();
        renamed.name = NativeDeckName::from_human_name("renamed");

        col.update_deck(&mut renamed).unwrap();

        assert_eq!(indices(&col, &c), [Some(2), Some(1)]);
    }

    #[test]
    fn cards_of_other_decks_in_a_filtered_child_deck_keep_their_order() {
        let mut col = Collection::new();
        let (deck, _) = ordered_deck(&mut col, 1);
        let (other, o) = {
            let other = DeckAdder::new("other").add(&mut col).id;
            let o = add_cards(&mut col, other, 2);
            col.set_deck_card_order_enabled(other, true).unwrap();
            (other, o)
        };
        col.move_cards_in_deck_order(other, &[o[1]], Some(o[0]), false)
            .unwrap();
        let mut filtered = col.get_or_create_filtered_deck(DeckId(0)).unwrap();
        filtered.human_name = "ordered::cram".into();
        filtered.config.search_terms = vec![FilteredSearchTerm {
            search: "deck:other".into(),
            limit: 100,
            order: FilteredSearchOrder::Added as i32,
        }];
        col.add_or_update_filtered_deck(filtered).unwrap();

        col.move_cards_in_deck_order(deck, &[], None, false)
            .unwrap();

        assert_eq!(indices(&col, &o), [Some(2), Some(1)]);
    }

    #[test]
    fn added_cards_go_at_the_end_of_the_order() {
        let mut col = Collection::new();
        let (parent, p) = ordered_deck(&mut col, 2);
        let child = DeckAdder::new("ordered::child").add(&mut col).id;
        let unordered = DeckAdder::new("unordered").add(&mut col).id;

        let in_parent = add_cards(&mut col, parent, 1);
        let in_child = add_cards(&mut col, child, 1);
        let elsewhere = add_cards(&mut col, unordered, 1);

        assert_eq!(
            indices(&col, &[p[0], p[1], in_parent[0], in_child[0], elsewhere[0]]),
            [Some(1), Some(2), Some(3), Some(4), None]
        );
    }

    #[test]
    fn deck_named_filtered_orders_its_own_cards() {
        let mut col = Collection::new();
        let deck = DeckAdder::new("filtered").add(&mut col).id;
        let c = add_cards(&mut col, deck, 1);
        let elsewhere = add_cards(&mut col, DeckId(1), 1);
        build_preview_deck(&mut col, "deck:Default");

        col.set_deck_card_order_enabled(deck, true).unwrap();

        assert_eq!(indices(&col, &[c[0], elsewhere[0]]), [Some(1), None]);
    }

    #[test]
    fn order_index_fails_with_card_id_when_custom_data_is_full() {
        let mut col = Collection::new();
        let deck = DeckAdder::new("ordered").add(&mut col).id;
        let cid = add_cards(&mut col, deck, 1)[0];
        let mut card = col.storage.get_card(cid).unwrap().unwrap();
        card.custom_data = format!(r#"{{"x":"{}"}}"#, "y".repeat(88));
        col.update_cards_maybe_undoable(vec![card], false).unwrap();

        let err = col.set_deck_card_order_enabled(deck, true).unwrap_err();

        assert!(err.message(&col.tr).contains(&cid.to_string()), "{err:?}");
        assert!(!col.get_deck(deck).unwrap().unwrap().card_order_enabled());
    }

    #[test]
    fn order_index_ignores_invalid_values() {
        assert_eq!(order_index_from_custom_data(r#"{"oi":7}"#), Some(7));
        assert_eq!(order_index_from_custom_data(r#"{"oi":"7"}"#), None);
        assert_eq!(order_index_from_custom_data(r#"{"oi":-1}"#), None);
        assert_eq!(order_index_from_custom_data(""), None);
    }
}
