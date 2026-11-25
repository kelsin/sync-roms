# Individual Collection Games on Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the card editor's collections list, Enter opens a collection's games for single picks. Sync writes every collection that has a game on the card to the frontend while `custom_collections` is on.

**Architecture:** `cardedit.pick_collections` returns the collection Enter was pressed on, and `edit_card` opens it with the existing `edit_set` (collections share the set shape). In `cli.py`'s `frontend_step`, `card_colls` gains every loaded collection with a game among the keys this sync puts on the card. The existing per-game `on_card` filter keeps each collection to its games on the card.

**Tech Stack:** Python 3.12+, unittest, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-24-collection-games-on-cards-design.md`

## Global Constraints

- Run everything through `uv run` (`uv run python -m unittest discover -s tests`); code must run on Python 3.12.
- Test modules import `isolate`/`helpers` before `sync_roms`, as the existing ones do.
- Conventional Commits, lowercase imperative. End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No change to `collections` ids, `excluded`, guest cards, `cardshare` or Surprise semantics. Sets never go to the frontend.
- Surgical: match the existing style and touch only what the task needs.

## Review Focus

- A card that has collections in `collections` but no games of theirs on the card must not get new warnings or writes: the muOS `muos_storage` warning and ES-DE's `skipped()` only happen when there is a collection to write. → Task 2 test `test_a_collection_with_no_game_on_the_card_is_not_written`.
- A collection both in `collections` and matched by a game must be written once, not twice. → Task 2 test `test_a_listed_collection_with_a_game_on_the_card_is_written_once`.
- Turning a game off in the collection view, when the whole collection is on, must put it in `excluded`, not drop the collection id. → Task 1 test `test_collection_view_switching_off_a_whole_collection_game_excludes_it`.
- Esc on the collections list still returns to the system list without opening anything. → Task 1 test `test_collections_list_esc_opens_nothing`.
- With `custom_collections` off, a collection matched only by a game is not written. → Task 2 test `test_collections_off_writes_no_matched_collection`.

---

### Task 1: Card editor — Enter opens a collection's games; per-collection count

**Files:**
- Modify: `src/sync_roms/cardedit.py` (`COLLECTIONS_HINT` line 27, `edit_card`'s `COLLECTIONS_KEY` branch ~line 376, `pick_collections` ~line 554)
- Modify: `README.md:326` (the `l` bullet) and `README.md:298` (the `collections` row)
- Modify: `CLAUDE.md` (Card fields `collections` row: "Collection ids synced whole; the card editor's `l` → Enter picks single games from one, as direct picks.")
- Test: `tests/test_cardedit.py`

**Interfaces:**
- Produces: `pick_collections(name, playable, card_status=None, setup=None) -> dict | None` returns the collection dict (from `colls.load_collections()`) Enter was pressed on, or None on Esc or when there are no collections. Space/Tab behaves as now (toggles the id in `collections`, saved at once).
- Consumes: `edit_set(name, game_set, setup, to_fetch, card_usages)` and `cardpicks.CardPicks(name, setup).on_card(key)`, both as they are.

- [ ] **Step 1: Write the failing tests** in `tests/test_cardedit.py`, next to the existing collections tests (reuse `self.card`, `self.favs`, `Script`, `returns`, `run_card`, `self.read`):
  - `test_collections_list_enter_opens_the_collections_games`: favs has `gba/Zelda.zip`. `run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns(0), <the edit_set pass toggling the row on and leaving>, returns(None))`, or patch `cardedit.edit_set` and assert it is called once with the favs dict as `game_set`. Assert `"collections"` is not set on the card (Enter doesn't add the whole collection).
  - Rewrite the existing test at ~line 490 (it now does `returns(0)` = Enter on favs): assert `cardedit.edit_set` is called with favs and `collections` stays `["favs"]`.
  - `test_collection_view_picks_a_single_game_as_a_direct_pick`: through the real `edit_set` on favs (one gba game in the storage cache), switching it on gives `cards.json["c"]["games"]["gba"] == [{"title": ..., "bucket": "gba/Zelda.zip"}]` and no `collections`.
  - `test_collection_view_switching_off_a_whole_collection_game_excludes_it`: card with `collections=["favs"]`; switching the game off in the view gives `excluded == {"gba": ["gba/Zelda.zip"]}` and `collections == ["favs"]`.
  - `test_collections_list_counts_the_collections_games_on_the_card`: favs with two gba games, one picked directly. The list's extras for favs contain `"  1/2 on the card"`, and after a Space toggle (whole on) `"  2/2 on the card"` (✅ form allowed: `"  ✅ 2/2 on the card"`). Keep `extras[i][0]` as the whole-collection mark (`"  ✅ on the card"` or `""`) so `test_collections_list_of_a_missing_or_malformed_card_entry_marks_none` still passes unchanged.
  - `test_collections_list_esc_opens_nothing`: `run_card(returns((COLLECTIONS_KEY, 0)), returns(None), returns(None))` with `edit_set` patched: not called.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run python -m unittest tests.test_cardedit -k collection`
