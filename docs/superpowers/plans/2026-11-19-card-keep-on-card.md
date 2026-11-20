# Card editor `k` (keep what's on the card) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the card editor opened during sync, `k` picks every file already on the card that matches a storage ROM, so sync stops offering to delete it.

**Architecture:** `SystemPicks.keep` reuses `apply` to switch matched keys on. `edit_card` takes a new optional `card_match(system, keys)` callback (like `to_fetch`, supplied only by sync), shows `k` only when it is given, and runs it per system. `cli.sync_card` builds the callback from the card's ROM folders; `surprise.run_surprise` passes it through.

**Tech Stack:** Python, unittest (`python -m unittest discover -s tests`).

**Spec:** `docs/superpowers/specs/2026-11-19-card-keep-on-card-design.md`

## Global Constraints

- Conventional Commits, lowercase imperative.
- Match files the way `downloads.find_extras` does: `downloads.name_key` (case, Unicode form) on `downloads.rom_rel(key, disc_dir, discs)`.
- `k` appears only when `card_match` is given (not in standalone `--edit`: no card on disk).
- Never put a real game list in the repo; tests use fixtures.

## Review Focus

- Full system on the card: skipped, no picks added.
- Game already picked or covered by a set: not duplicated in `games`.
- Excluded game whose file is on the card: un-excluded and kept.
- Game locked by a collection/surprise: left as is (`apply` skips `locked_from`).
- Card files matching nothing in storage: counted in the note, never picked.
- Multi-disc game with discs in `disc_dir`: matched via `rom_rel`.

---

### Task 1: `SystemPicks.keep`

**Files:**
- Modify: `src/sync_roms/cardpicks.py` (class `SystemPicks`)
- Test: `tests/test_cardpicks.py`

**Interfaces:**
- Produces: `SystemPicks.keep(self, keys, notes) -> int`: switches each of `keys` (bucket keys of this system) on; returns how many were off before and are on now. `notes` is `CardPicks.cover()`.

- [ ] **Step 1: Failing tests** in `tests/test_cardpicks.py` (follow that file's existing SystemPicks setup): `test_keep_picks_unpicked_keys` (two keys off → both in `games` with `names`-style titles, returns 2); `test_keep_skips_picked_and_set_covered` (returns 0, `games` unchanged); `test_keep_unexcludes` (excluded key covered by a set → removed from `excluded`, returns 1, not added to `games`); `test_keep_skips_locked` (key in `locked_from` → returns 0).
- [ ] **Step 2: Run** `python -m unittest tests.test_cardpicks -v` → FAIL (`keep` missing).
- [ ] **Step 3: Implement** `keep`: `base = self.states(notes)`, `before = sum(base[k] for k in keys)`, call `self.apply(keys, notes, base, [True] * len(keys))`, return count of keys now on minus `before` using a fresh `self.states(notes)`.
- [ ] **Step 4: Run** the same command → PASS.
- [ ] **Step 5: Commit** `feat(cardedit): add SystemPicks.keep`.

### Task 2: `k` in the system list

**Files:**
- Modify: `src/sync_roms/cardedit.py` (`KEEP_KEY`, hint/help, `edit_card`), `src/sync_roms/surprise.py` (`run_surprise` passes `card_match` through)
- Test: `tests/test_cardedit.py`, `tests/test_surprise.py` (the `edit_card` lambdas there take `(name, setup=None, to_fetch=None)`: add `card_match=None`)

**Interfaces:**
- Consumes: `SystemPicks.keep(keys, notes) -> int`.
- Produces: `cardedit.KEEP_KEY = "k"`; `edit_card(name, setup=None, to_fetch=None, card_match=None)`; `surprise.run_surprise(..., to_fetch=None, card_match=None)`; callback contract `card_match(system, keys) -> (set of keys on the card, int count of other card files in the system's folder)`.

- [ ] **Step 1: Failing tests** in `tests/test_cardedit.py` (near the `to_fetch` test at ~line 925, same `Script` pattern): `test_k_keeps_card_files` (first filter_list call returns `("k", 0)`, second `None`; callback returns `({"gba/Red.gba"}, 1)` → card's saved games contain Red; an `edit.note` was shown containing the added count and `1`); `test_k_skips_full_system` (full system → callback not called for it); `test_k_hidden_without_callback` (`hotkeys` kwarg lacks `"k"` and the hint lacks "k keep" when `card_match` is None).
- [ ] **Step 2: Run** `python -m unittest tests.test_cardedit -v` → FAIL.
- [ ] **Step 3: Implement** in `edit_card`: add `KEEP_KEY` to `hotkeys` and `· k keep card files` to the hint and a `("k", "pick every card file that matches a storage game")` entry to `key_help`, only when `card_match`. On `KEEP_KEY` (not in the per-`idx` branch; it is card-wide): create `picks = cardpicks.CardPicks(name, setup)`; for each non-full system in `systems`, `sp = picks.system(s)` (catch `s3.ERRORS` like `edit_system`), `matched, other = card_match(s, list(sp.in_storage))`, `added = sp.keep(sorted(matched), picks.cover())`; sum; `picks.save()`; `edit.note(...)` with totals ("Picked N card file(s) in M system(s); K card file(s) match nothing in storage and still get deleted"); `changed = ALL`. Update `run_surprise` and its two `edit_card` calls to pass `card_match`.
- [ ] **Step 4: Run** `python -m unittest tests.test_cardedit tests.test_surprise tests.test_edit -v` → PASS.
- [ ] **Step 5: Commit** `feat(cardedit): add k to keep card files in the system list`.

### Task 3: sync supplies `card_match`

**Files:**
- Modify: `src/sync_roms/cli.py` (define `card_match` beside `to_fetch`, ~line 983; pass to `surprise.run_surprise`)
- Modify: docs listing the editor keys, if any (`grep -rn "D clear" README.md docs src/sync_roms/data/setup-guide.html`)
- Test: `tests/test_cli_sync.py`

**Interfaces:**
- Consumes: `edit_card`'s `card_match` contract from Task 2.
- Produces: `card_match(s, keys)` in `sync_card`: walks `downloads.walk_roms` over the system's folder under `roms_dir` (and `disc_dir` under it when the layout has one), builds `{downloads.name_key(rel)}`, returns `({k for k in keys if name_key(rom_rel(k, disc_dir, m3u.disc_keys(keys) if disc_dir else ())) in names}, number of card files whose name_key matches none of the keys' rels)`; a system with no folder for the layout returns `(set(), 0)`.

- [ ] **Step 1: Failing test** in `tests/test_cli_sync.py` (follow its existing sync fixtures): interactive sync where the card has `gba/Kept.gba` (in storage, not picked) and `gba/Stray.gba` (not in storage); the patched `edit_card` calls the received `card_match` with the system and storage keys and asserts it returns `({"gba/Kept.gba"}, 1)`; also a case-differing file name (`kept.GBA`) matches.
- [ ] **Step 2: Run** `python -m unittest tests.test_cli_sync -v` → FAIL.
- [ ] **Step 3: Implement** as in Interfaces; pass `card_match=card_match` in the `surprise.run_surprise` call; document `k` where editor keys are documented.
- [ ] **Step 4: Run** `python -m unittest discover -s tests` → all PASS.
- [ ] **Step 5: Commit** `feat(sync): let the card editor keep files already on the card`.
