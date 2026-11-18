# Scrape State in Storage, Step 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** The scrape state that only references storage ROMs (manual matches, unknown ROMs, not-offered media, hashes, non-games awaiting review, and the `update-variants` skill's judged ROMs) lives in storage, shared by every machine, instead of in `~/.sync-roms/`.

**Architecture:** `scrape_state.py` keeps its public functions (callers don't change) but persists through `shared.py`:

| State | Storage key | Format |
|---|---|---|
| manual matches | `scrapes/<system>/matches.json` | `{rom path: ScreenScraper game id}` |
| unknown ROMs | `scrapes/<system>/unknown.json` | `{rom path: true}` |
| not-offered media | `scrapes/<system>/nomedia.json` | `{rom path: [media types]}` |
| hashes | `scrapes/<system>/hashes.json` | `{rom path: {"size","mtime","hashes"}}` |
| non-games and kept-for-later | `scrapes/notgames.json` | today's `scrape-notgames.json` content (keys `"system/rom"`, plus `"kept"`) |
| judged variants (skill) | `variants-checked.json` | today's `variants-checked.json` content |

In memory the module still works with `"system/rom"` keys; the per-system files hold the ROM path only. Reads come from the local mirror (`~/.sync-roms/storage/...`, kept by `shared.load` by tag) overlaid with pending marks. Every write is "read the storage file fresh, apply the pending changes, write it back" (`shared.update`), so two machines merge instead of overwrite and a removal removes only its own key. Matches and notgames writes happen at once (they are rare, typed by the user); unknown, nomedia and hashes marks stay buffered in memory and are written by `flush_unknown`/`flush_nomedia`/`flush_hashes` (hashes also every `HASH_FLUSH` = 1000 saved hashes), which the scrape commands already call at the end of a run and from their `finally` blocks.

**Tech Stack:** Python standard library, `unittest`.

## Global Constraints

- `scrape_state.py`'s public function names, arguments and return values stay (see its callers in `scrape_online.py` and `scrape_review.py`); only where the data lives changes.
- Never read or write the real `~/.sync-roms` or storage in tests; use the temp data dir and `StorageFolder` helpers the existing tests use (`tests/test_scrape_state.py`, `tests/test_ignore.py`, `tests/test_shared.py`).
- Storage listing goes only through `inventory.py` (`inventory.files(prefix, sizes=False)`, `inventory.tag`, `inventory.cached`); file contents through `shared.py`.
- A storage error while reading falls back to the mirror with a warning (`shared.load` already does). A storage error while writing warns (`ui.warn`) and drops the pending marks; never crashes a scrape run, never loses the in-memory state used for the rest of that run.
- `scrape_files.plan_clean` (`scrape clean`) must not treat the new JSON files under `scrapes/` as media or metadata to delete or rewrite; add a test.
- A corrupt `matches.json` keeps today's warning text style ("... isn't a valid JSON object; its manual matches are ignored, and the next `scrape match` replaces it") naming the storage key.
- No migration code in the runtime modules; the one-shot script lives in `tools/` (Task 5).
- Run tests with `PYTHONPATH=<worktree>/src /Users/kelsin/src/sync-roms/.venv/bin/python -m unittest discover -s tests`.
- Commits: Conventional Commits, imperative, lowercase, no attribution lines of any kind (no Co-Authored-By, no "Generated with").
- Match the codebase's style: long lines, short comments, no new classes unless needed.

## Review Focus

- Two marks for the same ROM, a mark then a clear, and a clear of a system, all give the right file after a flush against a storage file that changed meanwhile (concurrent machine).
- Unknown/nomedia/hashes still read their own unwritten marks before the flush.
- A scrape run that raises still flushes (existing `finally` paths) and a failed storage write only warns.
- No remaining `store.data_dir()` join for `scrape-*.json` or `variants-checked.json` in `src/` and `.claude/`.

---

### Task 1: shared.update

**Files:**
- Modify: `src/sync_roms/shared.py`, `tests/test_shared.py`

- [ ] **Step 1:** Add `update(key, parse, empty, change, dump)`: read the key fresh from storage (`read`; a missing file, `s3.missing(e)` or `FileNotFoundError`, gives `empty`), `data = change(data)` (change mutates or returns the value), `write(key, dump(data))`, and return the value. Use the same missing-file handling as `ignore.add`'s `_fresh`. If `change` leaves the data equal to what was read and the file existed, write nothing.
- [ ] **Step 2:** Tests in `tests/test_shared.py`: creates a missing file, merges into changed storage content (storage changed after the mirror was saved), writes nothing when unchanged, keeps mirror and tag in step with the write.
- [ ] **Step 3:** Full suite; commit `feat(shared): update a storage file from its fresh content`.

### Task 2: scrape_state on storage

**Files:**
- Modify: `src/sync_roms/scrape_state.py`, `tests/test_scrape_state.py`, other tests that write `scrape-*.json` into the data dir (`tests/test_scrape_review.py:265` and any found by `grep -rn "scrape-\(hashes\|matches\|unknown\|nomedia\|notgames\)" tests`), `src/sync_roms/scrape_plan.py`/`scrape_files.py` only if needed by the `plan_clean` constraint

- [ ] **Step 1:** Read `scrape_state.py`, its callers (`grep -rn "scrape_state\." src`) and the tests first. Write failing tests for the table above: round trips per kind through a `StorageFolder`, per-system file placement, pending marks visible before a flush, a flush merging into storage changed by another writer, `clear_unknown(system)` and `clear_unknown()` removing only their keys, `unkeep`/`mark_notgame`/`clear_notgame` semantics unchanged, corrupt `matches.json` warning, write failure only warns, and the `plan_clean` constraint.
- [ ] **Step 2:** Implement. Per-kind loading lists `scrapes/` through `inventory.files("scrapes/", sizes=False)` for the systems having that kind's file (one `shared.load` per system file, merged into `"system/rom"` keys, cached for the run and invalidated on the module's own writes; reset hook for tests as the module has today). Writes go through `shared.update` per affected system file. Drop the old data-dir path code (`_path`, `_sig`, the file-signature cache, tmp-file saving) that nothing uses now.
- [ ] **Step 3:** Raise `HASH_FLUSH` to 1000. Full suite; commit `feat(scrape): keep scrape state in storage`.

