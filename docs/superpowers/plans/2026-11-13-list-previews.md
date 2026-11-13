# List Image Previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lists of collections, sets, systems and games show the highlighted row's picture in the existing preview pane.

**Architecture:** A new `src/sync_roms/previews.py` turns a collection/set art id, a system or a game's bucket key into
an image path (or None), doing all lookups lazily and memoized. Each list passes a `preview=lambda i: ...` to
`picker.filter_list`, which already draws the pane and already drops `preview` when the terminal can't draw images.

**Tech Stack:** Python 3 stdlib (`tarfile`, `os`, `shutil`), existing `inventory`, `s3`, `store`, `themeart`,
`scrape_plan` modules; `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-13-list-previews-design.md`

## Global Constraints

- `picker.py` is unchanged.
- Nothing runs unless the terminal draws images: callers build nothing up front; every lookup happens inside a
  `previews.py` call, memoized per run.
- Which scrape files exist comes from `inventory` only, never by listing storage (`s3.list_*` is off limits).
- Game image order: `covers`, `miximages`, `titlescreens`, `screenshots`.
- Storage folder or mirror (`s3.read_root()` truthy): show the file in place. Bucket: download once to
  `store.data_dir()/previews/<key>` with `s3.download((key, path, None))`.
- Theme outlines: `store.data_dir()/theme-art/<commit>/<esde folder>.png`, extracted from `themeart.ESDE_ARCHIVE`'s
  `_inc/systems/artwork-outline/*.png` only; other commits' folders are removed.
- Any `s3.ERRORS` during a lookup gives None (a blank pane), never an exception into the list.
- Tests run with `python -m unittest discover -s tests`; every test module imports `isolate` first (see existing tests).

## Review Focus

- A game whose ROM path has subfolders (`ps2/USA/Game.chd`) or dots in its name (`Dr. Mario.zip`): stem is
  `store.key_title(key)`, so `scrapes/ps2/covers/USA/Game.png` is found — Task 1 test.
- Hovering a system when storage has no theme archive, or the archive can't be read: None, and the archive is not
  retried on every hover in that run — Task 2 test.
- An interrupted outline unpack (exception mid-extract) never leaves a folder that later counts as complete —
  Task 2 test.
- Non-item rows (➕ New, ✅ Done, 🚪 Quit) and rows past the item list return None, never IndexError — Task 3/4 tests.
- Bucket download failure: None, no partial file left behind (`s3.download` already removes `.part`) — Task 1 test.

---

### Task 1: `previews.collection` and `previews.game`

**Files:**
- Create: `src/sync_roms/previews.py`
- Test: `tests/test_previews.py`

**Interfaces:**
- Produces: `collection(art_id: str | None) -> str | None` (= `themeart.art_png(art_id)` when art_id else None);
  `game(key: str) -> str | None` where key is a bucket key like `"gba/Game (USA).zip"`; `GAME_MEDIA = ("covers",
  "miximages", "titlescreens", "screenshots")`; `reset()` clears memoized state (tests call it in `setUp`).

- [ ] **Step 1: Write the failing tests** in `tests/test_previews.py` (patch `inventory.files` and `s3.read_root` /
  `s3.download` with `mock.patch.object`):
  - `test_collection_art_path`: `collection("shmup") == themeart.art_png("shmup")`; `collection(None) is None`.
  - `test_game_prefers_covers_then_mix_title_screenshot`: listing has `scrapes/gba/screenshots/G.png` and
    `scrapes/gba/miximages/G.png` → `game("gba/G.zip")` ends with `scrapes/gba/miximages/G.png`.
  - `test_game_with_subfolder_and_dots`: `scrapes/ps2/covers/USA/Dr. Mario.jpg` → found for `"ps2/USA/Dr. Mario.chd"`.
  - `test_game_without_art_is_none`.
  - `test_folder_storage_returns_file_in_place`: `read_root()` = `"/r"` → `game(...) == s3.safe_join("/r", key)`;
    `s3.download` not called.
  - `test_bucket_downloads_once_into_previews`: `read_root()` = None → first call calls `s3.download` once with
    `(key, os.path.join(store.data_dir(), "previews", key), None)` (fake writes the file); second call doesn't download.
  - `test_bucket_download_error_is_none`: `s3.download` raises `OSError` → None.
  - `test_index_read_once_per_system`: two `game()` calls on one system call `inventory.files` once, with
    `("scrapes/gba/", sizes=False)`.

- [ ] **Step 2: Run** `python -m unittest tests.test_previews -v` → FAIL (no module).

- [ ] **Step 3: Implement** in `previews.py`. Index per system =
  `scrape_plan.scrape_index(inventory.files(f"{scrape_plan.SCRAPES}/{system}/", sizes=False))`, memoized in a module
  dict; system = `key.split("/", 1)[0]`, stem = `store.key_title(key)`. Wrap `inventory.files` and the download in
  `except s3.ERRORS: return None`.

- [ ] **Step 4: Run** `python -m unittest tests.test_previews -v` → PASS.

- [ ] **Step 5: Commit** `feat(previews): find a game's scraped image and a collection's art`

### Task 2: `previews.system` (theme outlines)

**Files:**
- Modify: `src/sync_roms/previews.py`
- Test: `tests/test_previews.py`

