# PortMaster on spruce cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Search and download PortMaster ports into storage, stage picked ports for PortMaster's autoinstall on 64-bit spruce cards, and get users' game data for paid ports from storage onto every card that has the port.

**Architecture:** A catalogue module (`portmaster_catalog.py`) caches PortMaster's `ports.json`; `portmaster_store.py` downloads ports and runtimes into storage and records each port's install facts in `scrapes/ports/metadata.json`; `portmaster.py` is the per-card sync step (installed-port detection, autoinstall staging, game data copy, needed list, summary); `ports` commands live in `commands.py` with thin wrappers. `Roms/PORTS` on spruce is PortMaster's: sync never copies zips there, sweeps it, or touches its `Imgs/`.

**Tech Stack:** Python 3.12+ stdlib (`urllib` through `github.get`, `zipfile` not needed), existing `s3.py`/`inventory.py`/`shared.py`/`store.py`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-25-portmaster-spruce-design.md`

## Global Constraints

- Run everything with `uv run`; tests: `uv run python -m unittest discover -s tests` (stdin closed: `</dev/null`). Code must run on Python 3.12.
- Test modules import `isolate` first (directly or via `helpers`).
- Storage access only through `s3.py`, `inventory.py`, `shared.py`; catch `s3.ERRORS`; `s3.check_root()` before treating a missing file as absent. Never call `s3.list_sizes`/`stat_sizes`/`list_with_etags`/`list_folders` outside `inventory.py`.
- Storage paths: port zips `ports/<zip>`; runtimes `os/portmaster/runtimes/<name>.squashfs`; game data `os/portmaster/gamedata/<port folder>/...`; titles and port facts `scrapes/ports/metadata.json`.
- Card paths (spruce): ports `Roms/PORTS/`; PortMaster control folder `Persistent/portmaster/PortMaster/`; autoinstall `Persistent/portmaster/PortMaster/autoinstall/`; runtimes `Persistent/portmaster/PortMaster/libs/`.
- Catalogue URL: `https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json`; cache `store.cache_dir()/portmaster/ports.json`, refreshed when older than 86400 s or with `--refresh`; never fetched during a sync.
- Only ports whose `attr.arch` contains `aarch64` or is empty/absent; only runtimes whose name has no `.armhf.`/`.x86_64.` part.
- Device flag `"portmaster": true` in `devices.json` on: every `anbernic-*` device listing `spruce` in `firmwares`, `magicx-zero40`, `miyoo-flip`, `trimui-brick`, `trimui-brick-hammer`, `trimui-brick-pro`, `trimui-smart-pro`, `trimui-smart-pro-s`. Not `miyoo-a30` or `miyoo-mini*`.
- sync-roms never deletes, overwrites or updates an installed port, its folder, its saves or a runtime in `libs/`.
- Personal file `store.data_dir()/ports-needed.json`, written with `store.write_json(..., **store.PRETTY)`; dry runs never write it.
- New card fields (absent when empty, sorted string lists): `portmaster_data`, `portmaster_staged`, `portmaster_ports`. Add to `data/cards.schema.json`, `commands.check_data`'s list-of-names loop, `tests/test_editor_data.py`'s schema key list, and CLAUDE.md's Card fields table.
- Conventional Commits, lowercase imperative, scope `portmaster`; end every commit with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Repo files never mention storage contents.

## Review Focus

1. A spruce card with ports installed by hand and no picks: sync must not offer to delete `Roms/PORTS/*.sh`, port folders, `Imgs/*.png` or `autoinstall/` (today `ports` is a "dropped" system there and its folder is swept). Tests in Task 1.
2. Undertale-style ports whose first run deletes the data folder: sync copies data once (recorded in `portmaster_data`) and never again, even though the folder looks empty. Test in Task 6.
3. A card that has never booted spruceOS (no `Persistent/portmaster/PortMaster/`): staging is skipped with a note, nothing created. Test in Task 5.
4. A `port.json` on the card that is malformed or lacks `attr`: skipped with a warning, other ports still handled. Test in Task 5.
5. Storage unreachable (unmounted share) during `ports needed` or sync: entries are never dropped from `ports-needed.json` because storage "has no data". Test in Task 7.

---

### Task 1: Ports apply only to PortMaster devices on spruce, and `Roms/PORTS` is never swept

**Files:**
- Modify: `src/sync_roms/data/devices.json` (add `"portmaster": true` per Global Constraints)
- Modify: `src/sync_roms/store.py:843` (`system_applies`)
- Modify: `src/sync_roms/cli.py:1316-1334` (sweep), `src/sync_roms/scrape_plan.py:603-609` (`stale_media`), `scrape_plan.py:624` (`prune_empty_systems`)
- Create: `src/sync_roms/portmaster.py` (constants and `owns_folder` only in this task)
- Test: `tests/test_portmaster_sync.py`

**Interfaces:**
- Produces in `portmaster.py`: `PORTS = "ports"`; `CONTROL = "Persistent/portmaster/PortMaster"`; `AUTOINSTALL = CONTROL + "/autoinstall"`; `LIBS = CONTROL + "/libs"`; `def enabled(device: dict | None, layout_name: str) -> bool` (spruce and `device.get("portmaster") is True`); `def owns_folder(system: dict) -> bool` (bucket is `ports`; true on every layout: PortMaster owns its ports folder).
- `store.system_applies(system, device, layout_name)`: for bucket `ports`, true only when `portmaster.enabled(device, layout_name)` (regardless of the device's tier list); other systems unchanged. Import `portmaster` inside the function (circular-import rule).

- [ ] **Step 1: Write failing tests** in `tests/test_portmaster_sync.py`:
  - `test_ports_applies_only_on_portmaster_spruce_devices`: `system_applies(ports, rg35xxh_device, "spruce")` true; same with `miyoo-a30` false; with RG35XXH on `"knulli"` false; device None false.
  - `test_devices_flag_portmaster_on_64bit_spruce_devices`: the set of ids with `portmaster` equals the Global Constraints list exactly.
  - `test_sync_never_sweeps_ports_folder`: spruce sync (pattern of `tests/test_cli_sync.py::test_spruce_samples_are_deleted_without_asking_and_its_own_files_kept`) with a card holding `Roms/PORTS/Celeste.sh`, `Roms/PORTS/celeste/port.json`, `Roms/PORTS/Imgs/Celeste.png`, `Roms/PORTS/autoinstall/x.txt` and a device without the flag (`miyoo-mini`): all four files still exist afterwards and the delete prompt never lists them. Repeat with `anbernic-rg-35xxh` and no picks.
  - `test_stale_media_keeps_ports_imgs`: `scrape_plan.stale_media` over a spruce manifest including `ports` returns nothing under `Roms/PORTS/Imgs`.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_portmaster_sync -v </dev/null`; expect failures.
- [ ] **Step 3:** Implement: devices flag; `system_applies`; drop `owns_folder` systems from `dropped_dests` and from the sweep set at cli.py:1333; skip them in `stale_media` and `prune_empty_systems`.
- [ ] **Step 4:** Run the new tests and the full suite; expect PASS. Update `tests/test_setup_guide.py` expectations only if `tools/update_setup_guide.py` copies every device key (it should not need `portmaster`; if it does, filter it out there).
- [ ] **Step 5:** Commit `fix(portmaster): keep sync out of the ports folder and apply ports to portmaster devices`.

### Task 2: Catalogue cache and search

**Files:**
- Create: `src/sync_roms/portmaster_catalog.py`
- Test: `tests/test_portmaster_catalog.py` (fixture: a small `ports.json` dict built in the test with `celeste.zip` (rtr false, runtime mono, arch aarch64), `2048.zip` (rtr true, no runtime), `armonly.zip` (arch `["armhf"]`), and `utils` with `mono-6.12.0.122-aarch64.squashfs` and `frt_3.5.2.armhf.squashfs`)

**Interfaces:**
- `URL`, `MAX_AGE = 86400`
- `def path() -> str` — `store.cache_dir()/portmaster/ports.json`
- `def load(refresh: bool = False, fetch: bool = True) -> dict | None` — returns the parsed catalogue; fetches with `github.get(URL)` when missing, older than `MAX_AGE` or `refresh`, and `fetch` is true; on fetch failure with a cached copy warns and returns the copy; with `fetch=False` returns the cache or None. Writes the cache atomically (`store.write_text` or `write_json`).
- `def ports(catalog: dict) -> dict[str, dict]` — zip name → entry, aarch64-filtered.
- `def search(catalog: dict, text: str, needs_data: bool | None = None) -> list[dict]` — every word of `text` (casefolded) in title + zip + genres + desc; `needs_data` True keeps `rtr` false, False keeps `rtr` true; sorted by title casefold.
- `def resolve(catalog: dict, name: str) -> str | None` — accepts `celeste` or `celeste.zip` (casefold) and returns the zip name.
- `def runtimes(entry: dict) -> list[str]` — `attr.runtime` or `[]`, minus non-aarch64 names.
- `def runtime_source(catalog: dict, name: str) -> dict | None` — `utils[name]`.

- [ ] **Step 1:** Tests: `test_ports_drops_non_aarch64`, `test_search_matches_all_words_in_title_genre_desc`, `test_search_needs_data_filter`, `test_resolve_accepts_bare_name`, `test_runtimes_drops_other_arches`, `test_load_uses_fresh_cache_without_fetching` (patch `github.get` to fail the test if called), `test_load_refetches_stale_cache` (set mtime 2 days back), `test_load_falls_back_to_cache_on_error` (patch `github.get` to raise `OSError`; returns cached dict, warns), `test_load_without_fetch_returns_none_when_no_cache`.
- [ ] **Step 2:** Run; expect FAIL (module missing).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): cache and search portmaster's catalogue`.

### Task 3: `sync-roms ports download`

**Files:**
- Create: `src/sync_roms/portmaster_store.py`
- Modify: `src/sync_roms/commands.py` (`COMMANDS`, `build_parser`, wrapper `ports_download`), `src/sync_roms/cli.py` (`ALIASES` `"port": "ports"`, `SUBCOMMANDS["ports"]`, `TOPICS["ports"]`), `src/sync_roms/names.py:12` (add `"ports"` to `SYSTEMS`), `README.md` (Commands and Options tables)
- Test: `tests/test_portmaster_store.py`

**Interfaces:**
- Consumes: Task 2's `load`, `ports`, `resolve`, `runtimes`, `runtime_source`.
- Metadata entry written per zip in `scrapes/ports/metadata.json` (my call, replacing the spec's md5 cache: the port facts sync needs live with the title, so sync never opens a zip):
  `{"<zip>": {"name": <attr.title>, "portmaster": {"folder": <the items entry that isn't a .sh, without trailing "/">, "items": [...], "rtr": bool, "inst": str, "runtime": [...], "md5": <source.md5>, "size": <source.size>}}}`. `name` is only added when absent; `portmaster` is set on download and replaced on `--update`. Written with `shared.update(scrape_plan.metadata_key("ports"), ...)`.
- `def download(names: list[str], update: bool = False, refresh: bool = False, dry_run: bool = False) -> int` — exit code.
- `def outdated(catalog: dict) -> list[str]` — zips in storage (`inventory.files("ports/")`) whose metadata `portmaster.md5` differs from the catalogue's `source.md5` (missing metadata counts as outdated).
- `def remind_outdated(catalog: dict) -> None` — prints `N ports in storage have newer versions: <titles>. Run sync-roms ports download --update` when `outdated` is non-empty.
- Per zip: skip when in storage and not `update` (or when `update` and md5 matches); else download `source.url` with `github.download` into a temp dir, verify md5 (`hashlib.md5`), `s3.put_file("ports/<zip>", path)`; then each runtime not in `inventory.files("os/portmaster/runtimes/")`, same way from `utils`; then metadata. `--update` with no names means every `outdated` zip. Unknown name / HTTP error / md5 mismatch: `ui.warn`, continue, exit 1. Start with `usersettings.ensure_bucket()` and the write-access check `drivers.can_write()` like `bbs.download_pico8`. Without `--update`, end with `remind_outdated`.
- CLI: `sync-roms ports download [ZIP...] [--update] [--refresh] [-n] [-y]`; README gets `--update` and `--refresh` rows.

- [ ] **Step 1:** Tests with `helpers.StorageDir` and `github.download` patched to write fixture bytes (md5 matched in the fixture catalogue): `test_download_puts_zip_runtime_and_metadata`, `test_download_skips_zip_already_in_storage`, `test_update_replaces_only_changed_md5`, `test_update_without_names_updates_all_outdated`, `test_md5_mismatch_uploads_nothing_and_exits_1`, `test_unknown_name_warns_and_others_continue`, `test_metadata_keeps_existing_name`, `test_remind_outdated_lists_titles`, `test_dry_run_writes_nothing`; plus `tests/test_readme.py` and `tests/test_cli_errors.py` passing.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement module and CLI wiring (`ports` subparser with `dest="action", required=True`, wrapper with lazy import).
- [ ] **Step 4:** Run the new tests plus `tests.test_readme tests.test_cli_errors tests.test_commands tests.test_completion`; expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): download ports and runtimes into storage`.

### Task 4: `sync-roms ports search`

**Files:**
- Modify: `src/sync_roms/portmaster_store.py` (`search_command`), `commands.py`, `cli.py` (`SUBCOMMANDS`/`TOPICS` usage row), `README.md` (`--needs-data`, `--ready` rows)
- Test: `tests/test_portmaster_store.py`

**Interfaces:**
- `def search_command(text: str, needs_data: bool | None, refresh: bool, yes: bool, dry_run: bool) -> int`
- Row per match: `<title>  <zip>  <genres comma-joined>  <human size>` plus ` · needs game data` when `rtr` false and ` · in storage` when `ports/<zip>` is in `inventory.files("ports/")`. With `ui.has_terminal()` and not `yes`: `picker.filter_list("Download which ports?", labels, multi=True)`; picks (excluding ones in storage) go to `download(picks)`. Without a terminal: print only. Always end with `remind_outdated`.
- CLI: `sync-roms ports search [TEXT...] [--needs-data | --ready] [--refresh] [-n] [-y]` (mutually exclusive group).

- [ ] **Step 1:** Tests: `test_search_prints_rows_with_flags` (no terminal), `test_search_picker_downloads_picks` (patch `ui.has_terminal` True and `picker.filter_list` to pick celeste; assert `download` called with `["celeste.zip"]`), `test_search_no_matches_message`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run with the CLI/README tests; expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): search portmaster's catalogue and pick ports to download`.

### Task 5: Sync stages picked ports for autoinstall

**Files:**
- Modify: `src/sync_roms/portmaster.py`, `src/sync_roms/cli.py` (call in `stage_spruce` for dry-run and real paths; drop `ports` from ROM jobs for spruce), `data/cards.schema.json`, `commands.check_data`, `tests/test_editor_data.py`
- Test: `tests/test_portmaster_sync.py`

**Interfaces:**
- `def installed(base: str) -> dict[str, dict]` — port folder name → parsed `port.json` for each `Roms/PORTS/<dir>/port.json`; malformed/non-dict or missing `attr` warns (`ui.warn`, naming the file) and is skipped.
- `def is_installed(zip_name: str, facts: dict, ports_on_card: dict, base: str) -> bool` — an installed `port.json` with `name` == zip (casefold), or every `facts["items"]` entry exists in `Roms/PORTS/` (case-insensitive listing).
- `def stage(card: str, device: dict | None, layout_name: str, base: str, picked: list[str], dry_run: bool, keep: bool) -> tuple[int, list[str]]` — failures and titles staged. For each picked zip not installed: copy `ports/<zip>` to `AUTOINSTALL/<zip>` unless present at storage's size; each `facts["runtime"]` not in `LIBS/` or `AUTOINSTALL/` copied from `os/portmaster/runtimes/` (missing in storage: warn `run sync-roms ports download <zip>`). Copies via `downloads.run_downloads`. Staged files no longer picked and still in `AUTOINSTALL/` (from `portmaster_staged`) removed unless `keep`. Writes `portmaster_staged` = sorted files sync staged that are still in `AUTOINSTALL/` (drop field when empty). Missing `CONTROL/`: print `🧩 Boot the device once so spruceOS sets up PortMaster, then sync again` and return. Prints `🧩 Open PortMaster on the device to install: <titles>` when titles. Dry run prints `🧪 Dry run: would stage ...` and writes nothing.
- `facts` comes from `scrape_plan.load_metadata("ports")[zip]["portmaster"]`; a picked zip with no facts warns `run sync-roms ports download --update <zip>` and is skipped.
- `picked` is the card's `ports` keys from the manifest (the same keys the ROM loop would copy); in cli.py the `ports` system is removed from `chosen` before the ROM job loop when `portmaster.enabled(device, layout_name)`, and the step is skipped for guests and when not enabled.

- [ ] **Step 1:** Tests (card fixtures under a temp card with `CONTROL/libs/` and storage via `helpers.StorageDir` holding `ports/celeste.zip`, `os/portmaster/runtimes/mono-...squashfs` and metadata): `test_stage_copies_zip_and_runtime_to_autoinstall`, `test_stage_skips_installed_port_by_port_json_name`, `test_stage_skips_installed_port_by_items`, `test_stage_skips_runtime_in_libs`, `test_stage_without_control_folder_notes_and_writes_nothing`, `test_stage_removes_unpicked_staged_zip_unless_keep`, `test_staged_field_drops_files_portmaster_installed`, `test_malformed_port_json_warns_and_continues`, `test_dry_run_stages_nothing`, `test_sync_never_copies_port_zips_into_roms_ports`, `test_guest_sync_skips_portmaster`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement and wire.
- [ ] **Step 4:** Run the file plus `tests.test_cli_sync tests.test_sync_flow tests.test_editor_data`; expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): stage picked ports and runtimes for portmaster's autoinstall`.

### Task 6: Game data copy, needed list and sync summary

**Files:**
- Create: `src/sync_roms/portmaster_needed.py`
- Modify: `src/sync_roms/portmaster.py`, `src/sync_roms/cli.py` (call after `stage`, summary printed next to `spruce_os.remind`)
- Test: `tests/test_portmaster_needed.py`, `tests/test_portmaster_sync.py`

**Interfaces:**
- `portmaster_needed.py`: `PATH` via `def path() -> str` (`store.data_dir()/ports-needed.json`); `def load() -> dict`; `def save(entries: dict) -> None`; `def add(entries, folder, title, zip_name, inst, card) -> None` (refreshes title/zip/inst/folder hint, adds card, sorts cards); `def remove_card(entries, folder, card) -> None` (drops the entry when no cards left); `def prune(entries) -> list[str]` (removes entries whose `os/portmaster/gamedata/<folder>/` has files in `inventory.files`; returns removed titles; calls `s3.check_root()` first and returns `[]` without pruning when storage can't be reached); `def subfolder(folder: str, inst: str) -> str` (path hint, below); `def block(entry: dict, folder: str) -> str` (summary text).
- `subfolder` cases (tests pin these): undertale `"Copy the contents of your Steam or GOG installation to ports/undertale/assets."` → `"assets"`; celeste `Copy the game's data into "celeste/gamedata".` → `"gamedata"`; tmntsr `"ports/tmntsr/gamedata/."` → `"gamedata"`; zeroranger `"into the assets folder."` → `"assets"`; slaythespire `"copy the desktop-1.0.jar to the slaythespire folder!"` → `""`; no path → `""`.
- `block` format:
  ```
  <title>
      <inst, each line indented 4>
      Put the files in <s3.location()>/os/portmaster/gamedata/<folder>/<subfolder>/
  ```
- `portmaster.game_data(card, base, ports_on_card, picked_facts, dry_run) -> tuple[int, list[str]]` — failures and folders listed as waiting. For each installed port with `attr.rtr` false whose folder isn't in `portmaster_data`: storage files under `os/portmaster/gamedata/<folder>/` → copy each whose card path doesn't exist (never overwrite) into `Roms/PORTS/<folder>/`; on full success add folder to `portmaster_data`. None → `add` to the needed list. Picked-not-installed ports needing data are added too. Writes `portmaster_ports` = sorted installed folders needing data. Then `prune` all entries and `save` (not on dry run).
- `portmaster.summary(card: str, waiting: list[str]) -> None` — prints `Ports waiting for game data` heading, a `block` per entry, then `Already on the card? sync-roms ports done <card> <folder>` and `All of them: sync-roms ports needed`.
- `portmaster.updates(base: str, ports_on_card: dict) -> None` — with `portmaster_catalog.load(fetch=False)`, prints `🧩 Updates available in PortMaster on the device: <titles>` for installed ports whose `status.md5` differs from the catalogue's `source.md5`.

- [ ] **Step 1:** Tests: the six `subfolder` cases; `test_add_and_remove_card_drops_empty_entry`; `test_prune_drops_entries_with_storage_data`; `test_copy_never_overwrites_and_records_portmaster_data`; `test_copied_port_is_not_copied_again_when_folder_empty` (Undertale: delete `assets/` after the first sync, sync again, nothing copied); `test_waiting_port_added_to_needed_file_and_summary_printed`; `test_rtr_true_port_never_listed`; `test_failed_copy_retried_next_sync`; `test_dry_run_writes_no_needed_file_and_copies_nothing`; `test_updates_note_uses_cached_catalogue_only` (patch `github.get` to fail if called).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement and wire.
- [ ] **Step 4:** Run the files plus `tests.test_cli_sync`; expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): copy game data from storage and list ports still waiting for it`.

### Task 7: `sync-roms ports done` and `sync-roms ports needed`

**Files:**
- Modify: `src/sync_roms/portmaster_needed.py` (`done_command`, `needed_command`), `commands.py`, `cli.py` (usage rows), `README.md` (`--undo` row)
- Test: `tests/test_portmaster_needed.py`

**Interfaces:**
- `def done_command(card: str, ports: list[str], undo: bool) -> int` — PORT is a folder name or zip (zip mapped to folder through metadata `portmaster.folder`, else the zip stem); adds to (or with `--undo` removes from) the card's `portmaster_data` via `store.update_card`/`drop_card_field`; `remove_card` from the needed list (not on `--undo`); unknown card → `ui.fail(..., 2)`.
- `def needed_command() -> int` — `prune` (print `Game data now in storage: <titles>` when any), then every entry in title order as `block` plus `    Cards: <names>`; empty → `No ports are waiting for game data`. Not in the dry-run-refusing list; it accepts no `--dry-run`.

- [ ] **Step 1:** Tests: `test_done_adds_portmaster_data_and_clears_card_from_needed`, `test_done_accepts_zip_name`, `test_done_undo_removes`, `test_needed_prints_blocks_in_title_order`, `test_needed_prunes_entries_with_storage_data`, `test_needed_keeps_entries_when_storage_unreachable` (`runtime.ROOT` pointing at a missing folder), `test_needed_empty_message`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement and wire.
- [ ] **Step 4:** Run with the CLI/README tests; expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): add ports done and ports needed`.

### Task 8: Keep ports out of Surprise, collections, scraping and the editor's counts on spruce

**Files:**
- Modify: `src/sync_roms/surprise.py:224` (`_current`), `src/sync_roms/cli.py` (`frontend_step` and `build_plan` systems), `src/sync_roms/cardedit.py:308-312` and budget calls
- Test: `tests/test_portmaster_sync.py`

**Interfaces:**
- `def portmaster.skip(system: dict, layout_name: str) -> bool` — `layout_name == "spruce" and system["bucket"] == "ports"`; used at each point below.
- Surprise never picks `ports` on spruce; spruce collections and Surprise entries exclude ports games; `build_scrape_plan`/`load_scrape_data` get systems without ports (no `miyoogamelist.xml` in `Roms/PORTS`, no `scrape art` hint for it); the card editor still lists `ports` but its size, to-fetch and on-card numbers count 0 for it.

- [ ] **Step 1:** Tests: `test_surprise_never_picks_ports_on_spruce`, `test_collections_skip_ports_games_on_spruce`, `test_scrape_plan_has_no_ports_gamelist_on_spruce`, `test_editor_counts_zero_for_ports_on_spruce` (`budget.card_usage` over systems the editor passes).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file plus `tests.test_surprise tests.test_cardedit tests.test_scrape_plan` (whichever exist); expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): keep port zips out of surprise, collections, scrapes and card sizes`.

### Task 9: Mirror and documentation

**Files:**
- Modify: `src/sync_roms/mirroring.py:13-46` (`mirror_wanted`), `CLAUDE.md` (Storage table rows for `ports/` and `os/portmaster/`, Personal data `ports-needed.json`, Card fields rows, What sync puts on a card bullet), `README.md` (a short PortMaster section if the README has per-feature sections)
- Test: `tests/test_mirroring.py` (or the existing mirror test file)

**Interfaces:**
- `mirror_wanted` also wants: for each card's picked `ports` zips, their `portmaster.runtime` files under `os/portmaster/runtimes/`; for each folder in a card's `portmaster_ports` and each picked zip's `portmaster.folder` with `rtr` false, every key under `os/portmaster/gamedata/<folder>/`. Add the two prefixes to the `others` listing tuple.

- [ ] **Step 1:** Test `test_mirror_keeps_runtimes_and_gamedata_for_cards_ports`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement; write the docs.
- [ ] **Step 4:** Run the full suite `uv run python -m unittest discover -s tests </dev/null`; expect PASS.
- [ ] **Step 5:** Commit `feat(portmaster): mirror ports' runtimes and game data` (docs in the same commit).
