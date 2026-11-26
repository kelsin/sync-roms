# Collections list size and counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each collection's playable size and 🎮 playable / 🚫 off / 📵 not playable counts in the card editor's collections list.

**Architecture:** All in `cardedit.pick_collections`'s `mark()`: split each collection's games three ways using `playable` and `store.systems_off`, size the 🎮 ones with `budget.game_costs` per system, and emit each value as its own extras column (the picker already aligns columns across rows).

**Tech Stack:** Python 3.12+, unittest, `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-26-collections-size-design.md`

## Global Constraints

- Column order: on the card, have/total, size, `🎮 N`, `🚫 N`, `📵 N`, then the existing match text.
- Each column a separate `(text, color)` extras part, every row the same number of parts; a 0 count is `("", "dim")`.
- Count numbers right-aligned to the widest number of that column across all rows (e.g. `"  🚫  5"` when another row has `🚫 12`).
- Size: `size_text(bytes)` (decimal), `SIZING` while partial, dim; no size part when `setup` is None.
- have/total and size count 🎮 games only.
- Code must run on Python 3.12.

## Review Focus

- A collection with every game off or not playable: size `0 B`, have/total `0/0`, 🎮 blank → test with an all-off collection.
- Sizes not cached (no `gba/` listing): size shows `…`, no crash → test.
- Toggling a system off elsewhere then reopening: counts move from 🎮 to 🚫 → covered by the off test.
- Malformed games (no system / no bucket): still counted as today (`test_collections_hotkey_skips_malformed_games`, update its expectation).
- `pick_collections(name, playable)` without setup (existing callers in tests): no size part, no crash.

---

### Task 1: Size and three-way counts in the collections list

**Files:**
- Modify: `src/sync_roms/cardedit.py` (`pick_collections`, ~644-704)
- Test: `tests/test_cardedit.py` (tests near `test_collections_hotkey_shows_playable_counts_and_space_toggles`, ~492-510)

**Interfaces:**
- Consumes: `budget.game_costs(card, system_dict, keys) -> ({key: bytes}, partial)`, `store.systems_off(entry) -> set`, `card_entry(name, setup)`, `size_text`, `SIZING`; system dicts from `store.load_catalog()["systems"]` by `bucket`.
- Produces: nothing used elsewhere.

- [ ] **Step 1: Update/write failing tests**

Update `test_collections_hotkey_shows_playable_counts_and_space_toggles` to expect the new extras for Favs (Ruby gba, Red gb, FF7 psx, Pokemon nds: 2 playable, 2 not playable, nothing off):
`[("  ✅ on the card", "green"), ("  ✅", "cyan"), ("  <size>", "dim"), ("  🎮 2", "dim"), ("", "dim"), ("  📵 2", "dim")]` — `<size>` is what the test fixture's cache gives (or `…` when it has no cache; use whichever the fixture produces and assert it exactly).
Update `test_collections_hotkey_skips_malformed_games` to the new column layout.
Add `test_collections_list_counts_off_systems`: card with `systems_off=["gb"]`, Favs → `🎮 1`, `🚫 1`, `📵 1` parts; have/total `0/1`; size equals Ruby's ROM size only (set `self.cache` with `gba/`, `gb/`, `scrapes/gba/`, `scrapes/gb/` like `test_collections_screen_shows_the_card_status_after_each_toggle`).
Add `test_collections_list_aligns_counts`: two collections, one with 12 playable games and one with 3 → the second's 🎮 part is `"  🎮  3"`.
Add `test_collections_list_size_is_sizing_without_cache`: no cache → size part `("  …", "dim")`.

Add `test_collections_list_explains_the_counts`: `picker.filter_list` gets a `tag_info` callable; `kw["tag_info"](0)` for Favs with gb off equals
`[("🎮", "Playable", "1 game on systems this card syncs"), ("🚫", "Off", "1 game on systems turned off on this card (x)"), ("📵", "Not playable", "1 game on systems this device can't run")]`
(all three lines always, count with `game`/`games` agreement: `2 games ...`, `0 games ...`).

- [ ] **Step 2: Run and see them fail**

Run: `uv run python -m unittest tests.test_cardedit -k collections < /dev/null`
Expected: the new/updated tests FAIL.

- [ ] **Step 3: Implement in `pick_collections`**

Split per collection into `on_games`, `off_games`, `not_playable` (counts) once outside `mark()` is wrong because `systems_off` can't change while the list is open — so compute once before the loop. Size once too (per system, `budget.game_costs(card_entry(name, setup), system, keys)`, summing bytes, any partial → `SIZING`). In `mark()` build the parts in the Global Constraints order with right-aligned numbers. Pass `tag_info=lambda i: ...` to `picker.filter_list` (the footer block game lists use for a highlighted game's tags, `picker.tag_lines`) returning the three `(emoji, name, description)` legend lines for collection i (index past `found` → `[]`).

- [ ] **Step 4: Run tests**

Run: `uv run python -m unittest tests.test_cardedit < /dev/null` then `uv run python tools/run_tests.py < /dev/null`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/cardedit.py tests/test_cardedit.py docs/superpowers
git commit -m "feat(cards): show collections' playable size and off counts"
```
