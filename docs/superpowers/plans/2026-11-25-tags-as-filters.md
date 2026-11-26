# Tags as filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete tags (every version of a game gets every applicable tag), make one tag filter sticky across every games list, and fix editor UX from an approved audit.

**Architecture:** One process-wide `TagFilter` in `tagui.py` that every games list applies and shows as a banner; key handling (`s` pick, `c` clear) is one shared helper, so lists stop owning their own filter. Tag data is reviewed by subagents that write proposals to a scratch folder; a script merges them through the `tags.py` API only after the user approves a per-tag diff.

**Tech Stack:** Python 3.12+, `uv`, `unittest`; existing `picker.filter_list`, `tags.py`, `shared.py`.

**Spec:** `docs/superpowers/specs/2026-11-25-tags-as-filters-design.md` (read its "Calls made" section too).

## Global Constraints
- Run everything with `uv run`; tests: `uv run python -m unittest discover -s tests` with stdin closed (`< /dev/null`).
- Test modules importing `sync_roms` import `isolate` first (via `helpers`).
- Storage access only through `tags.py`/`shared.py`; never write backups or scratch files to storage; no agent writes `tags.json`.
- Conventional commits, lowercase imperative; never hand-edit `__version__`, `CHANGELOG.md`, `.release-please-manifest.json`.
- `tests/test_readme.py` compares README tables with parsers: update the README with any key/command text change.
- Tags stay flat; tags never put a game on a card.

## Review Focus
- Filter on, list has zero matches: banner plus "no games match", no crash, `c` still clears.
- `t` removes the required tag from the highlighted game: game stays until refresh, cursor index unchanged, no crash.
- A multi-disc record's file keys filter as their game (existing `keep` behaviour) in every list.
- Filter set in one list, then a nested editor (collection editor from card editor) opened: same filter and banner.
- Select-all (`a`) with a filter on touches only shown games; hidden picks are untouched.

---

### Task 1: Rules and one-version assumptions

**Files:**
- Modify: `CLAUDE.md` (Tags and collections section), `README.md` (tags suggest paragraph near line 388), `src/sync_roms/tagsuggest.py` (`pool`, `untagged`, module docstring), `src/sync_roms/commands.py:927-937` (`check`), `src/sync_roms/cli.py:147,663` (help text), `.claude/skills/update-variants/` and `tools/` only where they state the one-version rule
- Test: `tests/test_tagsuggest.py`, existing check tests

**Interfaces:**
- Produces: `tagsuggest.pool(system) -> {key: title}` now holds every untagged-or-suggestible game (all versions, not one per game); `tagsuggest.untagged(system) -> int` unchanged signature.

- [ ] **Step 1:** Rewrite in CLAUDE.md: drop "A game is tagged once across all tags", the `variants`-instead-of-tags rule, and the Retro Oddities/Handheld/System Essentials "own versions" bullet. New rule: every version of a game gets every tag that applies; a game with no fitting tag stays untagged; `variants` remains a "related versions" note for the `v` key. Reword the `tags suggest`/`check` bullets (no "one-version pool"; `check` gives one untagged count per system).
- [ ] **Step 2:** Write failing tests in `tests/test_tagsuggest.py`: `test_pool_includes_every_version_of_a_game` (two ROMs with the same scraped name, both appear in `pool`) and `test_pool_still_skips_ignored_and_declined`. Run: expect FAIL on the first.
- [ ] **Step 3:** Change `tagsuggest.pool` to drop its one-version-per-game reduction (keep ignored ROMs and declined pairs out); update docstrings, `cli.py` help and the README paragraph to match.
- [ ] **Step 4:** In `commands.py` `check`, keep the per-system count line `"{system}: {n} untagged games"` (already a count); update the surrounding doc text only. Run the full suite: expect PASS. Commit `docs(tags): tag every version of a game`.

### Task 2: Sticky filter and shared key handling

**Files:**
- Modify: `src/sync_roms/tagui.py`, `src/sync_roms/cardedit.py` (`GameFilters.__init__`/key handling ~640-690, `_games_pass` loop ~955-1006), `src/sync_roms/listedit.py:290-308` (`toggle_all`), `src/sync_roms/edit.py` (`toggle_games`/`_toggle_games`)
- Test: `tests/test_tagui.py`, `tests/test_edit.py`, `tests/test_cardedit.py`

