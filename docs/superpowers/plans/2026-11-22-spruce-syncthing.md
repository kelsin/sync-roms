# Spruce Syncthing Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On `spruce` cards, sync-roms sets the cores, Spruce settings and RetroArch save settings that let Syncthing sync saves and states with Android RetroArch, unless `spruce_syncthing` is off; the setup guide covers the rest.

**Architecture:** A data file `data/syncthing.json` holds the values. A new module `spruce_syncthing.py` writes the cores (`Emu/<FOLDER>/config.json`) and RetroArch configs (`Saves/ra-configs/retroarch-*.cfg`) and is called from `cli.py`'s `stage_spruce`. `spruce_settings.py` applies the forced `spruce-config.json` values in its existing single write and takes those keys off the allowlist while the setting is on.

**Tech Stack:** Python 3.12+ stdlib, `unittest`, run with `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-22-spruce-syncthing-design.md`

## Global Constraints

- Run everything with `uv run` (`uv run python -m unittest discover -s tests`); code must run on Python 3.12.
- Test modules import `isolate` first (directly or via `helpers`).
- Never create a Spruce or RetroArch file that doesn't exist; only edit existing ones, keeping everything else in them (JSON: keep indentation and trailing newline, as `spruce_emu._dump` does).
- Write card text files with `cardfs.write_text`; read with `cardfs.text`.
- `spruce_syncthing` absent or `true` = on; only `false` turns it off. Off: no core, RetroArch or forced spruce-config write happens, and the allowlist is the full file.
- Conventional Commits, lowercase imperative, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Don't hand-edit `__version__`, `CHANGELOG.md`, `.release-please-manifest.json`.

## Review Focus

1. One sync writes both `spruce_emu`'s `ignoreList` and this feature's `selected` into the same `Emu/<FOLDER>/config.json`: both must survive (the later writer must read the file after the earlier one wrote it).
2. An `Emulator*` entry whose `options` lack the chosen core (e.g. the Mini group for some systems) keeps its `selected`.
3. Setting off: the card is byte-identical after the sync.
4. A second sync with nothing to change writes nothing and prints nothing.
5. A RetroArch cfg with CRLF line ends, no trailing newline, or `key="v"` without spaces is edited in place without duplicating the key.

---

### Task 1: Data file, setting and module skeleton

**Files:**
- Create: `src/sync_roms/data/syncthing.json`
- Create: `src/sync_roms/spruce_syncthing.py`
- Modify: `src/sync_roms/commands.py` (`CONFIG_KINDS`)
- Modify: `src/sync_roms/cli.py` (`TOPICS["config"]` text)
- Modify: `README.md` (Settings section, `config set` names sentence)
- Modify: `CLAUDE.md` (Repo data list: the new file; Personal data `settings.json` list: `spruce_syncthing`)
- Test: `tests/test_spruce_syncthing.py`

**Interfaces:**
- Produces, in `spruce_syncthing.py`:
  - `data() -> dict`: `store.repo_json("syncthing")`.
  - `enabled() -> bool`: `usersettings.load_settings().get("spruce_syncthing") is not False`.
  - `forced_keys() -> set[tuple[str, str]]`: every `(section, key)` in `data()["spruce"]["settings"]`.
  - `forced_settings(card: str) -> list[tuple[str, str, str]]`: `(section, key, value)` from `data()["spruce"]["settings"]`, leaving out `("Network Settings", "enableSyncthing")` when the card's device (`store.saved_card(card).get("device")`, looked up in `store.repo_json("devices")` by `id`) has `"network": False`. Empty list when not `enabled()`.

- [ ] **Step 1: Write the data file** with exactly these values:

```json
{
  "note": "Settings that let Syncthing sync RetroArch saves and states between devices: one libretro core per system on every device (so RetroArch's core-named save folders match), RetroArch's save settings, and per-firmware settings. Spruce cards get them from sync; Android gets them from the setup guide. N64, Saturn, Dreamcast and Jaguar keep each device's own core and don't sync between Spruce and Android.",
  "cores": {"arduboy": "ardens", "atarilynx": "handy", "colecovision": "bluemsx", "fbneo": "fbneo", "fds": "fceumm",
            "gamegear": "genesis_plus_gx", "gb": "gambatte", "gba": "mgba", "gbc": "gambatte", "genesis": "genesis_plus_gx",
            "mastersystem": "genesis_plus_gx", "msx": "bluemsx", "msx2": "bluemsx", "nes": "fceumm", "ngp": "mednafen_ngp",
            "ngpc": "mednafen_ngp", "psx": "pcsx_rearmed", "segacd": "genesis_plus_gx", "sg1000": "genesis_plus_gx",
            "snes": "snes9x"},
  "retroarch": {"autosave_interval": "10", "sort_savefiles_enable": "true", "sort_savestates_enable": "true",
                "sort_savefiles_by_content_enable": "false", "sort_savestates_by_content_enable": "false",
                "savefiles_in_content_dir": "false", "savestates_in_content_dir": "false"},
  "spruce": {"settings": {"Emulator Settings": {"raAutoSave": "True", "raAutoLoad": "True", "keepSavesBetweenCores": "Always"},
                          "Network Settings": {"enableSyncthing": "True"}}}
}
```

