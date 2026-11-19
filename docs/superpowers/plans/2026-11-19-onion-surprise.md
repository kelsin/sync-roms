# Onion Surprise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onion cards with Surprise on get the newest Surprise app from storage's `os/onion/` and a `Roms/surprise.json` of the card's surprises.

**Architecture:** One new module, `src/sync_roms/onion_surprise.py`, modelled on `pico8.py`: `install(...)` puts the app on the card, `write_list(...)` writes the JSON Lines file. `cli.py`'s sync calls both after downloads (next to `pico8.run`) and in the dry run.

**Tech Stack:** Python stdlib (`zipfile`, `json`, `tempfile`, `shutil`), unittest.

**Spec:** `docs/superpowers/specs/2026-11-19-onion-surprise-design.md`; the file format is `~/src/onion-surprise/docs/surprise-json.md`.

## Global Constraints

- Only the `onion` layout, and only when `surprise.enabled(entry)`.
- Zip key: `os/onion/Surprise-v<digits and dots>.zip` (regex `Surprise-v\d+(\.\d+)*\.zip`), newest by natural sort; anything else in `os/onion/` is ignored. Storage listing only through `inventory.files`.
- Never touch anything on the card outside `App/Surprise/`, `App/.Surprise.new/` and `Roms/surprise.json`.
- Card paths in `surprise.json` always start with `/mnt/SDCARD`, never normalised (keep `/../../`).
- Run tests with `python -m unittest discover -s tests`.

## Review Focus

- A zip with a member outside `App/Surprise/` (e.g. `App/Other/x`, `../x`, `/etc/x`) or a symlink member: nothing on the card changes, the installed app stays, failure count 1.
- Install interrupted / failed mid-extract: the old `App/Surprise/` is still there (extract goes to `App/.Surprise.new/` first; a leftover `.Surprise.new` from a past failure is removed before extracting).
- A title with `"`, `:` or `\` (e.g. `Zelda: Link's Awakening`): label stripped of them, entry still written; a ROM file name containing `:` is skipped.
- Two Emu folders pointing at one ROM folder (Onion WS/NGP style): the one named like the ROM folder wins, else first by name.
- Surprise turned off or surprises emptied: an existing `Roms/surprise.json` is removed.

---

### Task 1: Install the app

**Files:**
- Create: `src/sync_roms/onion_surprise.py`
- Modify: `src/sync_roms/runtime.py` (add `ONION_PREFIX = "os/onion/"` beside `PICO8_PREFIX`)
- Test: `tests/test_onion_surprise.py`

**Interfaces:**
- Produces: `newest_zip() -> str | None` (storage key); `install(card: str, layout_name: str, base: str, dry_run: bool) -> int` (failure count, 0 or 1). Records the zip file name in the card's `surprise_app` via `store.update_card(card, surprise_app=name)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_onion_surprise.py`, class `Install(helpers.StorageDir)` like `tests/test_pico8.py` (card at `self.tmp.name/card`, `self.put(key, data)` puts storage files, card entry `store.update_card("c", surprise=True)` where needed; a helper `app_zip(members: dict[str, bytes], symlink=None)` builds zip bytes):
  - `test_newest_zip_by_version`: puts `Surprise-v0.2.0.zip`, `Surprise-v0.10.0.zip`, `Surprise-v0.9.1.zip`, `Surprise-eadef4e.zip`, `Surprise-v1.0.0-dirty.zip` → `newest_zip() == "os/onion/Surprise-v0.10.0.zip"`.
  - `test_installs_and_records`: valid zip (`App/Surprise/config.json`, `App/Surprise/surprise`, `App/Surprise/launch.sh`, `App/Surprise/res/font.ttf`) → files exist under the card's `App/Surprise/`, `surprise` and `launch.sh` mode has `0o111` bits, `surprise_app == "Surprise-v0.1.0.zip"`, no `App/.Surprise.new`.
  - `test_recorded_and_present_skips`: recorded name equals newest and `config.json` + `surprise` exist → card files unchanged (write a marker file into `App/Surprise/`; it survives).
  - `test_recorded_but_missing_reinstalls`: recorded name, `App/Surprise/surprise` missing → reinstalled.
  - `test_newer_replaces_whole_folder`: old app with an extra file `App/Surprise/old.txt`, newer zip → `old.txt` gone, new files there.
  - `test_unsafe_zip_changes_nothing`: for each of `App/Other/x`, `App/Surprise/../../x`, `/abs/x`, a symlink member, and a zip missing `App/Surprise/surprise`: `install` returns 1, existing `App/Surprise/marker` survives, `surprise_app` unchanged, nothing else appears on the card.
  - `test_leftover_new_folder_removed`: a stale `App/.Surprise.new/junk` is gone after a good install.
  - `test_not_onion_or_surprise_off`: `knulli` layout, or card `surprise=False` → returns 0, card untouched.
  - `test_dry_run`: prints a line containing `Surprise-v0.1.0.zip`, card untouched, nothing recorded.

