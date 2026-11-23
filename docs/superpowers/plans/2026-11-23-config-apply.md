# `config apply` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms config apply [CARD] [--dry-run] [--yes]` writes the saved settings onto a mounted spruce card, or over adb onto an Android device (RetroArch's `retroarch.cfg`, ES-DE's per-system emulators and missing APKs from storage), turning RetroArch Cloud Sync off.

**Architecture:** Every setting is an `applied.Entry` (where, key, old, new, secret). The spruce modules and a new `android_settings.py` produce entry lists; `--dry-run` prints them all, a real run writes. Spruce real runs reuse the existing `install`/`run` functions unchanged. Android files are pulled to a temp folder, edited as text by pure functions, and changed ones pushed back.

**Tech Stack:** Python 3.12+ stdlib, `unittest`, adb via `sync_roms.adb`.

**Spec:** `docs/superpowers/specs/2026-11-23-config-apply-design.md`

## Global Constraints

- Run everything with `uv run`; tests: `uv run python -m unittest discover -s tests`. Code must run on Python 3.12.
- Every test module that imports `sync_roms` imports `isolate` first (directly or through `helpers`).
- Never print a password, token or API key: secret entries show `(hidden)`.
- Never write RetroArch's cfg while RetroArch runs (`android.wait_closed`).
- A file that can't be parsed is warned about and skipped, never overwritten; lines other than the listed keys are kept byte for byte (line ends included).
- Only `adb.py` runs adb.
- Conventional Commits, lowercase imperative; end each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Sync's own output and behaviour are unchanged.

## Review Focus

- `retroarch.cfg` with CRLF line ends, or a key present twice: only the listed keys change, CRLF kept. Test in Task 2.
- `spruce_ra_mode` `Manual` or unset, and no `spruce_ra_*` at all: no `cheevos_*` entry. Test in Task 2.
- A gamelist with an existing `<alternativeEmulator>` (another label) or none, or no file: exactly one block, with the new label, before `<gameList>`. Test in Task 2.
- No CARD and the current folder is a card of another layout (e.g. `onion`): exit 2 naming the supported layouts, never the device picker. Test in Task 4.
- Device lost mid-apply (`adb.AdbError`): exit 1 with "Lost the connection", temp folder removed. Test in Task 3.

---

### Task 1: `applied.Entry` and the spruce entry lists

**Files:**
- Create: `src/sync_roms/applied.py`
- Modify: `src/sync_roms/spruce_settings.py`, `src/sync_roms/spruce_wifi.py`, `src/sync_roms/spruce_syncthing.py`
- Test: `tests/test_applied.py`, `tests/test_spruce_settings.py`, `tests/test_spruce_wifi.py`, `tests/test_spruce_syncthing.py`

**Interfaces:**
- Produces: `applied.Entry = namedtuple("Entry", "where key old new secret")` (`old` is `None` when the key is missing; `secret` bool). `applied.changed(entry) -> bool` (`old != new`). `applied.show(entries, dry_run) -> None`: groups by `where` in order; per entry a line `   would set   KEY = NEW (was OLD)` / `   already set KEY = NEW` in a dry run (`(was missing)` when `old is None`), and in a real run only changed ones as `   KEY = NEW`; secrets print `(hidden)` for both values. Dry-run headers are `ui.dim("🧪 Dry run: " + where)`.
- Produces: `spruce_settings.entries(card, base) -> list[Entry]` (where `Saves/spruce/spruce-config.json`; keys `RetroAchievements Settings / <key>`, `<section> / <key>`, the Syncthing ones with ` (Syncthing)` appended to the key; secrets: `password`, `webApiKey`; `[]` when the file is missing or unreadable, with the same warnings as `install`). Allowlisted `spruce_settings` entries whose section/key the file lacks are left out, like `install`.
- Produces: `spruce_wifi.entries(base) -> list[Entry]` (where `Saves/spruce/wpa_supplicant.conf`, key `network <ssid>`, new `"present"`, old `"present"` when the SSID block exists with the same psk else `None`/`"different"`; secret False — the psk is never in the entry).
- Produces: `spruce_syncthing.entries(card, base) -> list[Entry]`: one per Emu folder core (where `Emu/<folder>/config.json`, key `core`) and per `retroarch-*.cfg` key (where `Saves/ra-configs/<file>`); `[]` when off. Reuse `core_writes`/`retroarch_writes` internals rather than duplicating the parsing (factor a helper that yields old and new values if needed).

