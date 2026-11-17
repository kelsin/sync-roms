# `cards copy` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms cards copy SRC DST` merges SRC's games, sets, exclusions and collections into DST, skipping systems DST can't play.

**Architecture:** A pure merge function in `cardshare.py` does all the data work; `commands.cards_copy` loads cards, works out DST's playable systems and what DST already syncs, calls it, prints counts and saves.

**Tech Stack:** Python 3 stdlib, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-17-cards-copy-design.md`

## Global Constraints

- Conventional Commits, lowercase imperative (`feat(cli): ...`). No AI attribution in commits.
- Never touch storage; nothing is read from or written to the bucket.
- Saving goes through `store.write_cards` (keeps `cards.json.bak`, refuses to overwrite invalid JSON).
- Match existing style: dense one-line argparse setup, docstrings in the same voice as `cardshare.py`.
- Run tests with `python -m unittest discover -s tests`.

## Review Focus

- SRC system is `full_system` with a stashed `games` list, DST has a plain list → DST becomes `{"full_system": True, "games": <union>}`.
- DST already full, SRC plain list → DST stays full, SRC games merged into its stashed `games`.
- SRC exclusion for a game DST picks or syncs through its own sets/collections → not copied.
- SRC `games` keys for systems DST can't play (and SRC exclusions for them) → skipped and reported; `sets` is never treated as a system.
- Copying onto a card twice adds nothing the second time (counts all 0).

---

### Task 1: merge function

**Files:**
- Modify: `src/sync_roms/cardshare.py`
- Test: `tests/test_cardshare.py`

**Interfaces:**
- Produces: `cardshare.copy_selections(src: dict, dst: dict, playable: set[str], dst_synced: dict[str, set[str]]) -> tuple[dict, dict, list[str]]`
  - `src`, `dst`: card entries from `cards.json` (not mutated).
  - `playable`: system buckets DST can play.
  - `dst_synced`: `{system bucket: set of bucket keys}` DST syncs before the copy.
  - Returns `(new_dst_entry, counts, skipped)`: `counts` has keys `"games"`, `"sets"`, `"collections"`, `"excluded"` (ints, things newly added); `skipped` is the sorted list of SRC system buckets (from `games` and `excluded`) not in `playable`.

Rules (from the spec):
- `games[system]` is a list of `{"title","bucket",...}` dicts or `{"full_system": True, "games"?: [...]}`; `games["sets"]` is a list of set ids. Add SRC games by bucket; DST's entry wins on the same bucket. Either side full → result full with merged list under `"games"` (omit `"games"` when empty). Result passed through `store.sorted_list`.
- `sets` and `collections`: union, DST order first then new ids appended.
- `excluded[system]`: add SRC's buckets for playable systems unless in `dst_synced[system]` or in the merged DST game list for that system; drop empty keys; omit `excluded` when empty and DST had none.
- Every other DST key (surprise, surprises, size, device, layout, drivers...) is kept unchanged; nothing else from SRC is copied.
- Malformed entries (non-dict games, non-list values) in SRC are skipped, not raised on.

- [ ] **Step 1: Write failing tests** in `class CopySelectionsTest(unittest.TestCase)`:
  - `test_merges_games_dst_wins`: src `{"games": {"gba": [A_src_note, B]}}`, dst `{"games": {"gba": [A_dst_note]}, "surprise": True}`, playable `{"gba"}` → gba list is `[A_dst_note, B]` (sorted by bucket), `counts["games"] == 1`, `surprise` kept.
  - `test_skips_unplayable_systems`: src games for `gba` and `psx`, excluded for `psx`, playable `{"gba"}` → no `psx` in result games or excluded; `skipped == ["psx"]`.
  - `test_src_full_makes_dst_full`: src `{"gba": {"full_system": True, "games": [B]}}`, dst `{"gba": [A]}` → `{"full_system": True, "games": [A, B]}`.
  - `test_dst_full_keeps_full`: dst `{"gba": {"full_system": True}}`, src `{"gba": [B]}` → `{"full_system": True, "games": [B]}`.
  - `test_sets_and_collections_union`: src sets `["a","b"]`, collections `["x","y"]`; dst sets `["b"]`, collections `["y"]` → sets `["a","b"]`, collections `["y","x"]`; counts 1 and 1.
  - `test_exclusion_not_copied_when_dst_syncs_it`: src excluded `{"gba": ["gba/A.zip","gba/C.zip"]}`, dst games `{"gba": [B]}`, `dst_synced={"gba": {"gba/A.zip"}}`, src games `{"gba": [B']}` where B' has bucket `gba/B.zip` → excluded `{"gba": ["gba/C.zip"]}`, `counts["excluded"] == 1`.
  - `test_surprises_not_copied`: src with `surprises`, `surprise` → result has dst's values (or none).
  - `test_second_copy_adds_nothing`: applying twice → second `counts` all 0 and entry equal.
  - `test_inputs_not_mutated`: deep-copied inputs equal after the call.
- [ ] **Step 2:** Run `python -m unittest tests.test_cardshare -v` → new tests FAIL (`AttributeError: copy_selections`).
- [ ] **Step 3:** Implement `copy_selections` in `cardshare.py` (import `store` there).
- [ ] **Step 4:** Run `python -m unittest tests.test_cardshare -v` → PASS.
- [ ] **Step 5:** Commit `feat(cards): add merge for copying one card's selections into another`.

### Task 2: `cards copy` command

**Files:**
- Modify: `src/sync_roms/commands.py` (new `cards_copy(args)` after `cards_delete`; parser line next to `rename`; completion words list line 986)
- Modify: `src/sync_roms/cli.py` (`"cards"` usage line ~25 adds `copy`; cards help block ~131 adds `sync-roms cards copy SRC DST   merge SRC's games, sets, excluded and collections into DST (not surprises); skips systems DST can't play`)
- Modify: `README.md:269` (add `copy` to the list and a clause `copy SRC DST` merges games, sets, excluded and collections into DST, skipping systems it can't play)
- Test: `tests/test_commands.py` (`CardsTest`)

**Interfaces:**
- Consumes: `cardshare.copy_selections` (Task 1); `store.load_cards`, `store.load_catalog`, `store.cards_readable`, `store.write_cards`, `store.load_manifest([dst])` (its systems' `games` bucket keys give `dst_synced`), `picker.saved_setup`, `cardedit.can_play` (or `store.system_applies` directly to avoid importing the editor).
- Produces: CLI `sync-roms cards copy SRC DST [--dry-run]`.

Behavior:
- Exit 2 via `ui.fail` for: unknown SRC, unknown DST, SRC == DST, DST without a usable device/layout (`saved_setup` returns None). Exit 3 for unreadable cards.json (same message pattern as `cards_import`).
- Prints `📋 Copied from SRC to DST: N games, N sets, N collections, N exclusions` (green), then `ui.dim("  skipped (DST can't play them): a, b")` when any. `--dry-run` prints the same counts prefixed `🧪 Would copy` and writes nothing. Returns 3 if `write_cards` fails, else 0.

- [ ] **Step 1: Write failing tests** in `CardsTest`:
  - `test_copy_merges_into_target`: create `A` and `B` with `cards new ... --device full --layout esde`; write `A` games `{"gba": [{"title":"X","bucket":"gba/X.zip"}], "sets": []}` and `collections: ["c"]` into `cards.json`; `run_cmd("cards","copy","A","B")` → 0; `B`'s gba list has `gba/X.zip`, `collections == ["c"]`, device/layout unchanged.
  - `test_copy_dry_run_writes_nothing`: same setup, `--dry-run` → 0, `B` unchanged.
  - `test_copy_errors`: unknown source → 2; unknown target → 2; same card → 2.
- [ ] **Step 2:** Run `python -m unittest tests.test_commands -v` → new tests FAIL.
- [ ] **Step 3:** Implement `cards_copy`, the parser line `p = csub.add_parser("copy", allow_abbrev=False); common(p, card=False); p.add_argument("src"); p.add_argument("dst"); p.set_defaults(fn=cards_copy)`, completion word, help text and README line.
- [ ] **Step 4:** Run `python -m unittest discover -s tests` → all PASS (including `test_readme`, `test_completion`).
- [ ] **Step 5:** Commit `feat(cli): add cards copy to merge one card's selections into another`.
