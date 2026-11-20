# muOS support: design

## Intent

Kelsin removed muOS support in #360 (`16febdc`) because it was incomplete: it had a layout, folder names, BIOS, catalogue art and a PICO-8 install, and none of the things the other layouts have (saves, collections, Surprise, flash, themes, setup guide). The goal is **full parity** with `knulli`/`onion`, for [muOS](https://muos.dev/) 2606.0 "Andromeda" on the devices that run it.

## Goals

- A `muos` layout that works for every sync-roms feature where the muOS equivalent exists (list below).
- Built from the removed code (`git show 16febdc^`) plus muOS's current docs and source, not from memory.
- One pull request (Kelsin's choice). A feature whose file locations can't be confirmed is not implemented and warns instead (see the policy section).

## Non-goals / anti-goals

- No second bucket layout, no muOS-specific storage files; the bucket stays as in CLAUDE.md.
- No automatic muOS image download (images are `.img.gz` bundles on Gofile/MEGA/Filen). `flash` uses images Kelsin puts in storage's `os/`.
- Writing muOS data to a path we haven't confirmed.
- No changes to the other layouts' behavior.

## Approaches considered

- **A. One PR with everything** (chosen by Kelsin): one review; unverified pieces ship alongside confirmed ones, so they are marked.
- **B. Phased PRs** (recommended, not chosen): isolates the unverified pieces.
- **C. Guide/flash/Surprise first**: rejected, sync can't write correct data without the layout and scraping.

## What muOS 2606.0 does (confirmed from docs and the MustardOS source)

| Area | Fact | Source |
|---|---|---|
| ROMs | `ROMS/<folder>` on the card; folder names are normalised (lowercased, spaces, `-`, `_`, `+` stripped) and looked up in a generated alias index; subfolders free-form | docs `first-steps`, `systems/cores` |
| BIOS | `MUOS/bios` (flat; per-core subfolders undocumented) | docs `storage` |
| Catalogue art | `MUOS/info/catalogue/<catalogue name>/box|preview|text` (also `grid`, `manual`), file name = ROM name without extension, case-insensitive, flat even for ROMs in subfolders | docs `catalogue` |
| Catalogue names | The removed `systems.json` had a `muos_catalogue` per system (e.g. `Nintendo Game Boy Advance`, `Sega Mega Drive - Genesis`); it matches the names the docs show | `16febdc^` |
| Saves (source-confirmed) | muOS now uses the Pickles frontend: `MUOS/pickles/sram/<core>[/<dir>]/<save>` and `MUOS/pickles/state/<core>[/<dir>]/<stem>/…`; RetroArch-era `MUOS/save/file/<core>` and `MUOS/save/state/<core>` still exist for external emulators | `Import RetroArch Saves to Pickles.sh` |
| Collections | `MUOS/info/collection/<collection folder>/<name>-<FNV1a-32 hex of the full ROM path>.cfg`, three lines: full ROM path (card mount + content dir + file name), the content folder name, the ROM name without extension. A duplicate entry is detected by file hash | `muxcollect.c`, `content.c` |
| Install | `ARCHIVE/` holds items for Archive Manager; `.muxbak` backups; `.muxcat` catalogue packages go in `MUOS/package/catalogue`; themes are open folders in `MUOS/theme` | docs, release notes |
| Devices | internal ids: `rg35xx-h`, `rg35xx-plus`, `rg35xx-2024`, `rg35xx-sp`, `rg35xx-pro`, `rg34xx-h`, `rg34xx-sp`, `rg40xx-h`, `rg40xx-v`, `rg28xx-h`, `rgcubexx-h`, `rg-vita-pro`, `rgsp`, `tui-brick`, `tui-brick-pro`, `tui-spoon`, `rk-g350-v`, `rk-pixel-2`, `mgx-zero28`, `gcs-h36s` | `MustardOS/internal/device` |

## Work, in one PR

1. **Layout and data.** Restore `muos` in `layouts.json` (`roms_dir` `ROMS`, `bios_dir` `MUOS/bios`, a `retroarch` block for saves/states, note updated for 2606.0). Restore `folders.muos` and `muos_catalogue` per system from `16febdc^`, re-checked against the docs' system names and the folder-alias rule; drop any that muOS no longer knows. Re-add `muos` to `firmwares` of the devices muOS supports, using the device ids above mapped to the existing `devices.json` entries; add device entries only where Kelsin's existing list lacks a supported device (RG CubeXX and RG Vita Pro already exist). BIOS lists stay as CLAUDE.md requires (all emulators). Restore tests.
2. **Scraping.** Restore catalogue `box`/`preview`/`text` writing and stale-art cleanup (from `scrape_plan.py` at `16febdc^`), review against current docs. PICO-8: restore the `ARCHIVE/` install but check whether the zip is still a valid package for Archive Manager in 2606.0.
3. **Saves.** `saves stash`/`apply` for muOS: Pickles tree under `MUOS/pickles/sram` and `state`, per core, matching how Pickles names cores (the import task shows `<core>[/<dir>]`). RetroArch-era `MUOS/save/...` handled only if a card has it.
4. **Collections.** Write muOS collection `.cfg` files (format above) for the card's collections and sets, tracked in the card's `frontend_collections` like Knulli/ES-DE, so only sync's own files are removed.
5. **Surprise.** Surprise picks as a muOS collection (muOS has no Surprise app).
6. **Themes/art.** Install Art Book Next collection art into `MUOS/info/catalogue/Collection/…` (the docs name a `Collection` catalogue area), not a theme; no muOS theme is installed.
7. **Flash.** `flash` offers muOS images found in storage's `os/` (`muos-*.img.gz`, naming chosen by Kelsin's files).
8. **Setup guide.** A muOS section in `setup-guide.html` only with steps Kelsin gave (per CLAUDE.md: leave empty rather than guess), plus the device-list update via `tools/update_setup_guide.py`.
9. **Docs.** README layouts table and CLAUDE.md data-file notes; conventional-commit PR title.

