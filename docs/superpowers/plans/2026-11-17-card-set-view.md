# Card Set View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `s` in the card editor's system list opens a set; its games from every playable system are toggled in one list, with the same rules as a system's game list.

**Architecture:** Move `cardedit.edit_system`'s per-system state and saving into `src/sync_roms/cardpicks.py` (`CardPicks` for the card, `SystemPicks` for one system). `edit_system` keeps its screen and filters but uses the model; a new `cardedit.edit_set` builds one list across many `SystemPicks`. `edit_card` gets an `s` hotkey that picks a set and opens `edit_set`.

**Tech Stack:** Python 3 stdlib, `unittest` (`python -m unittest discover -s tests`).

**Spec:** `docs/superpowers/specs/2026-11-17-card-set-view-design.md`

## Global Constraints

- Conventional Commits, lowercase imperative (`refactor(edit): ...`, `feat(edit): ...`).
- No commit trailers that mention Claude or AI.
- Match the existing style: short docstrings in the project's voice, no type hints (the codebase has none).
- What storage holds is read only through `inventory` (`inventory.files`, `inventory.cached`), never `s3.list_*`.
- No key in the set view adds or removes the whole set; the picker's `a` is off there.
- Games on systems the card can't play, or not in storage, are not shown in the set view.

## Review Focus