### Task 3: variants-checked in storage

**Files:**
- Modify: `.claude/skills/update-variants/scripts/find_candidates.py`, `apply_variants.py`, `SKILL.md`; their tests (`grep -rn "variants-checked\|checked_file" tests .claude`)

- [ ] **Step 1:** Replace the `CHECKED` data-dir path in both scripts with the storage key `variants-checked.json`, read with `shared.load` and written with `shared.update` (keep the file's existing JSON shape). `SKILL.md`'s `checked_file` line says it lives in storage's `variants-checked.json`.
- [ ] **Step 2:** Update their tests (temp storage), full suite, commit `feat(update-variants): keep judged variants in storage`.

### Task 4: docs

**Files:**
- Modify: `CLAUDE.md`, `README.md` (the "Local state" paragraph near line 499), any CLI help naming the old files (`grep -rn "scrape-hashes\|scrape-matches\|scrape-unknown\|scrape-nomedia\|scrape-notgames\|variants-checked" src README.md CLAUDE.md .claude`)

- [ ] **Step 1:** `CLAUDE.md`: in the data-files text, `scrape-notgames.json` and `variants-checked.json` are no longer personal local files; describe the storage keys from the Architecture table, and that `~/.sync-roms/storage/` mirrors them. `README.md`: the paragraph becomes shared state in storage's `scrapes/` (and what each file holds).
- [ ] **Step 2:** Full suite; commit `docs: describe scrape state in storage`.

### Task 5: one-shot migration script

**Files:**
- Create: `tools/migrate_scrape_state.py`, `tests/test_migrate_scrape_state.py`

- [ ] **Step 1:** The script reads the old `~/.sync-roms/scrape-{matches,unknown,nomedia,hashes,notgames}.json` and `variants-checked.json`, splits the `"system/rom"` kinds per system, and merges them into storage through `shared.update` (so existing storage content is kept and the result is idempotent). It prints per file what it would write; `--apply` is required to write; it never deletes or edits the old files. Honour `--bucket`/storage options the same way `sync-roms` itself does (reuse `cli`/`runtime` setup the other `tools/` scripts or commands use; if there is none, take the storage setup from `commands.py` for `ignore`/`cache`).
- [ ] **Step 2:** Test with a temp data dir and temp storage folder: dry run writes nothing, `--apply` writes the expected per-system files, a second `--apply` changes nothing, existing storage entries survive.
- [ ] **Step 3:** Full suite; commit `chore(tools): add a script that moves scrape state into storage`.
