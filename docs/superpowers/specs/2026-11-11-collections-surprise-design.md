# Custom collections and Surprise

Three changes, in this order:

1. Stop syncing ES-DE themes, collections and settings through storage.
2. Custom collections: personal lists of favourite games, added whole to cards, and shown as custom collections in
   ES-DE and Knulli.
3. Surprise: a per-card option that, at sync time, fills a "Surprise" collection with 10 random games not otherwise on
   the card.

## Why

- **Sets** help people *find* ROMs to add to cards. They live in the repo and are shared.
- **Collections** let a user keep their own favourites together and find them again in the frontend. They are
  personal and never need a repo checkout.
- **Surprise** puts games on a card the user would not have picked, so the card keeps offering something new.

Sets and collections must stay separate abstractions (data, loaders, UI, sync rules), so either can grow without the
other. Low-level, concept-free list helpers may be shared; nothing named or shaped "set" should be reused as a
collection (builder's call where that line falls, but err towards separate code).

## Part 1: drop themes, collections and settings from storage

Remove everything that uploads or installs `scrapes/esde/` (themes, `collections/*.cfg`, `settings.json`):

- `--upload-scrapes` no longer reads `ES-DE/themes/`, `ES-DE/collections/` or `ES-DE/settings/es_settings.xml`.
- Sync no longer lists or installs anything from `scrapes/esde/`.
- Remove the code that only served this (`plan_esde_extras`, `SETTING_*`, `share_setting`, `safe_settings`,
  `setting_line`, `update_settings`, `merge_lines`, the extras/texts plumbing in `load_scrape_data` /
  `build_scrape_plan` / `apply_scrape_plan` / `describe_scrape_plan`, the esde parts of `plan_upload`, `text_keys`,
  `plan_clean`), their tests, and the README rows. Part 2 needs its own small writer for one es_settings key; it does
  not reuse the removed allowlist code.
- Scraped metadata, media, Onion box art and Slot labels are unchanged.
- The user's storage had only `scrapes/esde/settings.json`; it has already been removed by hand. No migration code.

## Part 2: custom collections

### Personal sets go away

Collections replace personal sets. Remove them entirely:

- `load_sets` reads only the repo's `data/sets/`; `personal_sets_dir`, `save_personal_set`, `personal_set_problem`
  and the personal-set checks in `sync-roms check` go.
- The card editor's `m` "make set" key and `edit.make_set_from_extras` go. There is no way to save a card's selection
  as a set or a collection.
- Existing `~/.sync-roms/sets/*.json` files are left on disk and never read (as with the old `games.json`). A card's
  `games.sets` reference to a set that no longer loads is handled by the existing `prune_unknown_sets`.
- README and CLAUDE.md lose their personal-set text.

### Data

- One file per collection: `~/.sync-roms/collections/<id>.json` (under `store.data_dir()`), `id` = slug of the name.
- Shape (same fields as a set file, but its own schema and loader):
  `{"name", "description"?, "games": [{"title", "system", "bucket", "files"?, "category"?, "note"?}]}`.
  `files` = the other files of a multi-disc game, as in sets.
- Its own loader (`load_collections`) and writer, its own JSON schema. Never read from or written to the repo or
  storage.

### Collection editor

- Reached from the first menu of `sync-roms edit` (`--edit`): a "💖 Collections" entry after "📦 Sets"
  (`edit.edit_manifest`'s `menu()`), and from `sync-roms collections edit`.
- Same features as the set editor: list collections, new, delete, rename/description, switch games off, add games from
  a system (the full storage listing for that system), categories, notes if sets have them.
- Saves straight to `~/.sync-roms/collections/` on Done (Quit discards). No git, no `gh`, no PR.
- Deleting a collection that cards use: confirm, then also remove its id from those cards.

### On a card

- The card entry in `cards.json` gets `"collections": [ids]` (top level of the card, not inside `games`, so it never
  mixes with `games.sets`).
- Card editor system list: a hotkey (builder picks a free key, e.g. `l`) opens a list of collections with how many of
  each one's games the card's device can play; Space/Enter toggles a whole collection on or off. No per-game
  customising.
- Only games on systems the card's setup syncs (device can play and the layout has a folder) are synced; the rest are
  ignored silently (the picker can show "n not playable").
- Card editor game list: a collection's games show 💖 with the collection's name. They can't be switched off there;
  trying shows a note ("from collection X; remove the collection to remove it"). `excluded` never applies to them.
- Budget/usage counts collection games like picks.
- Sync merges collection games into the selection with BIOS, scrapes, multi-disc handling, etc. as for any game, on
  the systems this run syncs.
- Scripting: `games export`/`import` carry the card's `collections`, `surprise`, `surprises` and
  `frontend_collections`; `sync-roms check` validates `~/.sync-roms/collections/*.json` and `surprises.json`. The CLI
  gets a `collections` group with `edit` (help text and completion word lists updated).

### In the frontend (ES-DE and Knulli only)

For each collection on the card with at least one synced game, sync writes a custom collection file and enables it.

| | ES-DE | Knulli |
|---|---|---|
| File | `ES-DE/collections/custom-<Name>.cfg` | `system/configs/emulationstation/collections/custom-<Name>.cfg` (card root is `/userdata`) |
| Line | `%ROMPATH%/<system folder>/<path on card>` | `./roms/<system folder>/<path on card>` |
| Enable | `CollectionSystemsCustom` in `ES-DE/settings/es_settings.xml` | `CollectionSystemsCustom` in `system/configs/emulationstation/es_settings.cfg` (root `<config>`) |

- `<path on card>` is the game's path inside its system folder as sync writes it (`downloads.rom_rel`), so subfolders
  are kept and a multi-disc game is its `.m3u`.
- `<Name>` is the collection's name with characters ES-DE rejects (`* " , . / : ; < > \ |`, newline, tab, CR)
  removed; the same name is used on Knulli.
- `CollectionSystemsCustom` is a comma-separated list of names without `custom-`. Sync adds its names and keeps any
  others already there; it edits only that one line (or adds it), leaving the rest of the file as is, and creates the
  file if missing.
- **Ownership:** sync-roms only touches collection files it wrote. The card entry records the names it wrote
  (`"frontend_collections": [names]`). A collection removed from the card (or a renamed one) has its old file deleted
  and its name removed from `CollectionSystemsCustom`. Files the user made in the frontend are never touched. If a file
  sync-roms didn't write already has the name it wants, warn and skip that collection.
- Files are rewritten each sync (sync-roms' list is the truth; edits made in the frontend to these files are lost —
  say so in the README).
- Both frontends rewrite their settings file from memory when running; sync runs with the card on a computer, so this
  is only a README note.

## Part 3: Surprise

### Option

- On for every card unless the card entry has `"surprise": false` (existing cards included).
- Card editor system list: one hotkey (builder picks, e.g. `u`) toggles it; the title or status shows "🎁 Surprise on/off".
  Nothing else about Surprise is edited there.

### State

- Card entry: `"surprises": [{"system", "bucket", "title"}]` — the card's current surprises. Kept out of `games`.
- History: `~/.sync-roms/surprises.json`, a list of `{"system", "bucket", "title", "card", "date"}` (date ISO), one
  entry per pick. Entries older than the TTL are dropped when the file is written.
- TTL: `surprise_ttl_days` in `~/.sync-roms/settings.json`, default 183 (about 6 months).

### Sync flow (a card with Surprise on)

1. After the systems for this run are chosen (saved `systems`, `--systems` or the system picker): show the card's
   current surprises on those systems as a multi-select, nothing selected, titled "Pick the surprises to replace".
   With none, skip straight to picking. Current surprises on systems outside this run are dropped from the list
   (their files go the next time their system is synced, as unselected files always do) — builder's call, made so
   Surprise always matches the run.
2. Pick replacements for the selected ones (rules below) so the card has 10 again. Save at once: the card entry's
   `surprises`, and the new picks appended to the history.
3. Open the full card editor (`cardedit.edit_card`) for this card, so the user can change other picks before syncing.
   Its changes save to `cards.json` as usual. Surprise games show 🎁 in its game lists, can't be switched off there,
   and count in its budget header.
4. Reload the card and carry on with the normal sync. Surprise games are synced like picks (BIOS, scrapes, discs).
   Replaced surprises are no longer selected, so the existing "remove files no longer selected" step removes them
   (unless something else on the card still selects them).
5. If the card's planned size is over its capacity (`budget.card_capacity`), print a warning before downloading and
   go on (the user keeps cards under their limit; the editor in step 3 already shows red).
6. ES-DE/Knulli: write the "Surprise" collection like any owned collection (`custom-Surprise.cfg`, enabled).

With Surprise off: the card's surprises are no longer selected (removed by step 4's existing removal), `surprises` is
cleared, and the Surprise collection file is deleted and unlisted. History is kept.

`--dry-run`: changes no surprises (it says whether it would ask or replace all, and previews only empty slots), saves
nothing and doesn't open the editor. The name "Surprise" is reserved: no collection can use it. Unattended runs (`--yes`,
`--json`, no TTY): no prompt and no editor; the card's picks are synced as saved, and with Surprise on all 10 surprises
are replaced by new picks under the normal rules (and saved, as in step 2).

