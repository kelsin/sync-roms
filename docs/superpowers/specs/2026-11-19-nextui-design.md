# NextUI layout

## Intent

The user is moving their Anbernic RG SP (`anbernic-rg-sp`, H700, on NextUI's supported list) from Knulli to NextUI (https://github.com/LoveRetro/NextUI, a MinUI fork; docs at nextui.loveretro.games). sync-roms should treat NextUI as a first-class card layout with the same coverage as Onion and Knulli: folders, BIOS, saves/states, art, collections, Surprise, PICO-8, multi-disc, setup guide, device data, tests, docs.

## Goals

- New layout `nextui` ("NextUI"), selectable for `anbernic-rg-sp`; other H700 devices on NextUI's list may add `nextui` to `firmwares` too (their call, same one-word change).
- A sync to a NextUI card yields a card NextUI can boot into and play: right folders, BIOS, art, collections.
- Existing layouts behave exactly as before.

## Non-goals

- Installing NextUI itself or its Extras zip (the setup guide says to; `flash` stays Knulli-only).
- Trimui devices (not in `devices.json`; separate request).
- NextUI Paks/Pak Store, themes, overlays, shaders, RetroAchievements, cheats.
- Support for any other bucket layout.

## Anti-goals

- No copying NextUI code or assets into the repo (PolyForm Noncommercial).
- No bucket-content notes in repo files (CLAUDE.md rule).

## NextUI card facts (from the docs)

- ROMs: `Roms/<Name> (TAG)/`. The uppercase tag picks the emulator; the name is free. Same name with different tags merges into one menu entry. Only tagged folders show.
- BIOS: `Bios/<TAG>/<file>`, case-sensitive, per tag (GBA and MGBA each need their own `gba_bios.bin`). Exceptions: FBNeo `neogeo.zip` goes in the ROM folder (existing `rom_files` mechanism); FBNeo samples in `Bios/FBN/fbneo/samples/`; PRBOOM IWADs under `Bios/PRBOOM/`.
- Saves: `Saves/<TAG>/`, MinUI naming `Game.gba.sav` by default (RetroArch `.srm` or `Game.sav` are settings). States: `.userdata/shared/<TAG>-<core>/`.
- Art: PNG at `Roms/<folder>/.media/<rom filename without extension>.png`; no gamelist needed.
- Collections: `Collections/<name>.txt`, one absolute ROM path per line (`/Roms/<folder>/<file>`). `Collections/map.txt` renames or hides entries; `Roms/<folder>/map.txt` renames ROMs (a name starting with `.` hides it).
- Multi-disc: a folder named after the game holding the `.m3u` and discs; NextUI launches the `.m3u` instead of opening the folder. CHD and `.pbp` < 2 GB supported.
- Tags: base install FC, GB, GBC, GBA, MD, SFC, PS; Extras add 32X, A2600, A5200, A7800, C64, C128, COLECO, CPC, FBN, FDS, GG, LYNX, MGBA, MSX, NGP, NGPC, P8, PCE, PET, PLUS4, PRBOOM, PUAE, SEGACD, SG1000, SGB, SMS, SUPA, VB, VIC.

## Approaches

1. **One project, full parity (chosen).** Build everything below on one branch, in phases (data, sync, saves, art, collections, extras, docs).
2. Phased PRs, minimal first. Rejected: leaves a NextUI card without art or collections until later PRs land.
3. Reuse Onion/Allium code throughout. Rejected as a blanket rule: NextUI differs on art location, no gamelist, tag-based BIOS/saves, `map.txt`, folder-per-game discs. Reuse only helpers that genuinely match (e.g. the 250x360 derived art type if its size suits NextUI).

## Design

All calls below are the author's unless noted.

**Data.** `layouts.json` gains `nextui` (`roms_dir` Roms, `bios_dir` Bios, `retroarch` block for `Saves/{tag}` since `{core}`/`{system}` can't express it, note). `systems.json` gains a `nextui` key in all 102 systems: `"<Name> (TAG)"` or `null` for systems with no tag (expect ~65 nulls). The tag list above is the whole set. Where a system has two tags (GBA/MGBA, SFC/SUPA, GB/SGB), the folder uses the default tag: the base-install one where one exists (GBA, SFC, GB), else the extras one. A system's BIOS list already covers every emulator, so BIOS goes in every tag directory the system can use. `devices.json`: `anbernic-rg-sp` and `anbernic-rg34xx-sp` firmwares become `["nextui", "knulli"]`; run `tools/update_setup_guide.py`.

**Tags.** A helper derives the tag from the folder (`(...)` suffix). `layouts.json` gets a flag so BIOS destinations become `Bios/<tag>/<file>`; `cli.py` `bios_dests` and the extras/cleanup logic use it. Systems with two usable tags also get their BIOS under the second tag (small per-system data field).

**Saves.** `saves.py` templates gain `{tag}`; `saves stash/apply` map RetroArch `.srm` (and states) to `Saves/<TAG>/<rom>.<ext>.sav` naming for NextUI. States live under `.userdata/shared/<TAG>-<core>/`; builder decides whether to support states or list it as a limit (follow the "skip tiny edge cases" rule: only the common save path is required).

**Art.** New branch in `scrape_plan.py`: copy `<stem>.png` to `Roms/<folder>/.media/<stem>.png`; no gamelist. Add `nextui` to `SCRAPE_LAYOUTS` and `CART_LAYOUTS` (a `.p8.png` cart is its own picture); `stale_media` removes orphaned `.media` PNGs; `.media` is a dot-folder, so `walk_roms` and `find_extras` must neither treat it as ROM files nor delete sync-roms-written art. `GAMELIST_FILES` assumes a gamelist per scrape layout and needs a "none" case.

**Collections.** `frontend.py` gains a NextUI writer (separate from the ES-DE/Knulli settings-file mechanism): `Collections/<name>.txt` with absolute `/Roms/<folder>/<rel>` lines, recorded in the card's `frontend_collections` so only those are touched. `FRONTEND_LAYOUTS` and `surprise.enabled` default: Surprise on for `nextui` (it uses a collection). `themeart.install` must not fall through to the Knulli branch; NextUI collection art is out of scope.

**Multi-disc.** NextUI wants `<Game>/<Game>.m3u` plus discs inside the game folder, not a hidden disc dir. The existing `disc_dir` mechanism (hidden folder beside the playlist) doesn't fit; the builder adds a "folder per game" mode in `downloads.py`/`m3u.py` (playlist entries relative, discs and `.m3u` in a folder named for the playlist). BIN/CUE single-disc games likewise get a same-named folder.

**PICO-8.** `P8` is an Extras tag running fake08 on `.p8.png` carts; no installer needed (no `pico8.TARGETS` entry on purpose); carts sync as ordinary ROMs.

**Other code.** `picker`/`commands`/completion are data-driven. `drivers`, APKs, Themes, `onion_surprise`, `flash`, `vita`: no NextUI behaviour. `store.guess_system` already matches full folder names.

**Setup guide.** `LAYOUTS` map entry, `platformOf` (linux), sections gated `when layout nextui`: install steps, Extras zip, the save-format setting. Only steps the user has given go in; leave sections empty rather than guess.

**Docs and tests.** README layouts, scrape and saves tables, CLI help table, CLAUDE.md data-files notes. Tests: extend `test_firmware.py`, `test_saves.py`, `test_surprise.py`, `test_firmware_scrapes.py`, `test_frontend.py`, `test_themeart.py`; new tests for tag BIOS, folder-per-game discs and the NextUI collections writer.

## Left to the builder

Exact tag per system (data pass against the tag table; verify each folder name against NextUI docs), art image size, the `{tag}` and BIOS flag naming, whether states get support, phase order inside the branch.

## Calls made after the builder check

- Several systems may share one tag folder (as Onion already does for ngp/ngpc); code that dedupes by folder stays as is. Share only where one NextUI tag really runs both systems.
- A system with no tag gets `null`: sync skips it with the existing "no folder" message, the editors behave as they do for Onion's nulls.
- BIOS: the folder uses one tag; BIOS files go in `Bios/<tag>/` for every tag the system can use. FBNeo samples and PRBOOM IWADs only if they are already in the system's BIOS list (builder checks; no new bucket assumptions).
- Multi-disc folder-per-game is decided at sync time, per card layout, so other layouts are untouched. Switching a card's layout does no cleanup beyond what exists today.
- Collection lines whose ROM has a null folder or isn't on the card are dropped; multi-disc entries point at the `.m3u` in the game folder. Surprise is the collection alone (no app).
- Art: same source image as Onion's derived art unless NextUI's list view needs another size; it sits in the `.media/` beside the ROM (for a game folder, builder verifies where NextUI looks).

## Open for the user

1. Answered: `nextui` is the default (first in `firmwares`) for `anbernic-rg-sp` and `anbernic-rg34xx-sp`, with `knulli` second. Other H700 devices are unchanged.
2. Unanswered, so the author's call: assume NextUI's default MinUI `.sav` naming. Knulli-to-NextUI save migration converts only cores where a rename is safe (single-file battery saves); PlayStation memory cards, multi-file saves and the rest are listed as limits.