- [ ] **Step 2: Write failing tests** in `tests/test_spruce_syncthing.py` (import `helpers` first):
  - `Data.test_shape`: `note` is a non-empty str; every `cores` key is a system id (`bucket`) in `systems.json` and every value a non-empty str; systems that share a Spruce folder have the same core; every `(section, key)` in `spruce.settings` is in `data/spruce-settings.json`'s `sections`, values are str; every `retroarch` value is a str.
  - `Setting.test_on_by_default`: no `spruce_syncthing` saved → `enabled()` is True; `False` saved → False; `True` → True.
  - `Setting.test_forced_settings_skip_syncthing_without_wifi`: card "c" saved with device `miyoo-mini` (has `"network": false` in devices.json; confirm, else pick one that does) → `("Network Settings", "enableSyncthing", "True")` not in `forced_settings("c")`; with `anbernic-rg-sp` it is; with the setting off the list is `[]`.
  - `Setting.test_config_set_takes_it`: `commands.config_value("spruce_syncthing", "false") is False`.

- [ ] **Step 3: Run** `uv run python -m unittest tests.test_spruce_syncthing -v` → FAIL (module/key missing).

- [ ] **Step 4: Implement** the skeleton functions; add `"spruce_syncthing": bool` to `CONFIG_KINDS`; add `` `spruce_syncthing` `` to the README's `config set` sentence (with `eject`'s `true`/`false` group) plus one sentence: on by default; `false` stops sync from setting the Syncthing cores and settings on spruce cards (see the setup guide); mention it in `cli.TOPICS["config"]`; update CLAUDE.md's Repo data (`syncthing.json`: `cores` {system id: libretro core}, `retroarch` {retroarch.cfg key: value}, `spruce.settings` {section: {key: value}} for `spruce-config.json`, `note`) and the `settings.json` field list.

- [ ] **Step 5: Run** `uv run python -m unittest tests.test_spruce_syncthing tests.test_readme -v` → PASS.

- [ ] **Step 6: Commit** `feat(spruce): add the spruce_syncthing setting and its data`

---

### Task 2: Cores and RetroArch config on the card

**Files:**
- Modify: `src/sync_roms/spruce_syncthing.py`
- Modify: `src/sync_roms/cli.py` (`stage_spruce`)
- Test: `tests/test_spruce_syncthing.py`

