# Shared Storage Files, Step 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** One helper for "a file that lives in storage, mirrored locally by tag" (what `ignore.py` does today), with all such mirrors under `~/.sync-roms/storage/` and all caches under `~/.sync-roms/cache/`.

**Architecture:** New `src/sync_roms/shared.py` holds the read / tag-cached load / merge-write logic extracted from `ignore.py`. The local mirror of storage key `K` is `<data_dir>/storage/K` (exact storage text), and each mirror's storage tag is kept in `<data_dir>/storage/.tags.json` as `{key: tag}`. `ignore.py` becomes a thin user of it. Caches (`storage-cache.json`, `preview-cache/`, `previews/`, `theme-art/`, `names.json`) move to `<data_dir>/cache/` through a new `store.cache_dir()`.

**Tech Stack:** Python standard library, `unittest`.

This is step 1 of moving game-referencing data out of git and out of the personal data folder; later steps (scrape state, sets, dropping clones.json) build on `shared.py`.

## Global Constraints

- Behaviour of `ignore.py` does not change: same fallbacks, same warnings, same return values. Only where the local copy lives and its format change (raw storage text + tag in `.tags.json`, instead of `{"tag", "ignored"}`).
- The tag is `inventory.tag(key)` (ETag, or `<mtime_ns>-<size>` in a storage folder), unchanged.
- Reading a shared file's text always comes from storage itself, never from the local mirror of the storage folder (`runtime.ROOT` file or `s3` object), as `ignore._read` does today.
- Old files at the old locations (`~/.sync-roms/ignored.json`, `storage-cache.json`, `preview-cache/`, `previews/`, `theme-art/`, `names.json`) are not migrated and never read; caches rebuild. Do not add migration code.
- Never read or write the real `~/.sync-roms` or storage in tests: tests use the existing temp data dir / `StorageFolder` helpers.
- No call-sites outside `inventory.py` list storage; shared files use `inventory.tag` and `s3.put_text` only.
- Commits: Conventional Commits (`refactor(shared): ...`), imperative, lowercase. No attribution lines of any kind (no Co-Authored-By, no "Generated with").
- Match the codebase's style: long lines, short comments, no new classes unless needed.
- Run the suite with `python -m unittest discover -s tests`.

## Review Focus

- `ignore` tests still pass with only changes to assertions that inspected the old local file format.
- A storage file that disappears removes its mirror and its `.tags.json` entry.
- `.tags.json` is never read from or written to storage, and a corrupt `.tags.json` is treated as empty.
- No remaining `store.data_dir()` join for the five cache names.

---

### Task 1: shared.py and ignore.py on top of it

**Files:**
- Create: `src/sync_roms/shared.py`, `tests/test_shared.py`
- Modify: `src/sync_roms/ignore.py`, `tests/test_ignore.py`

Read `src/sync_roms/ignore.py` and `tests/test_ignore.py` first; the behaviour to preserve is in `_load`, `add`, `remove` and the `LoadTest`/`AddTest`/`RemoveTest` classes.

- [ ] **Step 1:** Write `tests/test_shared.py` (using `StorageFolder` from `tests/test_inventory.py` like `test_ignore.py`) covering `shared.load(key, parse)`: missing in storage gives `parse`'s empty value (`parse(None)` is not used: `load(key, parse, empty)` returns `empty`) and removes mirror and tag; reads storage and saves mirror at `<data_dir>/storage/<key>` plus tag in `.tags.json`; same tag reuses the mirror without reading storage; changed tag re-reads; storage error (`s3.ERRORS`, `ValueError` from `parse`) falls back to the mirror with a `ui.warn`; unmounted storage folder keeps the mirror; corrupt `.tags.json` is treated as empty; nested keys (`sets/a.json`) create folders.
- [ ] **Step 2:** Implement `shared.py` with:
  - `local_path(key)` — `os.path.join(store.data_dir(), "storage", *key.split("/"))`.
  - `read(key)` — storage text (moved from `ignore._read`).
  - `load(key, parse, empty)` — moved from `ignore._load`, generalized: the mirror and the storage file hold text; `parse(text)` returns the value and raises `ValueError` when malformed; the warning text names `key`.
  - `write(key, text)` — `s3.put_text(key, text)`, then save the mirror and `.tags.json` entry from `inventory.tag(key)`.
- [ ] **Step 3:** Rewrite `ignore.py` to use `shared.load`/`shared.read`/`shared.write` (keep `KEY`, `keys`, `is_ignored`, `add`, `remove`, `reset` and their behaviour). Update `tests/test_ignore.py` only where it asserts the old local file format.
- [ ] **Step 4:** Run the full suite; commit `refactor(shared): keep storage files' local copies in one helper`.

### Task 2: cache_dir for the caches

**Files:**
- Modify: `src/sync_roms/store.py` (add `cache_dir()` next to `data_dir()`), `src/sync_roms/inventory.py` (`path()`), `src/sync_roms/previews.py` (`preview-cache`, `previews`, `theme-art`), `src/sync_roms/names.py` (`_local_path`)
- Modify tests that build those paths: `tests/test_previews.py`, anything else `grep -rn "storage-cache\|preview-cache\|theme-art\|\"previews\"\|names.json" tests src` finds.

- [ ] **Step 1:** Add `store.cache_dir()` returning `os.path.join(data_dir(), "cache")`.
- [ ] **Step 2:** Point the five cache locations at it (files keep their names). Directories are created where they are written today (check each writer makes `cache/` if missing; `store.write_json` may already do this).
- [ ] **Step 3:** Update the tests' expected paths. Add one test that `inventory.path()` and `names._local_path()` are under `store.cache_dir()`.
- [ ] **Step 4:** Run the full suite; commit `refactor(store): keep caches in a cache folder`.

### Task 3: docs

**Files:**
- Modify: `CLAUDE.md`, `src/sync_roms/cli.py` (any help text naming the moved paths, e.g. the `~/.sync-roms/storage-cache.json` line)

- [ ] **Step 1:** In `CLAUDE.md`, update the "Data files" text: `ignored.json` mirror lives under `~/.sync-roms/storage/`, and `storage-cache.json`, `preview-cache/`, `names.json` (and the other caches) under `~/.sync-roms/cache/`. Describe the `storage/` (mirror of shared storage files, tags in `.tags.json`) and `cache/` split in one short paragraph.
- [ ] **Step 2:** Update help text in `cli.py` that names a moved path.
- [ ] **Step 3:** Run the full suite; commit `docs: describe the storage and cache folders`.
