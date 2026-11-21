# ROCKNIX layout

## Intent

Add `rocknix` as a ninth layout so a card for a ROCKNIX device (https://rocknix.org, a JELOS fork, EmulationStation-based) gets everything the other layouts get, wherever ROCKNIX allows it. The user will try ROCKNIX soon and doesn't know which device yet, so every ROCKNIX device in `devices.json` gets it, not a chosen one.

## Goals

- Every feature that has a ROCKNIX equivalent works: ROMs, BIOS, scraped media, saves stash/apply, collections, Surprise, PICO-8, RAOfflineProxy, flash, setup guide.
- Data-driven where the code already is; explicit `rocknix` branches wherever code falls through to Knulli's behavior today.

## Non-goals / anti-goals

- No standalone-emulator saves (PSP, PS1 memcards, N64): listed as limits.
- Android GPU drivers (esde only) and Onion's Surprise app are not applicable.
- No second bucket layout; no per-device guessing beyond the DTB list in the ROCKNIX source.
- Must not write anything under the OS storage partition (not reachable from a PC).

## Facts (from the ROCKNIX source, branch `next`, and rocknix.org)

- ROMs: `<card>/roms/<system>/`; system folders come from `config/emulators/<system>.conf` (SYSTEM_PATH basename). Some differ from Batocera: `coleco`, `sgfx`, `odyssey`, `pc88`, `pc98`, `pico-8`, `ports`, `megadrive-japan`, `gamegearh`, etc. Many systems exist only on some SoCs. Card may be FAT32/exFAT/ext4/btrfs; no volume label required; `roms/` is mandatory. ROCKNIX creates the system folders on first boot.
- BIOS: flat `roms/bios/` (standalone emulators use subfolders there: `GC/<region>/IPL.bin`, `dc/`, `xemu/bios/`).
- Saves: RetroArch `.srm` sits next to the ROM (`savefiles_in_content_dir`); states go in `roms/savestates/<ES system name>`.
- Scraped media: identical to Knulli: `<system>/gamelist.xml`, media in `<system>/images|videos|manuals/<stem>-<suffix>.<ext>`, tags image/thumbnail/marquee/video/manual/fanart/boxback/titleshot.
- Collections: only read from `/storage/.config/emulationstation/collections/custom-<name>.cfg` (internal storage). One ROM path per line, `/storage/roms/<folder>/<file>` or `./roms/<folder>/<file>` (never the `games-external` path).
- Themes: user themes under `<card>/themes/`; default theme is Art Book Next.
- PICO-8: binary at `roms/pico-8/` (`pico8_64` on aarch64, else `pico8_dyn`), not bundled.
- RAOfflineProxy (alpha): installer `RAOfflineProxy-Rocknix-v*-Install.sh` is a self-extracting script, run on the device. Official steps copy it to `/storage/.config/modules` (internal storage) and launch it from Tools; it installs under `/storage/.local/share/raofflineproxy`, adds a Tools entry (boot hook re-adds it) and deletes itself. It runs from wherever it is.
- Images: `os/rocknix/ROCKNIX-<SoC>.aarch64-<date>[-variant].img.gz` (already in storage for H700: DDR3 and DDR4, plus an update `.tar` that is not flashable). SoC and variant per device from the DTB lists in `projects/ROCKNIX/config.xml`.

## Approaches considered

1. **Install scripts on the card (chosen).** Anything that must land on internal storage (collections, RAOfflineProxy) goes on the card as a file in `roms/ports/`, run once from ES. Works from a PC; mirrors Knulli's installer pattern; adds one manual step.
2. Files only, user copies by hand over SSH/Samba. Least code, more manual work.
3. Skip collections/Surprise/RAOfflineProxy on ROCKNIX. Loses features the user wants.

The user approved Ports for RAOfflineProxy; collections use the same mechanism by my proposal (user hasn't said otherwise).

## Design

- **Data:** `layouts.json` `rocknix` (`roms_dir roms`, `bios_dir roms/bios`, RetroArch saves next to the ROM, states `roms/savestates/{system}`); every system gets a `rocknix` folder (before `nextui`; `null` where ROCKNIX has no system); `devices.json` adds `rocknix` as a non-default firmware to every device in the ROCKNIX DTB lists; regenerate setup-guide data.
- **Scrape:** `rocknix` in `GAMELIST_FILES` (`gamelist.xml`), `plan_scrapes`, stale cleanup, PICO-8 cart image and `convert.py` `ROM_FOLDER_MEDIA_DIRS` all share Knulli's behavior.
- **Saves:** a layout template if `saves.py` supports saves beside the ROM, else a small addition.
- **Collections/Surprise:** `rocknix` in `FRONTEND_LAYOUTS` (Surprise default on). Collection files are written to a folder on the card plus a `roms/ports/Install Collections.sh` that copies them to ES's collections folder; paths written as `/storage/roms/...`. Theme art: copy Art Book Next art into `<card>/themes/` customizations only if the ROCKNIX theme honors it (builder to verify), else collections have no art.
- **PICO-8:** install into `roms/pico-8/` from the newest official zip only if it contains a binary ROCKNIX can run; otherwise a warning like muOS's.
- **RAOfflineProxy:** `KINDS["rocknix"]`, prefix `os/rocknix/`, pattern `RAOfflineProxy-Rocknix-v[^/]+-Install\.sh`, copied to `roms/ports/RAOfflineProxy Install.sh`, recorded like Knulli's.
- **Flash:** `rocknix` firmware, images `os/rocknix/ROCKNIX-*.img.gz`, device to SoC image (and DDR3/DDR4 choice) mapping.
- **Docs/tests:** README (three tables + sections), CLAUDE.md, setup guide (`LAYOUTS`, a "run the installers from Ports" step), cli saves table, and tests mirroring Knulli's.

## Left to the builder (verify first, mark as calls)

- Whether `ports` is present on every ROCKNIX device and ES runs a bare `.sh` there.
- Exact folder names per system (take them from the source's `config/emulators/*.conf`, per SoC).
- Whether the ROCKNIX ES theme honors collection art customizations.
- Which official PICO-8 zip contents ROCKNIX can run.
- Device to SoC/variant mapping for the images already in storage.
