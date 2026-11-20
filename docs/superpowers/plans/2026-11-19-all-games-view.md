# All-games view Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everywhere an editor makes you pick a system first, offer one searchable list of games across all systems.

**Architecture:** Reuse the existing multi-system list machinery (`cardedit.edit_set` for cards, `edit.toggle_games` for sets/collections). Rows come from the storage cache (`store.folder_keys` -> `inventory.files`), never from S3 directly. A set filter narrows the list to one set's games; no metadata filter.

**Tech Stack:** Python, unittest (`python -m unittest discover -s tests`), the in-repo `picker` TUI.

**Spec:** the approved design in the conversation: (1) card editor: new "All systems" view on key `a` in the system list; (2) set and collection editors: "🌐 All systems" first entry in "Add games from which system?"; set filter yes, metadata filter no; rows from the cache.

## Global Constraints

- Conventional Commits, lowercase imperative (`feat(edit): ...`).
- Storage contents are read only through `inventory.py` (use `store.folder_keys`/`listedit.folder_lister`); never call `s3.list_*` directly.
- No notes about bucket contents in repo files.
- Surgical changes: don't touch the per-system views' behavior.
- Run Python tests with `python -m unittest discover -s tests` (use the project's Python; if `python` is not found use `python3`).

## Review Focus

- A system with an empty/missing folder contributes no rows and doesn't crash the list.
- Game files that exist on two systems with the same title stay distinct rows (label carries the system name).
- Multi-disc games with an `.m3u` show one row; their discs are folded into `files` on add (set/collection editors) and linked (card editor).
- Full systems on a card: their files are listed too, shown on and locked (as `edit_set` shows them), so a search finds them.
- Rows sort by game title (case-insensitive), then system name, not by system first.
- Ctrl-C inside the all-systems list keeps the toggles made (same as per-system lists).
- Set filter when the chosen set has no game among the rows: note shown, no filter applied.

---

### Task 1: Row builder and set filter in listedit

**Files:**
- Modify: `src/sync_roms/listedit.py`
- Test: `tests/test_collectionedit.py` (it already tests listedit helpers; add a `class AllRows`)

**Interfaces:**
- Produces: `listedit.all_rows(shown, systems, keys_of) -> list[tuple]` of `(s, key, title, label)` over `systems` in the given order, where `s = shown[system["bucket"]]` (the view entry, so toggles write into it), built from `system_rows(s, keys_of(bucket))`, each label prefixed `"{system name} — "`. Systems with no rows contribute nothing. The result is sorted by `(title.lower(), system name.lower())`, not by system.
- Produces: `listedit.toggle_all(title, rows, sets, place=None) -> None`: loop over `edit.toggle_games(title, narrowed_rows, hotkeys=(cardedit.SET_KEY, cardedit.CLEAR_KEY), hint="Space toggle · Enter done · s set · c clear filters", key_help=[(s, narrow to a set), (c, clear)], place=place, filters=...)` where `s` narrows to the rows whose `(system bucket, key)`... (use key only; keys are `bucket/file`, unique) belong to a set chosen from `pick_row_set`; `c` clears it and the `/` query via `place` as `GameFilters.handle` does. Returns when Enter/Esc (non-hotkey) ends it.
- Produces: `listedit.pick_row_set(sets, row_keys, current=None) -> dict | None`: `picker.filter_list` over sets that have at least one game (via `store.set_games(set)`) whose `bucket` is in `row_keys`, labelled `"{themeart.set_emoji(x)} {x['name']}  ({n} games)"`; returns the chosen set or None; notes (`edit.note(ui.yellow(...))`) and returns None when no set matches.
- (`listedit` must import `cardedit` lazily inside `toggle_all` to avoid a cycle: `cardedit` already imports `listedit`.)

- [ ] **Step 1: Write failing tests** in `tests/test_collectionedit.py`:
  - `test_all_rows_span_systems_with_system_prefixed_labels`: systems GBA and PSX with `keys_of` returning `{"gba/Ruby.zip"}` / `DISCS`; `shown = listedit.view({"games": []}, SYSTEMS)`; assert labels are ordered by title across systems (e.g. `Crash` before `FF7` before `Ruby`) and contain `"PlayStation — FF7.m3u"` and `"PlayStation — Crash.chd"`, no `"FF7 (Disc 1).chd"` row, and each row's `s` is `shown[bucket]`.
  - `test_all_rows_skip_a_system_with_no_files`: `keys_of` returns `set()` for gba -> no gba rows.
  - `test_pick_row_set_lists_only_sets_with_a_game_among_the_rows`: patch `picker.filter_list` to capture labels and return 0; two sets, only one with a game bucket in `row_keys`; assert one label and that set returned.
- [ ] **Step 2: Run** `python -m unittest tests.test_collectionedit -v`. Expected: FAIL (`all_rows` missing).
- [ ] **Step 3: Implement** the three functions in `listedit.py` per Interfaces. Use `edit.system_rows` label parts from `system_rows`; prefix only.
- [ ] **Step 4: Run** the same tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(edit): build rows across all systems for editors`.

### Task 2: "All systems" in the set and collection editors

**Files:**
- Modify: `src/sync_roms/listedit.py` (`add_from_system`)
- Test: `tests/test_collectionedit.py` (existing `Stocked`/add-from-system tests; update for the new first entry) and `tests/test_setedit.py` if it drives the same picker

**Interfaces:**
- Consumes: Task 1's `all_rows`, `toggle_all`.
- Produces: `add_from_system` offers `"🌐 All systems"` as the first option of "✏️  Add games from which system?" (no extras/preview for it; `file_counts` extras and `options` stay aligned by prepending an empty extras entry). Choosing it: `rows = all_rows(shown, options, keys_of)`; if no rows, `edit.note` and return; else `toggle_all(f"✏️  All systems — ✅ in {label}, ⬜ in storage only", rows, store.load_sets())`. Afterwards the existing flow runs unchanged: compute `added` over all `shown` systems (not just one), `ask_category` when `categories`, `reconcile`, `fold_discs` for every system in `shown` that has rows, re-raise KeyboardInterrupt if interrupted. The per-system path is unchanged (its `toggle` hook, e.g. the collection editor's `toggle_filtered`, still applies only there).

- [ ] **Step 1: Failing tests:** (a) the picker's labels start with `"🌐 All systems"` followed by the stocked systems; (b) selecting All systems with `edit.toggle_games` patched to add `RUBY` to `s["games"]` of the gba view and a psx disc game adds both to the listing (collection: no category prompt; set: category prompt asked once), and the psx game gets its discs in `files`; (c) selecting a real system still works (shift the index by one in the existing tests that return a system index).
- [ ] **Step 2: Run** `python -m unittest tests.test_collectionedit tests.test_setedit -v`. Expected: FAIL.
- [ ] **Step 3: Implement** in `add_from_system` as described.
- [ ] **Step 4: Run** both modules plus the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat(edit): add games across all systems in set and collection editors`.

### Task 3: All-games view in the card editor

**Files:**
- Modify: `src/sync_roms/cardedit.py`
- Test: `tests/test_cardedit.py`

**Interfaces:**
- Consumes: `edit_set`'s machinery (`cardedit.py:767`), `listedit.system_rows`, `store.folder_keys`.
- Produces: constant `ALL_KEY = "a"`; `LIST_HINT`/`LIST_KEYS` mention it (`("a", "every game across this card's systems")`).
- Produces: `edit_all(name, setup, systems, to_fetch=None, card_usages=None) -> bool` (changed or not). Builds a pseudo-set `{"name": "All games", "games": [{"system": s["bucket"], "bucket": key, "title": title} ...]}` from `listedit.system_rows` over `systems` (the card editor's stocked list) including systems the card syncs whole (their rows come out locked and on, as `edit_set` already does for full systems), using `store.folder_keys` (cache), then runs the `edit_set` loop on it. To share the loop, extend `edit_set(name, game_set, setup, to_fetch=None, card_usages=None, narrow_sets=False)`: when `narrow_sets` is true, `SET_KEY` is added to its hotkeys (and its key_help/hint) and narrows `listed` to the keys of a set chosen with `listedit.pick_row_set(list(picks.sets_by_id.values()), set(files_of))`; `CLEAR_KEY` clears it (plus the `/` query via `place`, as `GameFilters.handle` does); `filters=` shows `"{emoji} {set name} only (c clear filters)"`. When `narrow_sets` is true the rows are re-sorted by `(title.lower(), system name.lower())` instead of `edit.set_rows`' category/system order. Title uses `🌐` and the name "All games". Series key is not offered when `narrow_sets` is true (the pseudo-set has no series). `edit_card` handles `ALL_KEY`: `edit_all(...)`, `changed = ALL`, in the same `isinstance(i, tuple)` branch as the other hotkeys, and adds `ALL_KEY` to its `hotkeys` tuple.

- [ ] **Step 1: Failing tests** in `tests/test_cardedit.py` next to the existing `edit_set` tests (~line 1411; reuse their fixtures and fake `picker.filter_list`):
  - `test_edit_all_lists_every_file_of_every_system_with_system_names`: two systems with files; capture labels; assert both systems' files appear, each prefixed by its system name.
  - `test_edit_all_toggle_saves_picks_on_the_right_system`: turn on one gb file and one gba file; assert `store.card_games` has each under its own system.
  - `test_edit_all_lists_a_full_system_locked_on`: card with `{"gb": {"full_system": True}}`; gb rows are present, `locked` is true for them and they start on.
  - `test_edit_all_sorts_by_title_then_system`: same title on two systems and titles interleaved across systems; labels come out title-first.
  - `test_edit_all_set_key_narrows_to_a_set_then_c_clears`: first pass returns `("s", None)`-style hotkey result, set picker returns the set, second pass labels are only that set's games; then `("c", ...)` restores all rows.
  - `test_edit_card_a_opens_the_all_games_view`: `picker.filter_list` for the system list returns `("a", 0)` once, then None; assert `edit_all` is called (mock).
- [ ] **Step 2: Run** `python -m unittest tests.test_cardedit -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `ALL_KEY`, `edit_all`, the `narrow_sets` extension of `edit_set`, and the `edit_card` branch per Interfaces. Keep `edit_set`'s behavior with `narrow_sets=False` byte-for-byte the same.
- [ ] **Step 4: Run** the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat(cardedit): add an all-games view across systems`.

### Task 4: Check speed and docs

**Files:**
- Modify: `README.md` only if it lists the card editor's keys (search for `l collections` / `S surprise`); otherwise nothing.

- [ ] **Step 1:** With the real storage cache (`~/.sync-roms/cache/storage-cache.json`), time `listedit.all_rows` over every system and `edit_all`'s row build in a throwaway script in the scratchpad; report the numbers. If row building exceeds ~2 s, report it instead of optimizing speculatively.
- [ ] **Step 2:** Update README key lists if present; run `python -m unittest discover -s tests`. Expected: PASS.
- [ ] **Step 3: Commit** `docs: mention the all-games view` (skip if no doc changed).
