# Custom spruce themes: build and publish

## Intent

The user draws their own PyUI themes for spruce cards (first two: Pixel Consoles, Pixel Controllers; pixel-art icons on a black background, derived from the default SPRUCE theme). Today a prototype generator in `tools/` builds them into a local folder that the user copies into storage by hand. They want that to be part of sync-roms: commands that build the custom themes from the base theme in storage and publish them to storage (`os/spruceos/themes/<folder>/`), where the existing `themes pick`, card `spruce_theme` and sync copy them to cards like any other theme. More custom themes will follow, so adding one must be a small, self-contained change.

## Goals

- `sync-roms themes build [THEME...] [--out DIR]` builds the named custom themes (default: all) from the base theme in storage.
- `sync-roms themes publish [THEME...] [--dry-run] [--yes]` builds and uploads what changed, with the normal UI: a plan summary, confirmation, progress bar, Ctrl-C support, bucket and folder storage, failures reported and the exit code set.
- Publishing uploads only files whose content changed, and removes files of the custom theme's folder that a rebuild no longer produces.
- A custom theme is one module with a name, a base theme folder and a build function; a registry lists them. The two Pixel themes share their drawing code.
- Works with storage as a bucket or a folder; a missing share (`s3.check_root`) is never read as empty storage.

## Non-goals and anti-goals

- No theme data or built output in the repo or committed; only code. Built themes live in the cache and in storage.
- No changes to `themes update`, `themes pick` or sync: custom themes appear through the existing `spruce_themes.available()`.
- Never overwrite or delete a theme folder that sync-roms didn't publish itself (a downloaded PyUI-Themes theme with the same name, or a hand-made folder).
- No new layout support (only spruce cards use PyUI themes).
- Not a general theme editor.

## Constraints from the codebase

- Storage code goes through `s3.py`, `inventory.py` and `shared.py`; catch `s3.ERRORS`; confirm destructive steps; update the inventory cache for writes (`inventory.wrote`).
- Uploads go through `upload.run_uploads` (jobs of `(key, path, size)`; folder or bucket; progress bar; KeyboardInterrupt handling).
- Shared JSON in storage is read and written through `shared.py` so machines merge.
- A new command needs `cli.SUBCOMMANDS`/`TOPICS`, `commands.COMMANDS`/`second_words`, the README Options table (checked by `tests/test_readme.py`), and the CLAUDE.md storage table. Python 3.12 compatible. Pillow is already a runtime dependency.
- The generator and its sprite code currently live in `tools/` (`tools/gen_pixel_theme.py`, `tools/pixel_theme/`), which isn't in the installed package. They move to `src/sync_roms/` and `tools/gen_pixel_theme.py` is removed.

## Approaches

**Where the code lives.** Only one fits: move it into the package, because the command must import it. Not an option: shelling out to `tools/`.

**How unchanged files are detected** (user delegated this to me):

1. Compare sizes, as ROM uploads do. Rejected: a rebuilt PNG can change pixels and keep its size, and a folder share has no content hash.
2. A content-hash manifest in storage per custom theme, read and written through `shared.py`. Upload a file when its hash differs from the manifest or storage's listed size differs from the manifest's size; skip otherwise. **Chosen.** It works for folder and bucket storage and detects any content change.
3. Compare bucket ETags. Rejected: not available for a folder, and multipart ETags aren't MD5.

**Command shape.** Chosen: two commands, `build` (local, useful for previewing) and `publish` (build then upload). Rejected: one command that always uploads (no way to inspect the result first).

## Design

### Registry

`src/sync_roms/custom_themes/` package:

- `__init__.py`: `THEMES = {name: module}`; each module has `NAME` (the storage folder name, e.g. `"Pixel Consoles"`), `BASE` (the base theme folder, e.g. `"SPRUCE"`) and `build(base_dir, out_dir)` that writes the finished theme folder into `out_dir`.
- `pixel/`: the sprite code moved from `tools/pixel_theme/` (sprite toolkit, menu, handhelds, nintendo_sega, others, arcade, variants, extras, app and UI icon modules) and the generator logic (black backgrounds, per-resolution copies, preview.png, credits).
- `pixel_consoles.py`, `pixel_controllers.py`: thin modules selecting the console or controller sprites.

### Base theme

