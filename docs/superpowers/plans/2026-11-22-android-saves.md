# Android saves over wireless adb Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms saves stash|apply` reach an Android card over adb (pairing help, device and card pickers,
RetroArch folders found from `retroarch.cfg`), staging a temp copy so the existing stash/apply code runs unchanged.

**Architecture:** `adb.py` is a thin wrapper over the `adb` binary (the only module that runs it). `android.py`
holds the device-side logic: picking and pairing devices, matching the SD card to a card by volume id, finding
RetroArch's folders, staging a temp card folder and pushing written files back. `saves.py` decides path vs adb mode
in `card_setup` and pushes what apply wrote.

**Tech Stack:** Python 3.12+ stdlib (`subprocess`, `shlex`, `tempfile`), the Homebrew `adb` binary, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-22-android-saves-design.md`

## Global Constraints

- Always `uv run`: `uv run python -m unittest discover -s tests`. The code must run on Python 3.12.
- Test modules import `isolate` (directly or via `helpers`) before `sync_roms`. Tests never run a real `adb`: they
  patch `adb.run`.
- Android card: `layout == "esde"` and `device != "windows-pc"` (`full` counts as Android).
- The new card field is `android_volume` (a string like `"6AF3-53E9"`), written with `store.update_card` /
  `store.write_cards`.
- Default RetroArch folders when the cfg value is empty or `default`: `/storage/emulated/0/RetroArch/saves` and
  `/storage/emulated/0/RetroArch/states`.
- The config path is `/storage/emulated/0/Android/data/<pkg>/files/retroarch.cfg`. Packages match `com.retroarch*`.
- Nothing is pushed to the device in `--dry-run`. RetroArch is never force-stopped.
- Missing `adb`: fail (exit 2) with `brew install android-platform-tools`.
- Conventional Commits, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Save and ROM names with spaces, parentheses, apostrophes and `&` (`Pokémon - Crystal (USA).srm`, `Ms. Pac-Man`,
  `Tom & Jerry`) must survive every `adb shell` command. Every remote path goes through `shlex.quote`. Owned by
  Task 1 (`shell` quoting test) and Task 4 (stage/push with such names).
- A RetroArch with no saves or states folders yet (fresh install): stash says there are none, and apply creates the
  folders on push (`mkdir -p`). Owned by Task 4.
- The device drops off Wi-Fi mid-run (`adb` exits non-zero): a clear `ui.fail` (exit 1) naming the device, with the
  temp folder still removed. Owned by Task 4 (push failure test) and Task 5 (cleanup on error).
- An `unauthorized` or `offline` device in `adb devices`: shown as a hint, never picked, no crash. Owned by Task 3.
- Two SD volumes, or none with `ROMs/`: ask among those with `ROMs/`, or fail saying no card with `ROMs/` is in the
  device. Owned by Task 2.

---

### Task 1: `adb.py` wrapper

**Files:**
- Create: `src/sync_roms/adb.py`
- Test: `tests/test_adb.py`

**Interfaces:**
- Produces:
  - `class AdbError(Exception)`.
  - `require() -> str`: the adb path (`shutil.which("adb")`), else `ui.fail("…brew install android-platform-tools…", 2)`.
  - `run(*args: str, serial: str | None = None, check: bool = True, timeout: float = 60) -> str`: stdout. It passes
    `-s serial` when given and raises `AdbError(stderr or stdout)` on a non-zero exit when `check`. It is the only
    caller of `subprocess.run`, and tests patch it.
  - `Device = namedtuple("Device", "serial state model")`.
  - `devices() -> list[Device]`: parsed from `adb devices -l`, with the model's `_` turned into spaces (`""` when absent).
  - `shell(serial: str, *words: str, check: bool = True) -> str`: `run("shell", " ".join(shlex.quote(w) for w in words), serial=serial, check=check)`.
  - `shell_ok(serial: str, *words: str) -> bool`: true on exit 0. It uses `check=True` and catches `AdbError`.
  - `prop(serial: str, name: str) -> str`: `getprop`, stripped.
  - `mdns_services() -> list[tuple[str, str, str]]`: `(name, kind, "host:port")` from `adb mdns services` lines with
    three tab- or space-separated fields. The header line is skipped.
  - `pair(addr: str, code: str) -> None`, `connect(addr: str) -> bool` (true when the output has `connected to`),
    `pull(serial, remote, local) -> None` (`pull -a`), `push(serial, local, remote) -> None`.

- [ ] **Step 1: Write the failing tests** in `tests/test_adb.py` (patch `adb.subprocess.run` for `run` itself, and
  `adb.run` for the rest):
  - `test_devices_parses_l`: the output
    `"List of devices attached\nadb-1f137be-k7i7uw._adb-tls-connect._tcp device product:kalama model:Retroid_Pocket_Nova device:kalama transport_id:4\nR5CT unauthorized usb:1-1 transport_id:2\n\n"`
    gives `[Device("adb-1f137be-k7i7uw._adb-tls-connect._tcp", "device", "Retroid Pocket Nova"), Device("R5CT", "unauthorized", "")]`.
  - `test_shell_quotes`: `adb.shell("S", "ls", "/x/Tom & Jerry (USA).srm")` calls `run("shell", "ls '/x/Tom & Jerry (USA).srm'", serial="S", check=True)`.
  - `test_run_raises`: a non-zero `CompletedProcess` with stderr `"error: closed"` raises `AdbError("error: closed")`,
    and `check=False` returns stdout.
  - `test_run_passes_serial`: `run("pull", "a", "b", serial="S")` runs `[<adb>, "-s", "S", "pull", "a", "b"]`.
  - `test_mdns`: `"List of discovered mdns services\nadb-1f137be-k7i7uw\t_adb-tls-connect._tcp\t192.168.1.5:37011\n"`
    gives `[("adb-1f137be-k7i7uw", "_adb-tls-connect._tcp", "192.168.1.5:37011")]`.
  - `test_connect`: `"connected to 1.2.3.4:5"` is true, and `"failed to connect to 1.2.3.4:5"` is false.
  - `test_require_missing`: with `shutil.which` returning `None`, `SystemExit` code 2.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_adb -v`. Expected: an ImportError on `sync_roms.adb`.
