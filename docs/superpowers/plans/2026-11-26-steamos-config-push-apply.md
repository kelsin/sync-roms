# SteamOS `config push` and `config apply` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms config push USER@HOST` copies the Mac's settings and collections to a Steam Deck or Steam Machine over SSH, and `sync-roms config apply` on that device sets up RetroArch, ES-DE cores and Syncthing for clean save sync; the setup guide documents it.

**Architecture:** `config push` (`config_push.py`) is the only SSH code: system `ssh` with a tar stream each way. `config apply` for an `emudeck` card runs locally on the device (`steamos_settings.py`), reusing the Android text helpers (`android_settings.cfg_entries`/`cfg_apply`/`gamelist_apply`/`esde_wanted`) and a transport-free Syncthing REST part split out of `android_syncthing.py`. `steamos_syncthing.py` finds or installs Syncthing.

**Tech Stack:** Python 3.12+ stdlib (`subprocess`, `tarfile`, `urllib`, `xml.etree`), `unittest`, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-26-steamos-ssh-config-apply-design.md`

## Global Constraints

- Always `uv run`; tests: `uv run python -m unittest discover -s tests` with stdin closed (`< /dev/null`). Code must run on Python 3.12.
- Every new test module imports `isolate` first (directly or via `helpers`). No real SSH, network or Syncthing in tests: mock `subprocess.run` and `urllib`.
- `config push` never sends `bucket`, `root`, `endpoint`, `profile`, `write_profile`, `mirror`, `eject`, `storage_cache_declined`.
- Only one Syncthing: an existing one (any install) is used; never tell the user to uninstall or undo anything.
- No `sudo`; nothing written outside `~` and the Emulation folder. Nothing installed on the Mac.
- Never print secrets (setting values of `commands.HIDDEN`, `wifi_networks` passwords, the Syncthing API key). `config push` prints key names only, never values.
- `ssh` always with `-o BatchMode=yes -o ConnectTimeout=10`; remote arguments quoted with `shlex.quote`.
- Hotkeys, bezels, APKs, RAOfflineProxy and standalone emulators are not touched on SteamOS.
- Conventional Commits; each commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- New command words go through `commands.build_parser`, `cli.TOPICS`, `cli.SUBCOMMANDS`; README tables must keep `tests/test_readme.py` passing; CLAUDE.md updated where the task changes documented behaviour.

## Review Focus

1. **Paths with spaces or quotes** (an SD card label like `My SD`, a data folder under it): every remote command quotes with `shlex.quote`; local paths never go through a shell. Test in Task 5.
2. **An existing Syncthing on a non-default GUI port or with TLS on**: the address and scheme come from its `config.xml`, not assumed `127.0.0.1:8384` http. Test in Task 3.
3. **The device's `settings.json` missing (first push) or unparseable**: missing is created; unparseable is never overwritten (exit 3, as `usersettings` does locally). Test in Task 5.
4. **SSH unreachable or key not accepted**: fails fast (BatchMode) with exit 1 and a message naming the host; nothing written. Test in Task 5.
5. **`savefile_directory`/`savestate_directory` set to `default` or missing in EmuDeck's `retroarch.cfg`**: resolved to RetroArch's defaults under its config folder (`saves`, `states`) before `realpath`. Test in Task 4.

---

### Task 1: Transport-free Syncthing REST configuration

**Files:**
- Modify: `src/sync_roms/android_syncthing.py`
- Test: `tests/test_android_syncthing.py`

**Interfaces:**
- Produces:
  - `_api(port: int, key: str, method: str, path: str, body=None, scheme: str = "https")` (http skips the SSL context).
  - `plan(config, srv, defaults_device, defaults_folder, paths: dict | None = None, where: str = WHERE, mod_time_window: int | None = None)`: `paths` is `{"saves": path, "states": path}`; `None` keeps `PATHS` (Android). Warnings name `where` instead of the hardcoded "Syncthing-Fork". With `mod_time_window`, new folders get `modTimeWindowS` set to it and an existing folder at the right path with another value gets an entry and a PUT setting it (SteamOS passes `2`, for exFAT SD cards).
  - `configure` takes and passes on `mod_time_window: int | None = None`.
  - `configure(port: int, key: str, srv, paths: dict | None, dry_run: bool, scheme: str = "https", where: str = WHERE) -> list[applied.Entry] | None`: waits with `_up`, GETs config and both defaults, runs `plan`, warns, sends calls unless dry run. Returns `None` when the API doesn't answer or refuses the key (403), after a warning (`ui.dim` on dry run for "not answering").
  - `_up(port, key, scheme="https")`.
- `_folder_part` keeps its adb steps (export, forward, launch with `monkey`) and calls `configure`.

- [ ] **Step 1: Write failing tests** in `tests/test_android_syncthing.py`: `test_plan_uses_given_paths` (`plan(config, SRV, DD, DF, paths={"saves": "/home/deck/s", "states": "/home/deck/t"})` puts `"/home/deck/s"` in the `ra-saves` PUT body's `path`); `test_plan_warning_names_where` (`where="Syncthing"` → warning starts with `"Syncthing folder"`); `test_plan_mod_time_window` (`mod_time_window=2` → new folder body has `modTimeWindowS == 2`; an existing shared folder with `modTimeWindowS: 0` gets a PUT with `2`); `test_api_http_scheme` (mock `urllib.request.urlopen`; `scheme="http"` → request URL starts with `http://127.0.0.1:` and no `context` kwarg); `test_configure_403_returns_none`.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_android_syncthing < /dev/null`; expect the new tests to FAIL.
- [ ] **Step 3:** Implement the interfaces above; `_folder_part` becomes adb setup plus `configure(...)`.
- [ ] **Step 4:** Run the same command; all PASS (old tests unchanged).
- [ ] **Step 5:** Commit `refactor(syncthing): split the REST setup from adb and take folder paths and http`.

