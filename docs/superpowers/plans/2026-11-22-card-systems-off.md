# Card systems off and collection game exclusions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a card untick single collection games and turn whole systems off, keeping the saved picks so turning a system back on restores them.

**Architecture:** Collection games start honouring the card's existing `excluded` (store, budget, card editor). A new card field `systems_off` blanks those systems in `store.load_manifest` for one card, zeroes their budget, keeps Surprise off them (so `fill_surprises` refills their slots), and is toggled with `x` in the card editor's systems list.

**Tech Stack:** Python 3.12+, `unittest`, run through `uv`.

**Spec:** `docs/superpowers/specs/2026-11-22-card-systems-off-design.md`

## Global Constraints

- Always `uv run`: tests are `uv run python -m unittest discover -s tests` (one module: `uv run python -m unittest tests.test_x`).
- Code must run on Python 3.12.
- Test modules import `isolate` first (directly or through `helpers` / `test_cardedit`).
- `systems_off` is a sorted list of system ids, absent from the card when empty.
- Surprise games stay locked in the editor and are never filtered by `excluded`.
- A full system still ignores `excluded`.
- `games`, `excluded`, `collections` are never changed by turning a system off or on.
- Conventional Commits, lowercase imperative, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Match surrounding style: one-line docstrings that say what, short helpers, no new modules.

## Review Focus

- A key that is both a collection game and a set game, unticked: gone from the card entirely (manifest and budget). → Task 1 and Task 2 tests.
- An excluded collection game on a full system: still synced (full ignores `excluded`). → Task 1 test.
- An off system that was full: manifest has no `full_system`, sync sees nothing listed. → Task 1 test.
- A surprise kept at the keep/replace question whose system is then turned off: `fill_surprises` drops it and fills the slot elsewhere. → Task 3 test.
- `systems_off` holding an id that isn't a string or isn't a known system: ignored, no crash. → Task 1 test.

---

### Task 1: store — `systems_off`, collection exclusions in the manifest

**Files:**
- Modify: `src/sync_roms/store.py` (`card_excluded` area ~235, `card_locked_games` ~252, `load_manifest` ~411)
- Modify: `src/sync_roms/data/cards.schema.json` (add `systems_off` next to `collections`)
- Test: `tests/test_collections.py` (rewrite `test_load_manifest_adds_them_after_picks_and_excluded_never_drops_them` ~168), new tests in the same class

**Interfaces:**
- Produces: `store.systems_off(entry) -> set[str]` — string ids from `entry["systems_off"]` when it's a list; `set()` for a non-dict entry or anything else.
- Produces: `store.card_locked_games(entry, collections_by_id, excluded=None)` — `excluded` is `{system: [keys]}`; collection games whose key is in `excluded[system]` are skipped (all keys of a game are checked individually). Surprise games are never skipped. Default `None` keeps today's behaviour (used by `cardpicks`, which needs every row).

- [ ] **Step 1: Write the failing tests** in `tests/test_collections.py`:
  - `test_load_manifest_drops_excluded_collection_games` (replaces the old test): card `{"collections": ["favs"], "excluded": {"gba": [<one favs gba key>]}}` → that key is absent from the gba system's games, the other favs keys present.
  - `test_a_key_from_a_set_and_a_collection_excluded_is_gone`: the same gba key in a referenced set and in favs, excluded → absent.
  - `test_load_manifest_keeps_excluded_surprises`: card with Surprise on, a surprise on gba whose key is in `excluded["gba"]` → key still present.
  - `test_excluded_collection_game_on_a_full_system_still_full`: gba `{"full_system": True}`, excluded collection key → gba `full_system` truthy.
  - `test_systems_off_blank_the_system_and_keep_the_card`: card with gba picks, a set reference with gba games, favs collection, gba `full_system` variant in a second assertion, and `systems_off: ["gba"]` → gba system has `games == []` and falsy `full_system`; other systems untouched; `store.saved_card("c")` unchanged (games, excluded, collections).
  - `test_systems_off_ignores_bad_ids`: `systems_off: ["gba", 3, "nope"]` → `store.systems_off(...) == {"gba", "nope"}` and `load_manifest(["c"])` doesn't raise; gba blanked.
  - `test_systems_off_of_non_lists`: `store.systems_off({"systems_off": "gba"}) == set()`, `store.systems_off(None) == set()`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_collections` → the new tests FAIL.

- [ ] **Step 3: Implement** in `store.py`:
  - `systems_off(entry)` as above.
  - `card_locked_games(..., excluded=None)` skip rule as above.
  - `load_manifest`: in the `len(card_names) == 1` path, pass the card's excluded to `card_locked_games` for that card; then, after `merge_locked`, for each system in `systems_off(cards.get(card))` set `s["games"] = []` and `s["full_system"] = False`. Multi-card manifests (mirror, scrape) are unchanged.
  - Schema: `"systems_off": {"type": "array", "items": {"type": "string"}}`.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_collections tests.test_cli_sync tests.test_sync_flow` → PASS.