- [ ] **Step 3:** Implement `src/sync_roms/adb.py` with the interfaces above. `run` uses `text=True`,
  `capture_output=True` and `timeout`, and turns a `subprocess.TimeoutExpired` into `AdbError("timed out")`.
- [ ] **Step 4:** Run `uv run python -m unittest tests.test_adb -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(saves): add an adb wrapper`.

### Task 2: Device discovery (volumes, RetroArch, config)

**Files:**
- Create: `src/sync_roms/android.py`
- Test: `tests/test_android.py`

**Interfaces:**
- Consumes: `adb.shell`, `adb.shell_ok`, `adb.AdbError` (Task 1).
- Produces (in `android.py`):
  - `is_android(entry: dict) -> bool` (the Global Constraints rule).
  - `card_volumes(serial: str, roms_dir: str) -> list[str]`: the ids of `ls /storage` other than `emulated` and
    `self`, keeping those for which `/storage/<id>/<roms_dir>` is a dir (`adb.shell_ok(serial, "test", "-d", path)`).
  - `retroarch_package(serial: str) -> str`: from `pm list packages`, lines `package:com.retroarch…`. With several,
    `picker.filter_list("🕹️  Which RetroArch?", …)` (Esc exits 0). With none, `ui.fail("No RetroArch installed on <model/serial>", 2)`.
  - `parse_config(text: str) -> dict[str, str]`: `key = "value"` lines, with the quotes stripped.
  - `Folders = namedtuple("Folders", "saves states sort_saves sort_states")`.
  - `ra_folders(cfg: dict) -> Folders`: it applies the defaults and reads the sort flags (`"true"` means sorted).
    `savefiles_in_content_dir`/`savestates_in_content_dir` `"true"` and `sort_savefiles_by_content_enable`/
    `sort_savestates_by_content_enable` `"true"` each give `ui.fail(...)`, exit 2, naming the setting and saying to turn it off.
  - `read_folders(serial: str, pkg: str) -> Folders`: `cat` of the config path, then `ra_folders`. An `AdbError`
    gives `ui.fail(f"Can't read RetroArch's settings at {path}: …", 2)`.
  - `running(serial: str, pkg: str) -> bool`: `adb.shell_ok(serial, "pidof", pkg)`.
  - `wait_closed(serial: str, pkg: str) -> None`: while `running`, print the "save in-game, then close RetroArch on the
    device" message and `ui.confirm("Closed it? (Enter checks again)", default=True)`. A false answer prints
    `ui.yellow("↩️  Stopped: RetroArch is still open")` and raises `SystemExit(0)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_android.py`, with a fake `adb.run` that answers by command
  string from a dict:
  - `test_is_android`: `{"layout": "esde", "device": "retroid-pocket-nova"}` and `{"layout": "esde", "device": "full"}`
    are true; `{"layout": "esde", "device": "windows-pc"}` and `{"layout": "knulli", …}` are false.
  - `test_card_volumes_keeps_those_with_roms`: `ls /storage` gives `"6AF3-53E9\nemulated\nself\nAAAA-BBBB\n"`, and
    only `/storage/6AF3-53E9/ROMs` tests as a dir, which gives `["6AF3-53E9"]`.
  - `test_parse_config`: `'savefile_directory = "/storage/emulated/0/RetroArch/saves"\nsort_savefiles_enable = "true"\n'`.
  - `test_ra_folders_defaults`: `{"savefile_directory": "default", "savestate_directory": ""}` gives the two default
    paths, both sort flags false.
  - `test_ra_folders_real_nova`: the eight lines read from the Nova (see the spec's chat findings: saves
    `/storage/emulated/0/RetroArch/saves`, states `…/states`, sort savefiles and savestates `"true"`, the others `"false"`)
    give `Folders(".../saves", ".../states", True, True)`.
  - `test_ra_folders_content_dir_fails`: `savefiles_in_content_dir = "true"` gives `SystemExit` code 2.
  - `test_read_folders_unreadable_fails`: `cat` raises `AdbError("No such file")`, which gives `SystemExit` code 2.
  - `test_wait_closed_rechecks`: `running` is true, then false; `ui.confirm` is patched true; it returns after two
    checks.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_android -v`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement the Task 2 functions in `src/sync_roms/android.py`.
- [ ] **Step 4:** Run `uv run python -m unittest tests.test_android -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(saves): find an android device's sd card and retroarch folders`.

