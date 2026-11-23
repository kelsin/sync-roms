# Custom spruce themes: build and publish: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms themes build` and `sync-roms themes publish` build the user's custom PyUI themes (Pixel Consoles, Pixel Controllers, more later) from the base theme in storage and publish them to `os/spruceos/themes/<folder>/`.

**Architecture:** The sprite/theme generator moves from `tools/` into the package as `sync_roms.custom_themes`, with a registry of theme modules. `build` fetches the base theme from storage into the cache and builds each theme into the cache. `publish` hashes the build, diffs it against a manifest in storage (`os/spruceos/custom-themes.json`, through `shared.py`), uploads changed files with `upload.run_uploads`, deletes stale files, and updates the manifest.

**Tech Stack:** Python 3.12+, Pillow (already a runtime dependency), unittest (`helpers.StorageDir` for a folder storage), `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-23-custom-spruce-themes-design.md`

## Global Constraints

- Always `uv run python ...`; tests: `uv run python -m unittest discover -s tests`; code must run on Python 3.12.
- Storage code goes through `s3.py`, `inventory.py`, `shared.py`; catch `s3.ERRORS`; call `s3.check_root()` before treating a missing file as absent; never put test or backup files in the real storage.
- Conventional Commits (`feat(themes): ...`), imperative, lowercase; every commit ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- A test module importing `sync_roms` imports `isolate` first (through `helpers`).
- A new command needs `cli.SUBCOMMANDS`/`cli.TOPICS` text, `commands.second_words`, the README Options table (checked by `tests/test_readme.py`) and the CLAUDE.md storage table.
- No theme data, built output or real game lists in the repo. Built themes live in `store.cache_dir()` and in storage.
- Never overwrite or delete a theme folder named in `themes.json`; custom folder names are reserved for the registry (adopted on first publish).
- Stale-file deletion only inside `os/spruceos/themes/<NAME>/` (trailing slash, so `Pixel Consoles 2/` is never matched by `Pixel Consoles`).

## Review Focus

- A share that isn't mounted must not read as an empty theme folder (publish would upload everything, or delete nothing and claim success): `s3.check_root()` first; test it.
- Base theme missing from storage: stop with a message naming `themes update`, change nothing.
- A registered name that equals a folder in `themes.json`: skipped with exit 1, files untouched.
- Interrupted or partly failed upload: the manifest keeps the old entry for files that didn't upload, so the next publish retries them.
- Theme names with spaces and a prefix-sharing sibling folder: only the exact folder is read, uploaded to or cleaned.
- A rebuild with nothing changed uploads nothing and deletes nothing; `--dry-run` writes nothing anywhere (storage, manifest, cache build folders excepted).

## File Structure

- `src/sync_roms/custom_themes/__init__.py`: registry and the public API (`THEMES`, `names()`, `fetch_base`, `build`, `plan_publish`, `publish`).
- `src/sync_roms/custom_themes/pixel/`: moved from `tools/pixel_theme/` (`sprite.py`, `menu.py`, `handhelds.py`, `nintendo_sega.py`, `others.py`, `arcade.py`, `variants.py`, `extras.py`, `app_icons.py`, `ui_settings.py`, `ui_status.py`, `ids.py`) plus `build.py` (the generator logic from `tools/gen_pixel_theme.py`).
- `src/sync_roms/custom_themes/pixel_consoles.py`, `pixel_controllers.py`: theme modules (`NAME`, `BASE`, `build(base_dir, out_dir)`).
- `src/sync_roms/custom_themes/manifest.py`: manifest read/update through `shared.py`, file hashing.
- `tests/test_custom_themes.py`: all tests for the feature.
- Modify: `src/sync_roms/commands.py` (parsers, handlers, `second_words`), `src/sync_roms/cli.py` (`SUBCOMMANDS`/`TOPICS` text for `themes`), `src/sync_roms/runtime.py` (`CUSTOM_THEMES_STATE`), `README.md`, `CLAUDE.md`.
- Delete: `tools/gen_pixel_theme.py`, `tools/pixel_theme/`.

---

### Task 1: Move the generator into the package and add the registry

**Files:**
- Move: `tools/pixel_theme/*` to `src/sync_roms/custom_themes/pixel/` (use `git mv`); delete `tools/gen_pixel_theme.py` after porting it.
- Create: `src/sync_roms/custom_themes/__init__.py`, `pixel/build.py`, `pixel_consoles.py`, `pixel_controllers.py`
- Test: `tests/test_custom_themes.py`

