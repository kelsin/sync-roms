# Sets in Storage, Step 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Game sets live in storage as `sets/<id>.json` (shared by every machine and every person with their own storage), not in the repo. The repo ships no real game list; set ids and art ids are still plain names.

**Architecture:**
- `store.load_sets()` / the set-file reader read `sets/*.json` from storage through `inventory.files("sets/", sizes=False)` (listing) and `shared.load` (contents, tag-cached mirror under `~/.sync-roms/storage/sets/`). A set's id is its file name without `.json`. The result is cached for the process and rebuilt when a set is written or `reset` is called (callers call `load_sets()` many times per run; do not stat/HEAD every set file each time).
- Set files keep today's format (`name`, optional `description`, `games` with `title`, `system`, `bucket`, optional `files`, `category`, `series`, `variants`) plus one new optional top-level field `"art"`: an id from the Art Book Next `art.json`, picked like a collection's `"art"`. `themeart.set_emoji(game_set)` uses the set's `art` if it has one, else its own id (as today). All 46 current set ids already have art under their id in `art.json`, so no art data changes.
- `sync-roms sets edit` stops opening a PR: it edits the sets and saves changed sets to storage (`shared.write`), and deletes removed ones from storage (`s3.delete_keys`, which keeps the inventory cache in step), after the same review screen it has today.
- The `update-variants` skill scripts, `sync-roms check`, `tools/gen_theme_art.py` and the docs read/write sets the new way.
- `src/sync_roms/data/sets/*.json` stays in the repo in this step (unused by code, kept so the migration script can read it); a later cleanup PR deletes it.
- `tools/migrate_sets.py` copies a folder of set files into storage's `sets/` (dry run by default).

**Tech Stack:** Python standard library, `unittest`.

## Global Constraints