### Task 3: Picking the device and card, and pairing

**Files:**
- Modify: `src/sync_roms/android.py`
- Modify: `src/sync_roms/data/cards.schema.json` (add `android_volume`: `{"type": "string", "description": "The SD card's Android volume id (/storage/<id>), remembered by saves stash/apply"}`)
- Test: `tests/test_android.py`

**Interfaces:**
- Consumes: Task 1 (`devices`, `prop`, `mdns_services`, `pair`, `connect`) and Task 2 (`card_volumes`, `is_android`).
- Produces:
  - `reconnect() -> None`: `adb.connect` each `_adb-tls-connect._tcp` service whose name isn't the start of a
    connected serial. Errors are ignored.
  - `setup_device() -> None`: prints the steps (Settings → About → tap Build number 7 times; Developer options →
    Wireless debugging on, same Wi-Fi as this computer; "Pair device with pairing code"). It then polls
    `mdns_services()` every second for up to 30 s for a `_adb-tls-pairing._tcp` entry, else
    `ui.ask("Pairing IP:port shown on the device: ")`. Then `ui.ask("6-digit pairing code: ")` and `adb.pair`, then
    `reconnect()`. If no device connects within 10 s, `ui.ask("IP:port under Wireless debugging (not the pairing one): ")`
    and `adb.connect`. An `AdbError` is printed as a warning and returns, and an empty answer returns.
  - `Target = namedtuple("Target", "serial model volume card")`.
  - `resolve(card: str | None, cards: dict, roms_dir: str = "ROMs") -> Target`. It calls `adb.require()` and
    `reconnect()`. For a named card with `android_volume`, the first connected device whose `card_volumes` has it,
    without asking. Otherwise the device picker loop: `picker.filter_list("📱 Which device?", labels, hint=…)`, the
    rows are the connected devices `"<model>  (<serial>)  <card or 'new card'>"`, then `"➕ Set up a new device"`.
    Devices in any other state are printed first as `ui.dim("  <serial>: unauthorized — accept the prompt on the device")`
    (offline: `offline — reconnect Wireless debugging`). Picking the last row runs `setup_device()` and shows the
    picker again, and Esc exits 0. A device with no volume holding `roms_dir` fails (exit 2,
    `No SD card with ROMs/ in <model>`). With several volumes, the one a card has, else ask. The card is the one whose
    `android_volume` matches, else (when `card` is given) that card, else ask `"🃏 Which card is this?"` among the
    `is_android` cards, those whose `device` id's devices.json `name` equals the model listed first. The answer is
    saved: `android_volume` set on the card and popped from any other card, in one `store.write_cards`. A named
    card whose picked device holds another card's volume fails (exit 2) naming both.

