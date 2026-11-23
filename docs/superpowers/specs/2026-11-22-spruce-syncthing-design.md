# Spruce Syncthing support: design

## Intent

Kelsin plays on spruceOS on every non-Android handheld and on ES-DE + RetroArch on Android, with Syncthing syncing RetroArch saves and states through a home server. Saves and states should move between the two with no per-system fiddling. Anything that can be set from files on a `spruce` card, sync-roms sets on every sync and says so. Everything else (RetroArch on Android, ES-DE, Syncthing itself) goes in the setup guide, along with the core to use per system.

## Goals

- Saves (`.srm`) and states sync between Spruce and Android RetroArch for every system where both run the same libretro core, using one Syncthing folder for `saves/` and one for `states/` (RetroArch's default sort-by-core-name folders then line up by themselves).
- sync-roms sets on `spruce` cards: the chosen core per system, the Spruce settings Syncthing needs, and RetroArch's save settings.
- A setting turns all of this off for people who don't use Syncthing.
- The setup guide covers every manual step and lists the RetroArch core per system.

## Non-goals

- Systems that Spruce runs with a standalone emulator (NDS, PSP, PICO-8) or doesn't support. Android-to-Android sync already works for them.
- N64, Saturn, Dreamcast and Jaguar crossing between Spruce and Android: Spruce keeps its defaults for them; they sync only within Spruce devices and within Android devices.
- Mega Duck (Spruce's only core, armGBA, isn't on Android).
- Setting up Syncthing folders or devices automatically (needs device IDs; done in the web UI).
- Other layouts (Knulli, Onion, muOS).

## Anti-goals

- Changing a card when the setting is off.
- Creating Spruce or RetroArch files that don't exist yet (Spruce seeds them on first boot or launch; creating a partial one would stop that).
- Losing saves when a core changes.

## Decisions

### Cores (cross-referenced with spruceOS `Development` `Emu/*/config.json` and the libretro Android arm64 buildbot)

Changed from Spruce's defaults:

| Spruce folder | System | Core |
|---|---|---|
| SFC | SNES | `snes9x` |
| GBA | GBA | `mgba` (Kelsin's pick; the Mini family may get a lighter core later) |
| MD | Genesis | `genesis_plus_gx` |
| SEGACD | Sega CD | `genesis_plus_gx` |

Pinned to the core Spruce already uses (so a change on the device can't break matching): `ARCADE` fbneo, `FC` fceumm, `FDS` fceumm, `GB`/`GBC` gambatte, `GG`/`MS`/`SEGASGONE` genesis_plus_gx, `LYNX` handy, `NGP`/`NGPC` mednafen_ngp, `COLECO` bluemsx, `MSX` bluemsx, `ARDUBOY` ardens, `PS` pcsx_rearmed.

Systems with one fixed core in Spruce already match Android and need nothing: MAME 2003-Plus, Atari 2600/5200/7800, Intellivision, Odyssey², Vectrex, Channel F, C64, PC-98, Virtual Boy, WonderSwan/WSC, PCE/PCE-CD/SuperGrafx, 32X, Satellaview, Sufami, Supervision, Neo Geo CD, Pokémon Mini.

Left alone: N64, Saturn, DC, JAGUAR, NDS, PSP, PICO8, MEGADUCK.

### What a sync writes on a `spruce` card when `spruce_syncthing` is on

1. **Cores**: in `Emu/<FOLDER>/config.json`, for each `menuOptions` entry whose key starts with `Emulator` and whose `options` contain the chosen core, set `selected` to it (each device reads only its own key, so setting every matching key is correct on any device). Folders whose config is missing are skipped silently (the card may not have that system); an unreadable one is warned about. Merged into the file like `spruce_emu.py` does (keep everything else, keep indentation).
2. **`Saves/spruce/spruce-config.json`** (`menuOptions`):
   - `Emulator Settings`: `raAutoSave` = `"True"`, `raAutoLoad` = `"True"`, `keepSavesBetweenCores` = `"Always"` (on the first launch after a core change, Spruce copies the old core's save into the new core's folder without prompting).
   - `Network Settings`: `enableSyncthing` = `"True"`, only when the card's device has WiFi (`devices.json` has no `"network": false`).
   - Same rules as `spruce_settings.install`: only sections and keys the file already has, only `selected` changes; missing or invalid file is warned about and skipped.
   - While the setting is on, these four keys are taken off `data/spruce-settings.json`'s allowlist (see "Calls made after review").
3. **RetroArch config**: every `Saves/ra-configs/retroarch-*.cfg` on the card (Spruce's live per-platform config, seeded from `RetroArch/platform/*.cfg.bak` at the first launch):
   - `autosave_interval = "10"` (Spruce ships 0, so SRAM was only written on exit),
   - `sort_savefiles_enable = "true"`, `sort_savestates_enable = "true"`,
   - `sort_savefiles_by_content_enable = "false"`, `sort_savestates_by_content_enable = "false"`,
   - `savefiles_in_content_dir = "false"`, `savestates_in_content_dir = "false"`.
   An existing `key = ...` line is replaced; a missing key is appended. No `retroarch-*.cfg` there: warn "launch a game once on the device, then sync again" and skip.
4. **Output**: one "Syncthing" block listing each change (file and value), `would set` in a dry run; nothing printed when nothing changes.

The values above live in a new `src/sync_roms/data/syncthing.json`, shared by every device so other firmwares can use it later: `cores` {system id: libretro core} (Spruce maps a system to its folder through `systems.json`; the guide's table for Android comes from the same list), `retroarch` {retroarch.cfg key: value}, `spruce.settings` {section: {key: value}} and `note`, so changing a core is a data edit. A test checks its shape.

### The setting

`spruce_syncthing` in `settings.json`, a bool, default on (absent = on). A `config set`/`unset` name like `eject` (`commands.CONFIG_KINDS`), documented in the README's Settings section and CLAUDE.md's personal data list. Off: none of the writes above happen.

### Setup guide (`data/setup-guide.html`, Syncthing section and a new cores section)

- **spruceOS**: what sync-roms sets automatically (listed); by hand: WiFi on, network time (Advanced Settings > Network > Sync Time/RTC with network; wrong clocks pick the wrong file), the web UI at `http://<device IP>:8384` (default login `spruce` / `happygaming`, change it), accept the server's two existing folders at `/mnt/SDCARD/Saves/saves` and `/mnt/SDCARD/Saves/states`: `ra-saves` (ID `jkx7j-mnlfo`) and `ra-states` (ID `w5nqg-xmpq6`), the same IDs on every device, folder Advanced `modTimeWindowS` = 2 (FAT32 2 s timestamps). Spruce waits for a sync at boot (after WiFi connects) and at save-and-shutdown (hold POWER), not at game launch or resume; quit a game or shut down that way before switching devices.
- **Android**: Syncthing-Fork; RetroArch Settings > Directory: Save Files / Save States outside `Android/data` (Syncthing-Fork can't read it on Android 11+), e.g. `/storage/emulated/0/RetroArch/saves` and `/states`; Settings > Saving: sort saves and states into folders by core name on, by content directory off, write to content directory off, SaveRAM autosave interval 10 s, auto save state on, auto load state on; save the configuration. Share the same two folder IDs to those paths. Syncthing-Fork run conditions so it runs when switching.
- **ES-DE**: per system, the alternative emulator set to the core in the cores table.
- **Server**: Staggered or Simple file versioning on both folders.
- **RetroArch cores** table: per system, the core for Spruce and Android, and which systems don't cross (N64, Saturn, Dreamcast, Jaguar, Mega Duck).
- Notes rewritten: states sync now (cores match; a state from a different core version may fail to load, the in-game save still applies); RetroAchievements Hardcore forces auto load off; one of Syncthing or RetroArch Cloud Sync per device. The old "sync checker at launching a game and resuming" claim is removed.
- Run `tools/update_setup_guide.py` only if devices/device-systems data change (they don't here).

### Calls made after review (Claude's)

- Core writes go ahead even when `keepSavesBetweenCores` can't be set (warned): nothing is deleted, the old core's save stays in its folder, and Spruce's default `Prompt` asks to transfer it at the first launch.
- Spruce folders not in the lists (NEOGEO, CPS1-3, ATOMISWAVE, NAOMI, EIGHTHUNDRED, ATARIST, CHAI, EASYRPG, DOOM, OPENBOR) belong to systems with no folder in storage, so they're out of scope.
- The four keys are off the allowlist only while `spruce_syncthing` is on (with it off, `config import` and `spruce_settings` handle them as before). While it is on, saved values for them are ignored without a warning. Kelsin's `settings.json` has none today, so no cleanup is needed.
- No migration: both Spruce and Android RetroArch already default to sort-by-core, not by content, not in the content directory; only the autosave interval changes.

## Approaches considered

- **Match cores, keep sort-by-core folders (chosen)**: one Syncthing folder each for saves and states, no per-system mapping; costs a lighter-or-heavier core on some devices.
- Per-system Syncthing folders mapping different core folders: keeps each device's best core, but a dozen folders to set up by hand on every device, and states still don't cross.
- Flat folders (sort by core off everywhere): one folder, but ROM-name collisions across systems and states from other cores would load into the wrong core.

## Left to the builder

- Module layout (a new `spruce_syncthing.py` called next to `spruce_settings.install` and `spruce_emu` in cli.py's dry-run and real paths, or extending those modules).
- How `spruce_settings.install` and the new forced values share one read/write of `spruce-config.json`.
- Tests: card fixtures for each write, the setting off, missing files, dry run, the allowlist change.