**Mirror:** surprise candidates are listed from real storage, never the local mirror. The mirror's wanted list
(`mirroring.mirror_wanted`, `load_manifest(all_card_names())`) includes every card's collection and current surprise
games, and when a mirror is in use it is refreshed again after the surprise and editor steps so new picks are in it.

### Picking

- **Pool:** the systems this run syncs (chosen as in step 1) that have a storage folder.
- **Candidates in a system** (from the storage listing): full, English games only.
  - A multi-disc game is one candidate (its `.m3u`, or its disc group via `m3u.file_groups`) and takes one slot.
  - Out: anything already selected on the card (direct, sets, collections) and the surprises being kept.
  - Out: the system's BIOS files and `[BIOS]`; `(Proto)`, `(Beta)`, `(Demo)`, `(Sample)`, `(Kiosk)`, `(Pirate)`,
    `(Hack)`, `[h…]`, `[b…]`, `(Unl)`, re-releases (`(Virtual Console)`, `(Switch Online)` and the like, and
    compilation/collection re-release tags; builder lists them from the No-Intro/Redump naming conventions).
  - English: a language tag (e.g. `(En,Fr,De)`) containing `En`; without one, a region of USA, World, Europe, UK,
    Australia or Canada.
  - MAME/FBNeo (systems with a `clones.json` entry): parent sets only; a parent whose title names Japan as its region
    counts as not English.
  - Names with no No-Intro/Redump tags at all (homebrew systems, Vita, ...) count as full English games.
