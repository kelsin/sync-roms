# Language Flags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show on every editor game row a flag saying whether the game plays in English (🇺🇸) or in which language.

**Architecture:** A new `src/sync_roms/languages.py` takes over the region and language tag parsing from `surprise.py` and adds `flag(key)` and a `column(key)` picker part. Surprise and the editors (`cardedit`, `edit.toggle_games`, `setedit`) use it.

**Tech Stack:** Python 3.12+, unittest, the project's `picker.filter_list` `extras`.

**Spec:** `docs/superpowers/specs/2026-11-24-language-flags-design.md`

## Global Constraints

- Run everything through `uv run` (`uv run python -m unittest discover -s tests`). The code must run on Python 3.12.
- A test module importing `sync_roms` imports `isolate` first (see `tests/test_surprise.py`).
- Conventional Commits, lowercase and imperative. End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Surgical changes: touch only what the task needs.

## Review Focus

- Tags with mixed parts, like `(World, set 1)` or `(Rev 1)`, aren't regions. They must give no flag, not a wrong one (Task 1: `test_flag_unrecognised_groups_blank`).
- Arcade keys (`mame/`, `fbneo/`) have no tags in the file name. The flag comes from the scraped title, as Surprise judges them (Task 1: `test_flag_arcade_uses_scraped_title`).
- A ROM with no tag at all stays a Surprise candidate (the existing `IN` list has `VitaShell.vpk` and `Homebrew Game (2019).zip`).
- Rows with no flag must still line up: the column part is `("", "dim")`, never a missing part (Task 2: `test_row_extras_flag_column`).
- `[T-En …]` beats a Japanese language tag: `Game (Japan) (Ja) [T-En by X]` is English (Task 1: `test_english_translation`).

---

### Task 1: `languages.py`, with Surprise using it

**Files:**
- Create: `src/sync_roms/languages.py`
- Modify: `src/sync_roms/surprise.py` (the `ENGLISH_REGIONS`, `REGIONS` and `LANGUAGE` definitions at lines 19-32, `_paren_groups`/`_english` at lines 134-147, and `is_candidate`)
- Test: `tests/test_languages.py` (new), `tests/test_surprise.py`

**Interfaces:**
- Produces:
  - `languages.ENGLISH_REGIONS`, `languages.REGIONS` and `languages.LANGUAGE`, moved verbatim.
  - `languages.ARCADE = ("mame", "fbneo")`, moved from surprise. Surprise keeps its name as `ARCADE = languages.ARCADE` because other code may use `surprise.ARCADE`: grep before removing it.
  - `languages.paren_groups(name) -> list[list[str]]`, which is `_paren_groups` renamed.
  - `languages.stem(key) -> str`: `names.title(key)` when the key's top folder is in `ARCADE`, else the base name without its extension.
  - `languages.english(name) -> bool | None`:
    - True when a `[T-En` tag (case-insensitive) is in the name.
    - Otherwise the first all-language group decides (`En` or `En-*` means True).
    - Otherwise the first all-region group decides (whether any part is in `ENGLISH_REGIONS`).
    - Otherwise None.
  - `languages.flag(key) -> str`, decided on `stem(key)`:
    - `"🇺🇸"` when `english` is True.
    - When it's False: the flag of the first part of the deciding group with a map entry, skipping `En`. A language group reads `LANGUAGE_FLAGS` (keyed by the two-letter code before any `-`); a region group reads `REGION_FLAGS`.
    - `""` when `english` is None or nothing is mapped.
  - `languages.column(key) -> tuple[str, str]`: `("  " + f, "dim")` when there's a flag, else `("", "dim")`.
  - `LANGUAGE_FLAGS` covers at least `Ja 🇯🇵, Fr 🇫🇷, De 🇩🇪, Es 🇪🇸, It 🇮🇹, Nl 🇳🇱, Pt 🇵🇹, Sv 🇸🇪, Da 🇩🇰, No 🇳🇴, Fi 🇫🇮, Pl 🇵🇱, Ru 🇷🇺, Ko 🇰🇷, Zh 🇨🇳`.
  - `REGION_FLAGS` covers every non-English name in `REGIONS`: each country to its flag, `Asia` and other multi-country regions to 🌏, `Latin America` to 🌎, `Scandinavia` to 🇸🇪. `Unknown` has no entry.
  - Keep `names` imported inside the functions that use it if a top-level import turns out circular.