**Interfaces:**
- Consumes: `themeart._stored_commit() -> str | None`, `themeart.ESDE_ARCHIVE`, `s3.read_root()`, `s3.download`.
- Produces: `system(system: dict) -> str | None` (system is a `systems.json` entry; uses `system["folders"].get("esde")`).

- [ ] **Step 1: Write the failing tests** (build a small `.tar.gz` in a temp dir with a top folder
  `art-book-next-es-de-abc/` holding `_inc/systems/artwork-outline/gba.png`, `.../mame.png` and `theme.xml`):
  - `test_system_outline_from_folder_archive`: `read_root()` = temp root holding the archive at `ESDE_ARCHIVE`,
    `_stored_commit` → `"abc"` → `system({"folders": {"esde": "gba"}})` ==
    `os.path.join(store.data_dir(), "theme-art", "abc", "gba.png")` and the file exists; `theme.xml` was not extracted.
  - `test_outline_unpacked_once`: a second `system()` call (after `reset()`, same commit) doesn't open the archive
    (patch `tarfile.open` to fail after the first run).
  - `test_new_commit_replaces_old_folder`: existing `theme-art/old/` is removed after unpacking `abc`.
  - `test_no_archive_is_none_and_not_retried`: `_stored_commit` → None → None; a second call doesn't call
    `_stored_commit` again.
  - `test_interrupted_unpack_is_not_complete`: extraction raises mid-way → None, and `theme-art/abc/` doesn't exist.
  - `test_bucket_archive_downloaded_to_temp`: `read_root()` None → `s3.download` fetches the archive to a temp file
    (removed afterwards) and the outline is found.
  - `test_system_without_esde_folder_is_none`.

- [ ] **Step 2: Run** `python -m unittest tests.test_previews -v` → new tests FAIL.

- [ ] **Step 3: Implement.** Extract with `tarfile.open(path, "r|gz")`, keeping members whose path after the top folder
  starts with `_inc/systems/artwork-outline/` and ends `.png`, written flat into `theme-art/<commit>.part/`, then
  renamed to `theme-art/<commit>/` (so a folder without `.part` is complete). Remove other entries under `theme-art/`.
  Remember the outline folder (or a failure) in module state so it is resolved once per run.

- [ ] **Step 4: Run** `python -m unittest tests.test_previews -v` → PASS.

- [ ] **Step 5: Commit** `feat(previews): show the theme's outline art for a system`

### Task 3: Wire collection, set and system lists

**Files:**
- Modify: `src/sync_roms/cardedit.py` (collections list ~line 348, sets list ~395, card's systems ~238),
  `src/sync_roms/collectionedit.py` ("Which collection?" ~222, "Add games from which system?" ~82),
  `src/sync_roms/setedit.py` ("Which set?" ~227, "Add games from which system?" ~49),
  `src/sync_roms/listedit.py` ("Add games from which set?" ~79), `src/sync_roms/upload.py` (~213),
  `src/sync_roms/diff.py` (~230)
- Test: the matching `tests/test_*.py`

**Interfaces:**
- Consumes: `previews.collection(art_id)`, `previews.system(system)`.
- Collections use their `art`; sets use their own id (`previews.collection(set["id"])`, every set has art under its
  id); systems use `previews.system(s)` for the system the row stands for.

- [ ] **Step 1: Write failing tests**: in each module's existing test file, extend one test that drives the list
  through the fake `filter_list` to assert `kwargs["preview"]` maps a row to the right call (patch `previews.collection`
  / `previews.system` to return a marker) and returns None for rows past the items (➕ New, ✅ Done, 🚪 Quit).
- [ ] **Step 2: Run** `python -m unittest discover -s tests` → those FAIL.
- [ ] **Step 3: Implement**: add `preview=lambda i: ... if i < n else None` at each call site, indexing the same list
  the labels were built from. No work before the call.
- [ ] **Step 4: Run** `python -m unittest discover -s tests` → PASS.
- [ ] **Step 5: Commit** `feat(edit): show collection, set and system art while browsing`

### Task 4: Wire game lists

**Files:**
- Modify: `src/sync_roms/cardedit.py` (per-system game editor ~568), `src/sync_roms/edit.py` (`filter_list` ~79, rows
  carry `(system, key, ...)`), `src/sync_roms/collectionedit.py` (games of a collection, change category ~129, add from
  system), `src/sync_roms/setedit.py` (same, ~63), `src/sync_roms/listedit.py` (game lists)
- Test: matching `tests/test_*.py`

**Interfaces:**
- Consumes: `previews.game(key)` with the row's bucket key (`game["bucket"]` for collection/set games; the row key for
  system game lists).

- [ ] **Step 1: Write failing tests** as in Task 3: the fake `filter_list` asserts `kwargs["preview"](i)` calls
  `previews.game` with row i's bucket key, including with a set/metadata filter active (rows filtered).
- [ ] **Step 2: Run** `python -m unittest discover -s tests` → FAIL.
- [ ] **Step 3: Implement** the `preview=` argument at each site from the same row list as the labels.
- [ ] **Step 4: Run** `python -m unittest discover -s tests` → PASS.
- [ ] **Step 5: Commit** `feat(edit): show a game's scraped art while browsing`