`build` needs the base theme folder as local files. `custom_themes.fetch_base(base)` lists `os/spruceos/themes/<BASE>/` through `inventory.files`, downloads files whose local copy (in `cache/themes/base/<BASE>/`) is missing or differs in size (through the same download helpers sync uses), and returns the local folder. If the base theme isn't in storage, the command stops with a message to run `themes update` (spruce's own PyUI-Themes release provides `SPRUCE`).

### How this meets the existing themes code (checked in the source)

- `spruce_themes.available()` lists the folders under `os/spruceos/themes/` that hold a `config.json`, from `inventory.files`, not from `themes.json`: custom themes appear in `themes pick` and the card editor unchanged.
- `themes update` only removes or replaces folders named in `themes.json` and raises on a same-named folder it doesn't own, so it never touches a custom folder; the registry's names must not equal a PyUI-Themes release theme's folder.
- The prototype reads the base theme from a local folder (`--base`), builds one theme per run (the two Pixel themes differ only in which system sprites and games icon they use), and writes a full copy of the base theme with the overlays applied. `build` therefore emits a complete theme folder, so "stale" means every storage file under the folder that the build didn't produce, and Pillow's PNG writer adds no timestamps (determinism is tested, not assumed).
- The manifest is updated with `shared.update(key, parse, empty, change, dump)`, whose `change` callback receives the freshly re-read manifest, so removals (stale entries, a deleted theme) are expressible.
- Before deleting stale files, list storage itself for the folder (`inventory.uncached` on candidates), as the rest of sync-roms does before removing shared state.

### Build

`themes build` fetches each needed base once, runs each theme's `build` into `cache/themes/build/<NAME>/` (replaced each run) or `--out DIR/<NAME>`, and prints the output location and counts. Output is deterministic (same inputs give identical bytes: no timestamps, fixed PNG settings) so hashes are stable.

### Publish

1. Build as above, then compute `{relative path: (sha256, size)}` per theme.
2. Read the manifest `os/spruceos/custom-themes.json` (`{folder: {"files": {rel: [sha256, size]}}}`) through `shared.py`.
3. Ownership guard: a registered custom theme name is reserved for the registry, so a folder of that name already in storage but absent from the manifest (for example the user's hand-copied first build) is adopted: the plan says so, and all of its files count as changed (no hashes yet) and its extra files as stale. A folder named in `themes.json` (a theme `themes update` downloaded) is never touched: report and skip, exit code 1. Adopting is the author's call (the user said custom themes are always rebuildable).
4. Plan per theme: new (not in the listing), changed (hash or size differs from the manifest, or the manifest lacks it), same, stale (in the listing under the folder but not built). Print counts and sizes like `upload` does; `--dry-run` stops there.
5. Confirm (`ui.confirm`) unless `--yes`; stale files are deleted as part of the same confirmed publish (the user asked for this: custom themes are always rebuildable, so deleting leftovers is low risk), listing the first few.
6. Upload through `upload.run_uploads`; after it, `s3.delete_keys(stale)`, then write the manifest with the uploaded files' hashes for files that succeeded (a failed or interrupted upload leaves their old entries so the next publish retries them). Claim the folder in the manifest before the first upload, as `themes update` does, so an interrupted run leaves a folder the next run knows as its own.
7. Print a summary and return 1 if any upload failed.

### UI and interruption

Same patterns as `upload.upload_command`: the plan summary, `ui.confirm`, `run_uploads` progress bar and Ctrl-C handling (finishing in-flight uploads, dropping queued ones). Ctrl-C during the build step exits cleanly without touching storage.

### Docs and tests

- `cli.TOPICS` help for `themes build` and `themes publish`, README Options table rows, CLAUDE.md storage table row for `custom-themes.json` and a short custom-themes paragraph.
- Tests (using `helpers.storage_sets`-style temporary storage as other storage tests do): build output has the expected files and is byte-identical across two runs; publish plan classifies new/changed/same/stale; an unchanged second publish uploads nothing; a theme folder not in the manifest isn't touched; a failed upload keeps its old manifest entry; stale files are deleted; `--dry-run` writes nothing; the registry rejects a theme with an unknown base.

## Left to the builder

Exact function names, the sprite package layout details beyond the above, the deterministic-PNG settings, how `fetch_base` reuses the download helpers, the help text wording, and the file layout of the tests.