- [ ] **Step 1: Write the failing tests** (fake `adb.run`; patch `picker.filter_list` and `ui.ask`; cards via
  `store.write_cards`):
  - `test_named_card_finds_its_device`: cards `{"POCKETNOVA": {"layout": "esde", "device": "retroid-pocket-nova", "android_volume": "6AF3-53E9"}}`,
    one connected device with that volume. `resolve("POCKETNOVA", cards)` gives a `Target` with `volume="6AF3-53E9"` and
    `card="POCKETNOVA"`, and `filter_list` is never called.
  - `test_new_volume_asks_and_remembers`: with no `android_volume` anywhere, `filter_list` picks the device, then the
    card. Afterwards `store.load_cards()["POCKETNOVA"]["android_volume"] == "6AF3-53E9"`.
  - `test_volume_moves_between_cards`: `OLD` had the volume; picking `NEW` for it leaves `OLD` without `android_volume`.
  - `test_named_card_wrong_device_fails`: the volume belongs to `OTHER`, and `resolve("POCKETNOVA", …)` after picking that
    device gives `SystemExit` code 2.
  - `test_unauthorized_not_listed`: devices `[device, unauthorized]` list one device row plus the setup row.
  - `test_setup_row_runs_setup`: picking the last row calls `setup_device` once, then the picker shows again.
  - `test_no_roms_volume_fails`: `SystemExit` code 2.
  - `test_reconnect_connects_unconnected`: mdns lists `adb-X` (connected) and `adb-Y` (not), and only `adb-Y`'s address
    is connected.
  - `test_setup_device_pairs`: the mdns pairing entry `("adb-Y", "_adb-tls-pairing._tcp", "1.2.3.4:4000")` and the code
    `"123456"` give `adb.pair("1.2.3.4:4000", "123456")`. Patch `time.sleep`.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_android -v`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement `reconnect`, `setup_device`, `Target` and `resolve`, and add `android_volume` to `cards.schema.json`.
- [ ] **Step 4:** Run `uv run python -m unittest discover -s tests`. Expected: PASS (the schema tests included).
- [ ] **Step 5:** Commit `feat(saves): pick and pair android devices over wireless adb`.

### Task 4: Staging and pushing

**Files:**
- Modify: `src/sync_roms/android.py`
- Test: `tests/test_android.py`

**Interfaces:**
- Consumes: Task 1 (`shell`, `pull`, `push`), Task 2 (`read_folders`, `retroarch_package`, `wait_closed`), Task 3 (`Target`).
- Produces:
  - `class Session`: fields `target`, `pkg`, `folders`, `base` (the temp dir), `layout` (a copy of the esde layout whose
    `retroarch` has `"dir": "RetroArch"` and `saves`/`states` of `"saves/{core}"`/`"states/{core}"`, or `"saves"`/`"states"`
    when that kind's sort is off), `retroarch_dir` (`<base>/RetroArch`).
  - `open_session(target: Target, layout: dict, layout_name: str, systems: list) -> Session`: `retroarch_package`,
    `read_folders`, `wait_closed`, a `tempfile.mkdtemp(prefix="sync-roms-android-")`. ROM placeholders are empty
    files at `<base>/<roms_dir>/<rel>` for each line of `adb.shell(serial, "find", f"/storage/{volume}/{roms_dir}", "-type", "f")`,
    limited to the folders of `systems` in `layout_name`: one `find` per system folder that exists, so a huge
    non-ROM tree isn't walked. Then `adb.pull` of `folders.saves` into `<base>/RetroArch/saves` and of
    `folders.states` into `<base>/RetroArch/states`, each skipped when the remote dir is missing
    (`shell_ok("test", "-d", …)`). Pull into a sibling temp name and `os.rename`, since `adb pull dir dest` nests
    `dir`'s basename. The local `saves`/`states` dirs exist afterwards either way. It prints
    `📱 <card> on <model> (RetroArch <pkg>)`.
  - `Session.remote(local: str) -> str`: maps `<base>/RetroArch/saves/...` to `folders.saves + "/..."` (`states` likewise).
    It raises `ValueError` for any other path.
  - `Session.push(paths: list[str]) -> list[str]`: for each path, `adb.shell(serial, "mkdir", "-p", parent)`, then
    `adb.push`. It returns the remote paths that raised `AdbError` and keeps going.
  - `Session.close() -> None`: `shutil.rmtree(base, ignore_errors=True)`.

- [ ] **Step 1: Write the failing tests** (a fake `adb.run` whose `pull` copies from a fake remote tree in a temp dir
  and whose `push` copies into it):
  - `test_stage_pulls_saves_and_states`: the remote `…/saves/Gambatte/Tetris Plus (USA, Europe) (SGB Enhanced).srm`
    ends up at `<base>/RetroArch/saves/Gambatte/` with the same name and contents.
  - `test_stage_rom_placeholders`: the remote `ROMs/gb/Tom & Jerry (USA).zip` gives an empty `<base>/ROMs/gb/Tom & Jerry (USA).zip`.
  - `test_stage_missing_remote_dirs`: with no states dir, `<base>/RetroArch/states` exists and is empty, and there is no error.
  - `test_sort_off_flat_layout`: `Folders(..., sort_saves=False, sort_states=True)` gives `layout["retroarch"]["saves"] == "saves"`
    and `states == "states/{core}"`, and `catalog`'s own esde layout is unchanged.
  - `test_remote_mapping`: `remote("<base>/RetroArch/states/Gambatte/X.state1")` gives `"/storage/emulated/0/RetroArch/states/Gambatte/X.state1"`.
  - `test_push_mkdir_and_failures`: one push raises `AdbError`. It returns that remote path, still pushes the other, and
    calls `mkdir -p` with the quoted parent.
  - `test_waits_for_retroarch`: `open_session` calls `wait_closed` before any `pull`.
  - `test_close_removes_temp`.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_android -v`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement `Session`, `open_session`, `remote`, `push` and `close`.