- Run tests with `PYTHONPATH=<worktree>/src /Users/kelsin/src/sync-roms/.venv/bin/python -m unittest discover -s tests` (the venv is editable-installed to the main checkout).
- No code reads `data/sets` any more after Task 1. Tests must not depend on the real shipped set files: tests that need sets build small fixture sets in a temp storage folder (add a helper in `tests/helpers.py` or the existing storage helpers, e.g. `StorageFolder`/`StorageDir`). Never read or write the real `~/.sync-roms` or storage in tests.
- Storage listing only through `inventory.py`; contents through `shared.py`; deleting through `s3.delete_keys`. A storage error while loading falls back to the mirror with a warning (as `shared.load` does) and never crashes; no sets at all (a fresh storage) is a normal state: empty list, editors work, `sets edit` can create the first set.
- Writes refuse an unmounted storage folder (already enforced in `s3.write_file` and `shared.update`); sets editing must show that error, not a traceback (use the editor's existing error/note path).
- A stale cache means another machine's new set appears after `sync-roms cache update` (note it in the docs).
- `store.set_text` format and key order stay stable (a set file round-trips byte for byte); `art` is written only when the set has one.
- `games.schema.json` keeps validating set files; add `art` to it if it lists top-level properties strictly.
- Commits: Conventional Commits, imperative, lowercase, no attribution lines of any kind (no Co-Authored-By, no "Generated with").
- Match the codebase's style: long lines, short comments, no new classes unless needed; remove only code your change orphans.

## Review Focus

- `load_sets()` is cached per run and invalidated by the module's own writes; no per-call storage I/O after the first load.
- Every former caller of `repo_set_files`/`load_sets`/`REPO_DATA + "/sets"`: `store`, `setedit`, `cardedit`, `cardpicks`, `budget`, `edit`, `collectionedit`, `listedit`, `commands` (`check_sets`, `sets` commands, set lists), `bbs`, the two update-variants scripts, `tools/gen_theme_art.py`.
- `sets edit` never needs git/gh; deleting a set removes only that storage object; a set that cards still reference keeps the existing warning.
- No test left that reads `src/sync_roms/data/sets`.

---

### Task 1: Read sets from storage

**Files:**
- Modify: `src/sync_roms/store.py` (set reading: `read_set_file`, `repo_set_files`, `load_sets`, `set_data`/`set_text` for `art`; add a reset for the per-run cache), `src/sync_roms/themeart.py` (`set_emoji` uses `art`), every src caller of the renamed/changed functions (`grep -rn "repo_set_files\|load_sets\|REPO_DATA" src tools .claude`), `src/sync_roms/data/games.schema.json` if needed
- Test: `tests/test_sets.py`, `tests/test_set_data.py` and every test that reads shipped sets (see Global Constraints)

- [ ] **Step 1:** Read the current loaders and their callers. Write failing tests with fixture sets in a temp storage folder: a fresh storage gives `[]`; sets load sorted by name with ids from file names; `art` round-trips through `set_text`/reader and `set_emoji` prefers it; a malformed set file is skipped with a warning (not a crash); the per-run cache is reused and `reset` / a write rebuilds it; a storage error falls back to the mirror.
- [ ] **Step 2:** Implement. Rename `repo_set_files` to a storage-neutral name (e.g. `set_files`) and update all callers. Port the existing tests that depended on the shipped sets to fixture sets (`tests/test_set_data.py` validated the shipped sets' content: replace it with a test that validates fixture set files against `games.schema.json` / the format rules it checks, and keep the format rules enforced for real sets through `sync-roms check` in Task 4).
- [ ] **Step 3:** Full suite green; commit `feat(sets): read game sets from storage`.

### Task 2: sets edit saves to storage

**Files:**
- Modify: `src/sync_roms/setedit.py`, `src/sync_roms/cli.py` (the `sets edit` help line and topic text), `src/sync_roms/commands.py` if it names the PR flow
- Test: `tests/test_setedit.py`

- [ ] **Step 1:** Read `setedit.py` (`repo_sets`, `need_tools`, `open_pr`, `commit_title`, `pr_body`, the menu text) and `tests/test_setedit.py`. Write failing tests with fixture sets in temp storage: editing and saving a set writes its file to storage (and the mirror), a new set is created, a removed set's object is deleted from storage, unchanged sets are not rewritten, nothing needs git or gh, an unmounted storage folder gives a clear message and writes nothing.
- [ ] **Step 2:** Implement: remove `need_tools`, `run`, `open_pr`, `REPO`, `SETS_DIR`, `commit_title`, `pr_body` and the subprocess/tempfile/shutil/time imports they orphan; the review screen stays and its action becomes saving to storage ("Done (review & save)", "no changes, nothing saved"); update the picker prompts and the CLI help text that mention opening a PR.
- [ ] **Step 3:** Full suite green; commit `feat(sets): save edited sets to storage`.

### Task 3: skills, check, theme art, docs

**Files:**
- Modify: `.claude/skills/update-variants/scripts/find_candidates.py`, `apply_variants.py`, `SKILL.md`; `src/sync_roms/commands.py` (`check_sets`: validate the sets in storage with the same `check_game_file` rules); `tools/gen_theme_art.py` (`write_readme` no longer reads a sets folder: names come from `art.json`); the test that requires every set to have a PNG (keep: every `art.json` id has a PNG); `CLAUDE.md`, `README.md`, CLI help
- Test: `tests/test_update_variants.py`, `tests/test_commands.py` / the check tests, `tests/test_themeart.py`

- [ ] **Step 1:** update-variants scripts: list and write sets through the Task 1 loader and `shared.write`/`shared.update` (apply_variants writes set files to storage; keep its "all edits succeed, then write" order and do the storage preflight before writing any set); tests with temp storage.
- [ ] **Step 2:** `check_sets` validates storage sets (empty storage: no problems); `tools/gen_theme_art.py` and the set-PNG test per the Files line; `themeart` docs.
- [ ] **Step 3:** Docs: CLAUDE.md data-files table and text: sets are storage files `sets/<id>.json` mirrored in `~/.sync-roms/storage/sets/` (remove "sets only come from the repo", "Repo ... Never put a real game list in the repo" stays true; `data/sets/` is no longer described as the home of sets; mention the optional `art` field and that "every set has art under its id" now means art.json ids); README sets sections and any "open a PR" wording; the dated docs under `docs/superpowers/` stay untouched.
- [ ] **Step 4:** Full suite green; commit `feat(sets): use storage sets in the variants skill, check and docs`.

### Task 4: one-shot migration script

**Files:**
- Create: `tools/migrate_sets.py`, `tests/test_migrate_sets.py`

- [ ] **Step 1:** Model it on `tools/migrate_scrape_state.py` (same arguments, apply/dry-run, unmounted-storage failure, `inventory.flush()` in a `finally` on `--apply`, `usersettings.apply_settings()` storage setup). It copies `--from DIR` (default `src/sync_roms/data/sets`) `*.json` to storage `sets/<id>.json`; it never overwrites a set that already exists in storage (prints "kept N already in storage"), never deletes anything, validates each file parses as JSON with a `games` list before any write (a bad file exits 1 before any write), and a second `--apply` writes nothing.
- [ ] **Step 2:** Tests with a temp data dir, temp source folder and temp storage folder: dry run writes nothing, apply writes the files byte for byte, existing storage sets are kept, a bad file aborts before writes, unmounted storage exits 1, second apply is a no-op, the storage cache lists the new files afterwards.
- [ ] **Step 3:** Full suite green; commit `chore(tools): add a script that moves the sets into storage`.
