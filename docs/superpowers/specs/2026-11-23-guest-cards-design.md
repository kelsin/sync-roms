# Guest cards

## Intent

Some cards aren't the user's own: they copy games onto them now and then for family and friends. A sync of such a
card should copy ROMs, BIOS and scrapes and leave everything else on it alone: the friend's own games, their settings,
their theme, their apps. The card is still remembered (device, layout, guest mode) but kept out of the way of the
user's own cards.

## Goals

- A card can be marked as a guest card: `guest: true` in its `cards.json` entry. Set by `sync-roms --guest` (saved,
  so later syncs of that card are guest syncs without the flag) or toggled with `G` in the card editor.
- A guest sync:
  - copies the picked ROMs, their BIOS (BIOS folder and ROM-folder `rom_files`) and their scrapes (media and the
    gamelists / `miyoogamelist.xml` the scrape plan writes);
  - deletes only the storage ROMs that were on the card when the session started and the user deselected in the
    editor, plus the media sync-roms puts for those ROMs;
  - still runs the end-of-run card tidy (`clean`) and the eject;
  - on `spruce` cards still runs `spruce_emu` (BIOS zips it installs in ROM folders added to `Emu/<folder>/config.json`'s
    `ignoreList`). That step already merges: it only adds and removes the names it recorded in `spruce_emu`, keeps
    every other name and every other key in the file, and skips a missing or malformed config with a warning. It
    stays exactly as it is.
  - skips everything else (see Skipped steps).
- Each guest sync seeds the card's picks fresh from the card: every storage game whose file is on the card under a
  matching name (the same match as the editor's `K`, `card_match`: case and Unicode form left out) **and** with
  storage's size. Picks from an earlier session are thrown away, since the friend may have added or deleted games
  since. A same-named file of another size isn't recognized: it isn't seeded and is never touched.
- A guest sync never overwrites a file on the card (user's decision): ROMs, BIOS (`BIOS/` and ROM-folder
  `rom_files`) and media are written only where no file exists yet. A gamelist gets a `<game>` entry only for a ROM
  it has no entry for; existing entries are left as they are.
- `sync-roms cards list` leaves guest cards out; `cards list --all` shows them, marked as guests (a `guest` field in
  `--json`).

## Non-goals

- No guest-specific storage, sets, collections or Surprise. A guest card's picks are ordinary picks in `cards.json`,
  treated as scratch: overwritten by the next seed.
- No change to non-guest syncs.
- No hiding guest cards from other commands (`cards edit`, `cards delete`, completion, the `edit` card picker); only
  `cards list`.

## Anti-goals

- Deleting or changing anything on the card that sync-roms didn't recognize as a storage ROM the user deselected this
  session (the friend's own ROMs, saves, art, settings). Getting this wrong is the failure that matters.
- Writing any frontend or firmware setting other than the spruce `ignoreList` merge.

## Approaches

- **A. Guest checks inside `sync_card` (chosen).** The seed is computed at the start of the sync and kept in memory;
  the ROMs to delete are seed minus the picks after the editor. The usual ROM, BIOS and scrape steps run unchanged,
  stale-media removal is limited to the deleted ROMs, and every other step gets an `if not guest`. Smallest change;
  guest cards keep every fix to the core copy steps.
- **B. A separate `guest_sync` function.** Clearer in one place, but duplicates ~200 lines of `sync_card`'s setup
  (layouts, disc folders, BIOS planning, space check) that would drift.
- **C. The seed stored in `cards.json`.** Would let a dry run or a later sync delete what was deselected after a
  cancelled sync, at the cost of state the user doesn't want kept. Dropped.

## Design

### Card flag

- `guest` is a card field: present and `true` only on guest cards (absent otherwise, like the other card flags).
  Document it in CLAUDE.md's Card fields table and in `cards.schema.json`.
- `--guest` on the sync (a `cli.PLAIN_FLAGS` entry, an `ap.add_argument` in `cli.build_parser`, an Options-table row in
  the README, `cli.check_modes` rejects it with another mode like `--no-delete`). It saves `guest: true` on the card
  before anything else of the sync (not on a dry run, like the setup). There is no flag to turn it off; `G` in the
  editor does that.
- `G` (`GUEST_KEY`) in the card editor's system list toggles the flag and is listed in `LIST_KEYS`/`LIST_HINT`. The
  title shows `· 👤 guest` while on.
  - During a sync (the editor got `card_match`): turning guest on reseeds the picks right away (the same seeding as at
    sync start) and the sync becomes a guest sync from there; turning it off leaves the picks and the sync is a normal
    one again. `edit_card` needs a way to tell the sync: the sync re-reads the flag from `cards.json` after the editor
    returns (it already calls `reload_changes`), and computes the seed then if guest mode was turned on during the
    editor and there is no seed yet.
  - Outside a sync (`sync-roms edit`): only the flag changes.

### Seeding

At the start of a guest sync (after `choose_card_setup`, before `surprise.run_surprise`):

1. For each system the card syncs, the storage games whose file is on the card: `card_match(s, available keys of a
   full listing of the system)`. This must list the system's storage folder whether or not it has picks (a guest
   card's earlier picks don't decide what is seeded).
2. Write those as the card's picks: `games` = `{bucket: [keys]}` (no `full_system`, no `sets`), and clear `excluded`,
   `collections` and `systems_off`. The card's saved `surprises` are left out of a guest sync's manifest (my call), so
   old Surprise picks aren't copied. Not on a dry run: a dry run seeds in memory only and plans from that.
3. Keep `seed = {bucket: set(keys)}` in memory.

Systems turned off for the device or layout aren't seeded and aren't touched.

### Downloads

- ROM, BIOS and media jobs whose destination already exists (any size) are dropped from the guest plan: never
  re-downloaded. Same for `apply_scrape_plan`'s gamelist entries: only ROMs without an entry get one.
- Seeded ROMs use the card's own file spelling (what `card_match` found) for the "already there" check and for
  deletes, so case/Unicode differences never cause a duplicate download or a delete that misses. No renames to
  storage's spelling (`find_extras`'s `renames`) and no `card_moves`.