Expected: the new tests FAIL (Enter doesn't open anything; there's no count).

- [ ] **Step 3: Implement**
  - `pick_collections`: add the `setup=None` parameter. Store `picker.filter_list`'s return and return `found[i]` for an int `i < len(found)`, else None. The title becomes `💖 Collections on {name} (Space toggles · Enter opens)`, `COLLECTIONS_HINT = "Enter show its games · Space/Tab toggle the collection · / filter"`, and the key_help gains `("Enter", "show its games to pick them one by one")`. In `mark()`, build a fresh `cardpicks.CardPicks(name, setup)` (the toggle changes what's locked) and give each collection's extras `[whole mark, ("  {have}/{p} on the card", "cyan"), playable count]`, with `have` = its games on `playable` systems for which `picks.on_card(g["bucket"])`. Only build CardPicks when `setup` is given. Without it, leave out the count, as callers and tests without a setup do now.
  - `edit_card`: `chosen = pick_collections(name, ..., lambda: ..., setup)`, then `if chosen: edit_set(name, chosen, setup, to_fetch, usages)`. Still `changed = ALL`.
  - README `l` bullet: "`Space`/`Tab` toggles the whole collection, `Enter` opens its games to pick them one by one (as direct picks)". README `collections` row: add "single games picked from a collection with `l` → `Enter` are ordinary picks in `games`".

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run python -m unittest discover -s tests`
Expected: all pass (`tests/test_readme.py` included).

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/cardedit.py tests/test_cardedit.py README.md CLAUDE.md
git commit -m "feat(edit): pick single games from a collection on a card"
```

### Task 2: Sync — write every collection with a game on the card

**Files:**
- Modify: `src/sync_roms/cli.py` (`frontend_step`, ~line 1751)
- Modify: `README.md:304` (`custom_collections` row) and `CLAUDE.md` (the "What sync puts on a card" intro or the Sets and collections section: one line)
- Test: `tests/test_sync_flow.py`

**Interfaces:**
- Consumes: `chosen` (the systems this sync syncs) and `available(s)` (the keys it syncs for system `s`), both in scope in `frontend_step`'s enclosing function. `colls.load_collections()`.
- Produces: nothing new. The behaviour change is internal to `frontend_step`.

- [ ] **Step 1: Write the failing tests** in `tests/test_sync_flow.py`, next to `test_collections_off_writes_no_collection_files_and_no_art` (use `run_sync`, `FAVS` (one game, `GAME`, `gba/Game.zip`), `read_from`, `files=["ROMs/gba/Game.zip"]`):
  - `test_a_collection_with_a_game_on_the_card_is_written_without_being_listed`: `cards={"games": {"gba": [GAME]}, "surprise": False}`, `colls=[FAVS]`. Then `custom-Favs.cfg` under `ES-DE/collections` == `"%ROMPATH%/gba/Game.zip\n"`, and `frontend_collections` is updated to include `"Favs"`.
  - `test_collections_off_writes_no_matched_collection`: the same with `"custom_collections": False`. The file is None and no `frontend_collections` update happens.
  - `test_a_collection_with_no_game_on_the_card_is_not_written`: `cards={"games": {"gba": [GAME]}, "surprise": False}`, `colls=[{"id": "other", "name": "Other", "games": [{"system": "gba", "bucket": "gba/Else.zip", "title": "Else"}]}]`. Then `custom-Other.cfg` is None and no `frontend_collections` update happens.
  - `test_a_listed_collection_with_a_game_on_the_card_is_written_once`: `cards={"games": {"gba": [GAME]}, "collections": ["favs"], "surprise": False}`, `colls=[FAVS]`. The file holds the line once.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run python -m unittest tests.test_sync_flow -k collection`
Expected: the "without being listed" test FAILS (file None). The others may pass already, which is fine since they pin the behaviour.

- [ ] **Step 3: Implement** in `frontend_step`, replacing the `card_colls` line:

```python
synced = {k for s in chosen for k in available(s)}
listed = names("collections")
card_colls = ([by_id[i] for i in listed if i in by_id]
              + [c for c in by_id.values() if c["id"] not in listed
                 and any(g.get("bucket") in synced for g in c["games"])]) if collections_on else []
```

  Keep `by_id`'s order (load order, by name) for the matched ones. Everything after (the Surprise append, `owned`, the plans, the art) is unchanged. The collections listed first and the matched ones after only differ in order, which none of the frontends depends on.
  - README `custom_collections` row (or the line before the Card fields table): "a collection is written when it is on the card or any of its games is". CLAUDE.md Sets and collections: "While `custom_collections` is on, sync writes every collection with a game on the card (in `collections` or not), each with only its games on the card."

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run python -m unittest discover -s tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/cli.py tests/test_sync_flow.py README.md CLAUDE.md
git commit -m "feat(sync): write collections whose games are on the card"
```
