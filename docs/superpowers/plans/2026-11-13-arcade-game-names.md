# Arcade Game Names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Editors show, and new picks save, proper names for `mame` and `fbneo` games.

**Architecture:** A new `names.py` gives `title(key)`: the clones.json DAT name for family sets, else the scraped
`name` from storage's `scrapes/<system>/metadata.json`, else `store.key_title(key)`. Scraped names are kept in
`~/.sync-roms/names.json` per system with the metadata file's storage tag, reread only when `inventory.tag` changes
(same pattern as `ignore.py`). Callers that build editor rows or new titles switch from `store.key_title`.

**Tech Stack:** Python stdlib, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-13-arcade-game-names-design.md`

## Global Constraints

- Only `mame` and `fbneo` keys get names; every other key returns `store.key_title(key)` with no storage access.
- Clone/parent names match `scrape_plan.variant_tags`' `name` exactly.
- Existing saved `title`s in cards and sets are never rewritten.
- Storage is read only through `inventory.tag` (for the tag) and `s3.get_text` (for contents).
- Tests run with `python -m unittest discover -s tests`.

## Review Focus

- Storage unreachable / share unmounted: warn once, use the local copy; no local copy → set names, editor still opens.
- `metadata.json` removed from storage: that system's cached names are dropped.
- Malformed `metadata.json` (not an object, entry without `name`, non-string name): those entries are skipped.
- ROM in a subfolder or a MAME CHD folder key (`mame/kinst`, `mame/kinst/kinst.chd`): lookup is by the ROM path
  after the system folder; a key with no entry falls back to the set name.
- Many lookups in one editor open: metadata is read at most once per system per run.

---

### Task 1: `names.py`

**Files:**
- Create: `src/sync_roms/names.py`
- Modify: `tests/isolate.py` (after the `ignore._keys` line)
- Test: `tests/test_names.py`

**Interfaces:**
- Produces: `names.title(key: str) -> str`; `names.reset() -> None` (forget what was loaded this run);
  `names.KEY = "names.json"` (file name in `store.data_dir()`); `names.SYSTEMS = ("mame", "fbneo")`.
- Local file shape: `{system: {"tag": str, "names": {ROM path: name}}}`.

- [ ] **Step 1: Write the failing tests** in `tests/test_names.py`, subclassing `test_inventory.StorageFolder`,
  calling `names.reset()` in `setUp` (and `addCleanup` restoring the isolated state set in `isolate.py`). A helper
  writes `scrapes/<system>/metadata.json` under `self.root.name`, optionally with an `os.utime` mtime.
  - `test_clone_gets_dat_name`: `title("fbneo/1941j.zip") == "1941: Counter Attack (Japan)"` (from clones.json).
  - `test_parent_gets_dat_name`: `title("mame/1942.zip") == "1942 (set 1)"`.
  - `test_scraped_name_for_standalone_set`: metadata `{"005.zip": {"name": "005"}}` but use a stem not in
    clones.json, e.g. `{"zzstand.zip": {"name": "Stand Alone"}}` → `title("mame/zzstand.zip") == "Stand Alone"`.
  - `test_falls_back_to_set_name`: no metadata → `title("mame/zzstand.zip") == "zzstand"`.
  - `test_other_systems_untouched`: `title("gba/Some Game.zip") == "Some Game"` with `inventory.tag` patched to raise
    `AssertionError` (no storage access).
  - `test_saves_local_copy_and_reuses_it_on_same_tag`: after one lookup, local `names.json["mame"]["names"]` holds
    the entry; `reset()`, patch `s3.get_text` to raise `AssertionError`, lookup still returns the scraped name.
  - `test_rereads_on_tag_change`: change the metadata file (new mtime) → new name after `reset()`.
  - `test_removed_metadata_drops_names`: delete the file, `reset()` → set name, and `"mame"` gone from local file.
  - `test_storage_error_uses_local_copy_with_warning`: patch `inventory.tag` to raise `OSError` → scraped name from
    local copy, stderr contains `"names"`.
  - `test_malformed_entries_skipped`: metadata `{"a.zip": "x", "b.zip": {"name": 3}, "c.zip": {"name": "C"}}` →
    `a`, `b`, `C`.
  - `test_metadata_read_once_per_run`: with `s3.get_text` wrapped in a mock, 20 lookups → `get_text` called once.
  - `test_subfolder_path`: metadata `{"kinst": {"name": "Killer Instinct"}}` → `title("mame/kinst") ==
    "Killer Instinct"` (pick a stem not in clones.json if `kinst` is).

- [ ] **Step 2: Run** `python -m unittest tests.test_names -v` — Expected: FAIL, `ImportError` on `names`.

- [ ] **Step 3: Implement `src/sync_roms/names.py`.** Module docstring in the style of `ignore.py`. Lock and
  per-run `_scraped: dict | None` (system → {ROM path: name}), loaded lazily per system. Per system: read local
  copy; `tag = inventory.tag(scrape_online.metadata_key(system))` (or the same f-string via `scrape_plan.SCRAPES`, to
  avoid importing `scrape_online`); `None` → drop the system from the local file and return `{}`; equal tag → local
  names; else `json.loads(s3.get_text(key))`, keep `{rom: v["name"]}` where `v` is a dict and the name a non-empty
  str, save. Catch `(*s3.ERRORS, ValueError)` → `ui.warn(f"Couldn't check scraped names for {system} ({e}); using
  the local copy")`; `OSError` on save → warn. `title(key)`: system/rest split; not in `SYSTEMS` → `key_title`;
  stem = `os.path.splitext(os.path.basename(rest))[0]`; clones.json `family["clones"][stem][1]` or
  `family["parents"][stem]`; else scraped `names[rest]`; else `store.key_title(key)`. Load `clones` once per run.

- [ ] **Step 4: In `tests/isolate.py`** add `names._scraped = {s: {} for s in names.SYSTEMS}` with a comment like
  the ignore one (no test reads scraped names from storage unless it calls `names.reset()`).

- [ ] **Step 5: Run** `python -m unittest tests.test_names -v` — Expected: all PASS.

- [ ] **Step 6: Commit** `feat(names): look up proper names for mame and fbneo sets`

### Task 2: Use names in editors and new titles

**Files:**
- Modify: `src/sync_roms/edit.py:101` (new game title when `name` isn't used), `src/sync_roms/edit.py:115`
  (`system_rows` title), `src/sync_roms/edit.py:139` (`set_rows` fallback), `src/sync_roms/store.py:288`
  (`set_games` fallback — import `names` inside the function to avoid a cycle, since `names` imports `store`),
  `src/sync_roms/commands.py:296`, `src/sync_roms/surprise.py:159`
- Test: `tests/test_edit.py`, `tests/test_surprise.py`

**Interfaces:**
- Consumes: `names.title(key) -> str` from Task 1.

- [ ] **Step 1: Write failing tests.**
  - `test_edit.py`: `test_system_rows_use_arcade_names`: `edit.system_rows(s, {"fbneo/1941j.zip"})` with
    `s = {"bucket": "fbneo", "games": []}` → row title `"1941: Counter Attack (Japan)"`; the label (4th field)
    still contains `1941j.zip` so set names stay searchable.
  - `test_set_rows_keep_saved_title`: a set game with `"title": "Mine"` on `fbneo/1941j.zip` → row title `"Mine"`.
  - `test_surprise.py`: `surprise._surprise("fbneo", ["fbneo/1941j.zip"])["title"] == "1941: Counter Attack (Japan)"`.

- [ ] **Step 2: Run** those tests — Expected: FAIL (titles are `1941j`).

- [ ] **Step 3: Replace `store.key_title` with `names.title`** at each listed line. Leave `edit.py:101`'s extra-file
  branch (`k != key`) as `names.title(k)` too — extra files of arcade games are CHDs and fall back to set names.

- [ ] **Step 4: Run** `python -m unittest discover -s tests` — Expected: all PASS. If an existing test asserted a
  set name for a mame/fbneo family key, update its expectation to the DAT name (that is the intended change).

- [ ] **Step 5: Manual check** against real storage: `python -c "from sync_roms import names, runtime; ...;
  print(names.title('mame/1942.zip'), names.title('fbneo/mslug3.zip'))"` after `runtime` is set up as the CLI does
  (or open `sync-roms --edit` on a card's mame system) and confirm rows show names.

- [ ] **Step 6: Commit** `feat(edit): show proper names for mame and fbneo games`
