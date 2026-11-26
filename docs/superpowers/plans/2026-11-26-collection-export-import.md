# Collection Export and Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Export button on the share page that downloads a collection's file, and `sync-roms collections import FILE...` that adds it (Merge/Replace/Rename/Skip on an id clash).

**Architecture:** `collections_page.page_data(public=False)` embeds each collection's file data as `export`; `page.js` turns it into a download. A new module `collection_import.py` holds the import logic (read, diff, merge); `commands.collections_import_cmd` drives prompts and output.

**Tech Stack:** Python 3.12+ stdlib, `unittest`, vanilla JS in `src/sync_roms/data/collections-page/page.js`.

**Spec:** `docs/superpowers/specs/2026-11-26-collection-export-import-design.md`

## Global Constraints

- Run everything with `uv run` (`uv run python -m unittest tests.test_x`); code must run on Python 3.12.
- Test modules importing `sync_roms` import `isolate` first (directly or via `helpers`).
- Personal files are written with `store.write_json` / `collections.save_collection`; nothing goes to storage.
- Never an Export button on the public page (`page_data(public=True)`).
- The imported id is `store.slug(name)`, never the file name.
- `--yes` answers Merge; clash without terminal and without `--yes` → skipped with a warning.
- CLI rules: subparser in `commands.build_parser`, `cli.TOPICS["collections"]` usage string lists `import`, README Commands table row; `tests/test_readme.py` must pass.
- Conventional Commits, imperative lowercase, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- A file whose `name` slugs to `surprise` or to nothing → skipped with `collection_problem`'s message, not saved.
- Importing the same file twice → second time "nothing differs", skipped, no prompt.
- Rename to a name whose id is also taken → re-asked, not overwritten.
- Merge when the file's games carry `files` (multi-disc) → appended whole; a bucket already present is never duplicated.
- Not-a-collection JSON (a cards export, a list) → warned and skipped, exit code still reflects success of the others (0 unless every file failed to read → 2).

---

### Task 1: Export on the share page

**Files:**
- Modify: `src/sync_roms/collections_page.py` (`page_data`)
- Modify: `src/sync_roms/data/collections-page/page.js` (collection head), `page.css` (button style, reuse `.copy` look)
- Test: `tests/test_collections_page.py`

**Interfaces:**
- Produces: each collection in `page_data(public=False)["collections"]` has `"export": collections._file_data(c)` (dict with `name`, optional `description`/`art`, `games`); absent when `public=True`.

