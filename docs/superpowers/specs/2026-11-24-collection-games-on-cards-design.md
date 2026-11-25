# Individual collection games on a card

## Intent

Collections and sets are used differently: a collection is usually put on a card whole (its playable systems), and a set
mostly helps you find games in the editor. Both should still work the same way in the card editor: put the whole thing on,
or open it and pick single games.

## Behaviour

- **Card editor, `l` (collections list):** Space/Tab still toggles the collection id in the card's `collections`, as it
  does now. **Enter opens the collection's games** in the same view the set view (`s` → Enter) uses: games across the
  card's playable systems, toggled one by one, with the usual status, variants and size counts. A game picked there is an
  ordinary direct pick in `games`. A game the whole collection already brings shows as locked, and turning it off adds
  it to `excluded`, as the set view does with collection games now. Esc or Enter on the list closes it, as it does now.
  Each row also shows how many of the collection's games the card syncs (`n/total`, ✅ when all), like the sets list.
- **Sync, frontend collections:** while the card's `custom_collections` is on, a collection is written to the frontend
  when it is in `collections` **or any of its games is on the card**, however that game got there (picked through the
  collection, a set, or the system list). As now, each collection holds only its games that are on the card. This
  applies to every layout `frontend_step` handles (ES-DE, EmuDeck, Knulli, ROCKNIX, muOS, Spruce). Collection art and
  `frontend_collections` ownership work as now, so a collection whose last game goes is removed by the existing cleanup.

## Approaches

- **A (picked): a collection counts when any of its games is on the card.** No new card field. A game being on the card
  already decides whether it shows in a collection. A card that already has games from a collection it never added will
  start showing that collection.
- B: record the collections whose games were picked through the new view in a new card field. This is more exact, but
  the field has to be kept up to date. Rejected.
- For the UI, we reuse `edit_set` on the collection, which already has the `{"name", "games"}` shape, rather than writing
  a new collection view. A separate view would duplicate the set view's toggling, locks, exclusions and sizes.

## Non-goals

- No change to how `collections` ids, `excluded`, guest cards, `cardshare` or Surprise work.
- Sets don't go to the frontend.

## Left to the builder

- How `edit_set` is told it's showing a collection (title emoji/art, no series hotkey if collections have no series).
- Whether `pick_collections` returns the chosen collection to `edit_card` (as `pick_card_set` does) or opens it itself.
- Tests for: Enter opening the view and saving picks; the `n/total` count; `frontend_step` writing a collection that
  isn't in `collections` but has a game on the card, and not writing it with `custom_collections` off.