## Calls made while writing this (change any you disagree with)

- **Devices:** only devices already in `devices.json` that listed `muos` before #360 get it back, as the second firmware after `knulli` (as before, so Knulli stays the default). No new device entries.
- **Surprise:** on by default for muOS (like the other frontend-collection layouts); one collection with a fixed name, rewritten on each sync, listed in the card's `frontend_collections`.
- **Collection mount prefix:** `/mnt/mmc` (SD1, the muOS `storage/rom/mount` default), with a card setting for SD2 (`/mnt/sdcard`).
- **Saves:** Pickles tree only (below). The core folder is the core muOS has assigned to the content, so `saves stash` records each file's path relative to `MUOS/pickles` and the ROM folder maps it to a system; `saves apply` restores the same relative path.
- **Collection art:** `box` and `grid` images named after the collection folder, under `MUOS/info/catalogue/Collection/`, owned and cleaned up like the `.cfg` files.
- **Folder and catalogue names:** reuse the removed values wholesale; drop only systems the muOS docs or source show it no longer knows.
- **PICO-8:** not implemented on muOS (see below).
- **Flash:** lists every `muos-*.img.gz` in storage's `os/` and lets the user pick; no per-device matching, no post-flash steps beyond what the existing flash path does for other images.

## Policy for what isn't known (Kelsin's rule)

If we don't know where a feature's files go, it is not implemented; sync prints a warning that the feature is skipped for muOS and says why. Research settled most of the earlier unknowns from the MustardOS source (`frontend`, `internal`):

- **Collections:** entry file `MUOS/info/collection/<collection folder>/<ROM name>-<8 hex digits>.cfg` holding three lines: the ROM's path on the device (`<mount>/ROMS/<folder>/<file>`), the ROM folder under `ROMS/`, and the ROM name without extension. The hex is FNV-1a 32-bit of the path in line 1 (`muxcollect.c`, `content.c`). Collections are one folder deep.
- **Collection art:** `MUOS/info/catalogue/Collection/box|grid/<collection folder name>.<ext>` (`catalogue.c`, `grid.c`).
- **Saves:** `MUOS/pickles/sram/<core>[/<ROM folder>]/<ROM name>.srm|.rtc`; states `MUOS/pickles/state/<core>[/<ROM folder>]/<ROM name>/slot_N.state` plus `states.ini`, in Pickles' own state format, not RetroArch's (`Import RetroArch Saves to Pickles.sh`). The core folder is the libretro core id assigned to the content.
- **Mount:** `/mnt/mmc` is SD1 and `/mnt/sdcard` SD2 (`service.sh`); which one holds the ROMs is a card setting.

Left unimplemented, each with a warning:

- **PICO-8 install:** Archive Manager takes `.muxzip` (and `.muxapp`), but the structure of a package that installs PICO-8 is not documented, so the old "rename the Raspberry Pi zip" approach can't be trusted.
- **Per-device flash image matching:** flash lists every `muos-*.img.gz` in `os/` for you to pick, since muOS image names are not documented; it does not guess a device's image.

Still partly unconfirmed, implemented as stated because the paths are known: the folder aliases muOS recognises (restored names; a miss only leaves a folder unassigned in muOS, never loses data), and per-core BIOS subfolders (BIOS go flat in `MUOS/bios`).

## Left to the builder

Test names, module placement, helper naming, how to share code with Knulli's collection writer, and the exact device-to-id mapping once `devices.json` is read.