- [ ] **Step 1: Write failing tests**

`tests/test_applied.py`: `test_show_dry_run_lists_every_entry` (two entries, one changed, one not, one secret: output has `would set`, `already set`, `(hidden)` and never the secret value), `test_show_real_run_lists_only_changed`.
In each spruce test file add `test_entries_lists_unchanged_too`: a card where one setting already has its value and one differs → both entries, `old` correct; and for `spruce_settings`, `test_entries_hides_password` (`secret` True for `password`).

- [ ] **Step 2: Run to see them fail** — `uv run python -m unittest tests.test_applied tests.test_spruce_settings tests.test_spruce_wifi tests.test_spruce_syncthing` → FAIL (no `applied`, no `entries`).
- [ ] **Step 3: Implement** the functions above. `install`/`run` keep their output exactly (existing tests prove it).
- [ ] **Step 4: Run the whole suite** → PASS.
- [ ] **Step 5: Commit** `feat(config): list every spruce setting as an entry`

### Task 2: Android settings as pure text edits

**Files:**
- Create: `src/sync_roms/android_settings.py`
- Modify: `src/sync_roms/data/syncthing.json` (add `esde_labels`), the test that checks `syncthing.json`'s shape (find it with `grep -rn syncthing.json tests`)
- Test: `tests/test_android_settings.py`