- **Slots:** 10 per card. About two thirds (7) from the device's recommended (⭐) systems, the rest (3) from its other
  systems. If one group has no candidates (or the setup is Full with no recommended systems), the other takes all its
  slots. Within a group, slots are spread across its systems as evenly as possible (random system order, round robin);
  a system that runs out of candidates passes its slot on. The split counts the kept surprises too.
- **Which candidate:** within a system, pick at random from the best non-empty tier:
  1. not in the history (within the TTL) and not a current surprise on another card;
  2. in the history but not a current surprise on another card;
  3. a current surprise on another card.

### Finding past surprises

- Card editor game list: a hotkey (builder picks, e.g. `g`) narrows the list to games in the surprise history
  (within the TTL), like the set filter; `c` clears it. The collection editor's "add games from a system" list gets
  the same filter.

## Constraints

- Follow the repo's CLAUDE.md: no real game lists in the repo; keep its data-files table, the README and the JSON
  schemas up to date (`cards.schema.json`: `collections`, `frontend_collections`, `surprise`, `surprises`).
- Tests first for each behaviour (pick rules, filters, file writing, ownership, sync flow, editor saves), using the
  existing test helpers (`tests/helpers.py`, `isolate.py`).
- Conventional-commit messages.

## Calls made without the user (check these)

- 💖 for collection games, 🎁 for surprises.
- `collections` / `frontend_collections` / `surprise` / `surprises` field names and placement in the card entry.
- History pruned past the TTL on write; Surprise off keeps history.
- A frontend file name clash with a user-made collection is skipped with a warning, not overwritten.
- Kept surprises count towards the 7/3 split.
- Dry-run behaviour above.
- Current surprises on systems outside a run are dropped from the card's list.
- Part 1 also drops the `scrapes/esde/` listing from the mirror's wanted list.
- Deleting a collection removes it from cards after a confirm.
- The past-surprises filter also appears in the collection editor.