**Interfaces:**
- Consumes: `data()`, `enabled()` from Task 1.
- Produces:
  - `core_writes(base: str) -> tuple[list[tuple[str, str]], list[str], list[str]]`: `(writes [(path, new text)], lines, warnings)`. For each `cores` system whose `folders["spruce"]` (from `systems.json`) is set and whose `Emu/<FOLDER>/config.json` exists (one write per folder): parse; for each `menuOptions` key starting with `Emulator` whose value is a dict with `options` containing the core and `selected` different, set `selected`. Missing file: skipped silently. Unparsable / not a dict: warning `Emu/<FOLDER>/config.json can't be read; its core left as it is`. Line: `   Emu/<FOLDER>: <core>`. Text via `spruce_emu._dump(data, old_text)`.
  - `retroarch_writes(base: str) -> tuple[list, list, list]`: for each `Saves/ra-configs/retroarch-*.cfg` (sorted): replace every line matching `^\s*<key>\s*=.*$` with `<key> = "<value>"` when its value differs, append `<key> = "<value>"` for a missing key (adding a line end first if the file lacks one; use the file's own line end, `\r\n` if it has any). None found: warning `Saves/ra-configs has no retroarch-*.cfg yet; launch a game once on the device, then sync again for RetroArch's save settings`. Line per changed key: `   <file name>: <key> = <value>`.
  - `run(card: str, layout_name: str, base: str, dry_run: bool) -> int`: 0 (failures are warnings). Returns at once unless `layout_name == "spruce"` and `enabled()`. Prints warnings with `ui.warn`; when there are writes: dry run prints `ui.dim("🧪 Dry run: would set for Syncthing:")` and the lines dimmed, else writes each with `cardfs.write_text` and prints `🔄 Syncthing: set <n> setting(s) so saves and states sync` and the lines.

- [ ] **Step 1: Write failing tests** (class `Card(helpers.CardDir)`, card "c" with device `anbernic-rg-sp`):
  - `test_sets_the_core_in_every_entry_that_offers_it`: `Emu/SFC/config.json` with `Emulator_64` (options `["mednafen_supafaust","snes9x"]`, selected supafaust) and `Emulator_32` (options `["snes9x2010"]`, selected `snes9x2010`) plus `ignoreList: ["x.zip"]`, 2-space indent → after `run`, `Emulator_64.selected == "snes9x"`, `Emulator_32.selected == "snes9x2010"`, `ignoreList` kept, indent kept.
  - `test_missing_emu_config_is_skipped_quietly` and `test_unreadable_emu_config_warns`.
  - `test_retroarch_cfg_keys_replaced_and_appended`: `retroarch-Anbernic.cfg` with `autosave_interval = "0"`, `sort_savefiles_enable="true"`, `other = "1"`, no `savestates_in_content_dir` → `autosave_interval = "10"` once, `sort_savefiles_enable` left (same value), `savestates_in_content_dir = "false"` appended once, `other` kept.
  - `test_crlf_and_no_trailing_newline_kept`.
  - `test_no_cfg_warns`.
  - `test_second_run_writes_and_prints_nothing`.
  - `test_off_leaves_the_card_identical`: `spruce_syncthing: false` → `self.snapshot()` unchanged, no output.
  - `test_other_layouts_untouched`, `test_dry_run_writes_nothing_and_lists`.
  - `test_emu_ignore_list_and_core_both_kept_in_one_sync`: drive the real sync's spruce steps (or call `spruce_emu.plan`/`apply` then `run` in the order `cli.py` uses) on one `Emu/<FOLDER>/config.json` → both `ignoreList` additions and `selected` present.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_spruce_syncthing -v` → new tests FAIL.

- [ ] **Step 3: Implement** the three functions, and call `failed += spruce_syncthing.run(card, layout_name, base, dry_run)` in `cli.py`'s `stage_spruce` after `spruce_settings.install`. Check where `spruce_emu_step` runs relative to `stage_spruce` in both the dry-run and real paths; if `spruce_emu.apply` can run after `run` with a plan read before it, move the call so `run` reads `Emu` configs after `spruce_emu.apply` (Review Focus 1).

- [ ] **Step 4: Run** `uv run python -m unittest discover -s tests` → all PASS.

- [ ] **Step 5: Commit** `feat(spruce): set matching cores and RetroArch save settings for syncthing`

---

### Task 3: Forced Spruce settings and the allowlist

**Files:**
- Modify: `src/sync_roms/spruce_settings.py` (`allowed`, `wanted_settings`, `install`)
- Test: `tests/test_spruce_settings.py`

**Interfaces:**
- Consumes: `spruce_syncthing.enabled()`, `forced_keys()`, `forced_settings(card)`.
- Produces: `allowed()` leaves out `forced_keys()` while `enabled()`; `wanted_settings()` drops saved values for forced keys silently while `enabled()` (no "aren't shared" warning for them); `install(card, ...)` applies `forced_settings(card)` after the saved `spruce_settings` in the same single write, with the same rules (existing section and key only, only `selected` changes). A forced key the file lacks: `ui.warn(f"{shown} has no {section} / {key}; update spruceOS for Syncthing saves to work")`. Forced lines read `   {section} / {key} = {value} (Syncthing)`. The early `return 0` when nothing is wanted must account for forced settings.

- [ ] **Step 1: Write failing tests** in `tests/test_spruce_settings.py` (card "c" device `anbernic-rg-sp`, file with all four keys at Spruce defaults `Custom`/`Custom`/`Prompt`/`False`):
  - `test_forced_settings_applied_by_default`: no settings → the four `selected` become `True`, `True`, `Always`, `True`; output names them with `(Syncthing)`.
  - `test_forced_beat_saved_values_silently`: saved `spruce_settings` `{"Emulator Settings": {"raAutoLoad": "False"}}` → `raAutoLoad` is `True`, stderr has no "aren't shared".
  - `test_no_wifi_device_keeps_syncthing_off`: device `miyoo-mini` → `enableSyncthing` stays `False`.
  - `test_off_uses_saved_values`: `spruce_syncthing: false` and saved `raAutoLoad: "False"` → `False`; nothing forced.
  - `test_allowlist_drops_forced_keys_only_while_on` (check `allowed()` both ways) and `test_import_skips_forced_keys_while_on` (card with `raAutoSave` differing from settings.json → not listed, not saved).
  - `test_missing_forced_key_warns`.
  - Update existing tests that assume an empty settings.json writes nothing (e.g. `test_nothing_set_does_nothing`, `test_no_rewrite_when_unchanged`) so they save `spruce_syncthing: false`, keeping what they test.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_spruce_settings -v` → new tests FAIL.

- [ ] **Step 3: Implement** in `spruce_settings.py` (import `spruce_syncthing` inside the functions if a top-level import is circular).

- [ ] **Step 4: Run** `uv run python -m unittest discover -s tests` → all PASS.

- [ ] **Step 5: Update** README's `config import` sentence and CLAUDE.md's `spruce_settings.py` paragraph: while `spruce_syncthing` is on, `raAutoSave`, `raAutoLoad`, `keepSavesBetweenCores` and `enableSyncthing` (WiFi devices only) are set by sync-roms and aren't imported.

- [ ] **Step 6: Commit** `feat(spruce): set syncthing's spruce settings instead of importing them`

---

### Task 4: Setup guide

**Files:**
- Modify: `src/sync_roms/data/setup-guide.html` (`SECTIONS`: the `syncthing` section; a new `retroarch-cores` section after it)
- Test: `tests/test_setup_guide.py`

**Interfaces:**
- Consumes: `data/syncthing.json` `cores` (test only).

- [ ] **Step 1: Write failing test** `test_cores_section_matches_spruce_syncthing`: for every `cores` value, the guide's text contains `<code>{core}</code>`; it also contains `jkx7j-mnlfo` and `w5nqg-xmpq6`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_setup_guide -v` → FAIL.

- [ ] **Step 3: Edit the guide** with the spec's "Setup guide" content. Only facts from the spec (it is the user's record; add nothing else):
  - spruceOS item: a "Set by sync-roms" list (the cores, the four Spruce settings, the RetroArch keys, all as in the data file; turned off with `sync-roms config set spruce_syncthing false`); by hand: WiFi, Advanced Settings > Network > Sync Time/RTC with network, web UI `http://<device IP>:8384` (login `spruce` / `happygaming`, change it under Settings > GUI), accept `ra-saves` (`jkx7j-mnlfo`) at `/mnt/SDCARD/Saves/saves` and `ra-states` (`w5nqg-xmpq6`) at `/mnt/SDCARD/Saves/states`, each folder's Edit > Advanced > `modTimeWindowS` = 2; Spruce waits for Syncthing at boot after WiFi connects and at save-and-shutdown (hold POWER), so leave a game that way before switching devices. Replace the old "sync checker ... launching a game and resuming" note.
  - Android item: Syncthing-Fork; RetroArch Settings > Directory: Save Files `/storage/emulated/0/RetroArch/saves`, Save States `/storage/emulated/0/RetroArch/states` (not under `Android/data`, which Syncthing-Fork can't read on Android 11+); Settings > Saving: Sort Saves/Save States into Folders by Core Name on, by Content Directory off, Write Saves/Save States to Content Directory off, SaveRAM Autosave Interval 10 seconds, Auto Save State on, Auto Load State on; Main Menu > Configuration File > Save Current Configuration; share `ra-saves`/`ra-states` (same IDs) to those two folders; run conditions so Syncthing-Fork runs when switching. ES-DE: each system's alternative emulator set to the core in "RetroArch cores".
  - Pair and share: on the server, Staggered or Simple file versioning on both folders.
  - Notes: states sync now (matching cores); a state from another core version can fail to load, the in-game save still applies; RetroAchievements Hardcore turns auto load off; one of Syncthing or RetroArch Cloud Sync per device. Remove "Sync the in-game saves only, not save states".
  - New `retroarch-cores` section ("RetroArch cores", `when: { layout: ["esde", "spruce"] }`): a table of system → core (`<code>core id</code>`), one row per `cores` entry using the system names from `systems.json`; the table is for every device, not only Spruce, plus the fixed-core systems the spec lists as already matching; then a line: N64, Saturn, Dreamcast and Jaguar keep each device's own core and sync only between Spruce devices or between Android devices; Mega Duck doesn't sync with Android.

- [ ] **Step 4: Run** `uv run python -m unittest discover -s tests` → all PASS. Open the page (`uv run sync-roms guide` or the file) with the Spruce RG SP and an ES-DE device picked and check both sections render.

- [ ] **Step 5: Commit** `docs(guide): cover syncthing saves and states between spruce and android`