**Interfaces:**
- Produces: `custom_themes.THEMES: dict[str, module]` keyed by theme name (`"Pixel Consoles"`, `"Pixel Controllers"`); each module has `NAME: str`, `BASE: str` (`"SPRUCE"`), `build(base_dir: str, out_dir: str) -> str` (writes `<out_dir>/<NAME>/` as a full copy of `base_dir` with the overlays applied; replaces an existing folder; returns that path). `custom_themes.names() -> list[str]` sorted ignoring case. `pixel.build.build_theme(base_dir, out_dir, name, kind)` where `kind` is `"CONSOLES"` or `"CONTROLLERS"`.

- [ ] **Step 1: Write failing tests** in `tests/test_custom_themes.py` class `Build`, using a helper `make_base(path)` that writes a tiny SPRUCE-like theme (a `config.json` with a `screensaver` block, `skin/background.png` 640x480 gray `(40,40,40)`, `icons/gba.png` and `icons/sel/gba.png` 120x130 transparent, `skin/ic-game-n.png`/`-f.png` and the other six menu icon files 100x140, `icons_720x540/gba.png` 134x146, one `icons/app/SSH.png` 70x70):
  - `test_registry_names`: `custom_themes.names() == ["Pixel Consoles", "Pixel Controllers"]` and each module's `BASE == "SPRUCE"`.
  - `test_build_overlays_base`: after `build`, `skin/background.png` is all `(0,0,0,255)`, `icons/sel/gba.png` is not fully transparent, `config.json` has `"name"` equal to the theme name and `screensaver.bgColor == "#000000"`, `icons_720x540/gba.png` has size `(134, 146)`, and a base file the generator doesn't touch (`config.json` keys other than name/author/description/screensaver) is unchanged.
  - `test_build_is_deterministic`: two builds into two folders give identical bytes for every file (compare sorted `{rel: sha256}`).
  - `test_icons_missing_in_base_are_skipped`: with `icons/app/SSH.png` absent from the fixture, `build` still succeeds (ICON entries whose base file doesn't exist are skipped).

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m unittest tests.test_custom_themes -v` Expected: ImportError / FAIL (package missing).

- [ ] **Step 3: Move and port.** `git mv tools/pixel_theme src/sync_roms/custom_themes/pixel`, fix imports to relative (`from .sprite import ...`), port `tools/gen_pixel_theme.py` into `pixel/build.py` as `build_theme(base_dir, out_dir, name, kind)` (same behavior as the prototype: copy base, rewrite every `config*.json` name/author/description and `screensaver.bgColor`, black backgrounds, draw menu/system/extra/app/UI icons, redo the pre-scaled `icons_<size>/skin_<size>/` copies, write `preview.png`, append the credits line). Change the icon loop so an `ICON_MODULES` entry whose base file doesn't exist is skipped. Remove the argparse `main`, the contact-sheet code and `ids.py`'s dependence on the CLI (keep `IDS` for tests). Add the two theme modules and the registry in `__init__.py`. Delete `tools/gen_pixel_theme.py`.

- [ ] **Step 4: Run tests** Run: `uv run python -m unittest tests.test_custom_themes tests.test_imports -v` Expected: PASS. Then run the full suite `uv run python -m unittest discover -s tests` Expected: OK.

- [ ] **Step 5: Commit** `feat(themes): move the pixel theme generator into the package`

---

### Task 2: Fetch the base theme and `themes build`

**Files:**
- Modify: `src/sync_roms/custom_themes/__init__.py`, `src/sync_roms/commands.py`, `src/sync_roms/cli.py`, `README.md`
- Test: `tests/test_custom_themes.py`

**Interfaces:**
- Consumes: Task 1's registry and `build`.
- Produces: `custom_themes.fetch_base(base: str) -> str` (local folder `store.cache_dir()/themes/base/<base>/`; downloads missing or size-different files of `runtime.SPRUCE_THEMES_PREFIX + base + "/"`; raises `custom_themes.BaseMissing(base)` (a `ValueError`) when storage has no such folder; calls `s3.check_root()` first). `custom_themes.build(selected: list[str] | None, out: str | None = None) -> dict[str, str]` returning `{theme name: built folder}`; builds into `store.cache_dir()/themes/build/` unless `out`; unknown names raise `KeyError`. CLI: `sync-roms themes build [THEME...] [--out DIR]` handler `commands.themes_build(args)`.

- [ ] **Step 1: Failing tests** (class `Fetch` on `helpers.StorageDir`): `test_fetch_base_copies_files` (put `os/spruceos/themes/SPRUCE/config.json` and `skin/background.png` in storage; `fetch_base("SPRUCE")` returns a folder holding both, byte-equal); `test_fetch_base_reuses_same_size` (a second call downloads nothing: patch `downloads.run_downloads` and assert not called); `test_fetch_base_missing` (raises `BaseMissing`); `test_fetch_base_unmounted` (`runtime.ROOT` set to a non-existent folder raises the same `FileNotFoundError`-based error `s3.check_root` raises, not `BaseMissing`); and `test_build_command_writes_to_out` (storage has a mini base; `commands.main(["themes", "build", "Pixel Consoles", "--out", tmp])` exits 0 and `<tmp>/Pixel Consoles/config.json` exists; an unknown name exits 2 naming the known ones).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** `fetch_base`, `BaseMissing`, `build`, `commands.themes_build` (parser: `themes build` with `names` nargs `*`, `--out`, `common(p, card=False)`; add `"build"` to `second_words()["themes"]`), and the help text in `cli.TOPICS["themes"]` plus the `SUBCOMMANDS["themes"]` summary mention. Fetch through `inventory.files(prefix, sizes=True)`, `downloads.add_job`, `downloads.plan_downloads`, `downloads.run_downloads(todo, "Base theme", "🎨", cache_folder)`. Print the built folders. `BaseMissing` is reported as `ui.fail("... run `sync-roms themes update` first", 1)`.

- [ ] **Step 4: Add the README Options table row** for `themes build` (match the existing `themes update` row format) and run `uv run python -m unittest tests.test_custom_themes tests.test_readme tests.test_commands tests.test_completion -v`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(themes): add themes build for custom spruce themes`

---

### Task 3: Manifest and the publish plan

**Files:**
- Create: `src/sync_roms/custom_themes/manifest.py`
- Modify: `src/sync_roms/runtime.py` (add `CUSTOM_THEMES_STATE = "os/spruceos/custom-themes.json"` with a one-line comment), `src/sync_roms/custom_themes/__init__.py`
- Test: `tests/test_custom_themes.py`

**Interfaces:**
- Produces:
  - `manifest.hash_tree(folder: str) -> dict[str, tuple[str, int]]` (`{rel path with "/": (sha256 hex, size)}`, skipping `.DS_Store` and `._*`).
  - `manifest.read() -> dict` (`{theme folder: {"files": {rel: [sha256, size]}}}`, `{}` when the file is missing; `s3.check_root()` first) and `manifest.update(change)` (through `shared.update`, with `change(data)` mutating the dict).
  - `custom_themes.Plan` (a dataclass): `name: str`, `adopt: bool`, `new`, `changed`, `same: list[str]` (rel paths), `stale: list[str]` (storage keys), `skipped: str | None` (reason when the folder is a downloaded theme).
  - `custom_themes.plan_publish(name: str, built: str, listing: dict[str, int], state: dict, downloaded: set[str]) -> Plan` (pure): `listing` is `inventory.files(prefix)` of `os/spruceos/themes/<name>/`... as `{key: size}`; rules: skipped if `name in downloaded`; adopt if `listing` non-empty and `name not in state`; a built file is `new` if its key isn't in `listing`; `changed` if the manifest lacks it, its hash differs, or `listing[key] != size`; else `same`; `stale` = listing keys under `<prefix><name>/` (exact trailing-slash prefix) that aren't built.

- [ ] **Step 1: Failing tests** (class `PlanPublish`, pure, no storage): new/changed/same/stale classification (a same-size file with a different hash is `changed`; a file whose listed size differs from the built size is `changed` even when the manifest hash matches); `adopt` true when the folder exists and the manifest lacks the name, with every built file `changed` (no hash) or `new`; the sibling-prefix case (`listing` also holds `os/spruceos/themes/Pixel Consoles 2/x.png`: it never appears in `stale`); a name in `downloaded` returns `skipped` and empty lists. Plus `Manifest` tests on `StorageDir`: `read()` is `{}` for a missing file; `update` creates the file and a second `update` removing a key leaves the other keys; `hash_tree` skips `.DS_Store`.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** the above. `downloaded` is the set of `folder` values from `spruce_themes._read_state().values()`.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_custom_themes -v` Expected: PASS.

- [ ] **Step 5: Commit** `feat(themes): add the custom themes manifest and publish planning`

---

### Task 4: `themes publish`, docs and final verification

**Files:**
- Modify: `src/sync_roms/custom_themes/__init__.py` (`publish`), `src/sync_roms/commands.py`, `src/sync_roms/cli.py`, `README.md`, `CLAUDE.md`
- Test: `tests/test_custom_themes.py`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: `custom_themes.publish(selected: list[str] | None, dry_run: bool = False) -> int` (exit code); CLI `sync-roms themes publish [THEME...] [-n/--dry-run] [-y/--yes]` (`commands.themes_publish`).

- [ ] **Step 1: Failing tests** (class `Publish` on `StorageDir`, mini base in storage under `os/spruceos/themes/SPRUCE/`, `ui.ASSUME_YES` patched true where a confirm is reached): 
  - `test_first_publish_uploads_and_writes_manifest`: both themes' files exist in storage afterwards, `os/spruceos/custom-themes.json` lists each theme's files with their hashes, exit code 0.
  - `test_second_publish_uploads_nothing`: patch `upload.run_uploads` with a recorder; the second run calls it zero times and prints nothing-to-upload.
  - `test_changed_file_uploads_only_that_file`: modify one built source (patch a draw function) and assert exactly that key is in the jobs.
  - `test_stale_files_deleted_and_manifest_updated`: put an extra `os/spruceos/themes/Pixel Consoles/old.png` in storage; after publish it is gone, and a sibling `Pixel Consoles 2/old.png` is untouched.
  - `test_adopts_existing_unmanifested_folder`: pre-existing folder with an extra file is adopted (extra deleted, all files uploaded).
  - `test_downloaded_theme_name_is_skipped`: `themes.json` state names the folder; its files are untouched and the exit code is 1.
  - `test_dry_run_writes_nothing`: storage and manifest byte-identical before and after.
  - `test_failed_upload_keeps_old_manifest_entry`: `run_uploads` patched to return 1 and to fail one key; that file's manifest entry is its previous value (or absent), the others updated, exit code 1.
  - `test_base_missing_changes_nothing`: no base in storage exits 1 with storage unchanged.
  - `test_unmounted_share`: `runtime.ROOT` pointing at a missing folder exits non-zero without writing.
  - `test_interrupt_leaves_manifest_consistent`: `run_uploads` patched to raise `KeyboardInterrupt`; the manifest is not updated for uncompleted files and the error propagates.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** `publish`: `s3.check_root()`; fetch base(s) and build (as `build`); for each theme list storage with `inventory.files(prefix + name + "/")` (and `inventory.uncached` on the stale candidates before deleting, as the rest of sync-roms does); `plan_publish`; print per-theme counts and sizes like `upload.upload_command` (new, changed, same, stale, "adopting existing folder"); `dry_run` stops there; `ui.confirm(...)` (default False) unless `--yes` (the stale deletions are part of this confirm and the first few are listed); claim the folder in the manifest before the first upload (`manifest.update`); `upload.run_uploads(jobs)` with jobs `(key, path, size)`; then `s3.delete_keys(stale)` and a single `manifest.update` recording hashes for the files that uploaded (or were `same`) and dropping removed ones; run_uploads returns the failure count, and the set of failed keys is derived by re-checking `inventory.files` after the upload. Return 1 if any failure or any skipped theme.
  Add the `themes publish` parser (`names` nargs `*`, `common(p, card=False)`), handler, `second_words` entry, `cli.TOPICS["themes"]` text (what build/publish do, adoption, stale deletion, ownership rule), and `SUBCOMMANDS["themes"]` summary.

- [ ] **Step 4: Docs.** README Options table row for `themes publish` and a short paragraph under the Spruce themes section (custom themes: where defined, build then publish, delete of stale files, adoption). CLAUDE.md: a storage-table row for `custom-themes.json` (holds `{folder: {"files": {rel: [sha256, size]}}}`; written by `themes publish`), and a short "Custom themes" note under Repo data/What sync puts on a card that custom themes are code in `src/sync_roms/custom_themes/`, built from the base theme in storage and published by `themes publish`, with `themes pick` and sync treating them like any other theme.

- [ ] **Step 5: Verify.** Run the full suite `uv run python -m unittest discover -s tests` Expected: OK. Then a manual dry run against the real storage is the user's call, not part of this plan.

- [ ] **Step 6: Commit** `feat(themes): add themes publish for custom spruce themes`