- [ ] **Step 2: Run** `python -m unittest tests.test_onion_surprise -v` → FAIL (module missing).

- [ ] **Step 3: Implement `newest_zip` and `install` in `src/sync_roms/onion_surprise.py`.** Natural sort as in `pico8._natural`. Download with `s3.download((key, tmp_path, size))` into a `tempfile.TemporaryDirectory()`. Member check: `PurePosixPath` name, not absolute, no `..` part, starts with `App/Surprise/`, `(info.external_attr >> 16) & 0o170000 != 0o120000` (not symlink); required `App/Surprise/config.json` and `App/Surprise/surprise`. Extract members by hand (open/write, `os.makedirs`) into `<base>/App/.Surprise.new/` (strip the `App/Surprise/` prefix), then `shutil.rmtree` the old `App/Surprise/` if present and `os.replace` the new folder in. On `OSError`, `zipfile.BadZipFile`, `*s3.ERRORS` or a failed check: `ui.warn(...)`, remove `.Surprise.new`, return 1. Print `🎁 Surprise app <name> → App/Surprise` on success.

- [ ] **Step 4: Run** `python -m unittest tests.test_onion_surprise -v` → PASS.

- [ ] **Step 5: Commit** `feat(onion): install the surprise app from storage`.

### Task 2: Write Roms/surprise.json

**Files:**
- Modify: `src/sync_roms/onion_surprise.py`
- Test: `tests/test_onion_surprise.py`

