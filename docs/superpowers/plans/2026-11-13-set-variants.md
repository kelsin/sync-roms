# Set Variants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each set game's `variants` in the editors and let the card editor add a variant to a card with `v`.

**Architecture:** `store.variant_index(sets)` indexes variants across all sets; `edit.variant_line` turns it into the
text for one row; `picker.filter_list` gains a `row_note` callable shown on the bottom line for the highlighted row.
The card editor's system view uses all three plus a `v` hotkey that toggles the variant on the card under the
variant's own system; `edit.toggle_games` (set, collection and add-from-set lists) shows the note read-only.

**Tech Stack:** Python 3.11+, Textual (picker), unittest.

**Spec:** `docs/superpowers/specs/2026-11-13-set-variants-design.md`

## Global Constraints

- A set game's variants: `"variants": [{"bucket": "<system>/<file>", "note": "<what it adds>", "files": [...]?}]` (already in the data; optional `files` are a multi-disc variant's other files, added and removed with it, like a set game's `files`).
- Whole-set sync (`store.merge_lists`, `store.set_games`) must keep ignoring variants: no change there.
- Copy (exact): one variant `↳ Variant: <note>`; card view adds ` (v adds it)` when off, ` · ✅ on the card (v removes it)`
  when on; several in the card view `↳ <n> variants (v picks): <note1>; <note2>`; several read-only
  `↳ Variants: <note1>; <note2>`; a row that is a variant `Variant of <system name> — <title>`.
- Card view hint (exact): `Space toggle · Enter done · / search · s set · m meta · p past · v variant`.
- Run tests with: `PYENV_VERSION=3.10.15 uv run --python 3.12 --with boto3 --with textual --with textual-image python -m unittest discover -s tests`
  (restore `uv.lock` with `git checkout -- uv.lock` if the run changes it; never commit it).
- Commits: Conventional Commits, no AI attribution lines.

## Review Focus

- A variant on a **full system** on the card (`{"full_system": true}`) is already synced: line shows `✅ on the card`, `v` changes nothing. (Task 3 test)
- A variant **already synced through a referenced set** on the card: shown on, `v` changes nothing (no exclusion is written). (Task 3 test)
- A variant on the **same system** as the view: `v` toggles that row (the reopened list shows it on/off). (Task 3 test)
- Saving after `v` keeps the card's other systems, `sets`, `excluded` and the system being edited intact. (Task 3 test)
- A key that is both listed as a variant in one set and as a canonical game elsewhere: canonical text wins (`variants` checked before `parents`). (Task 1 test)

---

### Task 1: Variant index, row text and data check

**Files:**
- Modify: `src/sync_roms/store.py` (near `set_games`), `src/sync_roms/edit.py` (near `cover_notes`)
- Test: `tests/test_sets.py`, `tests/test_set_data.py`