**Interfaces:**
- Consumes: `applied.Entry`, `spruce_syncthing.data()`, `spruce_syncthing.enabled()`, `usersettings.load_settings()`, `android.parse_config`, `android.DEFAULT_SAVES/DEFAULT_STATES`.
- Produces: `android_settings.CFG = "retroarch.cfg"`; `cfg_wanted() -> dict[str, str]` (key → value, in this order: Syncthing `retroarch` keys and `savefile_directory`/`savestate_directory` when Syncthing is on; RetroAchievements; Cloud Sync); `cfg_entries(text, wanted) -> list[Entry]` (where `retroarch.cfg`; secret for `cheevos_password`, `webdav_password`, `cheevos_token`; adds `cheevos_token = ""` only when `cheevos_username` changes and the file has a non-empty token); `cfg_apply(text, entries) -> str` (replace each changed key's line(s) with `KEY = "VALUE"`, append missing keys, keep line ends — the approach of `spruce_syncthing.retroarch_writes`).
- Produces: `gamelist_entry(system_folder, text_or_None, label) -> Entry` (where `ES-DE/gamelists/<folder>/gamelist.xml`, key `alternativeEmulator`, old the current label or `None`); `gamelist_apply(text_or_None, label) -> str`; `esde_wanted(folders) -> list[tuple[folder, label]]` for the Syncthing cores (via `systems.json` `folders.esde` and `esde_labels`), `[]` when Syncthing is off.
- Values pinned by the spec:
  - RA mode: `Disabled` → `cheevos_enable "false"`; `Casual`/`Softcore` → `cheevos_enable "true"`, `cheevos_hardcore_mode_enable "false"`; `Hardcore` → both `"true"`; `Manual`/unset → neither. `spruce_ra_username` → `cheevos_username`, `spruce_ra_password` → `cheevos_password`.
  - Cloud Sync (always): `cloud_sync_enable "false"`, `webdav_url ""`, `webdav_username ""`, `webdav_password ""`.
  - `esde_labels`: `{"ardens": "Ardens", "handy": "Handy", "bluemsx": "blueMSX", "fbneo": "FinalBurn Neo", "fceumm": "FCEUmm", "genesis_plus_gx": "Genesis Plus GX", "gambatte": "Gambatte", "mgba": "mGBA", "mednafen_ngp": "Beetle NeoPop", "pcsx_rearmed": "PCSX ReARMed", "snes9x": "Snes9x - Current"}`. Update its `note` to say Android gets them from `config apply`. The shape test checks every `cores` value has a label.
  - Gamelist block, inserted after the XML declaration (or at the top) and before `<gameList>`: `<alternativeEmulator>\n\t<label>LABEL</label>\n</alternativeEmulator>\n` (ES-DE's own format, tabs); a missing file becomes `<?xml version="1.0"?>\n` + block + `<gameList />\n`. An existing block is replaced in place. XML-escape the label.

- [ ] **Step 1: Write failing tests** in `tests/test_android_settings.py`: `test_cfg_wanted_by_mode` (each mode), `test_cfg_wanted_clears_cloud_sync`, `test_cfg_wanted_without_syncthing` (no save keys, Cloud Sync still cleared), `test_cfg_entries_marks_unchanged`, `test_cfg_username_change_clears_token`, `test_cfg_apply_keeps_crlf_and_other_lines`, `test_cfg_apply_appends_missing_key`, `test_gamelist_replaces_existing_label`, `test_gamelist_inserts_before_gamelist`, `test_gamelist_creates_missing_file`, `test_esde_wanted_maps_cores` (`nes` → `("nes", "FCEUmm")`, `sg1000` → `("sg-1000", "Genesis Plus GX")`), and a shape test that every `cores` value is in `esde_labels`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_android_settings` → FAIL.
- [ ] **Step 3: Implement** `android_settings.py` pure functions and the data change.
- [ ] **Step 4: Run the whole suite** → PASS.
- [ ] **Step 5: Commit** `feat(android): plan retroarch and es-de settings edits`

### Task 3: Android apply over adb

**Files:**
- Modify: `src/sync_roms/android_settings.py`, `src/sync_roms/adb.py` (only if a helper is missing)
- Test: `tests/test_android_settings.py`

**Interfaces:**
- Consumes: Task 2 functions; `android.Target`, `android.retroarch_package(serial)`, `android.wait_closed(serial, pkg)`, `adb.shell/pull/push/is_dir`, `ui.confirm`, `ui.ASSUME_YES`, `applied.show`.
- Produces: `android_settings.apply(target, layout, systems, dry_run) -> int` (0, or 1 when a push fails; `adb.AdbError` propagates to the caller).
- Behaviour:
  1. `pkg = retroarch_package`; pull `/storage/emulated/0/Android/data/<pkg>/files/retroarch.cfg` into a temp dir (`tempfile.mkdtemp(prefix="sync-roms-apply-")`, removed in `finally`). Missing/unreadable → warn, skip the RetroArch part.
  2. ES-DE: for each `esde_wanted` folder whose `/storage/<volume>/<roms_dir>/<folder>` exists (`adb.is_dir`), pull `/storage/<volume>/ES-DE/gamelists/<folder>/gamelist.xml` when it exists.
  3. `applied.show(all entries, dry_run)` with `where` prefixed by nothing for the cfg (`retroarch.cfg`) and the ES-DE path. Dry run stops here.
  4. RetroArch part, when any cfg entry changed: `wait_closed`, then push.
  5. ES-DE part, when any gamelist changed: `ui.confirm("ES-DE must restart to see the new emulators. Close it now?", default=True)` (skipped by `--yes`; declining skips the ES-DE writes with a dim note); `adb.shell(serial, "am", "force-stop", "org.es_de.frontend")`, `mkdir -p` and push each changed gamelist, then `adb.shell(serial, "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")`.
  6. A failed push is listed (`ui.warn`) and makes the result 1.

- [ ] **Step 1: Write failing tests** with `adb` mocked (style of `tests/test_android.py`): `test_apply_dry_run_writes_nothing` (no `push`, no `force-stop`), `test_apply_pushes_only_changed_cfg` (cfg already right → no push, no `wait_closed`), `test_apply_restarts_esde_after_writing_gamelists` (order: force-stop, push, am start), `test_apply_declined_esde_skips_gamelists`, `test_apply_lost_device_removes_temp` (`pull` raises `AdbError` → raises, temp dir gone).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `apply`.
- [ ] **Step 4: Run the whole suite** → PASS.
- [ ] **Step 5: Commit** `feat(android): apply settings over adb`

### Task 4: APK installs

**Files:**
- Create: `src/sync_roms/apk.py` (manifest reading), `src/sync_roms/data/android-apks.json`
- Modify: `src/sync_roms/android_settings.py` (call it from `apply`), `src/sync_roms/adb.py` (`exec_out(serial, *words) -> bytes`, `install(serial, local)`)
- Test: `tests/test_apk.py`, `tests/test_android_settings.py`; the data shape test for the new file

**Interfaces:**
- Consumes: `inventory.files(runtime.APKS_PREFIX, sizes=True)`, `s3.download(job)` (see how `cli.py` builds `apk_jobs` near line 1280 and `downloads.with_sizes`), `store.card_flag(card_entry, "raofflineproxy")`, the device's tier from `device-systems.json` and the tier order of its `tiers` chain, the device's resolved systems (`store` loader used by the editors, overlay applied) and `screen2` from `devices.json`.
- Produces: `apk.package(manifest_bytes) -> str` (the `package` attribute of the root `<manifest>` element in Android binary XML: parse the string pool (UTF-8 and UTF-16) and the first START_ELEMENT's attributes; `ValueError` on anything else). `android_settings.apk_rules(card_name) -> callable(file_name) -> str | None` (`None` = install, else the skip reason). `android_settings.apk_entries(...)` and the install step inside `apply`.
- `android-apks.json`: `{"note": "...", "apks": [{"prefix": "dawn-zero", "never": true}, {"prefix": "gamenative", "tier": "switch"}, {"prefix": "DroidDeck", "tier": "switch"}, {"prefix": "Eden", "systems": ["switch"]}, {"prefix": "gba-ds", "dualscreen": true}]}`; note says why, concisely (dawn-zero isn't needed; Steam apps only from the Retroid Pocket Nova's tier up, Eden only where the device plays Switch; gba-ds needs two screens).
- Skip reasons printed: `not needed`, `device is below the Nova's tier`, `device doesn't play Switch`, `not a dual-screen device`, `RAOfflineProxy is off for this card`.

- [ ] **Step 1: Write failing tests**: `tests/test_apk.py` builds a minimal binary manifest in a helper (string pool with `manifest`, `package`, `com.example.app`; one START_ELEMENT) in both UTF-8 and UTF-16 pools → `apk.package` returns `com.example.app`; garbage → `ValueError`. In `test_android_settings.py`: `test_apk_rules` (dawn-zero never; gamenative on `retroid-pocket-nova` (tier `switch`) and `full` vs `retroid-pocket-mini` (tier `wii-3ds`) even with `switch` added by the overlay; Eden on a switch device vs `retroid-pocket-mini`; gba-ds on `retroid-pocket-duo` vs `retroid-pocket-nova`; RAOfflineProxy with the card flag off; `full` installs all but dawn-zero; `.json` files ignored), `test_apply_installs_only_missing_packages` (installed package → `already installed`, no install call), `test_apply_installs_from_card_copy_when_same_size` (`pm install /storage/<vol>/APKs/<file>`, no download), `test_apply_falls_back_to_storage_when_pm_install_fails`, `test_apply_dry_run_lists_every_apk` (no install calls, every APK listed with its state).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** APKs are handled after the RetroArch and ES-DE parts; an unreadable manifest is warned about and that APK skipped; a failed install is warned and makes the result 1.
- [ ] **Step 4: Run the whole suite** → PASS.
- [ ] **Step 5: Commit** `feat(android): install missing apks over adb`

### Task 5: The `config apply` command

**Files:**
- Create: `src/sync_roms/settings_apply.py`
- Modify: `src/sync_roms/commands.py` (`config_cmd`, the `config` parser's `action` choices, `words["config"]`), `src/sync_roms/cli.py` (`SUBCOMMANDS["config"]` usage, `TOPICS["config"]`), `README.md` (Commands table row and the Settings paragraph)
- Test: `tests/test_settings_apply.py`; `tests/test_readme.py` must still pass

**Interfaces:**
- Consumes: Task 1 `entries` functions and `applied.show`; `spruce_settings.install`, `spruce_wifi.install`, `spruce_syncthing.run`; Task 3/4 `android_settings.apply`; `android.resolve`, `android.is_android`; `store.load_cards`, `store.load_catalog`.
- Produces: `settings_apply.run(card_arg, dry_run) -> int`.
- Resolution (mirrors `saves._card`):
  - CARD is an existing folder, or names a saved non-Android card → mounted card: folder = CARD, or `/Volumes/<CARD>` for a name (as `commands.import_settings`); the card name is the folder's basename and must be saved.
  - No CARD and `basename(cwd)` is a saved card → that folder.
  - Mounted card with layout `spruce`: dry run → `applied.show(spruce_settings.entries + spruce_wifi.entries + spruce_syncthing.entries, True)`; else call the three existing functions and sum failures. Exit 1 when any failed.
  - Mounted Android card (`is_android`): exit 2, `"Android cards are applied over adb: run `sync-roms config apply <name>` without a folder"`. Any other layout: exit 2, `"config apply supports spruce cards and Android devices, not <layout>"`.
  - CARD names an Android card, or no CARD and the cwd isn't a card: needs a terminal (exit 2 otherwise), `adb.require(mounted=True)` when no CARD, `android.resolve(CARD, cards, catalog["layouts"]["esde"]["roms_dir"])`, then `android_settings.apply(target, catalog["layouts"][layout], catalog["systems"], dry_run)`. `adb.AdbError` → `ui.fail(f"Lost the connection to the device: {e}", 1)`.
- `config apply` takes only CARD (a second word → exit 2, like `import`).

- [ ] **Step 1: Write failing tests**: `test_apply_spruce_card_by_name`, `test_apply_spruce_from_cwd`, `test_apply_spruce_dry_run_lists_all` (unchanged setting shows `already set`, file unchanged), `test_apply_other_layout_cwd_refused` (exit 2, `android.resolve` not called), `test_apply_mounted_android_refused`, `test_apply_no_card_opens_device_picker` (`android.resolve` mocked, called with `None`), `test_apply_android_card_name_resolves_it`, `test_apply_lost_device_exits_1`, plus parser tests that `config apply` and `config apply CARD` parse and `config apply a b` exits 2.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `settings_apply.run` and wire `config_cmd` (`if args.action == "apply": return settings_apply.run(name, args.dry_run)`), the parser choice, completion words, help and README.
- [ ] **Step 4: Run the whole suite** → PASS (includes `test_readme`).
- [ ] **Step 5: Commit** `feat(config): add config apply for spruce cards and android devices`

### Task 6: Guide and project notes

**Files:**
- Modify: `src/sync_roms/data/setup-guide.html`, `CLAUDE.md`
- Test: `tests/test_setup_guide.py`

- [ ] **Step 1: Edit the guide**: delete the `cloudsync` section (id `cloudsync`); in the Syncthing "Notes" item drop the "Syncthing and RetroArch Cloud Sync both touch saves" line; in "Android and desktop", replace the RetroArch Directory/Saving/Save Configuration steps and the ES-DE alternative-emulator step with one step: `Run <code>sync-roms config apply</code> with the device on Wireless debugging: it sets RetroArch's save and state folders and save settings, turns Cloud Sync off, and sets each system's ES-DE emulator to its core in "RetroArch cores" (RetroArch closed; ES-DE restarts).`; in the "RetroArch cores" lede replace "on Android set each system's alternative emulator in ES-DE to it" with "Android gets them from <code>sync-roms config apply</code>". Remove any other reference to Cloud Sync (`grep -n -i "cloud" setup-guide.html`). In the "Install the apps" section, add a first item: `<code>sync-roms config apply</code> installs the card's APKs over Wireless debugging (all but those that don't fit the device); the steps below are the way by hand.`
- [ ] **Step 2: CLAUDE.md**: in Setup guide, change "The RetroAchievements and Cloud saves sections (RetroArch Cloud Sync against `https://cloud-saves.valefor.com/dav/`) hold login and sync settings" to "The RetroAchievements section holds login settings"; in "What sync puts on a card" add a bullet: "`config apply [CARD]` (`settings_apply.py`) applies a spruce card's settings (the spruce settings, WiFi and Syncthing steps of sync) without a sync, or over adb an Android device's (`android_settings.py`: missing APKs from `os/android/APKs/` by the rules in `android-apks.json`; RetroArch's `retroarch.cfg` Syncthing save keys, folders and RetroAchievements from `spruce_ra_*`, Cloud Sync off; ES-DE's `<alternativeEmulator>` per system from `syncthing.json`'s `cores` and `esde_labels`, restarting ES-DE). `--dry-run` lists every setting, changed or not."
- [ ] **Step 3: Run the whole suite** → PASS.
- [ ] **Step 4: Commit** `docs(guide): replace cloud sync with config apply for android`