- [ ] **Step 1: Write failing tests** in `tests/test_collections_page.py`:
  - `test_private_page_embeds_export`: with one saved collection `{"id": "couch", "name": "Couch", "games": [{"system": "snes", "bucket": "snes/a.sfc", "title": "A", "note": "n"}]}`, `page_data()["collections"][0]["export"] == {"name": "Couch", "games": [{"system": "snes", "bucket": "snes/a.sfc", "title": "A", "note": "n"}]}`.
  - `test_public_page_has_no_export`: `"export" not in page_data(public=True)["collections"][0]`.
  - `test_export_button_is_conditional`: `page.js` contains `c.export`, `"Export"`, `download` and `application/json`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_collections_page -v` → the three FAIL.
- [ ] **Step 3: Implement.** In `page_data`, add `export` only when not `public`. In `page.js`, when `c.export` is set, add an `Export` `<button type="button">` in the collection's head (stop the click from toggling the row: `event.stopPropagation()`, and keydown Enter/Space likewise), which builds `new Blob([JSON.stringify(c.export, null, 2) + "\n"], {type: "application/json"})`, an `<a download="<c.id>.json">` with `URL.createObjectURL`, clicks it, then revokes the URL; `title` attribute `Download this collection for sync-roms collections import`.
- [ ] **Step 4: Run** the module again → PASS; run `uv run python tools/run_tests.py` → all pass.
- [ ] **Step 5: Check in a browser** (`uv run sync-roms collections page --out <scratch>/p.html` with a test HOME is not needed; a JS syntax check is enough: `node --check src/sync_roms/data/collections-page/page.js` if node exists).
- [ ] **Step 6: Commit** `feat(collections): export a collection from the share page`.

### Task 2: `collections import`

**Files:**
- Create: `src/sync_roms/collection_import.py`
- Modify: `src/sync_roms/commands.py` (`collections_import_cmd`, parser), `src/sync_roms/cli.py` (`TOPICS["collections"]` usage `edit|import|page|publish|retitle|share|unshare` and description mentions importing; help text block for `collections` if one exists), `README.md` (Commands table row `collections import FILE...` and a paragraph after the `collections page` paragraph), `CLAUDE.md` (one sentence in the `collections-page/` bullet: the share page's Export button and `collections import`)
- Test: `tests/test_collection_import.py`

**Interfaces:**
- Consumes: `collections.load_collections`, `collections._clean_games`, `collections.save_collection`, `collections.collection_problem`, `collections.collections_dir`, `store.slug`, `store.backup`, `ui.choose`, `ui.ask`, `ui.has_terminal`, `ui.warn`, `ui.ASSUME_YES`.
- Produces (in `collection_import.py`):
  - `read(path) -> dict` — `{"name", "description"?, "art"?, "games"}` cleaned with `_clean_games`; raises `ValueError(message)` for unreadable/invalid files (same checks as `load_collections`).
  - `differences(mine: dict, theirs: dict) -> tuple[list, list]` — `(only_in_file, only_in_mine)`, game dicts matched by `bucket`, each in its list's order.
  - `merged(mine: dict, theirs: dict) -> dict` — `mine` with `only_in_file` appended to `games`; name, description, art, notes from `mine`. Input not changed.

- [ ] **Step 1: Write failing unit tests** for `read` (valid file; missing `name` → ValueError; list JSON → ValueError; malformed games dropped), `differences` and `merged` (no duplicate buckets; mine's notes win; `files` kept on appended games).
- [ ] **Step 2: Write failing command tests** calling `commands.main(["collections", "import", ...])` (or the project's usual CLI entry used in other command tests) with temp files:
  - free id → saved as `collections/<slug(name)>.json`, output contains `Imported`; file named `Couch (1).json` with name `Couch` → id `couch`.
  - taken id, `--yes` → merged, output `Merged 1 games into Couch` style line, existing notes kept.
  - taken id, input `r` (Replace) → file content replaced, `couch.json.bak` exists.
  - taken id, input `n` then a taken name then a free name (Rename) → saved under the free name's id, first answer re-asked.
  - taken id, input `s` → unchanged, `Skipped`.
  - identical → no prompt, `nothing differs`, unchanged.
  - taken id, no terminal, no `--yes` → unchanged, warning, exit 0.
  - `--dry-run` → nothing written, prints what would happen per file.
  - name `Surprise` → skipped with `collection_problem` message.
  - every file unreadable → exit 2.
  Patch `ui.has_terminal` and `ui._input` the way other command tests in the repo do.
- [ ] **Step 3: Run** `uv run python -m unittest tests.test_collection_import -v` → FAIL.
- [ ] **Step 4: Implement** `collection_import.py` and `collections_import_cmd(args)`. Parser: `colsub.add_parser("import", allow_abbrev=False); common(p, card=False); p.add_argument("files", nargs="+", metavar="FILE")`. Before asking on a clash, print the differences: `Only in the file (N):` then `  <system short name>: <title>` lines, and `Only in yours (N):` the same. Prompt: `ui.choose("<name> exists: merge, replace, rename or skip?", "mrns", "m")`. Rename uses `ui.ask("New name:")` and `collection_problem(name, existing_ids)` until it returns None (empty answer → skip). Result lines: `💾 Imported <name>`, `🔀 Merged N games into <name>`, `💾 Replaced <name>`, `↩️  Skipped <name>`; dry run prefixes `🧪 Would` versions. Keep existing ids up to date across files in one run.
- [ ] **Step 5: Run** the module → PASS; `uv run python tools/run_tests.py` → all pass (including `test_readme`, `test_cli`).
- [ ] **Step 6: Commit** `feat(collections): import collections exported from the share page`.