**Interfaces:**
- Consumes: card entry `surprises` list of `{"system", "bucket", "title", "files"?}` (`bucket` is a storage key `<system>/<file>`; a multi-disc game's `bucket` is its `.m3u`).
- Produces: `emu_folders(base: str) -> dict[str, tuple[str, str]]` (ROM folder name under `Roms/` → (Emu folder name, launch rel)); `lines(base: str, roms_dir: str, surprises: list[dict], folder_of: dict[str, str]) -> list[str]` (`folder_of`: system id → Onion ROM folder name); `write_list(card: str, layout_name: str, base: str, roms_dir: str, systems: list[dict], dry_run: bool) -> bool` (whether the card changed).

Return of `emu_folders` precisely: `{rom folder: (emu folder, launch rel)}`; built from each `<base>/Emu/*/config.json` with JSON keys `rompath` (e.g. `../../Roms/GBA`) and `launch`; unreadable or missing keys skipped; rompath resolved with `posixpath.normpath("Emu/<EMU>/" + rompath)` and kept only when it is `Roms/<one folder>`. Several Emu folders for one ROM folder: the one named like the ROM folder, else first by sorted name.

- [ ] **Step 1: Write the failing tests**, class `List(helpers.StorageDir)` with a helper that writes `Emu/<EMU>/config.json` and `Roms/<SYS>/<file>` on the card:
  - `test_line_format`: GBA emu, `Roms/GBA/Golden Sun (USA).gba` and `Roms/GBA/Imgs/Golden Sun (USA).png` → exactly
    `{"label":"Golden Sun","rompath":"/mnt/SDCARD/Emu/GBA/../../Roms/GBA/Golden Sun (USA).gba","imgpath":"/mnt/SDCARD/Emu/GBA/../../Roms/GBA/Imgs/Golden Sun (USA).png","launch":"/mnt/SDCARD/Emu/GBA/launch.sh","type":5}`
  - `test_no_image_empty_imgpath_omitted`: no Imgs file → line has no `imgpath` key, key order `label,rompath,launch,type`.
  - `test_missing_rom_or_emu_skipped`: surprise whose ROM isn't on the card, and one whose ROM folder has no Emu → no lines.
  - `test_label_stripped`: title `Zelda: Link's "Awakening"\` → label `Zelda Link's Awakening` (strip `"`, `:`, `\`, chars < 0x20; collapse double spaces).
  - `test_path_with_colon_skipped`, `test_long_line_skipped` (value ≥ 256 bytes).
  - `test_shared_rom_folder_prefers_same_name`: Emu `WS` and `WSC` both `../../Roms/WS` → launch uses `Emu/WS`.
  - `test_multi_disc_uses_playlist`: bucket `ps/Game.m3u` on card as `Roms/PS/Game.m3u` → rompath ends `Roms/PS/Game.m3u`.
  - `test_write_list_writes_once_and_removes`: `write_list` writes `Roms/surprise.json` (lines joined with `\n`, trailing `\n`) and returns True; second call returns False and leaves mtime; after `store.update_card("c", surprise=False)` the file is removed and True returned; non-onion layout returns False and writes nothing.
  - `test_write_list_dry_run`: prints a `surprise.json` line, writes nothing.

- [ ] **Step 2: Run** `python -m unittest tests.test_onion_surprise -v` → new tests FAIL.

- [ ] **Step 3: Implement `emu_folders`, `lines`, `write_list`.** Line JSON via `json.dumps(obj, separators=(",", ":"), ensure_ascii=False)` from a dict in key order. ROM rel is `downloads.rom_rel(bucket)`; image stem `os.path.splitext(rel)[0]`, only for top-level rels. `write_list` reads `store.load_cards().get(card)`, `folder_of = {s["bucket"]: s["folders"]["onion"] for s in systems if s["folders"].get("onion")}`, writes `os.path.join(roms_dir, "surprise.json")`.

- [ ] **Step 4: Run** `python -m unittest tests.test_onion_surprise -v` → PASS.

- [ ] **Step 5: Commit** `feat(onion): write surprise.json for the surprise app`.

### Task 3: Wire into sync and document

**Files:**
- Modify: `src/sync_roms/cli.py` (sync: next to both `pico8.run(card, layout_name, base, ...)` calls — the dry-run block, the "nothing to sync" early return, and after downloads)
- Modify: `CLAUDE.md` (Data files table: card's `surprise_app` field; `os/onion/Surprise-v*.zip`; `Roms/surprise.json`), `README.md` if it documents Surprise per frontend (check `tests/test_readme.py` still passes)
- Test: `tests/test_sync_flow.py` or `tests/test_cli_sync.py` (whichever already drives an onion sync)

**Interfaces:**
- Consumes: `onion_surprise.install(card, layout_name, base, dry_run) -> int`, `onion_surprise.write_list(card, layout_name, base, roms_dir, systems, dry_run) -> bool`.

- [ ] **Step 1: Write the failing test** `test_onion_sync_installs_surprise_app_and_list`: an onion card with Surprise on, one surprise ROM synced, `Emu/GBA/config.json` on the card, `os/onion/Surprise-v0.1.0.zip` in storage → after sync `App/Surprise/surprise` and `Roms/surprise.json` exist; a dry run of the same leaves both absent.

- [ ] **Step 2: Run it** → FAIL.

- [ ] **Step 3: Wire it.** `failed += onion_surprise.install(...)` beside `pico8.run`; `write_list(...)` after `frontend_step(False)` (surprises as saved now), and set `clean._clean_root = base` when it returns True and `clean_card`. Dry run calls both with `True`. The early "nothing to sync" return also calls `install` and `write_list` (it removes a stale list).

- [ ] **Step 4: Run** `python -m unittest discover -s tests` → all PASS.

- [ ] **Step 5: Commit** `feat(onion): sync the surprise app and list` (docs in the same commit).
