# PyUI Themes on Spruce Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every PyUI-Themes theme unpacked in storage, sync a default list plus each card's current theme to spruce cards, let a sync change the list for itself with `t`, and select the card's current theme.

**Architecture:** One new module, `src/sync_roms/spruce_themes.py`, owns everything theme-specific: refreshing storage from the GitHub release, listing and previewing storage's themes, the pickers, planning a card's theme copies and removals, and writing the selected theme. `cli.py`'s sync calls it for `spruce` cards where Onion's `themes_dir` jobs are built today, and its download question gains `t`. `commands.py` gets `themes pick`, `cardedit.settings_menu` gets the current-theme entry.

**Tech Stack:** Python 3.12+, `uv`, `unittest`, the `7z` tool via `external.find_tool("7z")`, `picker.filter_list`.

**Spec:** `docs/superpowers/specs/2026-11-22-spruce-themes-design.md`

## Global Constraints

- Run everything with `uv run` (`uv run python -m unittest discover -s tests`). Code must run on Python 3.12.
- Every test module imports `isolate` first (directly or through `helpers`). Never touch real storage, `~/.sync-roms` or `~/.aws`. Never put test files in storage.
- Storage access goes through `s3.py`, `inventory.py`, `shared.py`; catch `s3.ERRORS`; ask only `inventory.py` what storage holds; call `s3.check_root()` before treating a missing file as absent.
- Personal files go through `store.write_json` / `usersettings.save_settings`; card fields through `store.update_card`.
- Storage paths: `os/spruceos/themes/<theme folder>/...` and `os/spruceos/themes.json`. Release: `spruceUI/PyUI-Themes`, tag `1`.
- Names: setting `spruce_themes` (sorted list of theme folder names, in `settings.json`); card fields `spruce_theme` (string) and `spruce_themes_installed` (sorted list); key `t`.
- Commits use Conventional Commits, lowercase, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never hand-edit `__version__`, `CHANGELOG.md`, `.release-please-manifest.json`.
- `tests/test_readme.py` must keep passing: README's Options table and Settings section follow the parsers and settings.

## Review Focus

1. A theme folder name with spaces or an apostrophe (`2CleanMini by Sheezie`, `Star_Wars_-_Miyoo_Be_With_You_by_tenlevels`): storage keys, card paths and the picker all keep it intact (Task 1 and Task 3 tests use `2CleanMini by Sheezie`).
2. A card with a theme folder that sync never installed and that isn't in the list (spruceOS's own `SPRUCE`, a Theme Garden download): never removed, never recorded (Task 3 test `test_foreign_theme_never_removed`).
3. The device's selected theme isn't in this sync's list: kept on the card (Task 3 test `test_selected_theme_kept`).
4. Storage unreachable or unmounted during `themes update` or sync planning: warn and change nothing, never read as "no themes" so nothing is removed (Task 1 `test_unmounted_root_changes_nothing`, Task 3 `test_no_storage_themes_removes_nothing`).
5. Second sync after the Art Book fds fix: `fds.png` isn't copied back (Task 3 `test_fixed_file_not_recopied`).

---

### Task 1: Themes in storage (`themes update`)

**Files:**
- Create: `src/sync_roms/spruce_themes.py`
- Modify: `src/sync_roms/runtime.py` (add `SPRUCE_THEMES_PREFIX = "os/spruceos/themes/"` and `SPRUCE_THEMES_STATE = "os/spruceos/themes.json"` beside `ESDE_THEMES_PREFIX`)
- Modify: `src/sync_roms/commands.py:1195` (`themes_update` also calls `spruce_themes.update_storage(args.dry_run)`; exit code is the max of both)
- Modify: `src/sync_roms/cli.py` (`SUBCOMMANDS["themes"]` text and `TOPICS["themes"]`: say it also refreshes the PyUI themes for spruce in `os/spruceos/themes/`)
- Test: `tests/test_spruce_themes.py`