**Interfaces:**
- Produces in `tagui.py`:
  - `FILTER: TagFilter` (module-level singleton; never auto-cleared).
  - `banner() -> str`: `""` with no filter, else `f"{FILTER.describe()} (c clear filters)"`.
  - `handle_key(pressed: str, row_keys: Iterable[str], place: dict | None = None) -> bool`: for `SET_KEY="s"` calls `FILTER.pick(row_keys)`, for `CLEAR_KEY="c"` calls `FILTER.clear()` and pops `"query"` from `place.get("session", {})`; returns True when it handled the key.
  - `HOTKEYS = ("s", "c")` and `KEYS_HELP = [("s", "narrow by tags (stays on in every list)"), ("c", "clear filters")]`.
- Consumes: existing `TagFilter.keep/describe/pick/clear`.

- [ ] **Step 1: Tests** in `tests/test_tagui.py`: `test_filter_is_shared` (`tagui.FILTER` identity is the same object seen by a `cardedit.GameFilters(system).tags`), `test_banner_empty_without_filter`, `test_banner_lists_required_and_excluded`, `test_handle_key_clear_resets_filter_and_query`, `test_handle_key_ignores_other_keys`. Reset `tagui.FILTER.clear()` in `setUp`. Run: FAIL.
- [ ] **Step 2:** Implement `FILTER`, `banner`, `handle_key`, `HOTKEYS`, `KEYS_HELP` in `tagui.py`.
- [ ] **Step 3: Tests** in `tests/test_edit.py`: `test_toggle_games_hides_rows_the_filter_rejects` (filter required tag, only matching rows reach `picker.filter_list`, with `filters=tagui.banner()`), `test_toggle_games_s_and_c_handled_inside` (pressing `s`/`c` calls `tagui.handle_key` and reopens the list with `place` kept), `test_toggle_games_no_matches_shows_banner_and_message`. Run: FAIL.
- [ ] **Step 4:** In `edit.toggle_games`, filter `rows` by `tagui.FILTER.keep(row[1])` each pass, add `tagui.HOTKEYS` and `tagui.KEYS_HELP`, pass `filters=tagui.banner()` combined with the caller's `filters`, and loop on `tagui.handle_key(...)` as it already does for `t`. Zero matches: show the existing empty-list behaviour with an extra line "no games match the tag filter".
- [ ] **Step 5:** Remove the per-list filters: `cardedit.GameFilters.tags` becomes `tagui.FILTER`; `_games_pass` caller loop (~962-1000) and `listedit.toggle_all` drop their own `TagFilter()`, `SET_KEY`/`CLEAR_KEY` branches and `pick_tags` entry (the card editor's `s` from the system list now opens `tagui.FILTER.pick(...)` over all games then the all-games list). Update `cardedit.ALL_GAMES_KEYS`, `GAMES_HINT` and README key text. Keep `META_KEY`/`PAST_SURPRISE_KEY` handling in `GameFilters`.
- [ ] **Step 6:** Update `a` help in `key_help` to "all/none of the games shown". Run full suite: PASS. Commit `feat(tags): make the tag filter sticky across lists`.

### Task 3: Filter in the remaining games lists

**Files:**
- Modify: `src/sync_roms/listedit.py` (`add_from_system` ~84, `add_from_tag` ~127, `edit_menu` ~210), `src/sync_roms/cardedit.py` (variants list ~757), `src/sync_roms/collectionedit.py` (game lists ~53), any `edit.py` list built on `picker.filter_list` that shows games
- Test: `tests/test_listedit.py` (create if absent, using `helpers`), `tests/test_collectionedit.py`, `tests/test_cardedit.py`

**Interfaces:**
- Consumes: `tagui.FILTER`, `tagui.banner()`, `tagui.handle_key(pressed, row_keys, place)`, `tagui.HOTKEYS`, `tagui.KEYS_HELP`.

- [ ] **Step 1:** For each list that shows games (not cards, devices, settings, tag lists): write a failing test `test_<list>_applies_tag_filter` asserting rows passed to `picker.filter_list` exclude games the filter rejects and `filters` contains the banner. Lists: add-from-system, add-from-tag (its own tag choice stays; the filter narrows the games), card editor variants, collection editor game list.
- [ ] **Step 2:** Apply `tagui.FILTER.keep` to those rows, pass `filters=tagui.banner()`, add `tagui.HOTKEYS`/`KEYS_HELP`, dispatch through `tagui.handle_key`. Where a list reopens after a key, keep `place`/cursor as the neighbours do.
- [ ] **Step 3:** Test `test_t_on_filtered_game_keeps_cursor`: after `t` removes the required tag, the list reopens with the cursor at the same index (game gone only on refresh). Run full suite: PASS. Commit `feat(tags): filter every games list by tag`.

### Task 4: Editor UX audit (read-only, then user picks)

**Files:** none changed; output `docs/superpowers/specs/2026-11-25-editor-ux-audit.md` (scratch quality; commit only if the user wants it).

- [ ] **Step 1:** Dispatch read-only subagents, one per file group (`edit.py` + `listedit.py`; `cardedit.py`; `collectionedit.py` + `tageditor.py` + `tagui.py`; `picker.py` key/help layer). Each reports inconsistencies and improvements with filters in mind (key consistency, discoverability, counts shown, tag-from-anywhere flows, bulk tag editing from a filtered list), each item with file:line, a one-line fix, and effort S/M/L.
- [ ] **Step 2:** Merge into one ranked list. **Stop and show the user; implement only the items they pick** (new plan tasks per pick, each with its own failing test first).

### Task 5: Data review (scratch files; user-gated apply)

**Files:**
- Create: `tools/export_tag_review.py`, `tools/apply_tag_proposals.py`
- Test: `tests/test_tag_review_tools.py`

**Interfaces:**
- `export_tag_review.py OUT_DIR`: writes `OUT_DIR/vocabulary.json` (`{tag id: {name, description}}`) and `OUT_DIR/systems/<system>-<n>.json` chunks of at most 400 games, each `[{"key", "title", "tags": [ids]}]` (titles from `names.title`, ignored ROMs left out, every system with games in storage). Reads through `tags.py`/`inventory.py`; writes only to OUT_DIR (the session scratchpad, never storage).
- Proposal file (written by agents) `OUT_DIR/proposals/<same name>.json`: `{"add": {key: [tag ids]}, "remove": {key: [tag ids]}, "new_tags": {id: {name, emoji, description}}}`.
- `apply_tag_proposals.py OUT_DIR [--summary | --apply]`: `--summary` prints per-tag added/removed counts with 5 sample titles and ignores unknown tag ids and keys not in the export (reporting them); `--apply` writes through `tags.change_game_tags` (new tags are never created: `new_tags` are only listed).

- [ ] **Step 1: Tests:** `test_export_chunks_systems_at_400`, `test_export_leaves_out_ignored_roms`, `test_summary_counts_per_tag`, `test_summary_reports_unknown_ids_and_keys`, `test_apply_calls_change_game_tags_per_game`, `test_apply_never_creates_tags`. Run: FAIL.
- [ ] **Step 2:** Implement both tools to pass them. Run suite: PASS. Commit `chore(tags): add tag review export and apply tools`.
- [ ] **Step 3 (phase 1):** Run export into the session scratchpad. Dispatch one agent per chunk (batches of ~10 in parallel). Prompt: vocabulary file + chunk; add every tag that applies to every game, remove a tag only for a clear error, propose new tags only in `new_tags`, write the proposal file, touch nothing else.
- [ ] **Step 4 (phase 2):** Run `--summary`. For tags that grew most or look suspicious, dispatch one agent per tag to recheck precision and recall across systems (reads exports plus proposals, writes a corrective proposal file).
- [ ] **Step 5:** **Stop and show the user the per-tag summary.** Run `--apply` only after approval, then `uv run sync-roms cache update` is not needed; run `uv run sync-roms check` and report. Update the `update-variants` skill text if it mentions the one-version rule.

## Self-review
- Spec coverage: rules (T1), sticky filter + bulk-action scope + `s` meaning (T2), every list (T3), audit (T4), data review incl. phases, gate and no-new-tags (T5), `check`/`suggest` (T1).
- Order: T1 → T2 → T3 → T4 proceed sequentially in code; T5 steps 1–4 can run alongside T3/T4 (they touch tools and scratch only), apply last.

## Addendum: UX tasks picked by the user after the audit (bundles A, B, C, D)

Items come from `.superpowers/sdd/2026-11-25-tags-as-filters/audit-*.md` (git-ignored scratch; the numbers below refer to those files: E=audit-edit-listedit, C=audit-cardedit, T=audit-tag-collection). Run sequentially, one implementer at a time (they share `edit.py`, `cardedit.py`, `tagui.py`). Each task: failing tests first, full suite once before commit, README/help text kept in sync with `tests/test_readme.py`.

### Task 6: Bundle A, filter visibility
Items E2, C2, T5 ("N of M shown" in the banner whenever the filter is on and hides rows; `tagui.banner(shown: int | None = None, total: int | None = None)`); E8, C1, C11 (banner and `c` on the card editor's system list, collections list and the top menus; system list shows a "N match" count per system while a filter is on); E11, T9, T15 (opted-out lists show "tag filter paused here" when a filter is set); E5, E6, E7, C4, C10 (one hint builder so every games list says `s filter by tag · t edit tags · c clear filters`; hints list `/` and `w` where live); E12 (`c` help says it clears search and filters).

### Task 7: Bundle B, bulk tag and untagged
Items E1, C6, T1: `T` in every games list that applies the filter (`edit.toggle_games`, card editor system/all/collection lists) opens the tag checklist once and applies the add/remove diff to every shown row through `tags.change_games_tags`, after a confirm that shows the count; reports "Tagged N games". Items T4, C7: `FILTER.pick` always lists tags already required/excluded (even with 0 games here) and has a "no tags at all" entry (keep() true when `tags.record(key)` is None or has no tags); picker counts reflect the current narrowed set (E10).

### Task 8: Bundle C, add all shown
Items E3, C3: `a` works in All games / All systems lists when a filter is set (`select_all` true only then) and the hint says so. Item E4: "Add games from which tag?" becomes "add games with the tag filter preset" (opens the add list with that tag required) instead of a separate narrowing. Item T14: collection editor gets "Add games matching the current tag filter".

### Task 9: Bundle D, tag picker ergonomics
Items T2 (recent/frequent tags: checked first, then the last ~8 used this run, then alphabetical; search also matches descriptions), T3 (descriptions as row notes in pickers), T6 (direct `x` key in the filter picker to exclude), T7 (tag editor `o` toggles name/count sort; 0-game tags dimmed), T8 (rename checks duplicate names like `_new_tag`; merge/delete give a result note), T10 (note when `n` created a tag but Esc left it unapplied), T11/E9 (`t` shows "Tagged X: +2 −1"; `.` repeats the last add/remove set; note "No game under the cursor" on an empty list).

### Task 10: Tag-editing workflow walkthrough (user's acceptance test, runs last)
The user's most common work, which must be easy and efficient (simpler than before this branch, measured in keypresses and screens): (A) `sync-roms edit` → Tags → pick a tag → search for a game → if missing, add it (via a system list or a full all-games search) → save and quit. (B) open a tag → find a game in it → remove it → save and quit. Steps: first trace both flows in the code as they are now (edit.py menu → tageditor.py → tag menu → add/remove lists → save) and count screens/keypresses, including the quit/save path (Esc review & save prompts) and what the sticky filter does inside them; then fix friction found (e.g. the tag's own game list opening straight to a searchable list with `/`, add flow reachable from that list in one key with an all-games search, a pre-set filter or search, the filter not hiding the game being looked for, no redundant confirmations, one Esc to save and leave); implement with tests; report before/after counts of screens and keypresses for A and B.

### Task 11: Games-first tag editor (user decision after Task 10; origin/main already merged)
The user chose "Enter on a tag opens its games" and said: main already does this for collections (follow its patterns; `S` is the Settings menu for rename, emoji, etc.; main also removed art from tags). Rework `tageditor.py` so that, like `collectionedit.py` on main (#627), Enter on a tag in the tag list opens the tag's games list directly (searchable with `/`, Space removes/keeps, add key `A` with `+` kept as an alias to match collections, the all-systems add list as main's collection editor does it), and the former tag menu (rename, emoji, description, merge, delete; no art) moves behind `S` (a settings menu), with the same key names, hints, help text and structure main's collection editor uses so the two editors feel identical. Keep everything from Tasks 6-10 that still applies: `Q` leave-and-save (the collection editor on main may already have its own leave mechanism — reuse its pattern if so and drop duplicate keys), `+`/`A` search carry-over to All systems, the `o` view/sort keys, banner/counts, `tag_filter=False` for the lists that act on hidden rows, empty-tag adding. Then redo the walkthrough recount (flow A: add a missing game via a system and via search; flow B: remove a game) from `sync-roms edit` and `sync-roms tags edit`, and report before (5bf19aae) and after counts; update the Walkthrough/RealKeys tests, README, `tags` help topic. Do not change collections behaviour.
