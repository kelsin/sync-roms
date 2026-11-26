# Collections list: size and playable / off / not playable counts

## Intent

In the card editor's 💖 Collections list (`cardedit.pick_collections`), show what putting a collection on the card
costs, and how its games split between playable, off and not playable on this card, so systems turned off with `x`
don't count as playable or as space.

## Row

```
  🐉 Dragon Quest   ✅ on the card  11/11   2.4 GB  🎮 11  🚫  5  📵  6
  🏎️ Racers                         3/14   6.1 GB  🎮 14  🚫  2
  👾 Shmups                         0/22   812 MB  🎮 22         📵  9
```

- Parts, each its own extras column (the picker aligns columns): on the card, have/total (with a setup), size,
  🎮 playable, 🚫 off, 📵 not playable, then the existing `N match` while a tag filter is on.
- 🎮 playable: games on systems the setup plays (`playable`) that aren't in `store.systems_off(card)`.
- 🚫 off: games on playable systems that are off on the card (🚫 already marks an off system in the system list).
- 📵 not playable: games on systems the setup can't play.
- A count of 0 is a blank cell. Numbers are right-aligned within their column (padded to the widest in the list).
- have/total counts 🎮 games only.
- Size: the whole collection's 🎮 games, ROM bytes plus the scrapes the card's layout installs
  (`budget.game_costs`, per system), `size_text` (decimal, like the status bar); `…` (`SIZING`) while any of it is
  partial (not cached). Dim, like the counts. Without a setup there is no size column.

## Legend

The highlighted collection's three counts are explained at the bottom, in the block game lists use for a
highlighted game's tags (`filter_list`'s `tag_info`): `🎮 Playable  N games on systems this card syncs`,
`🚫 Off  N games on systems turned off on this card (x)`, `📵 Not playable  N games on systems this device can't run`.
All three always show.

## Approaches

- Whole playable size (picked): steady when the collection is toggled, same numbers as the status bar's sums.
- Only what it adds (games not on the card yet): goes to ~0 once on; not chosen.
- Also sizing off games: not chosen; off games cost nothing on this card.

## Non-goals

No BIOS in the size; no changes to other lists.