- [ ] **Step 5: Commit** `feat(cards): exclude collection games and turn systems off in the manifest`

### Task 2: budget — exclusions on collection games, off systems size 0

**Files:**
- Modify: `src/sync_roms/budget.py` (`_system_keys` ~70, `_system_usage` ~84)
- Test: `tests/test_budget.py` (rewrite `test_collection_games_count_like_picks_and_ignore_exclusions` ~42)

**Interfaces:**
- Consumes: `store.systems_off(entry)`, `store.card_locked_games(entry, by_id, excluded)` from Task 1.

- [ ] **Step 1: Write the failing tests:**
  - `test_collection_games_honour_exclusions` (replaces the old one, same fixture): expect `(u.bytes, u.count) == (100, 1)` (only `gba/A.zip`; `gba/C.zip` excluded). Adjust the numbers to the file's fixture sizes if they differ: the point is C is not counted.
  - `test_an_off_system_is_empty`: card `{"games": {"gba": [g("gba/A.zip")]}, "systems_off": ["gba"]}` → `Usage(0, 0, False)`, and the same with `{"gba": {"full_system": True}}`.
  - `test_card_usage_has_no_bios_for_an_off_system`: `card_usage` of that card over `[gba]` has the same bytes as an empty card.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_budget` → FAIL.

- [ ] **Step 3: Implement:** `_system_usage` returns `Usage(0, 0, False)` first when the system's bucket is in `store.systems_off(card)`; `_system_keys` passes `card.get("excluded") or {}` to `card_locked_games` and drops the "collection games ignore exclusions" comment.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_budget tests.test_commands` → PASS.

- [ ] **Step 5: Commit** `feat(budget): size off systems as empty and drop excluded collection games`

### Task 3: surprise — never pick from an off system, refill its slots

**Files:**
- Modify: `src/sync_roms/surprise.py` (`_current` ~251)
- Test: `tests/test_surprise.py` (next to `test_card_excluded_systems_are_never_picked_and_their_surprises_are_replaced` ~344)