- [ ] **Step 4:** Run `uv run python -m unittest tests.test_android -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(saves): stage an android device's saves in a temp folder`.

### Task 5: `saves` integration and docs

**Files:**
- Modify: `src/sync_roms/saves.py` (`card_setup`, `_card`, `stash_command`, `apply_command`)
- Modify: `src/sync_roms/cli.py` (`SUBCOMMANDS["saves"]` text, `TOPICS["saves"]`)
- Modify: `README.md` (the "Moving saves between cards" section: the paragraph at line ~460 and the **Android** bullet at ~478)
- Modify: `CLAUDE.md` (the Card fields table: an `android_volume` row, written by `saves stash`/`apply`, "the SD card's
  Android volume id"; plus one bullet under "What sync puts on a card", next to the Pickles one: `saves stash`/`apply` reach
  Android cards over adb through `android.py`, staging a temp copy)
- Test: `tests/test_saves.py`

**Interfaces:**
- Consumes: `android.is_android`, `android.resolve`, `android.open_session`, `Session.base`/`.layout`/`.retroarch_dir`/
  `.push`/`.remote`/`.close`.
- Produces: `card_setup(args) -> (base, name, setup, catalog, session | None)`, and `_card` returns
  `session` as a 7th element. These are the only callers: update both commands.

