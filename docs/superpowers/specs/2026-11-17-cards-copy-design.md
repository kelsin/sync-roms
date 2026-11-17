# `cards copy`: copy one card's selections into another

## Intent

Copy everything picked on one card onto another without rebuilding it by hand, merging into what the target already has.

## Approaches

- **CLI subcommand `sync-roms cards copy SRC DST` (picked).** Fits next to `rename`/`delete`/`export`; the merge is a pure
  function in `cardshare.py`, easy to test.
- Editor hotkey on the card list: a second UI for the same thing; not asked for.
- Reusing `export`/`import`: flattens collections into games and replaces instead of merging; wrong semantics.

## Design

- Playable systems come from DST's saved device/layout (`cardedit.can_play`); DST without a device fails.
- `games`: for each system DST can play, SRC's games are added to DST's list by bucket key; DST's entry (and note) wins
  on conflict. SRC `full_system` makes DST full, stashing DST's list the way `toggle_full` does; when DST is already
  full, SRC's games go into its stashed `games` list.
- Top-level `sets` ids are unioned (sets are live and span systems; sync limits them to what the card plays).
- `collections` ids are unioned.
- `excluded`: SRC's exclusions for playable systems are added, except for games DST already syncs (exclusions drop any
  game on the card, so a copied one could otherwise remove DST's own pick). *Builder's call on exactly how "already
  syncs" is computed; DST's pre-copy manifest is the reference.*
- Not copied: surprises, `surprise`, size, device, layout.
- Prints counts added (games, sets, collections, exclusions) and the systems skipped. `--dry-run` prints the same
  without saving. `cards.json.bak` is kept by `store.write_cards` as usual.
- Errors: unknown SRC or DST, SRC == DST, unreadable cards.json.
- Help text, shell completion, README and tests updated.

## Non-goals

No editor UI, no replace mode, no copying across machines (that's `export`/`import`).
