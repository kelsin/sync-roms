# Collection Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opening a collection shows its games as a toggle list (removed games stay as ⬜ until you leave), `A` adds games via the system list, `S` opens a settings menu (name, description, art with image).

**Architecture:** `collectionedit.edit_one` becomes a loop around one toggle list over all of the collection's games, with hotkeys `A` (add, `+` also works) and `S` (settings). Rows are kept across reopenings so removed games stay listed. Add reuses `listedit.add_from_system`; art reuses `pick_art`. No change to `tagui.py` / `tags.py` (another session owns tag UX).

**Tech Stack:** Python 3.12+, `unittest` (`uv run python -m unittest discover -s tests`), `picker.filter_list`, `edit.toggle_games`.

**Spec:** `docs/superpowers/specs/2026-11-25-collection-editor-design.md`

## Global Constraints

- Run everything with `uv run`; tests import `isolate` first (see `tests/test_collectionedit.py`).
- Conventional Commits, lowercase imperative. Commit message ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Surgical: don't touch `tagui.py`, `tags.py`, `cardedit.py`; keep `edit_collections`, `save`, `new_collection`, `cards_using` as they are.
- Update `README.md` only where it describes the collection editor's menu (grep `collections edit`); `tests/test_readme.py` must still pass.

## Review Focus

- Empty collection (no rows): `A` and `S` must still be reachable.
- Switch a game off, press `A`/`S`, come back: it is still listed ⬜; switching it on again restores its original entry (note, discs).
- Esc in the add-games system list returns to the games list with nothing changed.
- Invalid or empty new name in settings keeps the old name; empty description input keeps the old one (as today).
- Ctrl-C anywhere keeps the toggles made (existing behavior, tests `test_ctrl_c_keeps_*`).

---

### Task 1: Games-first editor with persistent removed rows and header

**Files:**
- Modify: `src/sync_roms/listedit.py` (`toggle_all`)
- Modify: `src/sync_roms/collectionedit.py` (`edit_one`, new `header`)
- Test: `tests/test_collectionedit.py` (update tests that drive `edit_one` through the old menu; add new ones)

**Interfaces:**
- Produces: `listedit.toggle_all(title, rows, place=None, hotkeys=(), hint=None, key_help=())` — as today, plus: keys in `hotkeys` end the list and are returned (`None` on Enter/Esc as before); `hint`/`key_help` extend the displayed hint and `?` help; `select_all` stays False.
- Produces: `collectionedit.header(collection) -> str` = `f"{emoji} {name} — {description}  ·  art: {art_label}"` (no description part when empty).
- Produces: `edit_one(collection, systems, keys_of)` keeps this signature.

