# Set Series Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Tag set games with a `series` and let the card editor's set view and `sets edit` narrow a set's games to one series with a key (`r`), cleared by `c`.

**Architecture:** `series` is an optional string on a set game (like `category`). A pure helper in `listedit.py` lists a set's series and filters rows. Both set views loop on `filter_list`/`toggle_games` hotkeys, keeping a `series` filter between passes, as `edit_system` does for sets.

**Tech Stack:** Python, unittest (`python -m unittest discover -s tests`).

**Spec:** the design agreed in conversation (sets only; series list reviewed before tagging).

## Global Constraints

- Keys: `r` = series picker, `c` = clear (`cardedit.CLEAR_KEY`). Hint/help text updated for both.
- Only series with 2+ games in the set are offered by the picker.
- One series per game; identical spelling across all sets (`Mario Kart`, `Tony Hawk`, ...). Names come from `src/sync_roms/data/series.json` (a sorted list of canonical names) which a test checks every `series` value against.
- Repo set files must not contain notes about the bucket's contents.
- Conventional commits, no attribution lines beyond the harness's.

## Review Focus

- A set with no series data: `r` shows a note, list unchanged.
- Filter must keep toggles made before pressing `r` (apply then re-enter, as `edit_system` does).
- Rows hidden by the filter keep their state; `c` with no filter is a no-op.
- `series` survives `reconcile`/`recategorize` in the set editor (existing entries are kept as dicts).

---

### Task 1: Series helpers, validation, data file

**Files:** Modify `src/sync_roms/listedit.py`, `src/sync_roms/commands.py:683`, `src/sync_roms/store.py:553` (docstring); Create `src/sync_roms/data/series.json`; Test `tests/test_sets.py`, `tests/test_set_data.py`.

**Interfaces:**
- Produces: `listedit.series_of(game_set, min_games=2) -> list[tuple[str,int]]` (series name, game count, file order of first appearance); `listedit.series_keys(game_set, series) -> set[str]` (bucket keys, incl. `files`, of that series' games); `series.json` = JSON list of canonical names (starts `[]`, filled in Task 4).

- [ ] Write failing tests: `series_of` skips series under 2 games and games without `series`; `series_keys` includes `files`; `check_game_file` reports `'series' must be a string`; `test_set_data` asserts every `series` value is in `series.json`.
- [ ] Implement helpers, validation, docstring mention of optional `"series"`.
- [ ] Run `python -m unittest discover -s tests`; commit `feat(sets): add an optional series to set games`.

### Task 2: Series key in the card editor's set view

**Files:** Modify `src/sync_roms/cardedit.py` (`edit_set`, `SET_GAMES_HINT`, `SET_GAMES_KEYS`); Test `tests/test_cardedit.py`.

**Interfaces:** Consumes Task 1 helpers. Produces `cardedit.SERIES_KEY = "r"`.

- [ ] Failing tests (follow existing `edit_set` tests' fakes): pressing `r` then choosing a series re-lists only its rows with the filter line showing the series; `c` restores all rows; a set with no series data queues a note and re-lists unchanged.
- [ ] Implement: `edit_set` keeps `series_filter`; rows/keys/links/extras computed from `shown` filtered by `series_keys`; hotkeys `(VARIANT_KEY, SERIES_KEY, CLEAR_KEY)`; `filters=` line `"<series> (c shows all)"`; apply toggles before re-entering; picker via `picker.filter_list` of `f"{name}  ({n} games)"`.
- [ ] Run tests; commit `feat(cardedit): filter a set's games by series`.

### Task 3: Series key in `sets edit`

**Files:** Modify `src/sync_roms/setedit.py` (`edit_one`, "Games in this set" branch), `src/sync_roms/edit.py` (`toggle_games` hint text only if needed); Test `tests/test_setedit.py`.

**Interfaces:** Consumes Task 1 helpers and `toggle_games(..., hotkeys=(), hint=, filters=)` returning the pressed key.

- [ ] Failing tests: in "Games in this set", `r` narrows rows to a series, `c` clears; toggles survive; reconcile keeps `series` on entries.
- [ ] Implement a loop around `edit.toggle_games` passing `hotkeys=(SERIES_KEY, CLEAR_KEY)`, `hint=GAMES_HINT + " · r series · c all"`, `filters=`; rows from `edit.set_rows` filtered by `series_keys`.
- [ ] Add menu item "Set a game's series" beside "Change a game's category" (asks for a name, offering existing ones, empty clears); test it.
- [ ] Run tests; commit `feat(sets): filter by series and assign series in the set editor`.

### Task 4: Series list, then tagging (data)

**Files:** `src/sync_roms/data/series.json`, `src/sync_roms/data/sets/*.json`.

- [ ] Research series across all 45 sets (titles per series with 2+ games), write the proposed list with counts to the scratchpad, and **stop for the user to review it**.
- [ ] After approval: write `series.json`; tag sets in batches with a script that sets `series` by title-pattern per series (deterministic, reviewed by a spot check of each series' matched titles); keep `series` placed after `category` in each entry.
- [ ] `python -m unittest discover -s tests` passes; commit `feat(sets): tag games with their series`.
