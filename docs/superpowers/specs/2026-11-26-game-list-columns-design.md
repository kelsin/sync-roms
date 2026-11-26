# Game lists: Name, System, Year columns and a changeable sort

## Intent
Make sync-roms' terminal game lists work like the games table of the collections page (`data/collections-page.html`): the game's name, system and release year in their own columns, sorted by year by default, with the sort changeable. Today a game list's row is one label (`System — Title`, or just the title in a one-system list) plus unlabelled extras columns, and each caller sorts its rows its own way.

## Goals
1. **Every game list** (rows that are games: a storage key, or a save's game) shows the columns **Name, System, Year**, in that display order, whether it lists one system or many. Existing extras columns (language, variant mark, size, tag emoji, ...) follow them, as today.
2. Default sort: **Year → Name → System**. Games with no known year sort last, in either direction.
3. The sort can be changed in every list that has sortable columns (game lists and any other `filter_list` whose caller names its columns), the same way everywhere.
4. A header line names the columns and marks the sort column (`▲` normal, `▼` reversed), like the page.

## Non-goals / anti-goals
- No new data in storage or the repo; the year comes only from scraped `metadata.json` (`releasedate`).
- The sort is never saved to `settings.json` and never changes what a list contains, only its order.
- Not a rewrite of the lists: rows, toggles, links, notes, tag filter, previews, `carry_place` all behave as now.
- Anti-goal: the cursor jumping to another game when the sort changes or years arrive; the highlighted game stays highlighted.
- Anti-goal: a list that waits on metadata before it opens.

## Constraints
- Storage reads through `s3`/`inventory`/`shared` as usual (CLAUDE.md "Reading and writing storage"); works with a bucket or a folder.
- Python 3.12+, `uv`, tests import `isolate` first; `tools/run_tests.py` passes.
- README tables/help are checked by `tests/test_readme.py` if any help text changes.

## Approaches considered
1. **Sorting and columns built into `picker.filter_list` (chosen).** A caller passes its columns (header, per-row cell, per-row sort value); the list draws the header, sorts the shown rows itself and keeps the cursor on the same row. One implementation, every list gets it the same way.
2. Each caller re-sorts and reopens the list on a sort hotkey: duplicated in ~6 places, extra work to keep place and toggles, works against "the same everywhere".
3. A helper for game lists only (in `edit.py`): other columned lists wouldn't get sorting.

## Design

### Columns in `filter_list`
- New optional argument (name is the builder's): the list's columns, each a header, and per row the cell `(text, color)` and a sort value (or None for unknown: sorts last both ways). Unsortable columns (e.g. the tag emoji) have no sort values.
- The **Name** column is the row's label (what `/` searches and what is cut with "…" when room is short); System and Year are columns after it, then the caller's extras. Rows are aligned as the extras are today (`extras_widths`, `fit_row`), and the header line uses the same widths.
- Sorting is applied in `_ListModel.update` to `vis`, after filtering, before the existing "revealed rows go last" grouping. The model's row indexes stay the caller's indexes (states, links, hidden, locked, session `row`/`visible` unchanged in meaning), so callers don't change how they read results. `picker.on_screen` returns rows in on-screen (sorted) order.
- Ties: the remaining columns in default order (Name, then System, then Year), then the caller's original order — the page's tie rule.
- Name sorts with `store.sort_key`; System by the system's displayed short name, case-insensitive; Year as a 4-digit string.

### Changing the sort
- **`o`** (order), in every list with sortable columns: opens a small single-select list of the sortable columns, the current first one marked. Picking a column makes it the first sort column; the others follow in default order (Name, System, Year, then the caller's sortable extras). Esc leaves it unchanged.
- **`O`**: reverses the whole current order (every key, ties included) without changing which column is first; again puts it back. Unknown values (no year, no size) still sort last.
- The header marks the first sort column with `▲` (normal) or `▼` (reversed).
- **The multi-select view toggle (all / on only / changed only) moves from `o`/Ctrl-O to `V`**; Ctrl-O is dropped. `?` help, hint lines, docstrings (`filter_list`'s), README and tests that name `o` as the view key are updated.
- Both keys are listed in `?` help and in the hint line of lists that have them.
- The sort is remembered for the rest of the run, process-wide for game lists (like `tagui.FILTER`), so every game list opens in the order last chosen. Non-game lists with columns keep their own sort per list kind for the run (builder decides the keying).

### Year
- Year rule as `metafilter.values`: the first 4-digit year in the entry's `releasedate`; "unknown"/empty → no year, shown as `—` (dim).
- Source: each listed system's `scrapes/<system>/metadata.json`. Loaded without blocking: the list opens at once with `—`, and years fill in (via `poll`) as each system's file arrives; when they arrive the list re-sorts with the cursor kept on its game. `cardedit.Metadata` already does a background, per-session-cached load of this file; reuse or generalise it rather than adding a second loader. A cached copy across runs (like `names.py`'s `cache/names.json` with the storage tag) is the builder's call if first-open speed needs it.
- Saves lists (`saves stash`, `saves apply`, `saves manage`) know a game only as `(system, stem)`: their year is the metadata entry whose ROM path's stem matches, when exactly one does; else `—`.

### Lists that change
Every list whose rows are games, including (builder to confirm by grep):
- `edit._toggle_games` (system lists, collection lists, tag lists, all-systems lists via `listedit`, tag editor games, `tags suggest` review),
- `cardedit._games_pass` (card editor, one system and all games), the variants list (`cardedit` "Variants of …"),
- `surprise` keep/replace list,
- `saves.pick_stash` (games list), `saves.pick_apply`, `saves_manage` game rows.

The callers stop baking the system into the label (`f"{s['name']} — {title}"`) and stop pre-sorting for display; `⚠️ not in storage` and the `title — path` form for arcade sets stay part of the Name cell. In `tags suggest` the suggested tag becomes its own column (sortable) instead of a label prefix.

### Headers, search and the shared sort
- Every column gets a header (short: `Name`, `System`, `Year`, `Lang`, `Size`, `Files`, `Tags`, ...); a column with no header text is allowed for marks.
- Sortable columns: Name, System, Year, and any extras column with a natural order: size (card editor, surprise, saves), dates and counts (saves lists), the suggested tag (`tags suggest`). Marks, notes and the tag emoji aren't sortable.
- Late values (card editor sizes while `SIZING`, years while loading) re-sort the same way when they arrive, cursor kept.
- The run-wide game-list sort is one (column id, direction). A list that lacks that column uses the default Year → Name → System, without forgetting the user's choice for lists that have it.
- `/` matches the Name and the System cells (as today, where the system was part of the label), not the year or other columns.

### Non-game lists with columns
The rule is "every list with columns you can sort by". Lists converted now: the tag editor's tag list (`tageditor`: name, game count; its own `o` sort (name / game count, by reopening) is replaced by the shared `o`/`O`, and `➕ New tag` stays the last row whatever the sort), the saves file lists (`saves stash` files, `saves manage` files), and the card list in `edit` where it has columns. Rows that are actions (`➕ New …`, "Add games", "Settings") are pinned in place and never sorted.

### Variants list
Name is the variant's title (`names.title` of its key); the variant note becomes its own column; the on-card ✅/⬜ becomes a mark column, not part of the Name.

## Left to the builder
- Argument and helper names; where the shared year loader lives.
- Whether the sort menu shows only sortable columns or all with the rest dimmed.
- Keying of the run-wide sort for non-game lists.

## Calls made (not discussed with the user)
- Approach 1 (user's pick); `o` sorts, `O` reverses, view toggle on `V` (user's pick); sort remembered for the run only.
- Default sort applies to `tags suggest` too (it was grouped by tag); the tag column lets the user group it again.
- `/` keeps matching the system; sortable extras and the fallback rule above; the variants list's Name is the title.
- PortMaster catalogue search (`ports search`) isn't a storage game list and is left as is.