**Interfaces:**
- Produces: `store.variant_index(sets: list[dict]) -> tuple[dict, dict]` — `(variants, parents)`;
  `variants = {canonical bucket: [{"bucket": str, "note": str, "files": [str]?}, ...]}` (entries copied as in the file) in file order, a variant bucket listed once per
  canonical (first wins); `parents = {variant bucket: {"bucket": str, "system": str, "title": str}}` (first set wins;
  title from the entry's `title`, else `store.key_title`). Entries without `variants` or without a `bucket` are skipped.
- Produces: `edit.variant_line(key: str, variants: dict, parents: dict, system_names: dict, on=None) -> str` — the
  copy in Global Constraints; `on` is `None` (read-only) or a callable(variant bucket) -> bool; returns `""` when the
  key is neither. `system_names = {system bucket: system name}`.

- [ ] **Step 1: Write failing tests** in `tests/test_sets.py`:
  - `test_variant_index_maps_both_ways`: two sets; set A has `{"system": "snes", "bucket": "snes/CT.zip", "title": "Chrono Trigger", "variants": [{"bucket": "nds/CT.zip", "note": "DS: adds the Lost Sanctum"}]}`; set B lists the same game with the same variant plus `{"bucket": "psx/CT.chd", "note": "PS1: anime scenes"}`. Assert `variants["snes/CT.zip"] == [{"bucket": "nds/CT.zip", "note": "DS: adds the Lost Sanctum"}, {"bucket": "psx/CT.chd", "note": "PS1: anime scenes"}]` and `parents["nds/CT.zip"] == {"bucket": "snes/CT.zip", "system": "snes", "title": "Chrono Trigger"}`.
  - `test_variant_line_texts`: with that index and `{"snes": "SNES", "nds": "Nintendo DS"}`:
    one variant read-only `"↳ Variant: DS: adds the Lost Sanctum"`; with `on=lambda b: False` → `"↳ Variant: DS: adds the Lost Sanctum (v adds it)"`; `on=lambda b: True` → `"↳ Variant: DS: adds the Lost Sanctum · ✅ on the card (v removes it)"`; two variants with `on` → `"↳ 2 variants (v picks): DS: adds the Lost Sanctum; PS1: anime scenes"`; read-only → `"↳ Variants: DS: adds the Lost Sanctum; PS1: anime scenes"`; `variant_line("nds/CT.zip", …)` → `"Variant of SNES — Chrono Trigger"`; unknown key → `""`; a key in both maps → the variants text.
  - In `tests/test_set_data.py::test_shipped_sets_are_well_formed`, for each game's `variants`: `v["bucket"].split("/")[0] in systems`, `v["note"].strip()` non-empty, every `v.get("files", [])` key starts with the variant's system + "/", `v["bucket"]` not among that set's entry buckets, no duplicate variant bucket in one game.
- [ ] **Step 2: Run** the test command; the two new `test_sets` tests fail (`AttributeError`), `test_set_data` passes on the shipped data.
- [ ] **Step 3: Implement** `store.variant_index` and `edit.variant_line` (docstrings in the codebase's style).
- [ ] **Step 4: Run** the test command; all pass.
- [ ] **Step 5: Commit** `feat(sets): index set game variants`.

### Task 2: Picker row note

**Files:**
- Modify: `src/sync_roms/picker.py` (`_ListModel.__init__`, `status_line`, `filter_list` signature + docstring)
- Test: `tests/test_edit.py` (next to the other `pilot_list` tests)

**Interfaces:**
- Produces: `picker.filter_list(..., row_note=None)` — `row_note(label index) -> str`; when it returns non-empty text
  for the highlighted row, that text replaces the status line. Precedence (highest first): keep/revert question, note
  being typed, `notice`, locked-row note, row note, status/counts.

- [ ] **Step 1: Write failing test** `test_row_note_shows_for_the_highlighted_row`: `pilot_list` over labels `["a", "b"]`, multi, `row_note=lambda i: "↳ Variant: x" if i == 1 else ""`; read the last row of `screen_lines(pilot.app)` before and after `j`: first has no `↳ Variant: x`, second contains it. Second test `test_locked_note_wins_over_row_note`: `locked=[True, False]`, `locked_note="L"`, `row_note=lambda i: "R"` → bottom row on row 0 shows `🔒 L`.
- [ ] **Step 2: Run**; fail (`unexpected keyword argument 'row_note'`).
- [ ] **Step 3: Implement** the parameter and the precedence above.
- [ ] **Step 4: Run**; all pass.
- [ ] **Step 5: Commit** `feat(picker): show a note for the highlighted row`.

### Task 3: Card editor `v` adds a variant

**Files:**
- Modify: `src/sync_roms/cardedit.py` (`GAMES_HINT`, new `VARIANT_KEY = "v"`, `edit_system`)
- Test: `tests/test_cardedit.py` (class `Flow`; use its `run_system`, `Script`, `returns`)

**Interfaces:**
- Consumes: `store.variant_index`, `edit.variant_line` (Task 1); `filter_list(row_note=...)` (Task 2).
- Produces: in `edit_system`, `VARIANT_KEY` in the game list's `hotkeys`; the result `(VARIANT_KEY, index)` is handled
  in the loop like `SET_KEY` (the list reopens with its session), not in `on_hotkey`.

Behaviour of `edit_system`:
- `variants, parents = store.variant_index(sets)` (it already loads `sets`); `system_names` from `store.repo_json("systems")`.
- `other_picks = {system bucket: [game dicts]}` — a working copy of the card's direct picks on systems other than the
  one on screen, filled lazily from `raw` when a variant first touches that system.
- `on_card(vb)`: same system → the row's current state (`states(cover())`); other system → full system in `raw`, or
  in `other_picks`/`raw` direct picks, or covered by `edit.cover_notes(sets_by_id, sets_on)` and not in
  `other_excluded` for that system.
- `row_note=lambda i: edit.variant_line(keys[i], variants, parents, system_names, on_card)`.
- On `(VARIANT_KEY, i)`: no variants → nothing. One variant → toggle it. Several → `picker.filter_list(f"Variants of {title}", [f"{'✅' if on_card(v['bucket']) else '⬜'} {v['note']}" …])` (single mode), toggle the picked one, `None` does nothing.
- Toggle: full system, or synced through a referenced set → no change. Same system → add/remove a direct pick in
  `s["games"]` (`{"title": names.title(vb), "bucket": vb}`, plus one entry per key in the variant's `files`) and drop it from `excluded`. Other system → add/remove in
  `other_picks[system]` (the bucket and its `files`). Then `work_out()` so the budget status counts it: `work_out` merges `other_picks` into the
  card's games before measuring.
- `save()`: `games` also takes every `other_picks` system (a non-empty list replaces that system; an empty one removes
  the key); `changed` compares as today.

- [ ] **Step 1: Write failing tests** (a set in `store.load_sets` whose `gba/Ruby.zip` entry has `"variants": [{"bucket": "gb/Red.gb", "note": "GB: the original"}]`; patch with `mock.patch.object(store, "load_sets", return_value=[...])`):
  - `test_variant_line_shows_on_the_highlighted_game`: `run_system(lambda labels, kw: (… assert kw["row_note"](labels.index("Ruby.zip")) == "↳ Variant: GB: the original (v adds it)"; return kw["session"]["sel"]))`; `GAMES_HINT` passed as `hint`.
  - `test_v_adds_the_variant_on_its_own_system_and_saves`: steps `returns((cardedit.VARIANT_KEY, idx_of_Ruby))`, then a step asserting `kw["row_note"](i)` now ends with `✅ on the card (v removes it)`, then Enter → `store.card_games("c")["gb"] == [g("gb/Red.gb")]`, `"gba"` unchanged, card's `sets`/`excluded` unchanged.
  - `test_v_again_removes_it`: two `v` presses → `"gb" not in store.card_games("c")`.
  - `test_v_on_a_same_system_variant_toggles_the_row`: variant `gba/Emerald.zip` → after `v` the reopened list's `kw["initial"]`/`session["sel"]` has Emerald on; saved under `gba`.
  - `test_v_leaves_a_full_system_or_set_covered_variant_alone`: card `games={"gb": {"full_system": True}}` → row note says on, `v` → `gb` still `{"full_system": True}`; and card `games={"sets": ["pk"]}` where set `pk` lists `gb/Red.gb` → `v` writes nothing new for `gb` and no `excluded`.
  - `test_v_with_two_variants_opens_a_picker`: two variants → second `filter_list` call has labels `["⬜ GB: the original", "⬜ PS1: x"]`; returning `0` adds `gb/Red.gb`.
- [ ] **Step 2: Run**; new tests fail.
- [ ] **Step 3: Implement** the behaviour above.
- [ ] **Step 4: Run** the full suite; all pass.
- [ ] **Step 5: Commit** `feat(edit): add a game's variant to a card with v`.

### Task 4: Read-only variant notes in the set, collection and add-from-set lists

**Files:**
- Modify: `src/sync_roms/edit.py` (`toggle_games`), `CLAUDE.md` (the variants paragraph under Data files)
- Test: `tests/test_sets.py`

**Interfaces:**
- Consumes: `store.variant_index`, `edit.variant_line` (Task 1); `filter_list(row_note=...)` (Task 2).
- Produces: `toggle_games` passes `row_note` (read-only, `on=None`) built from `store.variant_index(store.load_sets())`
  and `{s["bucket"]: s["name"] for s in store.repo_json("systems")}`; no signature change.

- [ ] **Step 1: Write failing test** `test_toggle_games_shows_variant_notes`: patch `store.load_sets` to a set whose `gba/A.zip` entry has one variant `{"bucket": "gb/A.gb", "note": "GB: x"}`, patch `store.repo_json` systems; `edit.toggle_games("t", rows)` with `picker.filter_list` mocked; assert `fl.call_args.kwargs["row_note"](i_of_A) == "↳ Variant: GB: x"` and `""` for a plain row.
- [ ] **Step 2: Run**; fails.
- [ ] **Step 3: Implement**; add one sentence to the CLAUDE.md variants paragraph: the editors show a game's variants on its highlighted row and `v` in the card editor adds one to the card.
- [ ] **Step 4: Run** the full suite; all pass.
- [ ] **Step 5: Commit** `feat(edit): show set game variants in the set and collection editors`.
