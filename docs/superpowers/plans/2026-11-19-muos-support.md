# muOS Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring back the `muos` layout with full parity (scraping, collections, Surprise, collection art, saves, flash, guide), writing only to paths confirmed in the muOS 2606.0 docs and source.

**Architecture:** Restore the removed muOS data and scraping by reverting `16febdc`, then add muOS-specific modules beside the existing frontend code: `muos_collections.py` (collection `.cfg` files and their art) and `muos_saves.py` (Pickles saves), dispatched from `cli.py` and `saves.py` on `layout_name == "muos"`. Anything whose location isn't known (PICO-8 install) is skipped with a warning.

**Tech Stack:** Python 3 stdlib, `unittest` (`python -m unittest discover -s tests`), the repo's JSON data files.

**Spec:** `docs/superpowers/specs/2026-11-19-muos-support-design.md`

## Global Constraints

- Commits and the PR title use Conventional Commits, imperative and lowercase (`feat(muos): ...`); end commit messages with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Never put backup or test files in the bucket; tests use temp folders. No real game lists in the repo.
- Repo files must not contain notes about the bucket's contents.
- Don't touch other layouts' behavior; their tests must keep passing.
- Collection `.cfg` entry: `MUOS/info/collection/<collection folder>/<ROM stem>-<%08X of FNV-1a 32 over line 1's UTF-8 bytes>.cfg`, three `\n`-separated lines: `<mount>/ROMS/<folder>/<rel>`, `<folder>[/<subdir of rel>]`, `<ROM stem>`. FNV-1a 32: offset basis `2166136261`, prime `16777619`.
- Mount is `/mnt/mmc` (SD1) or `/mnt/sdcard` (SD2), from the card's `muos_storage` field (`"sd1"` default, `"sd2"`).
- Collection art: `MUOS/info/catalogue/Collection/box/<collection folder>.png` and `.../grid/<collection folder>.png`.
- Pickles saves: `MUOS/pickles/sram/<core>[/<ROM dir>]/<stem>.srm|.rtc`; states `MUOS/pickles/state/<core>[/<ROM dir>]/<stem>/` holding `slot_N.state` and `states.ini` (Pickles' own format; copied, never converted). `<ROM dir>` is the ROM's folder path under `ROMS/`.
- Not implemented on muOS, with a printed warning: the PICO-8 install.

## Review Focus

- A ROM in a subfolder (`GBA/hacks/x.gba`): collection line 2 is `GBA/hacks`; the Pickles save sits under `<core>/GBA/hacks/`.
- A non-ASCII ROM name: the hash is over the UTF-8 bytes of line 1.
- `muos_storage` set to anything but `sd1`/`sd2`: warn and write no collections (no guessing a mount).
- A Pickles folder whose name differs in case from the system's muOS folder (`gba` vs `GBA`): still maps to that system.
- `saves apply` onto a file that already differs: existing "differs" handling asks, nothing is silently overwritten.
- A collection name with characters ES-DE rejects: the folder name uses `frontend.safe_name`.

---

### Task 1: Restore the muOS layout, data, devices and scraping

**Files:**
- Modify (via revert): `src/sync_roms/data/layouts.json`, `systems.json`, `devices.json`, `src/sync_roms/scrape_plan.py`, `src/sync_roms/pico8.py`, `README.md`, `CLAUDE.md`, `tests/test_firmware.py`, `tests/test_firmware_scrapes.py`, `tests/test_completion.py`, `tests/test_pico8.py`
- Modify: `src/sync_roms/data/layouts.json` (add `"pickles"` block, update note)

**Interfaces:**
- Produces: layout id `"muos"` in `layouts.json` with `roms_dir` `ROMS`, `bios_dir` `MUOS/bios`, `"pickles": {"dir": "MUOS/pickles"}` and no `retroarch` block; every system in `systems.json` has `folders["muos"]` (string or `null`) and, when set, `muos_catalogue`; `muos` in `firmwares` after `knulli` for the 13 devices listed in the removed diff (`anbernic-rg-cubexx`, `-rg-sp`, `-rg-vita-pro`, `-rg28xx`, `-rg34xx`, `-rg34xx-sp`, `-rg35xx-2024`, `-rg35xxh`, `-rg35xx-plus`, `-rg35xx-pro`, `-rg35xx-sp`, `-rg40xxh`, `-rg40xxv`).

- [ ] **Step 1: Run `git revert --no-commit 16febdc`.** It conflicts in `CLAUDE.md`, `devices.json`, `scrape_plan.py`, `tests/test_firmware.py` and `tests/test_firmware_scrapes.py`. Resolve each by keeping the current file's newer content and re-adding the removed muOS lines (the conflict hunks show both sides). For `systems.json`, systems added since #360 get `"muos": null` and no `muos_catalogue`; list them in the commit message body.
- [ ] **Step 2: Run `python -m unittest discover -s tests`; expect PASS** (the reverted tests include muOS catalogue and folder tests, including `test_muos_bios_dir_is_nested`).
- [ ] **Step 3: Edit `layouts.json` `muos`:** add `"pickles": {"dir": "MUOS/pickles"}`, and rewrite `note` for 2606.0 (card root is the games partition; folder names are matched ignoring case and `-_+` and spaces; systems with `muos = null` have no muOS system; sources `https://muos.dev/docs/infrastructure/storage`, `https://muos.dev/installation/catalogue`).
- [ ] **Step 4: Edit `pico8.py`:** remove the `muos` PICO-8 target if the revert restored one with `.muxzip`; add `def muos_notice(layout_name) -> bool` that prints `ui.warn("PICO-8 isn't installed on muOS: where an installable package must go isn't documented")` once per call and returns `True` for `"muos"`; call it at the top of `run()` and return `0` (no failure). Test in `tests/test_pico8.py`: `test_muos_card_skips_pico8_with_a_warning` asserts `run("c", "muos", tmp, False) == 0`, no files written, warning printed.
- [ ] **Step 5: Run the full suite; expect PASS.**
- [ ] **Step 6: Commit** `feat(muos): restore the muos layout, devices and catalogue scraping`.

### Task 2: Card setting `muos_storage` and its validation

**Files:**
- Modify: `src/sync_roms/commands.py` (card validation near the `'pico8'` check; `CARD_FIELDS` unchanged)
- Create: `src/sync_roms/muos_collections.py` (constants only for now)
- Test: `tests/test_muos_collections.py`

**Interfaces:**
- Produces in `muos_collections.py`: `MOUNTS = {"sd1": "/mnt/mmc", "sd2": "/mnt/sdcard"}`; `def mount(entry: dict) -> str | None` (the mount for a cards.json entry's `muos_storage`, default `"sd1"`; `None` when the value isn't a key of `MOUNTS`).

- [ ] **Step 1: Write failing tests:** `test_mount_defaults_to_sd1` (`mount({}) == "/mnt/mmc"`), `test_mount_sd2` (`mount({"muos_storage": "sd2"}) == "/mnt/sdcard"`), `test_mount_unknown_is_none` (`mount({"muos_storage": "usb"}) is None`), and in `tests/test_commands.py` a check problem `cards.json: <name>: 'muos_storage' must be sd1 or sd2` for `"usb"`.
- [ ] **Step 2: Run them; expect FAIL.**
- [ ] **Step 3: Implement `mount` and the validation line** in the style of the neighboring `pico8` check.
- [ ] **Step 4: Run them; expect PASS. Commit** `feat(muos): add the muos_storage card setting`.

### Task 3: muOS collections written to the card

**Files:**
- Modify: `src/sync_roms/muos_collections.py`, `src/sync_roms/cli.py` (`frontend_step`, near line 1214), `src/sync_roms/surprise.py:40` (`default_on`), `src/sync_roms/cli.py:85-86` (help text)
- Test: `tests/test_muos_collections.py`, `tests/test_surprise.py`

**Interfaces:**
- Consumes: `mount(entry)`; `frontend.safe_name`, `downloads.rom_rel(bucket_key)`, `store.replace_file`, `cardfs.exists/write_text`.
- Produces in `muos_collections.py`:
  - `fnv1a32(data: bytes) -> int`
  - `entry_lines(mount: str, folder: str, rel: str) -> list[str]` (the three lines above; `rel` may contain `/`)
  - `entry_path(base: str, collection: str, folder: str, rel: str, mount: str) -> str` (the `.cfg` path on the card)
  - `wanted(collections, systems, on_card, mount) -> {safe name: {path: text}}` (same inputs as `frontend.wanted_collections`)
  - `plan(base, wanted, owned) -> dict` with the keys of `frontend.plan_collections` (`writes`, `deletes`, `enable`, `disable`, `owned`, `warnings`) and, for a collection no longer wanted, deletes of its folder's `.cfg` files; an unowned existing folder is skipped with a warning
  - `apply(plan) -> None`, `describe(plan) -> None`

- [ ] **Step 1: Write failing tests:** `test_fnv1a32_known_values` (`fnv1a32(b"") == 2166136261`, `fnv1a32(b"a") == 0xE40C292C`); `test_entry_lines_for_a_top_level_rom` (`entry_lines("/mnt/mmc", "GBA", "Game.gba") == ["/mnt/mmc/ROMS/GBA/Game.gba", "GBA", "Game"]`); `test_entry_lines_for_a_subfolder_rom` (`"GBA/hacks/Game.gba"` gives line 2 `"GBA/hacks"`); `test_entry_path_name_has_stem_and_eight_hex_digits` (matches `Game-[0-9A-F]{8}\.cfg` under `MUOS/info/collection/<name>/`); `test_hash_is_over_utf8_bytes` (non-ASCII stem); `test_plan_skips_an_unowned_existing_collection_folder`; `test_plan_deletes_a_dropped_collection_files`; `test_surprise_defaults_on_for_muos` (`surprise.default_on({"layout": "muos"})`).
- [ ] **Step 2: Run them; expect FAIL.**
- [ ] **Step 3: Implement the functions above.** `fnv1a32` is the loop in the spec's Global Constraints. Collection folder = `frontend.safe_name(name)`. `plan`'s `owned` is the sorted wanted names, stored in the card's `frontend_collections` like the other layouts.
- [ ] **Step 4: Wire `cli.frontend_step`:** for `layout_name == "muos"`, call `muos_collections.mount(entry)`; when it is `None`, `ui.warn("muos_storage must be sd1 or sd2: collections skipped")` and return; else build and apply the muOS plan instead of `frontend.*` (dry run prints `describe`). Update `default_on` to treat `"muos"` as on. Keep the Surprise collection and `store.update_card(card, frontend_collections=...)` flow identical.
- [ ] **Step 5: Run the full suite; expect PASS. Commit** `feat(muos): write collections and Surprise as muOS collection entries`.

### Task 4: Collection art

**Files:**
- Modify: `src/sync_roms/themeart.py` (`install`/`describe`, near line 405-410), `src/sync_roms/muos_collections.py`
- Test: `tests/test_themeart.py`

**Interfaces:**
- Consumes: `themeart.art_path(art_id) -> path | None` (the existing function that returns `art/<id>.png`; use its real name from `themeart.py:90-96`); `arts: {collection name: art id}` as built in `cli.frontend_step`.
- Produces: `muos_collections.install_art(base: str, arts: dict) -> bool` (True when files changed) and `describe_art(base, arts)`.

- [ ] **Step 1: Write failing tests:** `test_install_art_copies_box_and_grid` (a temp card; the PNG lands at `MUOS/info/catalogue/Collection/box/<name>.png` and `.../grid/<name>.png`, returns True), `test_install_art_second_run_changes_nothing` (returns False), `test_install_art_removes_art_of_dropped_collections_it_wrote` (tracked in `MUOS/info/catalogue/Collection/.sync-roms-art`, one name per line, like `ESDE_OWNED`).
- [ ] **Step 2: Run them; expect FAIL.**
- [ ] **Step 3: Implement** `install_art`/`describe_art`; in `themeart.install`/`describe`, dispatch `layout_name == "muos"` to them before the ES-DE/Knulli branches.
- [ ] **Step 4: Run the full suite; expect PASS. Commit** `feat(muos): install collection art into the catalogue`.

### Task 5: Pickles saves

**Files:**
- Create: `src/sync_roms/muos_saves.py`
- Modify: `src/sync_roms/saves.py` (`stash_command`, `apply_command`, `scan`/`plan_apply` dispatch)
- Test: `tests/test_muos_saves.py`, `tests/test_saves.py`

**Interfaces:**
- Consumes: `saves.write_stash(card, layout_name, system, stem, core, entries, ...)` and the stash format (`files` hold flat `name` and `kind`); `layouts.json` `muos.pickles.dir`.
- Produces in `muos_saves.py`:
  - `scan(base, layout, systems) -> (games, skipped)` with the same shape as `saves.scan` (`{(system bucket, stem): [entry]}`); each entry adds `"rel"` (the path under `pickles/`'s `sram` or `state`, without the file name) and `core`, and has `kind` `"save"` or `"state"`; every file in a state folder (`slot_*.state`, `states.ini`) is one entry of that stem. A file whose first ROM-dir component matches no system's muOS folder (compared by lowercase with spaces, `-`, `_`, `+` removed) counts toward `skipped`.
  - `plan_apply(stash, base, layout, system, core) -> [(src, dst, "new"|"same"|"differs")]` writing saves to `sram/<core>/<folder>/<stem>.<ext>` and states to `state/<core>/<folder>/<stem>/<name>`, where `<folder>` is the stash's recorded ROM dir (stored in each entry of `stash.json` as `"rel"` through `write_stash`).

- [ ] **Step 1: Write failing tests** on a temp card tree: `test_scan_finds_a_save_and_maps_its_system`, `test_scan_groups_state_slots_and_states_ini_under_one_game`, `test_scan_maps_a_nested_rom_dir`, `test_scan_matches_folder_case_insensitively`, `test_scan_skips_unknown_folders_and_counts_them`, `test_plan_apply_writes_the_same_relative_paths`, `test_plan_apply_marks_a_differing_file_as_differs`; and in `tests/test_saves.py` `test_stash_and_apply_round_trip_on_a_muos_card`.
- [ ] **Step 2: Run them; expect FAIL.**
- [ ] **Step 3: Implement `muos_saves.py`; make `write_stash` store each entry's `rel` and `core` when present** (backward compatible for existing stashes: `rel` optional). In `saves.stash_command`/`apply_command`, use `muos_saves` when `"pickles" in layout`; the other layouts' code paths stay as they are, and `broken_links`/`core_folders` aren't called for muOS.
- [ ] **Step 4: Run the full suite; expect PASS. Commit** `feat(muos): stash and apply Pickles saves and states`.

### Task 6: Flash muOS images

**Files:**
- Modify: `src/sync_roms/flash.py` (`knulli_devices`, `images`, `run`), `tests/test_flash.py`

**Interfaces:**
- Produces: `devices_for(devices, firmware: str) -> list`, `images(listing, firmware: str = "knulli") -> list[str]` (for `"muos"`: keys matching `os/muos-*.img.gz`); in `run`, a picker `Which firmware?` shown only when storage has images for both.

- [ ] **Step 1: Write failing tests:** `test_images_lists_muos_images`, `test_images_knulli_default_is_unchanged`, `test_devices_for_muos_keeps_input_order`, `test_muos_images_are_never_marked_as_matching` (no `✓ matches` for muOS, since names aren't documented).
- [ ] **Step 2: Run them; expect FAIL.**
- [ ] **Step 3: Implement**, keeping `knulli_devices` as an alias of `devices_for(devices, "knulli")` if other code uses it; the existing write/verify path is unchanged.
- [ ] **Step 4: Run the full suite; expect PASS. Commit** `feat(muos): flash muOS images from storage`.

### Task 7: Setup guide, README, CLAUDE.md

**Files:**
- Modify: `src/sync_roms/data/setup-guide.html` (via `tools/update_setup_guide.py`), `README.md`, `CLAUDE.md`
- Test: `tests/test_setup_guide.py`, `tests/test_readme.py`

- [ ] **Step 1: Run `python tools/update_setup_guide.py`** so the embedded device list shows `muos` firmwares; add a `muos` entry to the guide's firmware label map (as `knulli` has one) and no steps (Kelsin hasn't given any).
- [ ] **Step 2: Edit README** (layouts table row, scrape table row, a short "muOS" note: `muos_storage`, the not-implemented PICO-8 warning, and flashing) and **CLAUDE.md** (the `muos` layout in the data-files notes: collections, collection art, Pickles saves, PICO-8 skipped; keep the "no notes about the bucket" rule).
- [ ] **Step 3: Run `python -m unittest discover -s tests`; expect PASS.**
- [ ] **Step 4: Commit** `docs(muos): document muOS support`.
