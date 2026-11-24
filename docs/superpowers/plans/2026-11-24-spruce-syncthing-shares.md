# Spruce Syncthing Shares Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync writes the Syncthing server device and the saves/states shared folders into a `spruce` card's Syncthing config, so a new device needs only "accept the device and tick the folders" on the server.

**Architecture:** A pure function in `spruce_syncthing.py` merges the server and folders into `Saves/syncthing/config/config.xml` text (or builds a fresh config when the file is missing), using `xml.etree.ElementTree`. `spruce_syncthing.run` and `entries` call it as a third part next to the core and RetroArch parts, so sync, dry run and `config apply` all get it.

**Tech Stack:** Python 3.12+ stdlib (`xml.etree.ElementTree`, `re`), unittest.

**Spec:** the design agreed in conversation (2026-11-24), summarised here:
- New personal setting `syncthing_server` in settings.json, edited by hand: `{"id": "<server device ID>", "address"?: "tcp://host:22000", "folders": {"saves": "<folder id>", "states": "<folder id>"}}`.
- Repo data `syncthing.json` gets `spruce.folders`: `{"saves": {"path": "Saves/saves", "label": "RetroArch saves"}, "states": {"path": "Saves/states", "label": "RetroArch states"}}`.
- Existing config: add the server device if missing (existing device element left untouched), add each folder if missing (path `/mnt/SDCARD/<path>`, shared with the server), make the server a member of an existing folder with that id at the same path, and set `modTimeWindowS` to `2` on both folders every sync. A folder id already present at another path: warn, leave it as it is.
- Missing config: write a fresh one with the same, plus GUI `0.0.0.0:8384`, user `spruce`, password the bcrypt hash below, `<listenAddress>default</listenAddress>`. Syncthing makes the device's keys and API key on first start.
- Off when `syncthing` is `false`, when `syncthing_server` is unset, and on devices with `"network": false`.

## Global Constraints