- [ ] **Step 1: Write `tests/test_languages.py`** with these tests:
  - `test_english_language_tag`:
    - `english("Golden Sun (Europe) (En,Fr,De)")` is True.
    - `english("Super Mario Bros. (Europe) (Fr,De)")` is False, so the language group beats the region.
  - `test_english_region`: `english("Mother 3 (Japan)")` is False, `english("Lemmings (UK)")` is True, `english("Homebrew Game (2019)")` is None.
  - `test_english_translation`: `english("Mother 3 (Japan) [T-En by Chewy v1.3]")` is True, and so is `english("Game (Japan) (Ja) [T-En by X]")`.
  - `test_flag`:
    - `flag("gba/Mother 3 (Japan).zip")` is `"🇯🇵"`.
    - `flag("gba/Golden Sun (Europe) (En,Fr,De).zip")` is `"🇺🇸"`.
    - `flag("gba/Super Mario Bros. (Europe) (Fr,De).zip")` is `"🇫🇷"`.
    - `flag("gba/Game (Japan, Korea).zip")` is `"🇯🇵"`.
    - `flag("gba/Mother 3 (Japan) [T-En by Chewy].zip")` is `"🇺🇸"`.
  - `test_flag_unrecognised_groups_blank`: `flag("gba/Tetris (Rev 1).zip")`, `flag("gba/VitaShell.vpk")` and `flag("gba/Game (Unknown).zip")` are all `""`.
  - `test_flag_arcade_uses_scraped_title`: patch `languages.names.title` to return `"Armed F (Japan)"`. Then `flag("mame/armedf.zip")` is `"🇯🇵"`, and with `"10-Yard Fight (World, set 1)"` it's `""`.
  - `test_column`: `column("gba/Mother 3 (Japan).zip")` is `("  🇯🇵", "dim")`, and `column("gba/VitaShell.vpk")` is `("", "dim")`.
  - `test_every_flag_mapped_region_is_a_region`: every key of `REGION_FLAGS` is in `REGIONS`.
- [ ] **Step 2: Add `test_translations_are_candidates`** to `SurpriseRulesTest` in `tests/test_surprise.py`: `surprise.is_candidate("gba/Mother 3 (Japan) [T-En by Chewy v1.3].zip", GBA, set())` is True.
- [ ] **Step 3: Check that they fail.** Run `uv run python -m unittest tests.test_languages tests.test_surprise </dev/null`. Expected: an ImportError for `languages`, and the new Surprise test fails.
- [ ] **Step 4: Write `languages.py`.** In `surprise.py`:
  - Delete the moved constants and the two functions, and import `languages`.
  - `is_candidate` uses `languages.stem(key)` for `stem` and `languages.paren_groups`, and returns `languages.english(stem) is not False`.
  - Grep `src` and `tests` for `surprise.REGIONS`, `ENGLISH_REGIONS`, `LANGUAGE` and `ARCADE`, and repoint any users.
- [ ] **Step 5: Run the whole suite.** Run `uv run python -m unittest discover -s tests </dev/null`. Expected: OK.
- [ ] **Step 6: Commit** with the message `refactor: share rom language tag parsing in languages.py` (and a body noting that Surprise now counts `[T-En]` ROMs).

### Task 2: The flag column in the editors

**Files:**
- Modify: `src/sync_roms/cardedit.py:788-804` (`_row_extras`)
- Modify: `src/sync_roms/edit.py` (the `picker.filter_list` call in `toggle_games`)
- Modify: `src/sync_roms/setedit.py:63-83` (the category and series blocks)
- Test: `tests/test_languages.py`, plus the existing editor tests (`tests/test_sets.py`, `tests/test_collectionedit.py`, `tests/test_list_previews.py`)

**Interfaces:**
- Consumes: `languages.column(key) -> tuple[str, str]` from Task 1.
- Produces:
  - `_row_extras` returns five parts: files, set note, lock, **flag**, size.
  - `edit.toggle_games` passes `extras=[[languages.column(key)] for _, key, _, _ in rows]`.
  - In `setedit`, one helper `pick_game(title, games, names) -> int | None` runs the `filter_list` the two blocks share (labels from `game_label`, `extras` from `languages.column(g["bucket"])`, `**previews.game_pane(...)`). The category and series blocks both call it.

- [ ] **Step 1: Write the failing tests.**
  - `test_row_extras_flag_column` in a new `EditorColumnsTest` class in `tests/test_languages.py`:
    - Build the smallest `sp` and `work` `_row_extras` needs (with `types.SimpleNamespace`).
    - For `"gba/Mother 3 (Japan).zip"`, `cardedit._row_extras(...)[3]` is `("  🇯🇵", "dim")`.
    - For `"gba/VitaShell.vpk"` it's `("", "dim")`, and the result has 5 parts.
  - `test_toggle_games_flag_extras`:
    - Patch `edit.picker.filter_list` to record its `extras` kwarg and return the initial state.
    - Call `edit.toggle_games` with one row for `"gba/Mother 3 (Japan).zip"`.
    - Assert that the recorded extras is `[[("  🇯🇵", "dim")]]`.
    - Follow how `tests/test_collectionedit.py` drives `toggle_games`.
  - `test_pick_game_flag_extras`: patch `setedit.picker.filter_list` the same way, and assert that `setedit.pick_game(...)` passes the flag extras and returns its index.
- [ ] **Step 2: Check that they fail.** Run `uv run python -m unittest tests.test_languages </dev/null`. Expected: the three new tests fail.
- [ ] **Step 3: Implement the interfaces above.** In `_row_extras`, the size moves to index 4: update its docstring and any reader of `out[3]` or `[3]` for the size (grep `cardedit.py` and `tests`).
- [ ] **Step 4: Run the whole suite.** Run `uv run python -m unittest discover -s tests </dev/null`. Expected: OK.
- [ ] **Step 5: Commit** with the message `feat(edit): show a language flag on game rows`.