### What gets deleted

- No `downloads.find_extras` sweep. The only ROM deletions are `seed[bucket] - picked[bucket]` after the editor, each
  at the card path where it was found (for a multi-disc game, its `.m3u` and the discs as the layout places them).
  They go through the existing `delete_extras` prompt.
- `x` (system off) on a guest card means skip that system this sync (user's decision): nothing copied to it, nothing
  deleted from it. Its seed is left out of the delete step. `D` (clear every pick) stays as it is: after its confirm,
  every seeded ROM is deselected and goes through the delete prompt.
- Stale media: only the media belonging to the deleted ROMs (the paths `scrape_plan` would write for those ROMs, the
  layout's own naming), not `scrape_plan.stale_media`'s sweep of every picture without a ROM. Gamelist entries are
  never removed, as in a normal sync (`update_gamelist` only adds and sets; frontends skip entries whose ROM is gone).
- `--no-delete` keeps them, as now.
- No `prune_empty_systems`, `nextui_folders.migrate`, `spruce_emu.OLD_FOLDERS` clearing or legacy-system cleanup.
- `downloads.hide_discs` (moving loose discs of recognized games into the disc folder) still runs: it only moves
  storage files the sync recognizes.

### Skipped steps

In a guest sync none of these run (dry run or real): Surprise (`run_surprise`'s replace step and `fill_surprises`; the
card editor still opens when interactive), `install_apps` (PICO-8 runtime, Onion Surprise app, RAOfflineProxy),
`onion_surprise.write_list`, `stage_spruce` (boot logos, spruceOS 7z, spruce settings, WiFi, Syncthing), Onion/spruce
themes (`theme_jobs`, `theme_plan`, the `t` answer, theme removal and selection), Android APKs, GPU drivers (copy,
refresh and prune), `frontend_step` (collections and theme art), `spruce_fixes.run`, `vita.add_psvita_files`
(writes `.psvita` launch files) and the budget-over warning that reads Surprise. The PICO-8 cart's own-picture copy
is part of the scrape plan and stays.

### Non-interactive

With `--yes`, `--json` or no terminal the editor doesn't open: the picks are the seed, nothing is deleted, and missing
BIOS and scrapes are filled in.

### `cards list`

`cards list` drops entries with `guest: true` unless `--all` (added to its parser in `commands.build_parser` and to
completion's second words if flags are listed there). With `--all` the text output marks guest rows (e.g. `👤`), and
`--json` rows carry `"guest": true|false`.

### Tests

- Seeding: a card with files matching storage and others not gets exactly the matching ones as picks; earlier picks,
  sets, full systems and exclusions are replaced.
- Deletion: deselecting a seeded ROM deletes it and its media; unrecognized files (other names, or the same name at
  another size) and media of other ROMs stay; an added pick downloads; `x` on a system deletes nothing there.
- No overwrite: an existing ROM, BIOS or media file of another size and an existing gamelist entry are left as they
  are.
- Skipped steps: a guest sync of a spruce/onion/esde card writes no theme, collection, app, settings or driver files;
  a spruce guest sync still updates the `ignoreList` and keeps the file's other contents.
- `--guest` saves the flag; `G` toggles it; `cards list` hides guest cards and `--all` shows them.
- `tests/test_readme.py` passes with the new flag documented.

## Left to the builder

- Where in `sync_card` the guest checks go and how the seed reaches the delete step; keep each check next to the step
  it skips.
- How the editor tells the sync that `G` turned guest on (re-reading `cards.json` after the editor is the expected
  way).
- The exact media paths for a deleted ROM per layout (reuse `scrape_plan`'s own path functions rather than new ones).
