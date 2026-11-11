# Editor UX redesign: system-first card editing with a live space budget

## Intent

Today a card's games come from a personal core list, the card's extras and whole sets. The core list never fits every device, and adding every set overshoots the card, so the user ended up working set-first, which is backwards: they know which systems suit a device and want to start there, find favorites and types through sets, and search for anything else.

The editor becomes system-first, with sets as a filter inside a system, and a live budget of the card's remaining space.

## Goals

1. `sync-roms edit` opens a main menu for everything editable: cards, sets, device systems. (Today's `edit`, `games edit` and `cards edit` all map to `--edit`.)
2. Editing a card lists systems. Systems *recommended* for the device are highlighted. Each row shows picked games and their size.
3. Inside a system: browse and search the system's whole catalog; a hotkey opens the set list; choosing a set narrows the view to that set's games *on this system*. Sets are never the entry point for card editing.
4. A header always shows card used / card size, and per-system totals.
5. Remove the core list (done). Only per-card picks (games, `sets` references, `full_system`) remain.
6. Add a stricter "recommended" tier per screen ratio, separate from "can play".

## Non-goals / anti-goals

- No set-first card editing flow.
- No hard block when over budget: warn only (builder: this is a guess, see Calls).
- No migration of the existing core list: it is dropped. The user will rebuild cards by hand.
- No new bucket layouts, no new dependencies (stdlib `curses` stays).
- Nothing about the bucket's contents goes into repo files (existing rule).

## Current state (facts from the code)

- TUI is stdlib `curses`: `picker.filter_list`, `pick_systems`; card/core editing in `edit.py` (`toggle_games`, `edit_manifest`, `edit_system`, `edit_device_systems`); set editing in `setedit.py`; persistence in `store.py`.
- Merge at sync: `store.load_manifest` merges the card's games, then its `sets` ids, dedups by bucket key, ORs `full_system`; single-card `excluded` is subtracted from the game lists (a full system still installs every file).
- Card size is a free-text string in `cards.json` (`"512 GB"`), `commands.parse_size` parses it; used only for the free-space check at sync.
- No sizes are stored. They come from listings (`s3.list_sizes`, `mirror_sizes`; `stat_sizes`). The edit flow already lists keys per system but discards sizes.
- `device-systems.json` = systems a device *can play* (tiers + per-device note), with a per-user add/remove overlay.
- `devices.json` has `screen` (ratio) on every device (4:3, 16:9, 3:2, 1:1, 31:27, 10:9, 3:5, 16:10; two have none). `systems.json` has no native ratio.
- Scrape data lives under `scrapes/<system>/<media type>/<ROM name>.<ext>` (plus `onion/`, `slot/` generated PNGs). `scrape_plan.plan_scrapes(layout, ...)` already decides which scrape files a layout installs and knows their sizes from the listing.

## Design

### Main menu
`sync-roms edit` → menu: Cards, Sets, Device systems. Existing flags/aliases keep working and land here or in the matching sub-editor.

### Card editor (system-first)
- Rows: all systems the device can play. Recommended ones are highlighted; the list keeps the normal `systems.json` order (decided by the user, no floating to the top).
- Row detail: picked count, size (ROMs + scrapes for this card's layout).
- Enter a system → game view.

### System game view
- List of the system's games with picked state; incremental search over the whole system.
- Set hotkey → list of sets that contain games on this system → choosing one restricts the list to that set's games on this system (clearable). Toggling a game or the whole filtered set is allowed.
- Existing coverage marks (`cover_notes`) become: picked directly / via a set reference / via full system.
- Header: `used / card size`, free space; green below 70% of the card, yellow below 90%, red above or over.
- Metadata filter (`m`): Developer, Publisher, Genre (first part) or Year from the system's scraped `metadata.json`, then a value with its count. Values match case-insensitively; spellings that differ only by case are one value, shown in their most common spelling. Filters on different fields, the set filter and search combine.
- A multi-disc game's playlist and discs switch on and off together, even when a filter shows only some of them; each file stays its own card entry.
- On/off agrees with sync: a game is on when picked directly or by a referenced set and not excluded. Switching on drops its exclusion (and picks it directly if no set covers it); switching off drops the direct pick and excludes it only while a referenced set covers it. Removing a set reference drops the exclusions no set needs, and resets what revert goes back to.

### Space budget
- Per game cost = ROM size + the scrape files the card's layout would install for that ROM (reuse `plan_scrapes` / layout rules). BIOS counted for the card's systems.
- Card size parsed from the card's existing size string (a card without size shows used only).
- Sizes cache: `sizes.json` in the data folder, one map keyed by bucket key (`gba/Game.zip`), shared by bucket, storage-folder and mirror reads, stored per prefix with a `built` time. A missing storage folder fails the refresh and keeps the cache. On opening a system: (1) name listing (fast on SMB) diffed against the cache — stat only new files, drop removed; (2) spot-check ~5 random cached files and, if any size differs, rebuild that system in the background; (3) background refresh after ~30 days. Work runs in the background so the screen is usable at once; uncached systems show "…" until ready.
- Measured: sizing one system on demand is fast enough; a whole-share scan of every system is slow and must not run at startup.
- Scrape sizes use the same cache, from the `scrapes/` listing.

### Core list removal
- Deleted (done): `games.json` handling (starter file, `seed_personal_files` copy, `merge_lists` core input, core editor menu entry, `prune_unknown_sets` for core). Existing `~/.sync-roms/games.json` is simply no longer read (not deleted).
- Repo docs/CLAUDE.md data-files section updated accordingly.
- Sets remain in the repo (`data/sets/`) and in the personal set support that exists today.

### Recommended tier
- `devices.json`: optional `screen2` (ratio of a second screen). A device with `screen2` is dual-screen.
- `systems.json`: new `ratio` — the system's native aspect ratio (user's examples: NES/SNES/PS1/Genesis 4:3, GBA 3:2, Game Boy 10:9; others filled by the builder from knowledge and flagged for review).
- New data file (`ratio-systems.json`) of per-ratio *overrides* of the form `{ratio: [system ids]}`, plus a dual-screen entry:
  - dual-screen devices: add `nds`, `3ds`, `n3ds`.
  - `3:5`: add `fbneo`, `mame`, and also `nds`, `3ds`, `n3ds`.
  - `1:1`: add `gb`, `gbc` (closest ratio available to their native 10:9; decided by the user).
- A device's recommended systems = (systems whose native `ratio` equals the device `screen`) ∪ (override list for that ratio) ∪ (dual-screen list if `screen2` present), intersected with what the device can play (`device-systems.json`). The per-user overlay is unchanged: it edits only the can-play list (`device-systems.json`) and never the recommended tier (decided by the user). The recommended tier is always computed from the repo data and then intersected with the overlaid can-play list.

## Calls I made (built as listed)
- Over budget warns, does not block.
- Cache spot-check count (~5) and refresh age (~30 days).
- Native ratios for systems beyond the user's examples.
- `ratio` / `screen2` field names (`screen2` is the user's).

## Further calls (from the builder check; my calls unless noted)
- Settings is dropped from the main menu (no editor for it exists); menu is Cards, Sets, Device systems.
- `games edit`, `cards edit` and bare `edit` all open the main menu (aliases kept).
- A card with no picks syncs nothing for games (BIOS and the like unchanged) and prints a one-line note; no refusal.
- `sets` references on cards stay. Budget is computed on the resolved set of bucket keys (direct picks + set references + `full_system`, minus the card's `excluded`), deduplicated by key, so a game picked twice counts once. "Picked count" is that resolved count.
- Scrape cost counts every file the layout would install for a ROM, including `onion/` and `slot/` PNGs that are already stored in `scrapes/`. A system with no scrapes costs ROM only. Refactor `plan_scrapes` into a per-ROM cost helper if needed. Until a system's sizes are cached, its numbers show "…" and the header total is marked partial.
- Sizes come from whichever backend `s3.read_root()` / the bucket currently resolves to. Entries are keyed by bucket key (the path from the storage root), shared by every backend; a refresh from a local mirror only adds and updates sizes, never drops names (the mirror holds only some files).
- `3ds` (original Nintendo 3DS) and `n3ds` are separate systems that share ES-DE's `n3ds` ROM folder; the ES-DE and EmuDeck media and gamelist folders follow the ROM folder name, so they share those too.
- Ratios match by exact string. A system or device with no ratio is never recommended by ratio (overrides still apply).
- A card with no or unparseable size string shows used only, no warning.

## Left to the builder (decided in the build)
Key bindings, screen layout details, cache file format and name, breaking the work into steps, tests, how `plan_scrapes` is called for estimates, file/override data name.
