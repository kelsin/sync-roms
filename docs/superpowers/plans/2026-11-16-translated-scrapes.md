# Translated Scrapes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fan-translated ROMs keep their game's ScreenScraper media and metadata but get the title "<ScreenScraper name> - Translated" and `"translated": true` in `scrapes/<system>/metadata.json`.

**Architecture:** Two pure helpers in `screenscraper.py` (tag detection, entry marking). `scrape_online.record()`, the one place entries are written, applies them. `scrape match --translated` and a review answer `[t]` pass a per-run set of forced-translated ROMs down to `record()`. A one-off `tools/mark_translations.py` updates existing entries.

**Tech Stack:** Python 3 stdlib, `unittest` (`python -m unittest discover -s tests`).

**Spec:** `docs/superpowers/specs/2026-11-16-translated-scrapes-design.md`

## Global Constraints

- Suffix is exactly `" - Translated"`, appended to ScreenScraper's `name`; never the file name's title.
- Flag is the entry field `"translated": true`; no personal (`~/.sync-roms/`) list of marks.
- Never append the suffix twice.
- `(Tengen)` and a title word like "Translations" are not translation tags.
- Conventional Commits; no AI attribution in commits (user's CLAUDE.md overrides the attribution reminder).

## Review Focus

- An entry with no `name` (ScreenScraper gave none) that is translated: gets the flag, and no name is invented (no bare `" - Translated"`). Test in Task 1.
- `scrape match --translated` on a ROM that is neither ignored nor in the listing still fails with today's "No …" error, and ignored.json is not rewritten. Test in Task 3.
- A `fill` run (`--fill-media`) on an existing translated entry keeps one suffix and the flag. Test in Task 2.
- A `replace` (re-match) of a ROM whose old entry had `"translated": true`, without `--translated` and with no tag, stays translated. Test in Task 2.
- A ROM in a subfolder (`Disc 1/Game [T-En].cue`): detection looks at the base name only. Test in Task 1.

---

### Task 1: Translation helpers

**Files:**
- Modify: `src/sync_roms/screenscraper.py` (near `_meta`)
- Test: `tests/test_screenscraper.py`

**Interfaces:**
- Produces: `TRANSLATED = " - Translated"`; `is_translation(rom: str) -> bool`; `mark_translated(entry: dict) -> dict` (new dict: `translated: True`, `name` + suffix when it has a name not already ending in the suffix).

- [ ] **Step 1: Write failing tests** in a new `TranslationTest` class:
  - `test_tags_detected`: each of `"Cave Noire (T).zip"`, `"X [T].zip"`, `".hack-Link (Japan) [T-En by Dothackers v1.0.2].chd"`, `"X [T+Eng].zip"`, `"X (T-En).zip"`, `"Mother 3 (English v1.3a).zip"`, `"Pokemon Card GB2 (English Fan Translation).zip"`, `"River City Girls Zero (USA) (RCG Translation, Switch).zip"`, `"Disc 1/Game [T-En].cue"` → `True`.
  - `test_lookalikes_not_detected`: `"Klax (USA, Europe) (Tengen).zip"`, `"Just in Time Translations - Say It in 6 Languages (USA) (En,Ja,Fr,De,Es,It,Zh).zip"`, `"Thracia 776 - Lil' Manster (v1.08).zip"`, `"Tetris (USA).zip"`, `"(T) Folder/Game (USA).zip"` → `False`.
  - `test_mark_adds_suffix_and_flag`: `mark_translated({"name": "Sakura Taisen", "genre": "RPG"})` == `{"name": "Sakura Taisen - Translated", "genre": "RPG", "translated": True}`.
  - `test_mark_is_idempotent`: marking the result again returns an equal dict.
  - `test_mark_without_name`: `mark_translated({"desc": "d"})` == `{"desc": "d", "translated": True}`.
  - `test_mark_does_not_change_input`.
- [ ] **Step 2:** `python -m unittest tests.test_screenscraper -k Translation` → FAIL (AttributeError).
- [ ] **Step 3: Implement.** One compiled case-insensitive regex over the base name (after the last `/`), matching only a whole `(...)`/`[...]` tag that is: `T`; `T-En…`/`T+En…` (any trailing text); `English v…`; or contains the word `Translation`. Docstrings say what counts.
- [ ] **Step 4:** Rerun → PASS; full suite passes.
- [ ] **Step 5: Commit** `feat(scrape): detect translation tags and mark translated entries`

### Task 2: Apply the rule when entries are written

**Files:**
- Modify: `src/sync_roms/scrape_online.py` — `record` (~705), `scrape_system` (~763), `run_scrape` (~826)
- Test: `tests/test_scrape_run.py`

**Interfaces:**
- Consumes: Task 1's `is_translation`, `mark_translated`.
- Produces: keyword `translated=frozenset()` (ROM paths to mark regardless of tags) on `record`, `scrape_system` and `run_scrape`; `run_scrape` passes it to `scrape_system`, which passes it to each `record` call (all four, including the one in the `except` block).

- [ ] **Step 1: Write failing tests** (use `RunBase`, `game()`, `self.put`, and read back `scrapes/gba/metadata.json`), class `TranslatedRecordTest`:
  - `test_tagged_rom_gets_suffix`: scraping `"Game (T).zip"` as game `"One"` writes `name == "One - Translated"`, `translated is True`.
  - `test_untagged_rom_unchanged`: `"Game.zip"` → `name == "One"`, no `translated` key.
  - `test_forced_translated`: `run_scrape(..., translated={"Game.zip"})` → suffix and flag.
  - `test_replace_keeps_old_flag`: existing entry `{"name": "One - Translated", "translated": True}`, re-scrape with `replace=True`, no tag, not forced → `name == "One - Translated"`, flag kept.
  - `test_fill_keeps_one_suffix`: existing translated entry, `fill=True` run on a tagged ROM → name has the suffix once.
- [ ] **Step 2:** Run them → FAIL.
- [ ] **Step 3: Implement.** In `record`, after computing `remote[rom]`, mark it when `rom in translated`, `screenscraper.is_translation(rom)`, or `old.get("translated")`. Add `translated` to the three signatures and docstrings.
- [ ] **Step 4:** Rerun → PASS; full suite passes.
- [ ] **Step 5: Commit** `feat(scrape): title translated ROMs "<name> - Translated"`

### Task 3: `scrape match --translated` (and un-ignore)

**Files:**
- Modify: `src/sync_roms/ignore.py` (beside `add`), `src/sync_roms/scrape_online.py` `match_command` (~1002), `src/sync_roms/cli.py` (argparse ~480, flag checks ~551-565, `scrape` help ~167/188), `README.md` (scrape match docs, near line 471)
- Test: `tests/test_ignore.py`, `tests/test_scrape_run.py` (`MatchReplaceTest` style), `tests/test_scrape_cli.py`

**Interfaces:**
- Produces: `ignore.remove(entries: dict[str, list[str]]) -> int` — mirror of `add` (reads storage fresh, drops the paths, drops systems left empty, writes storage and local copy, resets `_keys`), returns how many were removed. `match_command` reads `getattr(args, "translated", False)`.

- [ ] **Step 1: Write failing tests:**
  - `test_ignore.py::test_remove_drops_paths_and_empty_systems`: file `{"gb": ["a.zip"], "snes": ["b.zip", "c.zip"]}`, `remove({"gb": ["a.zip"], "snes": ["b.zip"]})` returns 2, file becomes `{"snes": ["c.zip"]}`, `is_ignored("gb/a.zip")` is False.
  - `test_ignore.py::test_remove_unknown_path_counts_zero`.
  - `test_scrape_run.py::test_match_translated_marks_entry`: `args.translated=True` on `a.zip` → entry name `"Seven - Translated"`, flag set.
  - `test_scrape_run.py::test_match_translated_unignores`: `a.zip` listed in storage's `ignored.json`; match with `translated=True` scrapes it and `ignored.json` no longer lists it.
  - `test_scrape_run.py::test_match_ignored_without_translated_still_fails`: same ignored ROM, `translated=False` → exits with the "No gba/a.zip" failure; `ignored.json` unchanged.
  - `test_scrape_run.py::test_match_translated_missing_rom_leaves_ignore_file`: ROM not in storage, `translated=True` → "No …" failure and `ignored.json` bytes unchanged.
  - `test_scrape_cli.py`: `sync-roms scrape match gba a.zip 7 --translated` reaches `match_command` with `translated=True`; `--translated` with any other command fails with exit 2 and `--translated only applies to \`scrape match\``.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** `ap.add_argument("--translated", action="store_true")` plus its only-applies check. In `match_command`, before `inventory.etags`, when translated and `ignore.is_ignored(f"{name}/{args.rom}")` and the ROM file exists in storage (`inventory.tag(f"{name}/{args.rom}") is not None`), call `ignore.remove({name: [args.rom]})` and print `🙉 Took {name}/{args.rom} off {ignore.KEY}`; the listing is read after it. Pass `translated={args.rom} if translated else frozenset()` to `run_scrape`. Add `--translated` to `rerun` when set, the `scrape` help usage line and `match` description ("--translated: the ROM is a fan translation: title '<name> - Translated'; an ignored ROM is taken off ignored.json first"), and README's scrape match section and flag table if `--skip-media` is listed there.
- [ ] **Step 4:** Rerun → PASS; full suite (incl. `test_readme`, `test_completion`) passes.
- [ ] **Step 5: Commit** `feat(scrape): add scrape match --translated`

### Task 4: Review answer `[t]ranslated`

**Files:**
- Modify: `src/sync_roms/scrape_review.py` (`PROMPT`, `_search`, `review`), `src/sync_roms/cli.py` (`review` help line ~190), `README.md` review section (~471)
- Test: `tests/test_scrape_review.py`

**Interfaces:**
- Consumes: `match_command`'s `args.translated` (Task 3).
- Produces: `_search(system, rom, client, translated=False) -> bool`, passing `translated` in its `argparse.Namespace`.

- [ ] **Step 1: Write failing tests** (pattern of `test_search_pick_scrapes_and_clears`):
  - `test_translated_search_marks_entry`: answers `t`, a search name, a pick → entry `name` ends with `" - Translated"`, `translated` True, ROM cleared from review lists.
  - `test_prompt_lists_translated`: `"[t]ranslated" in scrape_review.PROMPT`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** `PROMPT = "[i]gnore · [s]earch · [t]ranslated · [k]eep for later · [b]ack · [q]uit · [I]gnore all the rest  (k): "`; handle `t` exactly like `s` with `translated=True`. Help/README: "t search like s and scrape the pick as a fan translation".
- [ ] **Step 4:** Rerun → PASS; full suite passes.
- [ ] **Step 5: Commit** `feat(scrape): mark translations from scrape review`

### Task 5: One-off script for existing entries

**Files:**
- Create: `tools/mark_translations.py`
- Test: `tests/test_mark_translations.py`

**Interfaces:**
- Consumes: `screenscraper.is_translation`, `screenscraper.mark_translated`, `scrape_online.load_metadata`, `scrape_online.metadata_key`, `scrape_plan.dump_json`, `s3.put_text`, `store.repo_json("systems.json")`, `usersettings.apply_settings()`.
- Produces: `changes(metadata: dict) -> dict` (`{rom: new entry}` for tagged ROMs whose entry would change) and `main(argv=None) -> int`.

- [ ] **Step 1: Write failing tests** (import the module by path; `StorageDir` from `helpers`):
  - `test_changes_only_tagged_and_unmarked`: `{"A (T).zip": {"name": "A"}, "B.zip": {"name": "B"}, "C (T).zip": {"name": "C - Translated", "translated": True}}` → only `"A (T).zip"` → `{"name": "A - Translated", "translated": True}`.
  - `test_dry_run_writes_nothing`: storage `scrapes/snes/metadata.json` with a tagged entry; `main([])` prints the ROM and `old → new` title, returns 0, file bytes unchanged.
  - `test_write_updates_file`: `main(["--write"])` rewrites it with `dump_json` and the marked entry; untagged entries byte-identical in their values.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** Put the repo's `src/` on `sys.path` (`os.path.join(os.path.dirname(__file__), "..", "src")`) so it runs as `python tools/mark_translations.py` without installing; `apply_settings()`; for each system bucket in `systems.json` load metadata (skip `{}`; warn and skip a `ValueError`), print `system/rom: old → new`, and with `--write` put the file back. End with a count line. No ScreenScraper calls.
- [ ] **Step 4:** Rerun → PASS; full suite passes.
- [ ] **Step 5: Commit** `chore(tools): add one-off script to mark already scraped translations`