**Interfaces:**
- Produces: `spruce_themes.REPO = "spruceUI/PyUI-Themes"`, `spruce_themes.TAG = "1"`
- Produces: `spruce_themes.update_storage(dry_run: bool = False) -> int` (exit code)
- Produces: `spruce_themes._release() -> list[dict]` (the release's assets: `name`, `size`, `updated_at`, `browser_download_url`; via `github.json(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")["assets"]`, `.7z` only)
- Produces: `spruce_themes._unpack(archive: str, out: str) -> str | None` (runs `7z x -y -bso0 -bsp0 -o<out> -- <archive>`; returns the single theme folder name when every extracted file is under `mnt/SDCARD/Themes/<one folder>/`, else None). Tests patch it.

- [ ] **Step 1: Write failing tests** in `tests/test_spruce_themes.py` (storage is a temp folder via `runtime.ROOT`, as other tests do; patch `spruce_themes._release`, `spruce_themes._download(url, path)` and `spruce_themes._unpack` to write files into `out/mnt/SDCARD/Themes/<folder>/`):
  - `test_new_asset_uploaded`: asset `2CleanMini_by_Sheezie.7z` unpacking to `2CleanMini by Sheezie/config.json` → storage has `os/spruceos/themes/2CleanMini by Sheezie/config.json`; `themes.json` == `{"2CleanMini_by_Sheezie.7z": {"updated_at": ..., "size": ..., "folder": "2CleanMini by Sheezie"}}`; returns 0.
  - `test_unchanged_asset_skipped`: same `updated_at` and `size` as `themes.json` → `_download` not called.
  - `test_changed_asset_replaces_folder`: storage has `old.png` in the folder, new archive lacks it → `old.png` gone, new files present.
  - `test_removed_asset_folder_deleted`: `themes.json` names an asset no longer released → its folder and entry gone.
  - `test_custom_folder_untouched`: `os/spruceos/themes/Mine/config.json` not in `themes.json` survives every case.
  - `test_bad_member_paths_skipped`: `_unpack` returns None → nothing uploaded for it, a warning, other assets still processed.
  - `test_dry_run_changes_nothing`: lists add/update/remove lines; storage and `themes.json` unchanged.
  - `test_no_7z_warns`: `external.find_tool` returns None → warning naming `sync-roms tools install`, returns 1, storage unchanged.
  - `test_unmounted_root_changes_nothing`: `runtime.ROOT` set to a missing folder → returns 1, nothing written.

- [ ] **Step 2: Run them, see them fail**

Run: `uv run python -m unittest tests.test_spruce_themes -v`
Expected: FAIL / ImportError (no `spruce_themes`).

- [ ] **Step 3: Implement `update_storage`** in `spruce_themes.py`. Read `themes.json` with `s3.get_text` (absent → `{}`, after `s3.check_root()`); list storage's theme files with `inventory.files(runtime.SPRUCE_THEMES_PREFIX)`; per asset to refresh, download into a `tempfile.TemporaryDirectory()`, `_unpack`, upload each file with `s3.put_file(prefix + folder + "/" + rel, path)`, delete stale keys of that folder with `s3.delete_keys`, then write `themes.json` once at the end with `s3.put_text` (sorted keys, indent 2). Skip `.DS_Store` and `._*`. Print one line per added/updated/removed theme and a total. Model the GitHub and error handling on `themeart.update_storage` (`OSError`, `http.client.HTTPException`, `s3.ERRORS`).

- [ ] **Step 4: Run tests, see them pass**

Run: `uv run python -m unittest tests.test_spruce_themes -v`
Expected: PASS.

- [ ] **Step 5: Wire `themes_update`**, update the help text, run the full suite (`uv run python -m unittest discover -s tests`, expected OK), commit:

```bash
git add src/sync_roms/spruce_themes.py src/sync_roms/runtime.py src/sync_roms/commands.py src/sync_roms/cli.py tests/test_spruce_themes.py
git commit -m "feat(spruce): keep pyui themes unpacked in storage"
```

### Task 2: Default list and pickers (`themes pick`)

**Files:**
- Modify: `src/sync_roms/spruce_themes.py`
- Modify: `src/sync_roms/commands.py` (`themes pick` parser beside `update`, `words["themes"] = ["update", "pick"]`, function `themes_pick(args)`)
- Modify: `src/sync_roms/cli.py` (`SUBCOMMANDS`/`TOPICS["themes"]` lines for `themes pick`)
- Modify: `src/sync_roms/usersettings.py` (the settings docstring lists `spruce_themes`)
- Modify: `README.md` (themes command, Settings section entry for `spruce_themes`)
- Test: `tests/test_spruce_themes.py`

**Interfaces:**
- Consumes: Task 1's prefix constants.
- Produces: `spruce_themes.available() -> list[str]` (theme folder names in storage, case-insensitively sorted, from `inventory.files(runtime.SPRUCE_THEMES_PREFIX, sizes=False)`; a folder counts when it has a `config.json`)
- Produces: `spruce_themes.preview(name: str) -> str | None` (local path of `<prefix><name>/preview.png`, downloaded once to `store.cache_dir()/previews/<key>` like `previews._download`; None when storage has none or on `s3.ERRORS`)
- Produces: `spruce_themes.default_list() -> list[str]` (settings' `spruce_themes`, or `[]`)
- Produces: `spruce_themes.pick(title: str, chosen: list[str], locked: str | None = None) -> list[str] | None` (multi `picker.filter_list` over `available()` plus any `chosen` names storage lacks shown dim at the end, `preview=`, `locked` row always on; None on Esc)
- Produces: `spruce_themes.pick_one(title: str, current: str | None) -> str | None | False` (single `filter_list`, first row "None (no current theme)"; returns the name, None for that row, False on Esc)

- [ ] **Step 1: Write failing tests**:
  - `test_available_lists_theme_folders`: storage with `os/spruceos/themes/B/config.json`, `a/config.json`, `x/readme.txt` → `["a", "B"]`.
  - `test_themes_pick_saves_sorted_list`: patch `picker.filter_list` to return `[True, False, True]` over `["a", "B", "c"]` → `usersettings.load_settings()["spruce_themes"] == ["a", "c"]`.
  - `test_themes_pick_esc_saves_nothing`: `filter_list` returns None → setting unchanged.
  - `test_pick_keeps_missing_names`: chosen `["gone"]` not in storage → appears as a row, on.
  - `test_preview_none_without_png`.

- [ ] **Step 2: Run, see them fail** (`uv run python -m unittest tests.test_spruce_themes -v`).

- [ ] **Step 3: Implement** the functions above and `commands.themes_pick(args)`: `usersettings.ensure_bucket()`, `ui.require_terminal("pick themes", "a terminal")`, then `pick("🎨 Spruce themes synced by default", default_list())`; on a list, save it sorted into settings with `usersettings.save_settings` and print how many are on.

- [ ] **Step 4: Run tests and `tests/test_readme.py`, see them pass.**

- [ ] **Step 5: Commit** `feat(spruce): pick the default theme list`.

### Task 3: Planning a card's themes and selecting the current one

**Files:**
- Modify: `src/sync_roms/spruce_themes.py`
- Modify: `src/sync_roms/spruce_fixes/__init__.py` (add `keeps(path) -> bool`), `src/sync_roms/spruce_fixes/fds.py` (add `keeps(path) -> bool`), `src/sync_roms/spruce_fixes/pokemini.py` (`keeps` returning False)
- Test: `tests/test_spruce_themes.py`, `tests/test_spruce_fixes.py`

**Interfaces:**
- Consumes: `available()`, prefixes.
- Produces: `spruce_themes.wanted(card: str, names: list[str]) -> list[str]` (names plus the card's `spruce_theme`, limited to `available()`; prints a dim note per name storage lacks, a warning when it's the current theme)
- Produces: `spruce_themes.plan(card: str, base: str, names: list[str], keep: bool) -> dict` with keys `jobs` (`[(key, path, size)]` for every file of each wanted theme into `base/Themes/<folder>/`, built with `downloads.add_job`), `remove` (folder names to delete), `installed` (the new `spruce_themes_installed` list)
- Produces: `spruce_themes.todo(jobs) -> list` (like `downloads.plan_downloads`, except: a job whose card file `spruce_fixes.keeps(path)` is dropped; a `config*.json` job is kept unless the card file's bytes equal storage's, read with `s3.get_text`)
- Produces: `spruce_themes.remove(base: str, names: list[str], dry_run: bool) -> int` (deletes `Themes/<name>/` trees; failure count)
- Produces: `spruce_themes.selected(base: str) -> set[str]` (the `"theme"` values in `Saves/*-system.json` that parse)
- Produces: `spruce_themes.select(card: str, base: str, dry_run: bool) -> int` (sets `"theme"` to the card's `spruce_theme` in every `Saves/*-system.json`; failure count, always 0)
- Produces: `spruce_fixes.keeps(path: str) -> bool` (any fix's `keeps`); `fds.keeps(path)` is True when `path` is `Themes/<one of THEMES>/icons/overlay/fds.png` and its bytes equal `data/themes/spruce-fds/fds.png`

Ownership rule for `plan` (from the spec): `installed` = previous `spruce_themes_installed` ∪ wanted themes whose `Themes/<folder>/` doesn't exist on the card now; `remove` = previous installed names not wanted, not in `selected(base)`, not the card's `spruce_theme`, and none at all when `keep` or when `available()` is empty; `installed` drops removed names (and keeps them with `keep`).

- [ ] **Step 1: Write failing tests** (card is a temp folder; `cards.json` through `store.update_card`):
  - `test_plan_list_plus_current`: names `["A"]`, card `spruce_theme` `"B"` → jobs cover A's and B's files under `Themes/A/`, `Themes/B/`.
  - `test_new_theme_recorded`: card lacks `Themes/A/` → `installed == ["A"]`.
  - `test_foreign_theme_never_removed`: card has `Themes/SPRUCE/`, not installed by sync, not wanted → not in `remove` or `installed`.
  - `test_unwanted_installed_removed`: installed `["A", "C"]`, wanted `["A"]` → `remove == ["C"]`, `installed == ["A"]`.
  - `test_no_delete_keeps`: same with `keep=True` → `remove == []`, `installed == ["A", "C"]`.
  - `test_selected_theme_kept`: `Saves/flip-system.json` `{"theme": "C"}` → C not removed.
  - `test_no_storage_themes_removes_nothing`: `available()` empty → `remove == []`.
  - `test_config_compared_by_content`: card `config.json` same size, different bytes → in `todo`; identical → not.
  - `test_fixed_file_not_recopied`: card `Themes/ART_BOOK_NEXT/icons/overlay/fds.png` equals the fix image → its job dropped by `todo`.
  - `test_select_sets_theme_keeps_keys`: `Saves/miyoo-mini-system.json` `{"theme": "X", "vol": 5}` → `{"theme": "B", "vol": 5}`, indent kept.
  - `test_select_missing_file_warns`, `test_select_malformed_skipped`, `test_select_dry_run_writes_nothing`, `test_select_without_current_does_nothing`.
  - In `tests/test_spruce_fixes.py`: `test_fds_keeps_only_fixed_file`.

- [ ] **Step 2: Run, see them fail.**

- [ ] **Step 3: Implement.** `select` follows `spruce_settings.install`'s read/parse/indent/write shape (`cardfs.text`, `json.loads`, `spruce_settings._indent`, `cardfs.write_text`), printing `🎨 Spruce theme → <name> (<n> file(s))`.

- [ ] **Step 4: Run tests, see them pass** (`uv run python -m unittest tests.test_spruce_themes tests.test_spruce_fixes -v`).

- [ ] **Step 5: Commit** `feat(spruce): plan theme copies and select the card's theme`.

### Task 4: Sync wiring and the `t` key

**Files:**
- Modify: `src/sync_roms/cli.py` (theme jobs ~1237-1252, summary ~1311, dry run ~1456-1490, download question ~1517-1530, downloads ~1545, end of sync ~1583-1592)
- Modify: `src/sync_roms/data/cards.schema.json` (`spruce_theme` string, `spruce_themes_installed` string array, with descriptions like `boot_logos`)
- Test: `tests/test_sync_spruce_themes.py` (follow the sync tests that already drive `cli.sync` on a spruce card, e.g. in `tests/test_spruce_bootlogo.py` or the nearest sync-level test)

**Interfaces:**
- Consumes: Task 2 `default_list()`, `pick()`; Task 3 `wanted()`, `plan()`, `todo()`, `remove()`, `select()`.

Behavior (spec "Sync"):
- On `spruce`, `theme_jobs` come from `spruce_themes.plan(card, base, spruce_themes.wanted(card, names), args.no_delete)` with `names = default_list()`, and `theme_todo = spruce_themes.todo(theme_jobs)`; theme downloads go to `base` (jobs already hold full paths) instead of `base/themes_dir`. The summary shows a `🗑️  Themes to remove: N` line when `remove` is non-empty.
- The download question on spruce, with a terminal and not `ui.ASSUME_YES`, uses `ui.choose("⬇️  Download N file(s) (size)?", "ynt", "y", "t: themes for this sync")`; on a spruce card it's asked even when `todo_all` is empty (as `"Nothing to download. Continue?"` with the same letters). `t` calls `pick("🎨 Themes for this sync only", names, locked=<card's spruce_theme>)`; a list replaces `names`, re-plans the theme jobs and the totals, and asks again; Esc asks again unchanged. `settings.json` never changes here.
- Free space shown counts `remove`'s folder sizes as freed. `spruce_themes.remove` runs after the answer, before the downloads; then `store.update_card(card, spruce_themes_installed=plan["installed"])` after the theme downloads (only when it changed).
- After the theme downloads and before `spruce_fixes.run`, `spruce_themes.select(card, base, False)`. Dry run: plan with the default list, print would-copy/would-remove lines, call `select(card, base, True)`, never ask.

- [ ] **Step 1: Write failing tests**: `test_spruce_sync_copies_default_and_current`, `test_t_override_not_saved` (patch `ui.choose` to return `"t"` then `"y"`, `pick` to return `["A", "C"]` → C copied, `settings.json`'s `spruce_themes` unchanged), `test_question_asked_when_nothing_to_download`, `test_yes_uses_default_list`, `test_removal_after_answer` (answer `n` → nothing removed), `test_dry_run_never_asks`, `test_onion_themes_unchanged` (Onion's `os/onion/Themes/` path still works).

- [ ] **Step 2: Run, see them fail.**

- [ ] **Step 3: Implement** the wiring above. Keep Onion's `themes_dir` path as it is.

- [ ] **Step 4: Run the full suite** (`uv run python -m unittest discover -s tests`). Expected: OK.

- [ ] **Step 5: Commit** `feat(spruce): sync themes with a per-sync override`.

### Task 5: Card editor entry, mirror, docs

**Files:**
- Modify: `src/sync_roms/cardedit.py:378` (`settings_menu`: on a `spruce` card add `🎨 Spruce theme: <name or none>`; it calls `spruce_themes.pick_one` and saves with `store.update_card(name, spruce_theme=...)`, removing the field for None)
- Modify: `src/sync_roms/mirroring.py:13` (`mirror_wanted`: add the files of the themes in `spruce_themes.default_list()` and every card's `spruce_theme`, from `inventory.files(runtime.SPRUCE_THEMES_PREFIX)`; docstring)
- Modify: `CLAUDE.md` (storage table `os/` row; personal data `settings.json` key list; card fields table rows for `spruce_theme` and `spruce_themes_installed`; the spruce row and a bullet in "What sync puts on a card" saying what the spec's Sync section says, briefly)
- Modify: `README.md` (sync's `t` key and the card editor entry, where spruce sync behavior is described)
- Test: `tests/test_cardedit*.py` nearest the settings menu tests, `tests/test_mirroring*.py`

**Interfaces:**
- Consumes: Task 2 `pick_one`, `default_list`.

- [ ] **Step 1: Write failing tests**: `test_settings_menu_spruce_theme_entry_only_on_spruce`, `test_settings_menu_sets_and_clears_spruce_theme`, `test_mirror_wants_listed_and_current_themes`.
- [ ] **Step 2: Run, see them fail.**
- [ ] **Step 3: Implement**, then update the docs.
- [ ] **Step 4: Run the full suite.** Expected: OK.
- [ ] **Step 5: Commit** `feat(spruce): pick a card's current theme in the card editor`.

## Known limit

A spruce card with no systems to sync returns before the download question (`cli.py` "has nothing to sync"), so it gets no themes; stated in the CLAUDE.md bullet.
