# Moving RetroArch saves between cards

## Why

A game started on one handheld should continue on another. Each firmware keeps RetroArch's save files (`.srm`) and
save states (`.state`, `.stateN`, `.state.auto`, with `.png` thumbnails) in its own folders, so moving them by hand
means knowing every layout's paths. `sync-roms saves stash CARD` copies chosen saves off a card into the user data
folder; `sync-roms saves apply CARD` puts chosen ones on another card, in the folders that card's firmware reads.

## Goals

- `saves stash [CARD]`: list the games on the card that have RetroArch saves or states, pick games, then pick their
  files (all on to start), and copy them into `~/.sync-roms/saves/` with what they are for and where they came from.
- `saves apply [CARD]`: list the stashed saves of games in systems the card syncs, pick them, and copy them into the
  card's RetroArch folders for its layout.
- Every layout (`esde`, `knulli`, `onion`, `allium`, `emudeck`) both ways.
- Save files (`.srm`) as well as states.

## Non-goals

- Standalone emulators (PPSSPP, Dolphin, DuckStation, ...): RetroArch only for now.
- Converting states between cores, or checking core versions.
- Syncing saves through storage or between machines: stashes are personal and stay in `~/.sync-roms/saves/`.
- A `saves list` / `saves delete` command (the stash folder is plain files).
- Reading Android internal storage over adb or MTP: `--retroarch DIR` points at a copy instead.

## Anti-goals

- Overwriting a different save on a card without asking (a newer save there would be lost). Default is no.
- Writing anything to storage.

## Where RetroArch keeps them

RetroArch names every file after the loaded content's stem (the file name cut at the last dot; an `.m3u`'s own stem
for multi-disc games): `<stem>.srm`, `<stem>.state` (slot 0), `<stem>.stateN`, `<stem>.state.auto`, and a thumbnail
`<state file>.png`. With "sort by core" on, each goes in a subfolder named after the core's library name (`mGBA`,
`gpSP`, `Snes9x`, `PCSX-ReARMed`, ...).

| Layout | RetroArch folder (card relative) | Saves | States | Sorted |
|---|---|---|---|---|
| `esde` | `RetroArch` | `saves/<core>` | `states/<core>` | by core (RetroArch default) |
| `knulli` | `saves` | `<system folder>` | `<system folder>` | no (configgen forces it off) |
| `onion` | `Saves/CurrentProfile` | `saves/<core>` | `states/<core>` | by core |
| `allium` | `Saves/CurrentProfile` | `saves/<core>` | `states/<core>` | by core (as Onion; unconfirmed) |
| `emudeck` | `Emulation/saves/retroarch` | `saves` | `states` | no (EmuDeck's cfg) |

- `esde`: RetroArch on Android keeps them in internal storage (`/storage/emulated/0/RetroArch/`), not on the SD card.
  Either point RetroArch's Save Files / Save States directories at `<SD card>/RetroArch/saves` and `.../states`, or
  copy `/storage/emulated/0/RetroArch` off the device and pass it with `--retroarch DIR`.
- `emudeck`: `Emulation/saves/retroarch/{saves,states}` are symlinks into
  `~/.var/app/org.libretro.RetroArch/config/retroarch/`; they resolve on the Deck itself. Elsewhere, pass the real
  folder with `--retroarch`.

This goes in `layouts.json` as each layout's `retroarch`: `{"dir": ..., "saves": ..., "states": ...}` where the paths
may hold `{core}` or `{system}`. `--retroarch DIR` replaces `dir`.

Sources: RetroArch `config.def.h` (sort defaults), `platform_unix.c` (Android dirs), knulli `libretroConfig.py`,
OnionUI `static/configs/RetroArch/.retroarch/retroarch.cfg`, EmuDeck `emuDeckRetroArch.sh`.

## Design

### Reading a card

- The card is the folder's basename in `cards.json`; it must have a layout (else exit 2, naming `cards set`).
- The card's ROMs: every file under each system's ROM folder (recursively, hidden folders included), indexed by stem.
- Save files: walk each `saves`/`states` folder. `{core}` folders: each subfolder is a core. `{system}` folders: one
  per system with a folder in the layout. Classify by name: `.srm` save, `.state`/`.stateN`/`.state.auto` state,
  `<state>.png` thumbnail (follows its state). Anything else is ignored.
- A file's game is (system, stem): a `{system}` folder gives the system; otherwise the system whose ROM folder has a
  file of that stem. A stem found in no system, or in more than one, is skipped and counted in a dim note.

### Stash

`~/.sync-roms/saves/<system>/<stem>/<YYYYMMDD-HHMMSS>-<card>/` holds the files under their own names and `stash.json`:

```json
{"system": "gba", "game": "Golden Sun (USA)", "card": "SHARE", "layout": "onion", "core": "gpSP",
 "stashed": "2026-11-18T10:02:03", "files": [{"name": "Golden Sun (USA).srm", "kind": "save"},
 {"name": "Golden Sun (USA).state.auto", "kind": "state"}]}
```

`core` is null when the card's layout doesn't sort by core. One stash per (game, core) per run. Stashes are never
replaced: each run adds a new one.

Flow: list games (title = stem, then system name, counts of saves/states, cores), none on; then list the chosen games'
files (game, file, kind, size, modified, core), all on; copy (`shutil.copy2`) and print what was stashed.

### Apply

- Rows: one per stash of a system the card syncs (the layout has a folder for it and, unless Full, the device runs
  it), sorted by game then newest first: game, system, from card, date, counts, core, and "not on card" when no ROM of
  that stem is on the card. Picking two stashes of one game keeps the list open with a note.
- Target folder: the layout's `saves` (for saves) or `states` (states, thumbnails) path. `{system}` is the system's
  layout folder. `{core}` is the stash's core; a stash without one asks, in a list of the core folders already on the
  card plus "Type a name", once per (system, chosen core). With `--yes` or no terminal, such a stash is skipped.
- A target file that exists with the same bytes is skipped. Different ones are listed and overwritten only after a
  confirm (default no); otherwise they are skipped.
- After copying, a stash with states prints that states only load in the core they came from (naming it, if known).

### CLI

`sync-roms saves stash|apply [CARD] [--retroarch DIR] [-n] [-y]`. CARD defaults to the current folder. `--dry-run`
prints what would be copied. Both need a terminal for their lists.

## Questions (answered for this first pass)

1. Where do stashes live? `~/.sync-roms/saves/` (personal, this machine). Storage would share them across machines.
2. Android internal storage? Not read directly: SD-card save folders or `--retroarch` on a copy. adb could come later.
3. Several stashes of one game? All kept, timestamped; apply picks one.
4. A state from a different core? Copied anyway with a warning; only `.srm` usually crosses cores.
5. Overwriting on the target? Asked, default no.
6. Apply for a game whose ROM isn't on the card? Allowed and marked.
7. Allium's folders follow Onion's; unconfirmed from Allium's own source.
8. Standalone emulators (PPSSPP, DuckStation, Dolphin) later?
9. Pruning old stashes? Not yet.