1. A set game covered by a set reference (`📦`) that is switched off in the set view lands in that system's `excluded`, exactly as in `edit_system`. Test in Task 2.
2. A set game with extra `files` (SET's `gba/Ruby.zip` + `gba/Ruby.sav`) is one row, and its files are picked and dropped with it. Test in Task 2.
3. Ctrl-C in the set view keeps the toggles made so far and saves them. Test in Task 2.
4. A set game on a full system shows as on and locked, with `edit.FULL_SYSTEM_NOTE`, and toggling it changes nothing. Test in Task 2.
5. A set with no games in storage on any playable system isn't offered; with none left, a note is shown and nothing opens. Test in Task 3.

---

### Task 1: Extract the picks model (pure refactor)

**Files:**
- Create: `src/sync_roms/cardpicks.py`
- Modify: `src/sync_roms/cardedit.py` (`edit_system`, about lines 377-648)
- Test: `tests/test_cardpicks.py` (new), and all of `tests/test_cardedit.py` and `tests/test_collectionedit.py` must pass unchanged

**Interfaces:**
- Produces:
  - `class CardPicks(name, setup, cards=None)`. It loads the card once and holds:
    - attributes `raw` (`store.card_games`), `sets_on` (list), `before_excluded` (`store.card_excluded`), `sets_by_id`, `variants`, `parents`, `system_names`, `locked_from` (`{system bucket: {key: from}}` from `store.card_locked_games`)
    - `system(system) -> SystemPicks`: built on first call per bucket and cached. It lists storage with `inventory.files(f"{bucket}/", sizes=False)` and lets `s3.ERRORS` propagate.
    - `cover() -> {key: note}`: `edit.cover_notes(self.sets_by_id, self.sets_on)`
    - `full(bucket) -> bool`: whether that system is a full system in `raw`
    - `picks_of(bucket, writing=False) -> list`: the loaded `SystemPicks.games` if loaded. Otherwise it gives a working copy of `raw`'s list, kept once `writing` is set, as `other_picks` is today.
    - `excluded_of(bucket) -> set`: the loaded `SystemPicks.excluded`, or a working copy from `before_excluded`
    - `on_card(key) -> bool` and `toggle_variant(variant) -> None`: today's `on_card` and `toggle_variant` from `edit_system`, written over the `picks_of`/`excluded_of` methods above
    - `card() -> dict`: `cardedit.card_entry` with the edits so far: games, set references and exclusions, which is what `work_out` builds today
    - `save() -> bool`: today's `save()`, writing every loaded system plus every working copy, and returning whether anything changed
  - `class SystemPicks`: attributes `system`, `bucket`, `in_storage`, `rows` (`edit.system_rows`), `titles`, `groups` (`m3u.file_groups`), `playlist_of`, `bundled`, `games` (list, this card's direct picks), `excluded` (set) and `locked_from` (`{key: from}`). Methods:
    - `states(notes) -> {key: bool}`
    - `changes(keys, base, state) -> {key: bool}`
    - `apply(keys, notes, base, state) -> None`

    These three are moved without changes from `edit_system`.

- [ ] **Step 1: Write `tests/test_cardpicks.py`.** Reuse `Flow`'s patches by importing from `test_cardedit` (`from test_cardedit import Flow, DEVICE, SET, g`) and subclass it:
  - `test_apply_on_adds_a_direct_pick_and_save_writes_it`: `p = CardPicks("c", (DEVICE, "esde"))`, `sp = p.system(GBA)`, `notes = p.cover()`, `base = sp.states(notes)`, `sp.apply(["gba/Zelda.zip"], notes, base, [True])`. Then `assertTrue(p.save())` and `store.card_games("c") == {"gba": [g("gba/Zelda.zip")]}`.
  - `test_off_on_a_set_reference_game_is_excluded`: the card has `games={store.SETS_KEY: ["pk"]}`. Switching `gba/Ruby.zip` off and saving gives `store.card_excluded("c") == {"gba": ["gba/Ruby.zip"]}`.
  - `test_save_without_changes_returns_false`.
  - `test_system_is_built_once_per_bucket`: `p.system(GBA) is p.system(GBA)`.
- [ ] **Step 2: Run it and check it fails.** Run `python -m unittest tests.test_cardpicks -v`. Expected: `ModuleNotFoundError: sync_roms.cardpicks`.
- [ ] **Step 3: Implement `cardpicks.py`, then rewrite `edit_system` to use it.** Keep `edit_system`'s screen, filters (`keep`, set, meta, past), `row_extras`, `status` and `work_out` in `cardedit.py`, written against `CardPicks.card()` and the `SystemPicks` attributes. Behaviour and every label stay byte-for-byte the same.
- [ ] **Step 4: Run the whole suite.** Run `python -m unittest discover -s tests`. Expected: OK, with no test edited in `test_cardedit.py` or `test_collectionedit.py`. Tests that patch `cardedit.<name>` (`pick_set`, `pick_meta`, `_spawn`, `_metadata`) must still find those names in `cardedit`.
- [ ] **Step 5: Commit.** Commit with `refactor(edit): move the card editor's picks into cardpicks`.

### Task 2: `edit_set`, one list across systems

**Files:**
- Modify: `src/sync_roms/cardedit.py` (new `edit_set`, `SET_GAMES_HINT`, `SET_GAMES_KEYS`), `src/sync_roms/picker.py` (`filter_list` and the list model get `select_all=True`)
- Test: `tests/test_cardedit.py` (new class `SetFlow(Flow)`), `tests/test_picker_session.py` (or wherever the real-model key tests live)

**Interfaces:**
- Consumes: `CardPicks`, `SystemPicks` (Task 1).
- Produces:
  - `cardedit.edit_set(name, game_set, setup, to_fetch=None, card_usages=None) -> bool`: whether anything changed. It is saved when left and on Ctrl-C.
  - `cardedit.set_view_keys(game_set, systems) -> [(system, key, files)]`: the set's games on the given systems, in file order, keeping only the first occurrence of each key. `files` is the game's `files` list.
  - `picker.filter_list(..., select_all=True)`. With `False`, `a`/`ctrl+a` do nothing.

**Behaviour** (as in the spec):
- Rows come from `set_view_keys` over `can_play(...)`, minus keys not in that system's `in_storage`, unless the system is full.
- Order is category (file order), then system name, then title, and labels are `"{cat} — " if cat` + `"{system name} — {title}"`. That is `edit.set_rows`'s order and label without its warning, so reuse it.
- A full system's rows are locked and on, with `edit.FULL_SYSTEM_NOTE`.
- Each toggle is applied by key: the row's key plus its `files`, expanded through that system's `groups`, goes to the owning `SystemPicks.apply`.
- Hotkeys are `w` notes, `v` variants (`CardPicks.toggle_variant`) and the row note `edit.variant_line(..., on_card)`. There are no `s`/`m`/`p`/`c` filters.
- The status is the card total for the systems not shown, plus the picked rows' `game_costs`, plus `budget.bios_usage` over the picked systems. With `to_fetch`, it adds `fetch_bytes` per shown system. `count=False`.
- `title` is `f"{set_emoji} {set name} on {name} — ✅ synced, ⬜ not, 📦 from a set"`, `select_all=False`, `links` and `locked` like `edit_system`.

- [ ] **Step 1: Write the failing tests in `SetFlow`.** Use `run_set(*steps)`, which patches `picker.filter_list` with `Script` and calls `cardedit.edit_set("c", SET, (DEVICE, "esde"))`.
  - `test_lists_the_sets_games_from_every_system`: labels are `["Game Boy — Red", "Game Boy Advance — Ruby"]`. Use the titles `names.title` gives in the fixture, and check the label strings first.
  - `test_toggling_a_game_with_files_picks_its_files_too`: switch Ruby on. `store.card_games("c")["gba"]` holds `gba/Ruby.zip` and `gba/Ruby.sav`, and there is no `gb` entry.
  - `test_switching_off_a_set_reference_game_excludes_it`: the card has `games={store.SETS_KEY: ["pk"]}`, and Red starts on. Switch Red off, and `store.card_excluded("c") == {"gb": ["gb/Red.gb"]}`.
  - `test_full_system_rows_are_locked_on`: the card has `games={"gb": {"full_system": True}}`. Red's `locked` is True and its initial state is True. A step that flips it saves nothing for `gb`.
  - `test_games_not_in_storage_or_unplayable_are_hidden`: add `{"system": "psx", "bucket": "psx/X.chd"}` and `{"system": "gba", "bucket": "gba/Gone.zip"}` to a set copy. Neither shows.
  - `test_ctrl_c_keeps_the_toggles`: a step sets `kw["session"]["sel"]` with Ruby on and raises `KeyboardInterrupt`. `assertRaises(KeyboardInterrupt)`, then Ruby is in `cards.json`.
  - `test_no_select_all`: `kw["select_all"] is False`.
  - `test_status_counts_picked_games_and_their_bios`: the cache is like `test_game_view_counts_other_systems_bios_once`. `status([False, True])` (Ruby: 5+1, GBA BIOS 16) passes 22 bytes to `status_of`.
  - Picker test: drive the real model with `a` then `enter`, with `select_all=False`. The states are unchanged.
- [ ] **Step 2: Run them and check they fail.** Run `python -m unittest tests.test_cardedit.SetFlow -v`. Expected: `AttributeError: ... 'edit_set'`.
- [ ] **Step 3: Implement `picker`'s `select_all`, `set_view_keys` and `edit_set`.**
- [ ] **Step 4: Run the whole suite.** Run `python -m unittest discover -s tests`. Expected: OK.
- [ ] **Step 5: Commit.** Commit with `feat(edit): list a set's games across a card's systems`.

### Task 3: `s` in the card's system list

**Files:**
- Modify: `src/sync_roms/cardedit.py` (`edit_card`, `LIST_HINT`, `LIST_KEYS`, new `pick_card_set`). Check `README.md` and `docs/` for the card editor's key list (`grep -rn "f full" README.md docs`) and add `s` there too.
- Test: `tests/test_cardedit.py`

**Interfaces:**
- Consumes: `edit_set` (Task 2), `set_view_keys`.
- Produces: `cardedit.pick_card_set(name, setup, systems, current=None) -> game_set or None`. It is a single-select list of the sets with at least one game in storage on `systems` (the systems the list shows). Labels are `f"{emoji} {name}  ({n} games)"`, plus extras showing the synced count (`✅` when all are synced, else `have/total`), from `CardPicks.on_card`. The preview is `previews.collection(set id)`. With none, it shows `edit.note("ℹ️  No set has games in storage for this card's systems.")` and returns None.

- [ ] **Step 1: Write the failing tests.**
  - `test_s_opens_a_set_then_its_games`: `run_card(returns((cardedit.SET_KEY, 0)), returns(0), toggle("Game Boy — Red"), returns(None))`. `calls[1][1][0]` starts with SET's emoji and `Pokemon`. Red is saved on `gb`.
  - `test_s_says_when_no_set_has_games_here`: `store.load_sets` returns a set with only `psx` games. The note is sent and no set list opens.
  - `test_set_list_counts_synced_games`: Red is picked. The set's extra shows `1/2`.
  - `test_s_is_in_the_hint_and_help`: `"s set"` is in `LIST_HINT`, and an entry for `s` is in `LIST_KEYS`.
  - `test_esc_on_the_set_list_returns_to_systems`.
- [ ] **Step 2: Run them and check they fail.** Run `python -m unittest tests.test_cardedit -v -k s_`. Expected: FAIL.
- [ ] **Step 3: Implement it.** Add `SET_KEY` to `edit_card`'s hotkeys. On `s`, call `pick_card_set`, then `edit_set(name, chosen, setup, to_fetch, usages)`, then set `changed = ALL`. The cursor stays on the system row.
- [ ] **Step 4: Run the whole suite.** Run `python -m unittest discover -s tests`. Expected: OK.
- [ ] **Step 5: Commit.** Commit with `feat(edit): open a set from the card's system list`.