### Task 2: RetroArch settings for SteamOS

**Files:**
- Modify: `src/sync_roms/android_settings.py` (`cfg_wanted`)
- Test: `tests/test_android_settings.py`

**Interfaces:**
- Produces: `cfg_wanted(overlay_dir=None, platform: str = "android") -> dict`. With `platform="steamos"`: everything Android gets except `hotkeys()`, `overlay_directory`, `savefile_directory`, `savestate_directory`. Auto save/load (`savestate_auto_save`/`savestate_auto_load` `"true"`) and `syncthing.json`'s `retroarch` keys still apply while Syncthing is on; RetroAchievements and `CLOUD_SYNC` always.

- [ ] **Step 1: Write failing tests**: `test_cfg_wanted_steamos_skips_hotkeys_and_folders` (no key ending `_btn`, no `savefile_directory`, `savestate_directory`, `overlay_directory` even when `overlay_dir` given; has `sort_savefiles_enable == "true"`, `cloud_sync_enable == "false"`, `savestate_auto_load == "true"`); `test_cfg_wanted_android_unchanged` (default call still has `savefile_directory == android.DEFAULT_SAVES`).
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_android_settings < /dev/null`; new tests FAIL.
- [ ] **Step 3:** Implement the `platform` parameter.
- [ ] **Step 4:** Run; PASS.
- [ ] **Step 5:** Commit `feat(settings): RetroArch settings for SteamOS without hotkeys or save folders`.

### Task 3: Syncthing on SteamOS

**Files:**
- Create: `src/sync_roms/steamos_syncthing.py`
- Test: `tests/test_steamos_syncthing.py`

**Interfaces:**
- Consumes: `android_syncthing.configure` (Task 1), `spruce_syncthing.enabled()`/`server()`, `github.json` (as `drivers.py` uses it).
- Produces:
  - `Install = namedtuple("Install", "config flatpak")`: path of its `config.xml`, and the Flatpak app id or `None`.
  - `find(home: str) -> Install | None`: first of, in order: the `--home`/`--config` folder in a running `syncthing` process's command line (`pgrep -a syncthing`); `~/.local/state/syncthing/config.xml`; `~/.config/syncthing/config.xml`; the same two under `~/.var/app/<id>/` for each id in `FLATPAKS`; the Decky plugin's config path. `FLATPAKS` and the Decky path: verify the ids/paths of SyncThingy, Syncthing GTK and the Decky Syncthing plugin from their sources and list them as constants.
  - `read_config(text: str) -> tuple[str, int, str] | str`: `(api key, GUI port, "http"|"https")` from `gui/apikey`, `gui/address` and the `gui` element's `tls` attribute; else why it can't be used.
  - `flatpak_entries(app: str, folders: list[str], permissions: str) -> list[applied.Entry]`: one per folder the app's `flatpak info --show-permissions` output (`filesystems=` line) doesn't cover (`home`, `host`, or a parent path covers it).
  - `install(home: str) -> str`: downloads `syncthing-linux-<amd64|arm64>-v*.tar.gz` of the latest release of `syncthing/syncthing`, checks it against that release's `sha256sum.txt` (mismatch raises `ValueError`), extracts with `tarfile` `filter="data"`, puts `syncthing` in `~/.local/bin/` (mode 755), writes `~/.config/systemd/user/syncthing.service` from the tarball's `etc/linux-systemd/user/syncthing.service` with `ExecStart` pointing at that binary, then runs `systemctl --user daemon-reload` and `systemctl --user enable --now syncthing`. Returns the new `config.xml` path (`~/.local/state/syncthing/config.xml`), waiting up to 30 s for it.
  - `apply(paths: dict, dry_run: bool, failed: list) -> None`: while enabled: find, else (not dry run) install, else on dry run print that it would install; Flatpak access via `flatpak override --user --filesystem=<folder>` with a "restart <app>" hint; then `configure(..., paths, dry_run, scheme, where="Syncthing", mod_time_window=2)` when `server()` is set; `applied.show` the entries. An existing install that doesn't answer is warned about (start it), never restarted or replaced. Errors (`OSError`, `ValueError`, `subprocess.CalledProcessError`) warn and append `"Syncthing"` to `failed`.

- [ ] **Step 1: Write failing tests** (temp HOME from `isolate`; `subprocess.run` and `github.json` mocked): `test_find_order` (state path wins over `.config`; a pgrep `--home=/x` wins over both); `test_find_flatpak` (config under `~/.var/app/<FLATPAKS[0]>/...` → `Install(..., FLATPAKS[0])`); `test_find_none`; `test_read_config_tls_and_port` (`<gui tls="true"><address>0.0.0.0:8385</address><apikey>k</apikey></gui>` → `("k", 8385, "https")`; no tls → `"http"`); `test_read_config_no_key`; `test_flatpak_entries` (`filesystems=home;` covers `/home/deck/Emulation/x` → `[]`; `filesystems=xdg-download;` → one entry); `test_install_checksum_mismatch_raises`; `test_install_writes_unit_and_enables` (tarball built in the test; asserts binary mode 755, unit `ExecStart=` points at `~/.local/bin/syncthing`, `systemctl --user enable --now syncthing` called); `test_apply_existing_not_installed_again`; `test_apply_dry_run_installs_nothing`.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_steamos_syncthing < /dev/null`; FAIL.
- [ ] **Step 3:** Implement the module.
- [ ] **Step 4:** Run; PASS.
- [ ] **Step 5:** Commit `feat(steamos): find, install and configure Syncthing`.

