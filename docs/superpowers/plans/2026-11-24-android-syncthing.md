# Syncthing-Fork over adb Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms config apply` on an Android device sets up Syncthing-Fork: the server device, the `ra-saves`/`ra-states` folders at RetroArch's folders, All files access and the battery-optimization exemption.

**Architecture:** New module `src/sync_roms/android_syncthing.py`: pure functions (API key from the export zip; a plan of REST calls and `applied.Entry`s from Syncthing's config JSON) plus a thin `apply` that talks to the device over adb and to Syncthing's REST API through `adb forward`. `android_settings.apply` calls it after the APK step in both the dry-run and real paths.

**Tech Stack:** Python 3.12+ stdlib (`zipfile`, `xml.etree`, `urllib.request`, `ssl`, `json`), `unittest` + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-11-24-android-syncthing-design.md`

## Global Constraints

- Always `uv run`; tests: `uv run python -m unittest discover -s tests` (stdin closed: `< /dev/null`). Code must run on Python 3.12.
- Test modules import `isolate` first (directly or via `helpers`).
- Package `com.github.catfriend1.syncthingfork`; export at `/storage/emulated/0/backups/syncthing/config.zip`; GUI port from the export's `<gui><address>`, default 8384; HTTPS with a self-signed cert; header `X-API-Key`.
- Only runs while `spruce_syncthing.enabled()`. Device/folders only with a valid `spruce_syncthing.server()`. Folder paths: `android.DEFAULT_SAVES` for role `saves`, `android.DEFAULT_STATES` for `states`; labels from the `srv["folders"]` tuples.
- Never change an existing server device; a folder id at another path, or another folder id at the wanted path → warn, leave. No `modTimeWindowS`.
- Exit-code failures (`failed.append("Syncthing-Fork")`) only for adb errors in this part, HTTP errors other than 403, bad JSON. No/encrypted export, no `<apikey>`, 403, app not answering → `ui.warn`, no failure.
- A dry run never launches the app or writes anything; it lists every entry (`applied.show(entries, True)`).
- Conventional Commits; commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- The server's ID in `syncthing_server` is lowercase or the device's config has it in another case: compare device IDs uppercased (`server()` already uppercases; uppercase config `deviceID`s too). Test in Task 2.
- A folder path in the config with a trailing slash (`/storage/emulated/0/RetroArch/saves/`) is the same folder. Test in Task 2.
- Running `config apply` twice: the second run sets nothing and prints nothing new (all entries unchanged). Test in Task 2.
- `adb forward` left behind after an error: the forward is always removed. Test in Task 3.
- Export zip with `config.xml` that can't be parsed, or a zip that isn't one: warn, no traceback. Test in Task 2.

---

### Task 1: `adb.forward` and `adb.forward_remove`

**Files:**
- Modify: `src/sync_roms/adb.py`
- Test: `tests/test_adb.py`

**Interfaces:**
- Produces: `adb.forward(serial: str, remote_port: int) -> int` (runs `adb -s <serial> forward tcp:0 tcp:<remote_port>`, returns the local port adb prints); `adb.forward_remove(serial: str, local_port: int) -> None` (`forward --remove tcp:<local_port>`, `check=False`).

- [ ] **Step 1:** Tests `test_forward_returns_local_port` (patch `adb.run` to return `"57983\n"`, assert result `57983` and the args `("forward", "tcp:0", "tcp:8384")` with `serial=`), `test_forward_remove` (asserts args `("forward", "--remove", "tcp:57983")`, `check=False`). Follow the existing patching style in `tests/test_adb.py`.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_adb < /dev/null`, expect FAIL.
- [ ] **Step 3:** Implement both in `adb.py` with `run(...)`.
- [ ] **Step 4:** Rerun, expect PASS.
- [ ] **Step 5:** Commit `feat(adb): add port forwarding helpers`.

### Task 2: pure functions in `android_syncthing.py`

**Files:**
- Create: `src/sync_roms/android_syncthing.py`
- Test: `tests/test_android_syncthing.py`

**Interfaces:**
- Consumes: `applied.Entry(where, key, old, new, secret)`; `spruce_syncthing.server()`'s shape `{"id", "address", "folders": [(role, folder_id, label, card_path)]}`.
- Produces:
  - `PACKAGE = "com.github.catfriend1.syncthingfork"`, `EXPORT = "/storage/emulated/0/backups/syncthing/config.zip"`, `WHERE = "Syncthing-Fork"`.
  - `read_export(data: bytes) -> tuple[str, int] | str`: `(api_key, gui_port)` or a reason string for the warning: `"isn't a zip"`, `"is encrypted (export it without a backup password)"`, `"has no config.xml"`, `"has a config.xml that can't be parsed"`, `"has no API key"`. Port from `<gui><address>` (`host:port`, IPv6 `[::]:8384` too), else 8384. Encrypted: a `zipfile` member with `flag_bits & 0x1`, or `RuntimeError`/`NotImplementedError` on read.
  - `folder_paths(srv) -> list[tuple[str, str, str]]`: `[(folder_id, label, android_path)]` mapping role `saves`→`android.DEFAULT_SAVES`, `states`→`android.DEFAULT_STATES`.
  - `plan(config: dict, srv: dict, defaults_device: dict, defaults_folder: dict) -> tuple[list[Entry], list[tuple[str, str, dict]], list[str]]`: entries, REST calls `(method, path, body)` and warnings. `config` is `GET /rest/config` JSON (`devices: [{deviceID, ...}]`, `folders: [{id, path, label, devices: [{deviceID}]}]`).
    - Entry `device server`: old = `srv["id"]` if present (case-insensitive) else None, new = `srv["id"]`. Missing → call `("PUT", f"/rest/config/devices/{id}", {**defaults_device, "deviceID": id, "name": "server", "addresses": [address]})`.
    - Per folder, entry key `folder <id>`, new = `f"{path}, shared with the server"`:
      - id found at path (trailing `/` ignored) with the server → old = new, no call.
      - id found at path without the server → old = `f"{path}, not shared with the server"`; call `("PUT", f"/rest/config/folders/{id}", {**found, "devices": found["devices"] + [{"deviceID": id_srv}]})`.
      - id found at another path → warning `f"Syncthing-Fork folder {id} is at {its path}, not {path}; left as it is"`, no entry.
      - other folder at path → warning `f"Syncthing-Fork folder {other} is already at {path}, so {id} isn't added there; left as it is"`, no entry.
      - none → old None; call `("PUT", f"/rest/config/folders/{id}", {**defaults_folder, "id": id, "label": label, "path": path, "type": "sendreceive", "devices": [{"deviceID": id_srv}]})`.

- [ ] **Step 1:** Tests (build zips in memory with `zipfile`; `srv` literal with id `"AAAAAAA-" * 7 + "AAAAAAA"` style valid ID and folders `[("saves","ra-saves","RetroArch saves",...), ("states","ra-states","RetroArch states",...)]`):
  - `test_read_export_key_and_port` (`<configuration><gui><address>127.0.0.1:8385</address><apikey>abc</apikey></gui></configuration>` → `("abc", 8385)`), `test_read_export_default_port`, `test_read_export_ipv6_port` (`[::]:8384`), `test_read_export_not_zip` (`b"nope"`), `test_read_export_no_config`, `test_read_export_bad_xml`, `test_read_export_no_key`, `test_read_export_encrypted` (set `ZipInfo.flag_bits |= 1` on the member).
  - `test_plan_empty_config_adds_device_and_folders` (3 calls, entries old None, bodies keep defaults keys, `type == "sendreceive"`, paths `android.DEFAULT_SAVES`/`DEFAULT_STATES`).
  - `test_plan_existing_device_other_case_left` (config deviceID lowercase → no device call, entry unchanged).
  - `test_plan_folder_without_server_gets_it` (trailing slash in path; body keeps the folder's other keys).
  - `test_plan_folder_at_other_path_warns`, `test_plan_other_folder_at_path_warns`.
  - `test_plan_all_set_is_unchanged` (every entry `not applied.changed`, no calls).
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_android_syncthing < /dev/null`, expect FAIL (import error).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, expect PASS.
- [ ] **Step 5:** Commit `feat(android): plan syncthing-fork's server and folders`.

### Task 3: `android_syncthing.apply` and the call from `config apply`

**Files:**
- Modify: `src/sync_roms/android_syncthing.py`, `src/sync_roms/android_settings.py` (`apply`, after `_apk_part` in both paths)
- Test: `tests/test_android_syncthing.py`, `tests/test_android_settings.py`

**Interfaces:**
- Consumes: Task 1's `adb.forward`/`forward_remove`, Task 2's functions, `adb.shell`, `adb.exec_out`, `adb.is_file`, `adb.AdbError`, `applied.show`, `ui.warn`, `ui.dim`.
- Produces: `android_syncthing.apply(serial: str, dry_run: bool, failed: list) -> None`. Inside: `_access_entries(serial) -> list[tuple[Entry, list[str]]]` (each entry with the adb shell words that set it) and `_api(port: int, key: str, method: str, path: str, body: dict | None = None) -> dict | None` (urllib, `ssl._create_unverified_context()`, `X-API-Key`, JSON, timeout 10 s; raises `urllib.error.HTTPError`/`URLError`).

Behavior:
1. Not `spruce_syncthing.enabled()` → return. Package missing from `pm list packages` → `print(ui.dim("Syncthing-Fork isn't installed: install it to sync saves with the server"))`, return.
2. Access entries (`where = WHERE`): `battery optimization` old `"exempt"` if the package is in `dumpsys deviceidle whitelist` output else `"on"`, new `"exempt"`, set with `dumpsys deviceidle whitelist +<pkg>`. Storage: `getprop ro.build.version.sdk` ≥ 30 → key `all files access`, old from `appops get <pkg> MANAGE_EXTERNAL_STORAGE` (`allow` in output → `"allow"`, else the reported mode or `"default"`), new `"allow"`, set with `appops set <pkg> MANAGE_EXTERNAL_STORAGE allow`; < 30 → key `storage permission`, old `"granted"` when `dumpsys package <pkg>` shows `android.permission.WRITE_EXTERNAL_STORAGE: granted=true`, new `"granted"`, set with `pm grant` of READ and WRITE.
3. `srv = spruce_syncthing.server()`; None → only the access entries.
4. Export: not `adb.is_file(serial, EXPORT)` → warn `"Syncthing-Fork has no export at /storage/emulated/0/backups/syncthing/config.zip: export its settings (Settings > Import and Export > Export, no backup password) so config apply can add the server and folders"`; else `read_export(adb.exec_out(serial, "cat", EXPORT))`, a reason → warn `f"Syncthing-Fork's export {reason}; the server and folders aren't set"`.
5. `local = adb.forward(serial, port)`; `try`/`finally adb.forward_remove`. Health `GET /rest/noauth/health` polled every 1 s up to 15 s; not answering and not dry run → `adb.shell(serial, "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")` and poll again; still down → warn (`"Syncthing-Fork isn't running (its run conditions may keep it stopped); the server and folders aren't set"`); dry run and down → `print(ui.dim(...))` same text, no launch.
6. `GET /rest/config`, `/rest/config/defaults/device`, `/rest/config/defaults/folder`; HTTP 403 → warn `"Syncthing-Fork refused the export's API key: export its settings again"`; `plan(...)` → print warnings with `ui.warn`.
7. Dry run: `applied.show(access + plan entries, True)`. Real: run access commands for changed entries, then the REST calls, then `applied.show(entries, False)`.
8. `adb.AdbError`, other `HTTPError`, `URLError`, `ValueError` (JSON) → `ui.warn(f"Syncthing-Fork: {e}")`, `failed.append("Syncthing-Fork")`.

- [ ] **Step 1:** Tests with `mock.patch.object` on `adb.shell`, `adb.is_file`, `adb.exec_out`, `adb.forward`, `adb.forward_remove`, `android_syncthing._api`, `spruce_syncthing.server`/`enabled`, `time.sleep`:
  - `test_skips_when_syncthing_off` (no adb calls).
  - `test_not_installed_prints_hint`.
  - `test_access_entries_android_11` / `test_access_entries_android_10` (expected shell words run only for changed entries).
  - `test_no_export_warns_without_failing` (`failed == []`).
  - `test_dry_run_never_launches_or_writes` (health fails → no `monkey`, no PUT, `failed == []`).
  - `test_forward_removed_on_error` (`_api` raises `URLError` → `forward_remove` called, `failed == ["Syncthing-Fork"]`).
  - `test_403_warns_without_failing`.
  - `test_real_run_sends_planned_calls` (empty config → three PUTs in order device, saves, states).
  - In `tests/test_android_settings.py`: `test_apply_runs_syncthing_after_apks` (patch `android_syncthing.apply` and `_apk_part`, record call order, both for `dry_run` True and False).
- [ ] **Step 2:** Run both test modules, expect FAIL.
- [ ] **Step 3:** Implement; wire `android_syncthing.apply(serial, dry_run, failed)` into `android_settings.apply` after `_apk_part` in both branches.
- [ ] **Step 4:** Run `uv run python -m unittest discover -s tests < /dev/null`, expect all PASS.
- [ ] **Step 5:** Commit `feat(android): set up syncthing-fork in config apply`.

### Task 4: setup guide and project docs

**Files:**
- Modify: `src/sync_roms/data/setup-guide.html` (Android section in the Syncthing `SECTIONS` entry, around line 1043), `CLAUDE.md` (the `config apply [CARD]` bullet), `README.md` only if it describes `config apply`'s Android steps (grep `config apply`).

- [ ] **Step 1:** Replace the Android `<ol>` with the five steps of the spec's "Guide (Android section) after the change", keeping the existing markup style (`<b>`, `<code class="copy">`). Step 5 text: `Syncthing-Fork: set its run conditions (Settings &gt; Run conditions) so it runs when switching devices.`
- [ ] **Step 2:** CLAUDE.md `config apply` bullet: after the ES-DE part, add that on Android it also sets up Syncthing-Fork while `syncthing` is on (All files access, battery-optimization exemption, and with `syncthing_server` the server device and the two folders at RetroArch's save/state folders through its REST API over `adb forward`, the API key read from its export `backups/syncthing/config.zip`; a missing export or stopped app warns). One or two sentences, same style.
- [ ] **Step 3:** Run `uv run python -m unittest tests.test_setup_guide tests.test_readme < /dev/null`, expect PASS; run `uv run python tools/update_setup_guide.py` and check `git diff --stat` shows no unexpected change.
- [ ] **Step 4:** Commit `docs(guide): automate the android syncthing steps`.