- Code must run on Python 3.12. No new dependencies.
- Always `uv run`: tests are `uv run python -m unittest discover -s tests`.
- Card files are written with `cardfs.write_text`; read with `cardfs.text` (returns `""`/falsy when missing).
- Fresh-config GUI password hash (bcrypt of spruce's public default `happygaming`), exact: `$2a$10$Eycxnvj3BtN8fq7suC4.W.ZrDRyH6fgN/pFY.LrOJCG6xIBeDSxdO`
- Device path prefix on the card: `/mnt/SDCARD/`.
- Server device name in the config: `server`. Default address when `address` is absent: `dynamic`.
- Device ID check: uppercase it, then `^[A-Z2-7]{7}(-[A-Z2-7]{7}){7}$`.
- Conventional Commits, lowercase imperative.
- Test modules import `helpers` (which imports `isolate`) before `sync_roms`.

## Review Focus

- `syncthing_server` malformed (not a dict, bad id, a missing or non-string folder id): one warning naming the problem, the config part skipped, cores and RetroArch parts still applied, exit code 0.
- A config.xml that doesn't parse: warning, file left byte-identical.
- Second sync on an already-merged config: no write, no output lines (idempotent).
- Card with no `Saves/` folder (spruceOS not installed): no fresh config created, one warning.
- A device with `"network": false` (e.g. `miyoo-mini`): nothing written and no warning.

---

### Task 1: Config merge function and settings parsing

**Files:**
- Modify: `src/sync_roms/data/syncthing.json` (add `spruce.folders`)
- Modify: `src/sync_roms/spruce_syncthing.py`
- Test: `tests/test_spruce_syncthing.py`

**Interfaces:**
- Produces:
  - `server() -> dict | None`: the validated `syncthing_server` as `{"id": str (uppercased), "address": str, "folders": [(role, folder_id, label, card_path)]}` in `spruce.folders` order, `card_path` like `/mnt/SDCARD/Saves/saves`; `None` when unset or malformed (malformed warns once via `ui.warn`, text starting `syncthing_server in settings.json`).
  - `merge_config(old: str | None, srv: dict) -> tuple[str | None, list[str], list[str]]`: `(new text or None when unchanged, lines, warnings)`. `old` `None` means build a fresh config. Lines are indented `"   "` like the existing parts: `   config.xml: server device`, `   config.xml: folder <label> at <card_path>`, `   config.xml: <label> modTimeWindowS = 2`, `   config.xml: new config` (fresh only, first line).

- [ ] **Step 1: Write the failing tests** in a new `class Config(helpers.DataDir)` in `tests/test_spruce_syncthing.py`:

```python
SERVER = "ABCDEFG-HIJKLMN-OPQRSTU-VWXYZ23-4567ABC-DEFGHIJ-KLMNOPQ-RSTUVWX"
SETTING = {"id": SERVER.lower(), "folders": {"saves": "jkx7j-mnlfo", "states": "w5nqg-xmpq6"}}

def test_data_has_folders(self):  # both roles, path and label strings
def test_server_unset_is_none(self):
def test_server_parsed(self):
    usersettings.save_settings({"syncthing_server": SETTING})
    srv = spruce_syncthing.server()
    self.assertEqual(srv["id"], SERVER); self.assertEqual(srv["address"], "dynamic")
    self.assertEqual(srv["folders"][0], ("saves", "jkx7j-mnlfo", "RetroArch saves", "/mnt/SDCARD/Saves/saves"))
def test_server_malformed_warns_and_is_none(self):  # bad id, missing "states", folders not a dict, setting a list: each None + one warning
def test_fresh_config(self):
    text, lines, warnings = spruce_syncthing.merge_config(None, srv)
    root = ET.fromstring(text)
    # gui address 0.0.0.0:8384, user spruce, password == the hash, options/listenAddress == "default"
    # device id=SERVER name="server" with <address>dynamic</address>
    # two folders with id, label, path, a <device id=SERVER>, <modTimeWindowS>2</modTimeWindowS>, type sendreceive
    self.assertEqual(lines[0], "   config.xml: new config"); self.assertEqual(warnings, [])
def test_merge_keeps_other_content(self):  # an existing config with own device, gui apikey, another folder: those kept, server + 2 folders added
def test_merge_existing_folder_same_path(self):  # folder present without server and modTimeWindowS 0 -> server device added to it, modTimeWindowS 2, no "folder" line
def test_merge_folder_at_other_path_warns(self):  # left unchanged, warning names the folder id and both paths
def test_merge_existing_server_device_untouched(self):  # its <address> and name stay as they were
def test_merge_unchanged_returns_none(self):  # merge twice: second is (None, [], [])
def test_merge_unparsable_warns(self):  # "<configuration" -> (None, [], [warning about config.xml])
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run python -m unittest tests.test_spruce_syncthing -v`
Expected: the new tests fail (`AttributeError: ... 'server'` / `'merge_config'`); existing tests pass.

- [ ] **Step 3: Implement `server()` and `merge_config()`** in `spruce_syncthing.py`, and add `spruce.folders` to `syncthing.json` (keep its compact style). `merge_config` parses with `ET.fromstring`, compares `ET.tostring` before/after to decide "unchanged", and returns the new text with an XML declaration-free `ET.tostring(root, encoding="unicode")` plus a trailing newline (call `ET.indent(root)` only on a fresh config). A fresh config's root is `<configuration version="37">` with `<folder>` elements first, then `<device>`, `<gui enabled="true" tls="false">`, `<options>`. The folder element: attributes `id`, `label`, `path`, `type="sendreceive"`; children `<filesystemType>basic</filesystemType>`, `<device id=SERVER introducedBy=""/>`, `<modTimeWindowS>2</modTimeWindowS>`. Device element: attributes `id`, `name="server"`, `compression="metadata"`, `introducer="false"`; children `<address>`, `<paused>false</paused>`, `<autoAcceptFolders>false</autoAcceptFolders>`. When merging, insert new folders after the last existing `<folder>` (or first in the root) and the new device after the last `<device>` child of the root.

- [ ] **Step 4: Run the tests**

Run: `uv run python -m unittest tests.test_spruce_syncthing -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/data/syncthing.json src/sync_roms/spruce_syncthing.py tests/test_spruce_syncthing.py
git commit -m "feat(syncthing): merge the server and shared folders into a syncthing config"
```

### Task 2: Write the config during sync and config apply

**Files:**
- Modify: `src/sync_roms/spruce_syncthing.py` (`run`, `entries`, new `config_writes`)
- Test: `tests/test_spruce_syncthing.py` (`Card` class)

**Interfaces:**
- Consumes: `server()`, `merge_config(old, srv)` from Task 1.
- Produces: `config_writes(card: str, base: str) -> tuple[list[tuple[str, str]], list[str], list[str]]` in the same `(writes, lines, warnings)` shape as `core_writes`/`retroarch_writes`; `CONFIG = ("Saves", "syncthing", "config", "config.xml")`.

- [ ] **Step 1: Write the failing tests** in `Card` (its card is `anbernic-rg-sp`, which has WiFi; set `syncthing_server` to Task 1's `SETTING` in each):

```python
def test_fresh_config_written(self):  # with a Saves/ folder: run_sync writes Saves/syncthing/config/config.xml, output has "config.xml: new config", and Saves/saves/.stfolder and Saves/states/.stfolder are directories
def test_no_saves_folder_warns(self):  # no Saves/: no config written, output warns spruceOS isn't installed
def test_existing_config_merged(self):  # put() a minimal config; after run it has the server and both folders
def test_no_wifi_device_skipped(self):  # card device miyoo-mini: no config written, no warning
def test_unset_setting_skipped(self):  # no syncthing_server: config not created
def test_dry_run_writes_nothing(self):  # dry_run=True: no file, output lists the config.xml lines
def test_second_sync_quiet(self):  # second run_sync prints nothing about config.xml
def test_bad_setting_still_applies_cores(self):  # malformed setting + a retroarch-x.cfg: cfg still updated, warning printed
def test_entries_list_config(self):  # entries("c", self.card) has Entry(where "Saves/syncthing/config/config.xml") for key "server" and each folder label
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run python -m unittest tests.test_spruce_syncthing -v`
Expected: the new tests fail.

- [ ] **Step 3: Implement `config_writes(card, base)`** and wire it in. It returns `([], [], [])` when `server()` is `None` or the card's device has `"network": False` (factor the device check out of `forced_settings` into `_no_wifi(card) -> bool` and use it in both). A missing config with no `Saves/` dir (`cardfs.is_dir`) warns `"Saves/ is missing (spruceOS isn't installed?); Syncthing's config not written"`. `run` adds it as the third part; on a real (not dry) run, after the writes, it `os.makedirs(<base>/<path>/.stfolder, exist_ok=True)` for each folder when the config part wrote anything. `entries` adds one `applied.Entry("Saves/syncthing/config/config.xml", key, old, new, False)` per item: key `server` (old `None` when missing, new the server id), and per folder its label (old the current path or `None`, new the card path).

- [ ] **Step 4: Run all tests**

Run: `uv run python -m unittest discover -s tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/spruce_syncthing.py tests/test_spruce_syncthing.py
git commit -m "feat(syncthing): set up the shared folders on spruce cards"
```

### Task 3: Documentation

**Files:**
- Modify: `README.md` (the settings paragraph: after the `syncthing` sentence, describe `syncthing_server`, edited by hand, its shape, what sync does with it on spruce cards)
- Modify: `CLAUDE.md` (Personal data `settings.json` list gains `syncthing_server`; Repo data `syncthing.json` line gains `spruce.folders`; a new "What sync puts on a card" bullet for the config.xml merge, the fresh config and the skips)
- Modify: `src/sync_roms/usersettings.py` (`load_settings` docstring gains `"syncthing_server"`)
- Modify: `src/sync_roms/data/setup-guide.html` (spruceOS item of the Syncthing section: steps become sync (now including the Syncthing config from `syncthing_server`), WiFi + RTC, server UI accept the device and tick `ra-saves`/`ra-states`; keep the login line only as a note for checking the device UI)

- [ ] **Step 1: Make the edits.**
- [ ] **Step 2: Run** `uv run python -m unittest discover -s tests` — expected: all pass (`test_readme`, `test_setup_guide` included).
- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md src/sync_roms/usersettings.py src/sync_roms/data/setup-guide.html
git commit -m "docs(syncthing): describe the syncthing_server setting"
```
