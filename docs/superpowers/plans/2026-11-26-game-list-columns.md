# Game list columns and sorting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every game list shows Name, System, Year columns under a header, sorted Year → Name → System by default; `o` picks the first sort column and `O` reverses the order in every list with sortable columns; the multi-select view toggle moves to `V`.

**Architecture:** `picker.filter_list` learns named columns, a shared sort object and a sort-value callback, and sorts its shown rows itself (row indexes stay the caller's). A new `gamecols.py` builds the Name/System/Year columns, cells and sort values for game rows, with years read in the background from scraped `metadata.json` through a loader moved out of `cardedit.py`. Each game list's caller then stops baking the system into its label and passes `gamecols`' arguments.

**Tech Stack:** Python 3.12+, Textual/Rich (existing), `unittest`, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-26-game-list-columns-design.md`

## Global Constraints

- Run everything with `uv run`; tests: `uv run python tools/run_tests.py` (single module: `uv run python -m unittest tests.test_x -v`). Test modules import `isolate` (directly or through `helpers`) before `sync_roms`.
- Code must run on Python 3.12.
- Display order: **Name, System, Year**, then the caller's existing extras. Default sort: **Year → Name → System**; unknown values (no year, no size) sort last in either direction.
- Keys: `o` opens the sort-column menu; `O` reverses the whole order; view toggle (all / on only / changed only) is `V`; Ctrl-O no longer does anything.
- Year: the first 4-digit year in `releasedate` (as `metafilter.values`), shown as `—` (dim) when unknown.
- Sort is remembered for the run only (module-level object), never written to `settings.json`.
- `/` matches the Name (label) and the System cell.
- Storage reads only through `s3`/`inventory`/`shared` (reading `scrape_plan.metadata_key(bucket)` with `s3.get_text`, as `cardedit.Metadata` does today).
- Conventional Commits; never edit `__version__`, `CHANGELOG.md`, `.release-please-manifest.json`.

## Review Focus

1. A list whose years arrive after it opens: the highlighted game must stay highlighted when the list re-sorts (`test_late_values_keep_cursor`, Task 1).
2. A sort column the current list lacks (user sorted by Size in the card editor, then opens a collection list): the list uses the default order, and the next list that has Size sorts by Size again (`test_missing_first_column_falls_back`, Task 1).
3. `O` with rows that have no year: they stay last, not first (`test_reverse_keeps_unknown_last`, Task 1).
4. Pinned action rows (`➕ New tag`) stay last under every sort and `O` (`test_pinned_rows_stay_last`, Task 1).
5. Narrow terminals: the header row is cut like a row, never wraps (`test_header_row_fits_width`, Task 1).

---

## File Structure

- `src/sync_roms/picker.py` — `Column`, `Sort`, `GAMES_SORT`; `filter_list`/`_ListModel` columns, sorting, `o` menu, `O`, `V`, header line, `/` on the System cell.
- `src/sync_roms/gamemeta.py` (new) — the background per-system metadata loader moved from `cardedit.py` (`Metadata`, `LOADING`, the session cache).
- `src/sync_roms/gamecols.py` (new) — Name/System/Year columns for game rows: `GameColumns`.
- Callers: `edit.py`, `listedit.py`, `tageditor.py`, `tagsuggest.py`, `cardedit.py`, `surprise.py`, `saves.py`, `saves_manage.py`.
- Docs: `README.md` (keys table line 157, tag editor paragraph line 387), `CLAUDE.md` (line 172, `o` view → `V` view).

---

### Task 1: Columns, sorting and the new keys in `picker`

**Files:**
- Modify: `src/sync_roms/picker.py` (`MULTI_HINT` line 85, `help_lines`, `_ListModel`, `_ListLines.render/row`, `filter_list` and its docstring, `on_screen` docstring)
- Test: `tests/test_picker_columns.py` (new; build models the way `tests/test_tag_summary.py` does)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Column: id: str; header: str; sortable: bool = False`
  - `class Sort: __init__(self, default: tuple[str, ...])`; attributes `first: str | None` (None = default order), `reverse: bool`; `order(self, available: list[str]) -> list[str]` = `[first] + [c for c in default if c != first and c in available] + [c for c in available if c not in default and c != first]` when `first in available`, else default order filtered to `available` then the rest of `available`.
  - `GAMES_SORT = Sort(("year", "name", "system"))` — shared by every game list.
  - `filter_list(..., columns=None, sort_value=None, sort=None, pinned=None)`:
    - `columns`: `list[Column]`; `columns[0]` describes the label, `columns[1:]` describe each row's extras parts by position (`len(columns) == 1 + len(extras[i])`).
    - `sort_value(i: int, col_id: str) -> Any | None`, called on every `update` (so late values re-sort); None = unknown.
    - `sort`: a `Sort` (default: a fresh `Sort` whose default is the sortable column ids in display order).
    - `pinned`: per-row bools; pinned rows go after all others, in caller order, under any sort.
  - The model stores `vis` sorted; every other per-row list stays indexed by the caller's index.

- [ ] **Step 1: Write the failing tests** in `tests/test_picker_columns.py`:
  - `test_default_sort_year_name_system`: rows labels `["B", "A", "C", "A"]`, systems `["snes", "gba", "nes", "nes"]`, years `["1994", "1994", None, "1990"]`; with `sort=Sort(("year","name","system"))` `vis == [3, 1, 0, 2]`.
  - `test_o_menu_sets_first_column`: `key("o")` opens the menu (`model.sort_menu` not None, listing sortable headers); moving to "Name" and `key("enter")` gives `sort.first == "name"`, order Name → Year → System; `key("escape")` in the menu leaves `sort` unchanged.
  - `test_O_reverses_all`: after `key("O")`, `vis` is the reversed order of known-value rows, `sort.reverse is True`; `key("O")` again restores it.
  - `test_reverse_keeps_unknown_last`: the row with no year is last both before and after `O`.
  - `test_late_values_keep_cursor`: cursor on label "C"; change `sort_value` results so "C"'s year becomes "1980"; `update()`; highlighted row is still index 2 and `vis[0] == 2`.
  - `test_missing_first_column_falls_back`: `Sort` with `first="size"` on a list without a size column sorts by default; `sort.first` is still `"size"` afterwards.
  - `test_pinned_rows_stay_last`: pinned last row stays last under name sort and after `O`.
  - `test_slash_matches_system_cell`: query `"snes"` shows only the snes row (System is `columns[1]`, id `"system"`).
  - `test_V_cycles_view_and_o_does_not`: multi list; `key("V")` → `view_mode == 1`; without sortable columns `key("o")` leaves `view_mode` at 0 and does nothing; `"ctrl+o"` does nothing.
  - `test_header_row_fits_width`: the header `Text` built for width 30 has `cell_len == 30` and marks the first sort column `▲` (`▼` after `O`).
  - `test_help_lists_sort_keys`: `help_lines` for a list with sortable columns includes lines for `o` and `O`, and the multi line reads `V               view: all / on / changed`.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_picker_columns -v` — Expected: FAIL (no `Column`/`Sort`).

- [ ] **Step 3: Implement in `picker.py`.**
  - Sorting in `_ListModel.update`, applied to `vis` after filtering and before the existing "revealed rows go last" grouping, unpinned rows first. Key per row: for each column id in `sort.order(available sortable ids)`, `(value is None, value)`; reversal flips the order of known values only (sort known rows with `reverse=sort.reverse` per key tuple, unknowns for the first column always after), ties then by caller index (reversed too under `O`). Name values: when `sort_value` returns None for `"name"`, use `store.sort_key(label)`.
  - Cursor: before recomputing, remember the highlighted row index; after sorting, if it is still in `vis` and nothing reset the cursor to 0 (query or view change), put the cursor on it.
  - `o` (only when some column is sortable, and not while typing/notes/prompts): opens `self.sort_menu = cursor index` over the sortable columns; j/k/arrows move, Enter sets `sort.first` (keeps `reverse`), Esc/q closes. Render the menu in `_ListLines` in place of the rows (one line per column, current first one marked `▲`/`▼`), like the help overlay but on the list screen. `poll` is skipped while it is open (as for `help`).
  - `O` toggles `sort.reverse` when some column is sortable.
  - `V` replaces `("o", "ctrl+o")` for the view toggle; update `MULTI_HINT` to `... · a all · V view · u revert` and add `o sort · O reverse` to hint lines of lists with sortable columns (append to the hint shown by `_ListHeader`), and to `help_lines` (new parameter `sortable: bool`): `"o               sort by a column"`, `"O               reverse the order"`.
  - Header: when `columns` is given, `_ListLines` draws one header line (dim, the first sort column bold with ` ▲`/` ▼` appended) above the rows and `view` shrinks by 1. Label header is indented by the 3-cell mark when rows are marked. Each extras header starts after the smallest leading-space count of that column's non-empty cells; column widths (`extras_widths`) include the header's width. Cut with `fit_row`.
  - `/`: `self.lowered[i]` is the label plus, when a column has id `"system"`, that row's System cell text (re-read on `update` is not needed; System cells don't change).
  - Docstring of `filter_list`: document the four new arguments, `o`/`O`, and `V`.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_picker_columns tests.test_tag_summary tests.test_editor_data tests.test_picker_session -v` — Expected: PASS. Fix existing tests that pressed `o` for the view so they press `V`.

- [ ] **Step 5: Commit** `feat(picker): sortable named columns, o sort, O reverse, V view`

---

### Task 2: `gamemeta` loader and `gamecols` game columns

**Files:**
- Create: `src/sync_roms/gamemeta.py` — move `LOADING`, `_metadata`, `_spawn` and `Metadata` from `cardedit.py:171-208` unchanged; `cardedit.py` imports them from there (keep the names `cardedit.Metadata`/`cardedit.LOADING` available as imports so existing tests and `GameFilters` work).
- Create: `src/sync_roms/gamecols.py`
- Test: `tests/test_gamecols.py`

**Interfaces:**
- Consumes: Task 1's `Column`, `GAMES_SORT`, `filter_list` `columns`/`sort_value`/`sort`/`poll`; `gamemeta.Metadata(bucket).get() -> index | None | LOADING` (index: `{bucket key: {field: set}}`, `"year"` among the fields).
- Produces:
  - `class GameColumns: __init__(self, rows: list[tuple[str, str, str | None]], extra_columns: list[picker.Column] = ())` — rows are `(system bucket, title, bucket key or None)`; a None key means a save's game: its year is the metadata entry whose ROM path's stem (`os.path.splitext(os.path.basename(path))[0]`) equals the title, when exactly one does.
  - `GameColumns.cells(i) -> list[tuple[str, str]]`: `[("  " + short system name, "dim"), ("  " + year or "  —", "dim")]`; the System name is `store.short_name` of the systems.json entry (the bucket itself when unknown).
  - `GameColumns.kwargs(extras: list[list[tuple[str, str]]] | None = None, poll=None) -> dict` for `filter_list`: `columns=[Column("name","Name",True), Column("system","System",True), Column("year","Year",True), *extra_columns]`, `extras` = each row's `cells(i)` + the caller's parts, `sort=picker.GAMES_SORT`, `sort_value`, and `poll` = a function that fills year cells in place as systems' metadata arrives, then calls the caller's `poll` when given. Caller sort values for extra columns: `GameColumns(..., extra_values=lambda i, col_id: ...)` (keyword, default None).
  - Sort values: `"name"` → `store.sort_key(title)`, `"system"` → short name casefolded, `"year"` → the year string or None.

- [ ] **Step 1: Write the failing tests** in `tests/test_gamecols.py` (patch `gamemeta.Metadata.get` or seed `gamemeta._metadata` with an index):
  - `test_columns_and_cells`: two rows on `snes`/`gba` with seeded years `"1994"` and none → `kwargs()["columns"]` ids `["name","system","year"]`, cells `[("  SNES"-style short name, "dim"), ("  1994","dim")]` and `("  —","dim")` for the yearless row.
  - `test_years_fill_in_on_poll`: metadata LOADING at first (cells `—`), then available → after `kwargs()["poll"]()`, the cell reads the year and `sort_value(i, "year")` returns it.
  - `test_stem_year_for_saves`: key None, title `"Chrono Trigger (USA)"`, metadata `{"snes/Chrono Trigger (USA).sfc": {year}}` → that year; two matching paths → None.
  - `test_caller_poll_and_extras_kept`: caller extras parts follow the two cells; caller poll is called.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_gamecols -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `gamemeta.py` (move) and `gamecols.py`. One `gamemeta.Metadata` per distinct system in the rows.
- [ ] **Step 4: Run** `uv run python -m unittest tests.test_gamecols tests.test_cardedit -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(editor): game list columns with release years`

---

### Task 3: The shared games toggler and its callers

**Files:**
- Modify: `src/sync_roms/edit.py` (`_toggle_games` 123-180, `system_rows` 183-196, `list_rows` 205-222), `src/sync_roms/listedit.py` (`all_rows` 297-306), `src/sync_roms/tageditor.py` (rows at 188), `src/sync_roms/tagsuggest.py` (rows at 97-106), `src/sync_roms/collectionedit.py` only if it builds labels with the system
- Test: `tests/test_edit.py`, `tests/test_tageditor.py`, `tests/test_tagsuggest.py`, `tests/test_collectionedit.py`

**Interfaces:**
- Consumes: Task 2's `GameColumns`.
- Rows stay `(system entry, bucket key, title, label)`; the label no longer starts with the system (`f"{s['name']} — "`, `f"{short_name} — "` and the tag editor's `system_names` prefix go). `system_rows` keeps `title — path` and `⚠️ not in storage`; `list_rows` keeps `⚠️ not in storage`. The system for a row is always `key.partition("/")[0]` (the tag editor's entry has bucket `""`).
- Callers keep sorting their row lists as before (it sets the caller index used for ties); display order comes from the picker.

- [ ] **Step 1: Write failing tests**:
  - `test_edit.test_toggle_games_columns`: capture `filter_list` kwargs (patch `picker.filter_list`) for a two-system list → `columns` ids start `["name","system","year"]`, labels have no system prefix, `sort is picker.GAMES_SORT`, extras rows have the two game cells then language and tag.
  - `test_tagsuggest.test_suggested_tag_column`: labels are titles; a `Column("tag","Tag",True)` is present; its sort value is the tag name casefolded.
  - Update existing assertions on labels that included `System — ` (in `test_edit`, `test_tageditor`, `test_collectionedit`, `listedit` tests).
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_edit tests.test_tageditor tests.test_tagsuggest tests.test_collectionedit -v` — Expected: FAIL.
- [ ] **Step 3: Implement**: in `_toggle_games` build `GameColumns([(key.partition('/')[0], title, key) for _, key, title, _ in rows], extra_columns=[Column("lang","Lang"), Column("tags","Tags")])` and pass `**cols.kwargs(extras)`; `toggle_games` gains `extra_columns=()`/`extra_cells=None`/`extra_values=None` passthrough used only by `tagsuggest` (tag column first among the extras).
- [ ] **Step 4: Run** the Step 2 command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(editor): name, system and year columns in the games lists`

---

### Task 4: Card editor lists

**Files:**
- Modify: `src/sync_roms/cardedit.py` (`_games_pass` 852-931, the all-games rows at 1046-1048, `_toggle_variant` 817-850)
- Test: `tests/test_cardedit.py`

**Interfaces:**
- Consumes: Task 2's `GameColumns`; Task 1's `Column`.
- `_games_pass` extras after the game cells: `files` (`Column("files","Files")`), `from` (`Column("from","")`), `lang` (`Column("lang","Lang")`), `size` (`Column("size","Size",True)`, sort value = `work["costs"][bucket][key]` bytes, None while `SIZING`), `variant` (`Column("variant","")`), `tags` (`Column("tags","Tags")`); full-system rows give blank cells. Labels lose `f"{s['name']} — "` (line 1047).
- Variants list: Name = `names.title(v["bucket"])`; the on-card mark ✅/⬜ becomes `Column("on","")` as an extras cell before the system; the note becomes `Column("note","Variant")` after the year.

- [ ] **Step 1: Write failing tests** (patch `picker.filter_list` to capture kwargs, as existing `test_cardedit` tests do):
  - `test_games_pass_columns`: ids `["name","system","year","files","from","lang","size","variant","tags"]`; size sort value is the cost in bytes, None for a row still sizing.
  - `test_all_games_labels_have_no_system`.
  - `test_variants_list_columns`: labels are titles, note cell present, `columns[0].id == "name"`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_cardedit -v` — Expected: FAIL.
- [ ] **Step 3: Implement.** Merge `GameColumns.kwargs` with `list_kw` (the caller's `hint`, `hotkeys`, ... stay).
- [ ] **Step 4: Run** the Step 2 command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(card-editor): name, system and year columns, sortable by size`

---

### Task 5: Surprise and saves lists

**Files:**
- Modify: `src/sync_roms/surprise.py` (keep list 290-298), `src/sync_roms/saves.py` (`pick_stash` 428-447, `pick_apply` 516-529 and where its labels/extras are built), `src/sync_roms/saves_manage.py` (`_columns` 225-232, the stash list 287-294, `_show_files` 244-255)
- Test: `tests/test_surprise.py`, `tests/test_saves.py`, `tests/test_saves_manage.py`

**Interfaces:**
- Consumes: Task 2's `GameColumns` (saves rows pass key None, title = the save's game stem), Task 1's `Column`/`Sort`.
- Surprise: label = title (no `(System)` suffix); extras: `Column("size","Size",True)` (sort value in bytes, from `_size_column`'s source), tags.
- `saves stash` games list: game columns + `Column("kinds","Saves")`, `Column("core","Core",True)`; the files list (not games): `columns=[Column("name","File",True), Column("kind","Kind",True), Column("size","Size",True), Column("modified","Modified",True), Column("core","Core",True)]` with its own module-level `Sort(("name",))`.
- `saves manage` stash list: game columns + card (`"from"`), stashed date (`Column("stashed","Stashed",True)`, sort value the ISO string), counts, size (sortable, bytes), core, missing, note; unreadable rows: System/Year cells blank. Its files list: as the stash files list, plus mark.
- `pick_apply`: game columns + its existing extras with headers; date and size sortable where present.

- [ ] **Step 1: Write failing tests** capturing `filter_list` kwargs: each list's column ids in the order above, labels without system, and one sort value per sortable extra (size in bytes, date ISO string).
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_surprise tests.test_saves tests.test_saves_manage -v` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the Step 2 command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(saves): name, system and year columns in the surprise and saves lists`

---

### Task 6: Tag list, docs and full run

**Files:**
- Modify: `src/sync_roms/tageditor.py` (`SORT_KEY` line 6, `_tag_list` 233-265), `README.md` (line 157 keys table: `a` `V` `u`, add a row for `o` `O`; line 387: tag editor sort sentence), `CLAUDE.md` line 172 (`o` view → `V` view)
- Test: `tests/test_tageditor.py`, `tests/test_readme.py`

**Interfaces:**
- Consumes: Task 1's `Column`, `Sort`, `pinned`.
- Tag list: `columns=[Column("name","Tag",True), Column("games","Games",True)]`, games cell = count or `no games` (dim), sort value = count; module-level `TAG_SORT = Sort(("name","games"))`; the `➕ New tag` row is `pinned`. `SORT_KEY` and the `by_count` reopen loop go.

- [ ] **Step 1: Write failing tests**: `test_tageditor.test_tag_list_columns` (ids, pinned last row, no `"o"` in hotkeys); README check passes after edits.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_tageditor tests.test_readme -v` — Expected: FAIL.
- [ ] **Step 3: Implement** and update the docs.
- [ ] **Step 4: Run** `uv run python tools/run_tests.py` — Expected: all pass. Then `grep -rn '"o", "ctrl+o"\|o view' src README.md CLAUDE.md` — Expected: no matches.
- [ ] **Step 5: Commit** `feat(tags): sortable tag list columns; document o, O and V`