### Task 4: SteamOS `config apply`

**Files:**
- Create: `src/sync_roms/steamos_settings.py`
- Modify: `src/sync_roms/settings_apply.py`, `src/sync_roms/cli.py` (`TOPICS["config"]`, `SUBCOMMANDS["config"]` summary), `README.md` (Commands row and the `config apply` text in Settings), CLAUDE.md (the `config apply` bullet)
- Test: `tests/test_steamos_settings.py`, `tests/test_settings_apply.py`

**Interfaces:**
- Consumes: `cfg_wanted(platform="steamos")` (Task 2), `steamos_syncthing.apply` (Task 3), `android_settings.cfg_entries`/`cfg_apply`/`gamelist_entry`/`gamelist_apply`/`esde_wanted`, `android.parse_config`, `frontend.esde_dir`/`emudeck_problem`.
- Produces:
  - `steamos_settings.RA_DIR = "~/.var/app/org.libretro.RetroArch/config/retroarch"`.
  - `steamos_settings.folders(cfg_text: str, ra_dir: str) -> dict`: `{"saves": real path, "states": real path}`; a key missing or `default` → `<ra_dir>/saves` / `<ra_dir>/states`; `~` and `:` (RetroArch's own-dir prefix) expanded; `os.path.realpath`.
  - `steamos_settings.warnings(ra_dir: str, emudeck_settings: str | None) -> list[str]`: EmuDeck Cloud Saves on (from `~/emudeck/settings.sh`: verify the variable name in EmuDeck's source); each per-core override `<ra_dir>/config/*/*.cfg` that sets `savefile_directory` or `savestate_directory`.
  - `steamos_settings.apply(base: str, layout: dict, systems: list, dry_run: bool) -> int` (0 or 1): reads the cfg (missing: warn, skip RetroArch); RetroArch running (`pgrep -f org.libretro.RetroArch`) → `android.wait_closed`-style prompt, no terminal → fail; ES-DE gamelists under `frontend.esde_dir("emudeck", base)` skipped with `emudeck_problem`'s reason, and when ES-DE runs (`pgrep -f es-de`) ask (`ui.confirm`, default no) before writing them; dry run shows all entries and the warnings and writes nothing; else writes changed files, prints the warnings, then `steamos_syncthing.apply(folders, ...)`.
  - `settings_apply.run`: layout `emudeck` → `steamos_settings.apply(base, layout, systems, dry_run)`; the unsupported-layout message reads `"config apply supports spruce, Knulli and EmuDeck cards and Android devices, not {layout}"`.

- [ ] **Step 1: Write failing tests**: `test_folders_default_and_missing` (cfg with `savefile_directory = "default"` and no `savestate_directory` → `<ra_dir>/saves`, `<ra_dir>/states`); `test_folders_resolve_symlink` (a symlinked folder → its target); `test_warnings_cloud_and_override`; `test_apply_dry_run_writes_nothing` (fake home with cfg and gamelists; file bytes unchanged after); `test_apply_writes_only_changed`; `test_apply_missing_cfg_skips`; `test_apply_esde_running_declined_keeps_gamelists`; in `test_settings_apply.py`: `test_emudeck_routes_to_steamos`.
- [ ] **Step 2:** Run the two test modules; FAIL.
- [ ] **Step 3:** Implement; update `TOPICS["config"]` (config apply: an EmuDeck card's folder, run on the Steam Deck or Steam Machine itself, gets RetroArch's settings, ES-DE cores and Syncthing), the SUBCOMMANDS/README Commands wording ("a spruce, Knulli or EmuDeck card or an Android device") and the README Settings paragraph, and CLAUDE.md.
- [ ] **Step 4:** Run the full suite; PASS (including `tests/test_readme.py`).
- [ ] **Step 5:** Commit `feat(config): apply RetroArch, ES-DE and Syncthing settings on SteamOS`.

### Task 5: `config push`

**Files:**
- Create: `src/sync_roms/config_push.py`
- Modify: `src/sync_roms/commands.py` (`config` action choices add `push`; `config_cmd` routes it; the `--dry-run` refusal list lets `config push` through), `src/sync_roms/cli.py` (`SUBCOMMANDS["config"]` usage adds `push USER@HOST`; `TOPICS["config"]` text), `README.md` (Commands row; Settings paragraph), CLAUDE.md (`settings.json` line or a new bullet: what push sends)
- Test: `tests/test_config_push.py`

**Interfaces:**
- Produces:
  - `NEVER_SENT = ("bucket", "root", "endpoint", "profile", "write_profile", "mirror", "eject", "storage_cache_declined")`.
  - `merge(mac: dict, device: dict | None) -> dict`: Mac's keys minus `NEVER_SENT`, plus the device's own values for `NEVER_SENT` keys.
  - `changes(old: dict | None, new: dict) -> list[str]`: lines `"added <key>"`, `"changed <key>"`, `"removed <key>"`, sorted; never values.
  - `remote_dir(host: str) -> str`: the device's data folder from `ssh host 'printf %s "${XDG_DATA_HOME:-$HOME/.local/share}"'`-style query that mirrors `store.data_dir()` (XDG set → `$XDG_DATA_HOME/sync-roms`, else `$HOME/.sync-roms`).
  - `fetch(host: str, data_dir: str) -> tuple[bytes | None, dict[str, bytes]]`: one `ssh` running `tar -cf -` of whichever of `settings.json` and `collections/*.json` exist (an empty tar when neither), read with `tarfile`.
  - `send(host: str, data_dir: str, settings: bytes, collections: dict[str, bytes]) -> None`: one `ssh` fed a tar on stdin, whose remote script extracts into a fresh temp folder inside `data_dir`, then `mv`s `settings.json` into place (`chmod 600` before the move) and swaps `collections/` (old one moved aside, new moved in, old removed).
  - `push(host: str, dry_run: bool) -> int`: device settings unparseable → `ui.fail(..., 3)`, nothing written; SSH failure (`CalledProcessError`/non-zero) → `ui.fail(f"Can't reach {host} over SSH: ...", 1)`; prints settings changes, then `added|changed|removed collection <name>`; `"Nothing to change"` when none; dry run stops before `send`.

- [ ] **Step 1: Write failing tests** (`subprocess.run` mocked, tar bytes built in tests): `test_merge_keeps_device_storage` (mac `{"root": "/Volumes/roms", "ra_mode": "Casual"}`, device `{"bucket": "b", "ra_mode": "Hardcore", "old": 1}` → `{"bucket": "b", "ra_mode": "Casual"}`); `test_never_sent_not_in_tar` (sent settings JSON has none of `NEVER_SENT` from the Mac); `test_changes_hide_values` (`ra_password` changed → line `"changed ra_password"`, output has no password text); `test_collections_matched` (device has `a.json`, `b.json`; Mac has `a.json` changed and `c.json` → sent tar holds exactly `a.json`, `c.json`, output lists changed a, added c, removed b); `test_first_push_no_device_settings`; `test_unparseable_device_settings_exit_3_nothing_sent`; `test_ssh_failure_exit_1`; `test_dry_run_sends_nothing`; `test_remote_paths_quoted` (data folder `/run/media/deck/My SD/.sync-roms` appears only `shlex.quote`d in the ssh command); `test_ssh_batch_mode` (argv has `-o BatchMode=yes` and `-o ConnectTimeout=10`).
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_config_push < /dev/null`; FAIL.
- [ ] **Step 3:** Implement the module and the command wiring and docs.
- [ ] **Step 4:** Run the full suite; PASS (including `tests/test_readme.py` and completion tests).
- [ ] **Step 5:** Commit `feat(config): push settings and collections to a SteamOS device over SSH`.

### Task 6: Setup guide

**Files:**
- Modify: `src/sync_roms/data/setup-guide.html` (Syncthing section), CLAUDE.md only if the guide description changes
- Test: `tests/test_setup_guide.py`

- [ ] **Step 1:** In the Syncthing section, add a "SteamOS" subsection (`when: { platform: ["steamos"] }`) with the spec's steps in order: install uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and `uv tool install git+https://github.com/kelsin/sync-roms` on the device; on the Mac `sync-roms config push USER@HOST` (needs SSH access to the device; run again after changing settings or collections, which are made on the Mac only); first `sync-roms` on the device asks for storage and sets up the card (layout `emudeck`) and syncs; with RetroArch closed, `sync-roms config apply <folder holding Emulation>` on the device, with what it sets (RetroArch save settings, Cloud Sync off, RetroAchievements, ES-DE cores, Syncthing found or installed, the server and folders); server UI: accept the device and tick `ra-saves` and `ra-states`; after an EmuDeck update or reset, run `config apply` again. No SSH setup steps. Use `class="copy"` for commands as the other subsections do.
- [ ] **Step 2:** Change "Desktop" to `when: { platform: ["windows"] }` and drop its Steam Deck `~/.var` note; remove `"steamos"` from "Pair and share"'s `platform`.
- [ ] **Step 3:** Run `uv run python tools/update_setup_guide.py` then `uv run python -m unittest tests.test_setup_guide < /dev/null`; PASS.
- [ ] **Step 4:** Open the page (`uv run sync-roms guide`), pick Steam Machine / EmuDeck, check the SteamOS subsection shows and Desktop and Pair and share don't.
- [ ] **Step 5:** Commit `docs(guide): set up Syncthing on SteamOS with config push and config apply`.