- [ ] **Step 1: Write failing tests** in `tests/test_collectionedit.py`:
  - `test_opening_a_collection_lists_its_games_without_a_menu`: patch `edit.toggle_games`; `edit_one` calls it first (no `picker.filter_list` menu) with rows of the collection's games and a title containing the name, description and art label.
  - `test_a_game_switched_off_stays_listed_after_a_hotkey`: first toggle_games call switches game X off and returns `"S"` (then Esc of the settings menu), second call's rows still contain X's key, with X not on (X absent from the view's games), and a final `Enter` leaves `collection["games"]` without X.
  - `test_switching_a_removed_game_back_on_restores_its_note_and_discs`: game with `note` and `files`; off, hotkey, on, done → entry equals the original.
  - `test_header_omits_an_empty_description`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_collectionedit -v` — expect the new tests to FAIL.
- [ ] **Step 3: Implement.** Extend `toggle_all` as described. In `edit_one`: loop { `shown = view(collection, systems)`; rows = `edit.list_rows(...)` merged with `kept` (dict key→row of every row ever listed this call, so removed games stay; sorted as `list_rows` sorts); remember each game dict before it is dropped in `dropped[key]`; call `listedit.toggle_all(header(collection), rows, place, hotkeys=("A","+","S"), hint=..., key_help=[("A / +","add games")  # hint line shows only A; ? help shows both
,,("S","settings")])` inside `try/finally` that runs `collection["games"] = reconcile(collection["games"], shown)` and, for keys switched back on that are in `dropped`, restores the original dict (then `fold_discs` is not needed); return on `None`. Empty collection: if `toggle_all` cannot take hotkeys with zero rows, show a two-row `picker.filter_list` menu ("Add games", "Settings") instead and map to the same actions. Remove the old five-item menu and the `GAMES_HINT`/`toggle_filtered` use only if now unused (they are used by Task 2 — keep them until then).
- [ ] **Step 4: Run** the full file — new tests PASS; fix old tests that selected menu rows by index so they enter via the games list instead.
- [ ] **Step 5: Commit** `feat(collections): open the editor on the collection's games`.

### Task 2: `A` (or `+`) adds games from the system list

**Files:**
- Modify: `src/sync_roms/collectionedit.py` (`edit_one`)
- Test: `tests/test_collectionedit.py`

**Interfaces:**
- Consumes: Task 1's `edit_one` loop and `kept` rows; `listedit.add_from_system(collection, systems, shown, keys_of, label, toggle=None)` (first row is `ALL_SYSTEMS`; all-systems list already has the `s` tag filter).

- [ ] **Step 1: Write failing tests:** `test_a_opens_the_system_list_with_all_systems_first` (hotkey `"A"` (add a test that `"+"` does the same) → `picker.filter_list` called with options starting `listedit.ALL_SYSTEMS`); `test_games_added_with_a_appear_in_the_list_on_return` (add one game via all systems; next `toggle_games` rows include it, on); `test_esc_in_the_system_list_returns_to_the_games_list_unchanged`.
- [ ] **Step 2: Run** them — expect FAIL.
- [ ] **Step 3: Implement** the `"A"`/`"+"` branch: `add_from_system(collection, systems, shown, keys_of, label)` (with `toggle=toggle_filtered` so single-system lists keep their filters); catch `KeyboardInterrupt` the way the old branch did (keep toggles, re-raise after reconcile). The loop's next pass rebuilds rows so new games show. Delete the old "Add games from a tag" menu path; tag filtering inside the lists replaces it (drop `add_from_tag` import and its tests only if nothing else uses them — it is still used elsewhere, so only remove the collection menu's use).
- [ ] **Step 4: Run** the file — PASS.
- [ ] **Step 5: Commit** `feat(collections): add games with A from the system list`.

### Task 3: `S` settings menu with art image

**Files:**
- Modify: `src/sync_roms/collectionedit.py` (new `settings_menu`, `edit_one`)
- Modify: `README.md` if it describes the collection editor's old menu
- Test: `tests/test_collectionedit.py`

**Interfaces:**
- Produces: `collectionedit.settings_menu(collection) -> None`: `picker.filter_list` rows `Name: <name>`, `Description: <description or none>`, `<art emoji> Theme art: <label>`; `preview=lambda j: themeart.art_png(collection.get("art"))` so the current art image shows; Esc returns; the menu reopens on the row last used. Name prompt: `ui.ask` + `colls.collection_problem(name, ())`, empty keeps, invalid warns and keeps (id never changes). Description prompt: empty keeps. Art row calls the existing `pick_art(collection)`.

- [ ] **Step 1: Write failing tests:** rename sets the name; invalid name keeps the old one with a warning; empty description input keeps the old; art row calls `pick_art`; the menu's `preview` returns `themeart.art_png` of the collection's art; `S` in `edit_one` opens it and the next list's title shows the new name/art (header refreshed).
- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement** `settings_menu` and the `"S"` branch in `edit_one`.
- [ ] **Step 4: Run** the full suite `uv run python -m unittest discover -s tests` with stdin closed (`< /dev/null`) — all PASS, including `test_readme`.
- [ ] **Step 5: Commit** `feat(collections): settings menu for name, description and art`.