**Interfaces:**
- Consumes: `store.systems_off(entry)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_off_systems_are_never_picked_and_their_surprises_are_replaced`: as the card-excluded test above it, with `systems_off=["gb"]` instead → 10 picks, all gba.
  - `test_a_kept_surprise_on_a_system_turned_off_after_the_question_is_refilled`: card with surprises on gba and gb; `run_surprise(..., interactive=False ...)` is not used — instead save the card with both surprises, then `store.update_card("c", systems_off=["gb"])` (the editor's toggle), then call `fill_surprises` → result has `SLOTS` picks, none on gb, the gba surprise kept.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_surprise` → FAIL.

- [ ] **Step 3: Implement:** `_current` adds `store.systems_off(entry)` to its `excluded` set; extend its docstring and `run_surprise`'s to name off systems.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_surprise tests.test_onion_surprise` → PASS.

- [ ] **Step 5: Commit** `feat(surprise): skip systems turned off on the card`

### Task 4: card editor — untick collection games

**Files:**
- Modify: `src/sync_roms/cardpicks.py` (`SystemPicks.__init__`, `states`, `apply`; `CardPicks.on_card`)
- Modify: `src/sync_roms/cardedit.py` (`_locked_note` ~737, the `locked=` / `locked_note=` lists ~814, the collection-row label ~720 stays)
- Test: `tests/test_cardpicks.py`, `tests/test_cardedit.py` (rewrite `test_collection_games_are_on_locked_and_marked_even_when_excluded` ~454; `test_surprise_rows_are_locked_in_the_game_list` ~383 must still pass)

**Interfaces:**
- Produces: `SystemPicks.surprise: set[str]` — keys of `locked_from` whose label is `surprise.LABEL` (the only rows that stay locked); `SystemPicks.collected: set[str]` — the other `locked_from` keys.
- Rules (from the spec): a collection key is on unless in `excluded`; switching it off adds it (and its multi-disc group, which `changes` already expands) to `excluded`; on removes it from `excluded` and never adds a direct pick. Surprise keys: always on, untouched by `apply`. `CardPicks.on_card` follows the same rule for a system not shown (`excluded_of(bucket)`).

- [ ] **Step 1: Write the failing tests:**
  - `test_cardpicks`: `test_off_on_a_collection_game_excludes_it` (favs on card, switch `gba/Ruby.zip` off → `p.save()`, `store.card_excluded("c") == {"gba": ["gba/Ruby.zip"]}`, `card_games` unchanged); `test_on_again_removes_the_exclusion_and_adds_no_pick`; `test_keep_switches_an_excluded_collection_game_back_on` (n == 1, `sp.games == []`, exclusion gone); `test_on_card_of_an_excluded_collection_game_on_a_system_not_shown_is_false`.
  - `test_cardedit`: `test_collection_games_are_on_unlocked_and_marked` (no exclusion: initial on, not locked, `locked_note` `""`, the `💖 Favs` extra still there); `test_an_excluded_collection_game_shows_off` (with `excluded`: initial off, not locked, still marked `💖 Favs`).

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_cardpicks tests.test_cardedit` → FAIL.

- [ ] **Step 3: Implement** the rules above; `_locked_note` returns its text only for `sp.surprise` keys (wording unchanged); the editor's `locked` list uses `sp.surprise`.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_cardpicks tests.test_cardedit` → PASS.

- [ ] **Step 5: Commit** `feat(edit): untick collection games on a card`

### Task 5: card editor — `x` turns a system off

**Files:**
- Modify: `src/sync_roms/cardedit.py` (keys ~9-33, `system_labels` ~89, `toggle_full` neighbour ~237, `edit_card`'s `on_hotkey` and `hotkeys` ~300-312, the system games list title)
- Modify: `README.md` (editor keys list ~311-316, cards.json table rows for `excluded` and `collections` ~288-289, new `systems_off` row)
- Modify: `CLAUDE.md` (card fields table: `excluded` row drops "Never applies to collections." and says it covers set and collection games; new `systems_off` row: written by card editor's `x`, meaning "System ids nothing syncs for on this card; picks, sets and collections there stay saved. Surprise skips them.")
- Test: `tests/test_cardedit.py` (next to the `FULL_KEY` test ~639)

**Interfaces:**
- Consumes: `store.systems_off(entry)`, budget from Task 2 (off usage 0).
- Produces: `cardedit.OFF_KEY = "x"`; `cardedit.toggle_off(name, bucket) -> None` — adds/removes the bucket in the card's `systems_off` through `store.update_card`, sorted, and removes the field when empty (pass `systems_off=None` or pop it, whichever `update_card` supports; check it).
- Copy: `LIST_HINT` gains ` · x off` after `f full`; `LIST_KEYS` gains `("x", "turn the system off on this card: nothing of it syncs, its picks stay (again to turn it back on)")` after the `f` entry. Off row in `system_labels`: first column `("  🚫 off", "red")`, other columns as an unpicked system's (the full-size column stays). Games list title of an off system ends with ` · 🚫 off on this card`. README key line: "`x` turns the system off on this card: nothing of it syncs and Surprise skips it, while its picks, sets and collections stay saved (again turns it back on)."

- [ ] **Step 1: Write the failing tests:**
  - `test_x_turns_a_system_off_and_on_in_place`: modelled on the `FULL_KEY` test: hotkey `(cardedit.OFF_KEY, i)` → `store.saved_card("c")["systems_off"] == ["gba"]`, the row's first column is `("  🚫 off", "red")`; again → `"systems_off" not in store.saved_card("c")`, picks unchanged throughout.
  - `test_system_labels_mark_an_off_system`: `system_labels` with a card `systems_off: ["gba"]` and gba picks → `("  🚫 off", "red")` first column.
  - `test_an_off_system_still_opens_with_a_notice`: entering gba of an off card shows its games and the title ends with ` · 🚫 off on this card`.
  - `test_d_leaves_systems_off_alone`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_cardedit` → FAIL.

- [ ] **Step 3: Implement** as specified: `x` handled in `on_hotkey` in place like `f` (recompute that system's usage and `extras`), added to `hotkeys`.

- [ ] **Step 4: Run** the full suite `uv run python -m unittest discover -s tests` → PASS (includes `tests/test_readme.py`).

- [ ] **Step 5: Commit** `feat(edit): turn a system off on a card with x`
