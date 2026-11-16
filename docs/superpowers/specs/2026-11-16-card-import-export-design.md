# Card import and export

## Intent

Sync a card for another person from this machine. They export their cards to a file; this user imports the ones
wanted into `~/.sync-roms/cards.json` and syncs them like any other card.

## Goals

- `sync-roms cards export FILE`: a multi-select list of this user's cards; the chosen ones are written to FILE.
- `sync-roms cards import FILE`: a multi-select list of the cards in FILE (an export, or a raw `cards.json`); the
  chosen ones are added to `cards.json`.
- In the import list: `r` renames the highlighted card, `p` sets a prefix put in front of every imported card's name.

## Non-goals / anti-goals

- No collections or surprises come along as such; collections can be added to an imported card later in the editor.
- Never import sync's record of a physical card (`frontend_collections`, `drivers`, `pico8`) or anything else not
  listed below: it would make the first sync remove or skip files.
- Never overwrite an existing card.

## Design

**Exported card** (FILE is `{name: card}`, same shape as `cards.json`): `size`, `device`, `layout`, `games`,
`excluded`, each only when the card has it. In `games`, the card's collection games and every entry in its
`surprises` (whether Surprise is on or off) are flattened into plain entries under their system:
`{"title", "bucket", "files"?, "note"?}`, skipping a bucket the card already lists there. A system the card has as
`{"full_system": true}` stays that way and gets no flattened entries. `sets` stay as set ids. If FILE exists, ask
before overwriting.

**Import:** each chosen card keeps only `size`, `device`, `layout`, `games`, `excluded`, plus `"surprise": false`.
Rows show the final name (prefix + name, or the rename). A row whose final name is taken by an existing card or by
another chosen row, or isn't a valid name (same rule as `cards rename`: not empty, no `/`), is marked; Enter with such
a row chosen shows a note and keeps the list open. A card whose device or layout is unknown is locked with a note.
Saved with `store.write_cards` (keeps `.bak`); refuses when `cards.json` is unreadable, like `cards new`.

Both commands take `--dry-run` like the other `cards` subcommands (say what would be written, write nothing).
Nothing selected or Esc: nothing written. Help text in `cli.py` and shell completion list the new subcommands.

## Approaches

- **A (chosen): export writes a `cards.json`-shaped file, import accepts any `cards.json`-shaped file.** Matches the
  original ask (import another user's `cards.json`); a raw `cards.json` just loses its surprises and collections.
- B: a marked export format only import accepts. Stricter, but rules out a plain `cards.json`.

## Left to the builder

How `r`/`p` read text inside the list (`on_hotkey` with the picker's prompt), exact row and note wording, tests.
