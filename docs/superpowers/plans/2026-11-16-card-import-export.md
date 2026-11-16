# Card Import and Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms cards export FILE` and `sync-roms cards import FILE`, so another person's cards can be synced from this machine.

**Architecture:** A new module `src/sync_roms/cardshare.py` holds the pure data functions (export entry, import entry, naming) and the two multi-select lists. `commands.py` gets `cards_export` / `cards_import` handlers and parser entries next to `cards rename`; `cli.py` help, completion words and the README table list them.

**Tech Stack:** Python stdlib, the project's `picker.filter_list` (Textual), `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-16-card-import-export-design.md`

## Global Constraints

- Exported/imported card fields: only `size`, `device`, `layout`, `games`, `excluded` (each only when present). Import adds `"surprise": false`.
- Never copy `collections`, `surprises`, `frontend_collections`, `drivers`, `pico8`, `android_media`, `systems` or any other key.
- `games` keeps `sets` ids and `{"full_system": true}` entries as they are.
- Export flattens every collection game and every `surprises` entry (whether Surprise is on or off) into plain game entries `{"title", "bucket", "files"?, "note"?}` under the game's system, skipping a bucket already listed in that system; a `full_system` system gets none.
- Never overwrite an existing card. Valid name: same rule as `cards_rename` (`name.strip()` non-empty, no `/`).
- Save through `store.write_cards`; refuse (exit 3) when `not store.cards_readable()`, with the same message style as `cards_save_setup`.
- Both commands take `--dry-run` / `-n` via `common(p, card=False)`; dry run prints what would be written and writes nothing.
- Conventional Commits; no AI attribution in commit messages.

## Review Focus

- Export with a collection id that no longer loads (deleted collection): skipped silently, not a crash.
- Import file that isn't valid JSON, isn't an object, or has non-dict entries: `ui.fail` with a clear message (exit 2); non-dict entries are left out of the list.
- Prefix plus rename: a renamed row uses the typed name as-is (no prefix); un-renamed rows get prefix + original name.
- Two chosen rows that end up with the same final name: both marked, Enter refuses.
- Export FILE already exists and the user declines overwrite: nothing written, exit 0.

---

### Task 1: Data functions in `cardshare.py`

**Files:**
- Create: `src/sync_roms/cardshare.py`
- Test: `tests/test_cardshare.py`

**Interfaces:**
- Produces:
  - `KEPT = ("size", "device", "layout", "games", "excluded")`
  - `export_entry(entry: dict, collections_by_id: dict) -> dict` — the exported card (Global Constraints). `collections_by_id` is `{id: collection}` as `collections.load_collections()` gives (check its return shape and adapt the caller, not this signature).
  - `import_entry(entry: dict) -> dict` — `{k: entry[k] for k in KEPT if k in entry}` plus `"surprise": False`.
  - `final_name(name: str, prefix: str, renames: dict) -> str` — `renames[name]` if present, else `prefix + name`.
  - `name_problem(name: str, taken: set) -> str | None` — `"taken"` when in `taken`, `"invalid"` when empty after strip or has `/`, else None.

- [ ] **Step 1: Write failing tests** in `tests/test_cardshare.py` (import style like `tests/test_commands.py`: `sys.path` inserts, `import isolate`):
  - `test_export_keeps_only_card_fields`: entry with all keys (`device`, `layout`, `size`, `games`, `excluded`, `collections`, `surprises`, `surprise`, `frontend_collections`, `drivers`, `pico8`, `android_media`, `systems`) → result keys ⊆ `KEPT`.
  - `test_export_flattens_surprises_and_collections`: entry `games={"gba": [{"title": "A", "bucket": "gba/A.zip"}], "sets": ["shmups"]}`, `surprise=False`, `surprises=[{"system": "gba", "bucket": "gba/B.zip", "title": "B"}, {"system": "gba", "bucket": "gba/A.zip", "title": "A"}]`, `collections=["c", "gone"]`, collections `{"c": {"name": "C", "games": [{"system": "psx", "bucket": "psx/D.cue", "title": "D", "files": ["psx/D.bin"], "note": "n"}]}}` → `games == {"gba": [A, {"title": "B", "bucket": "gba/B.zip"}], "sets": ["shmups"], "psx": [{"title": "D", "bucket": "psx/D.cue", "files": ["psx/D.bin"], "note": "n"}]}`; the input entry is not mutated.
  - `test_export_full_system_gets_nothing`: `games={"gba": {"full_system": True}}` with a gba surprise → `games == {"gba": {"full_system": True}}`.
  - `test_import_entry_turns_surprise_off`: `import_entry({"device": "x", "surprise": True, "collections": ["c"], "surprises": [...]}) == {"device": "x", "surprise": False}`.
  - `test_final_name_and_problems`: `final_name("A", "Bob ", {}) == "Bob A"`; `final_name("A", "Bob ", {"A": "Z"}) == "Z"`; `name_problem("Z", {"Z"}) == "taken"`; `name_problem(" ", set()) == "invalid"`; `name_problem("a/b", set()) == "invalid"`; `name_problem("ok", set()) is None`.
- [ ] **Step 2:** Run `python -m unittest tests.test_cardshare -v` → FAIL (module missing).
- [ ] **Step 3:** Implement the four functions and `KEPT`. Deep-copy `games` (`copy.deepcopy`) before appending.
- [ ] **Step 4:** Run `python -m unittest tests.test_cardshare -v` → PASS.
- [ ] **Step 5:** Commit `feat(cards): add card export and import data helpers`.

### Task 2: Lists and the `cards export` / `cards import` commands