Card argument rules in `card_setup`:
1. `args.card` is an existing folder: today's path mode.
2. `args.card` is a name in `cards.json`: an Android card goes to adb mode; any other card gives
   `ui.fail(f"{name!r} isn't an Android card: pass its mounted folder", 2)`.
3. `args.card` is neither: today's "No card named" failure.
4. No `args.card`: the current folder's basename is in `cards.json`, so path mode on cwd; else adb mode with `resolve(None, cards)`.

In adb mode the `os.path.isdir(base)` check is skipped (the card isn't mounted), and `args.retroarch` gives `ui.fail("--retroarch only applies to a mounted card", 2)`. `base = session.base`,
the layout used is `session.layout`, and `args.retroarch = session.retroarch_dir`. The terminal check in `_card` happens
before any adb call.

- [ ] **Step 1: Write the failing tests** in `tests/test_saves.py` (patch `android.resolve` and `android.open_session`
  with a fake `Session` whose `base` is a temp folder you fill like the existing esde tests do, and whose `push` records
  its paths):
  - `test_name_of_android_card_uses_adb`: `saves stash POCKETNOVA` (not a folder) calls `resolve("POCKETNOVA", …)` and
    stashes from the session's base, with the stash's `card == "POCKETNOVA"`.
  - `test_name_of_other_card_fails`: a `knulli` card's name gives `SystemExit` code 2.
  - `test_cwd_card_keeps_path_mode`: cwd named after a card means no `resolve` call.
  - `test_no_arg_other_cwd_uses_adb`: cwd not a card means `resolve(None, …)`.
  - `test_retroarch_flag_with_adb_fails`: code 2.
  - `test_apply_pushes_written_files`: apply writes `RetroArch/saves/Gambatte/Game.srm` in the session base, and `push`
    receives exactly that path.
  - `test_apply_dry_run_never_pushes`: `push` is not called.
  - `test_apply_push_failure_exits_1`: `push` returns `["/storage/…/Game.srm"]`, which gives `SystemExit` code 1, and the
    message names the file.
  - `test_session_closed_on_error`: `pick_apply` raises `KeyboardInterrupt`, and `close` is still called.
- [ ] **Step 2:** Run `uv run python -m unittest tests.test_saves -v`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement the card rules. Wrap each command's body after `_card` in `try/finally: session.close()`.
  In `apply_command`, collect `written` (the `dst` of each real copy); after the copy loop, `failed = session.push(written)`
  when there's a session and not `--dry-run`. For each failure, `ui.warn(f"Couldn't copy {path} to the device")`, then
  `ui.fail(f"{len(failed)} file(s) not copied to {card}", 1)` after the summary lines. Print paths shown to the user
  (the differs list, dry-run `src → dst`) as `session.remote(dst)` in adb mode.
- [ ] **Step 4:** Update the help in `cli.py` (`TOPICS["saves"]`: CARD may be a card name; an Android card is reached
  over wireless adb, with the pairing help, the RetroArch-must-be-closed check and the folders read from
  `retroarch.cfg`; `--retroarch` only on a mounted card) and the README section. Replace the Android bullet's "copy that
  folder off the device" advice with the adb flow. Update the CLAUDE.md rows. Keep `tests/test_readme.py` passing (no new flags).
- [ ] **Step 5:** Run `uv run python -m unittest discover -s tests`. Expected: PASS.
- [ ] **Step 6:** Commit `feat(saves): stash and apply android cards over wireless adb`.

### Task 6: Check against the real device (read-only)

- [ ] **Step 1:** Run `uv run sync-roms saves stash POCKETNOVA --dry-run` with the Nova connected. Expected: the
  `📱 POCKETNOVA on Retroid Pocket Nova (RetroArch com.retroarch.aarch64)` line, then the game picker listing the
  Gambatte saves. Esc out. Then run `uv run sync-roms saves apply POCKETNOVA --dry-run` and confirm the paths shown
  are `/storage/emulated/0/RetroArch/...`. Nothing is pushed. A real apply is left to the user.