**Files:**
- Modify: `src/sync_roms/cardshare.py` (add the two list functions)
- Modify: `src/sync_roms/commands.py` (handlers after `cards_delete`; parser entries after the `delete` parser at ~line 1015; completion `words["cards"]` at ~line 900)
- Modify: `src/sync_roms/cli.py` (the `"cards"` summary at line 25 and the `cards` help block at ~line 130)
- Modify: `README.md` (the `cards list|new|set|rename|delete` table row, ~line 279)
- Test: `tests/test_cardshare.py`, and `tests/test_completion.py` / `tests/test_readme.py` if they assert those lists

**Interfaces:**
- Consumes: Task 1's functions.
- Produces:
  - `RENAME_KEY = "r"`, `PREFIX_KEY = "p"` in `cardshare.py`.
  - `pick_export(names: list[str]) -> list[str] | None` — `picker.filter_list(..., multi=True, esc_asks=False)`, none chosen initially; returns chosen names (None on Esc).
  - `pick_import(cards: dict, existing: set, devices: set, layouts: set) -> dict | None` — `{final name: source name}` of the chosen cards, or None on Esc. Rows sorted by source name; label is the final name, with the source name in `extras` when it differs. Locked rows (with `locked_note`): device not in `devices | {"full", None}` or layout not in `layouts | {None}`. Hotkeys `r`/`p` (in `hotkeys`, listed in `key_help` with the default list keys) return to a loop that asks with `ui.ask` (empty answer keeps the current value; for `r` an empty answer removes the rename) and reopens the list with the same `session` dict so selection and cursor survive (`picker.carry_place` pattern, decorated `@picker.one_app` like `edit.py:270`). A row whose final name has a `name_problem` against `existing` or another chosen row's final name shows it in extras (red). Enter with any chosen row having a problem: `picker.queue_note` explaining which, and reopen.
  - `cards_export(args) -> int`, `cards_import(args) -> int` in `commands.py`; parsers `p.add_argument("file")`.
- `cards_export`: no cards → `ui.fail("No cards yet", 2)`. Picks, nothing chosen → print `↩️  Nothing exported`, 0. FILE exists → `ui.confirm(f"Overwrite {file}?", default=False)`, no → `↩️  Kept`, 0. Writes `{name: export_entry(...)}` JSON, `indent=2`, trailing newline. Dry run: `🧪 Would export N card(s) to FILE`. Success: `💾 Exported N card(s) to FILE`.
- `cards_import`: reads FILE (OSError / ValueError / not a dict → `ui.fail(..., 2)`), drops non-dict entries; refuses on unreadable `cards.json` before the list. Writes `cards[new] = import_entry(source[old])` for each chosen. Dry run: `🧪 Would import: A → Bob A, ...`. Success: `💾 Imported: ...`. Nothing chosen → `↩️  Nothing imported`, 0.

- [ ] **Step 1: Write failing tests** (subclass `helpers.Cmd`, `run_cmd("cards", ...)`, mock `cardshare.pick_export` / `cardshare.pick_import` / `ui.confirm` with `mock.patch.object`):
  - `test_export_writes_chosen_cards`: two cards saved, `pick_export` returns `["SD"]` → file holds only `SD`, flattened per Task 1, exit 0.
  - `test_export_declined_overwrite_keeps_file`: file exists with `"old"`, confirm → False → content unchanged, exit 0.
  - `test_export_dry_run_writes_nothing`.
  - `test_import_adds_cards_with_surprise_off`: import file `{"A": {"device": "full", "layout": "esde", "surprises": [...], "drivers": ["x"]}}`, `pick_import` returns `{"Bob A": "A"}` → `cards.json["Bob A"] == {"device": "full", "layout": "esde", "surprise": False}`, existing cards untouched.
  - `test_import_bad_file_fails`: invalid JSON and a JSON list → exit 2.
  - `test_import_refuses_unreadable_cards_json`: `cards.json` holds `"{"` → exit 3, `pick_import` not called.
  - `test_pick_import_marks_clash_and_applies_prefix`: drive `pick_import` with `picker.filter_list` mocked to a scripted sequence — first returns `("p", 0)`, `ui.ask` returns `"Bob "`, then returns states `[True, True]` for cards `{"A": {...}, "SD": {...}}` with `existing={"Bob SD"}` → refuses (queue_note called) and reopens; scripted third call deselects row 1 → result `{"Bob A": "A"}`. Assert the second call's labels are `["Bob A", "Bob SD"]`.
  - `test_pick_import_rename_overrides_prefix`: `("p", 0)` → `"X-"`, `("r", 0)` → `"Mine"`, then `[True]` → `{"Mine": "A"}`.
  - `test_pick_import_locks_unknown_device`: a card with device `"nope"` is locked in the `locked` argument.
- [ ] **Step 2:** Run `python -m unittest tests.test_cardshare -v` → new tests FAIL.
- [ ] **Step 3:** Implement `pick_export`, `pick_import`, `cards_export`, `cards_import`, parser entries, completion word list `["edit", "list", "new", "set", "rename", "delete", "export", "import"]`, `cli.py` summary `edit|list|new|set|rename|delete|export|import` and help lines `sync-roms cards export FILE` / `sync-roms cards import FILE` with one line: export flattens surprises and collections into games; import keeps size, device, layout, games and excluded, turns Surprise off, `r` renames, `p` prefixes all. Update the README row the same way.
- [ ] **Step 4:** Run `python -m unittest discover -s tests` → all PASS.
- [ ] **Step 5:** Commit `feat(cards): add cards export and cards import`.
