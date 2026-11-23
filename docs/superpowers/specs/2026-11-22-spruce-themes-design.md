# PyUI themes on spruce cards

## Intent

spruceOS's Theme Garden downloads each PyUI theme on the device, over the device's WiFi, one at a time. Syncing them from storage is much quicker. The user wants every theme in storage, a default list of the themes they use synced to every spruce card, a key during a sync to change that list for that sync only (to try all themes now, then keep favorites), and one current theme per card that is always synced and set as the card's selected theme.

## Goals, non-goals, anti-goals

- Goals: all PyUI-Themes release themes in storage, refreshed by a command; a global default theme list picked in a UI with previews; a per-sync override of that list from the sync's download question; a per-card current theme, always copied and selected; themes sync put on a card and no longer wanted are removed.
- Non-goals: theme settings. Every theme on the card keeps storage's files, so tweaks made on the device (PyUI saves them into the theme's own `config*.json`) are reset by the next sync. A user who wants other defaults makes a custom theme. Other firmwares. Theme Garden's previews or its `garden.json`.
- Anti-goals: removing themes sync didn't put on the card (spruceOS's own, Theme Garden downloads, hand-copied ones); `themes update` removing folders in storage it didn't create (the user's custom themes).

## Constraints (spruceOS and PyUI-Themes, checked on GitHub)

- Theme Garden downloads `https://github.com/spruceUI/PyUI-Themes/releases/download/1/<name>.7z`. Release `1` has one `.7z` asset per theme (94 now, about 1.36 GB); assets are replaced in place when a theme changes (each has its own `updated_at` and `size`).
- Each archive's members are `mnt/SDCARD/Themes/<theme folder>/...`. The theme folder name can contain spaces and differs from the asset name (`2CleanMini_by_Sheezie.7z` → `2CleanMini by Sheezie/`).
- Each theme folder has a `preview.png` (PyUI's own theme menu shows it; it falls back to `preview.qoi`).
- The selected theme is the `"theme"` key (the theme's folder name under `Themes/`) in the device's system JSON, `Saves/<device>-system.json` (`miyoo-mini-system.json`, `flip-system.json`, `a30-system.json`, `anbernic-rg-xx-system.json`, ...). The file appears on the card after spruceOS's first boot on a device.
- PyUI writes theme setting changes into the theme's `config.json` / `config_<W>x<H>.json`, and makes resized copies (`icons_<W>x<H>/` and the like) inside the theme folder, which `spruce_fixes/pyui.py` already patches.

## Approaches

- **Unpacked themes in storage, copied file by file (chosen).** `themes update` unpacks the archives with `7z` and uploads the folders; sync copies files like ROMs. Repeat syncs copy only changes, the Art Book fixes see the themes in the same sync, and a custom theme is just another folder. Cost: many small files in storage.
- **Archives in storage, unpacked by spruceOS at boot** (copy the `.7z` into the card's `Themes/`, as Theme Garden does). Rejected: the first boot unpacks over a gigabyte on the device, the archives delete themselves so sync must track installs, any change re-copies a whole archive, and fixes land a sync later.
- **Per-card theme lists.** Rejected by the user: one default list, overridden per sync.

## Design

### Storage: `sync-roms themes update`

- Storage folder `os/spruceos/themes/<theme folder>/...` (new prefix in `runtime.py`), plus `os/spruceos/themes.json`: `{asset name: {"updated_at", "size", "folder"}}` for the release assets that `themes update` unpacked.
- `themes update` (existing command, which keeps refreshing Art Book Next for ES-DE) also lists release `1`'s assets through `github.py`. For each asset that is new or whose `updated_at`/`size` differs from `themes.json`: download it to a temp folder, unpack with `7z` (found through `external.find_tool`; missing 7z is a warning pointing at `tools install`, and the Art Book Next part still runs), check every member is under `mnt/SDCARD/Themes/<one folder>/` (otherwise skip that asset with a warning), then replace `os/spruceos/themes/<folder>/` in storage with the unpacked files (upload new and changed files, delete files of that folder no longer in the archive) and record it in `themes.json`.
- An asset gone from the release has its folder removed from storage and its `themes.json` entry dropped. Folders not in `themes.json` (custom themes) are never touched.
- `--dry-run` lists what would be added, updated and removed, with sizes, and changes nothing.
- Writes go through `s3.py` and `inventory.py` (the storage cache is patched by `s3.py`). Downloads are kept local (temp folder); nothing but theme files and `themes.json` goes to storage.

### Default list: `sync-roms themes pick`

- New `themes` second word `pick` (`commands.second_words`, `cli.TOPICS`, README).
- Opens `picker.filter_list` in multi mode over the theme folders in storage (from `inventory.files` on the new prefix), sorted case-insensitively, with the default list's themes on. `preview=` shows the theme's `preview.png` from storage, cached in `cache/` like other previews. `a` toggles all shown.
- Saves the chosen folder names as `spruce_themes` (a sorted list) in `settings.json` via `usersettings`. Absent means none. A name in the list that storage no longer has is kept and ignored by sync with a dim note.

### Current theme per card

- New card field `spruce_theme`: a theme folder name. Set from a new entry in the card editor's S menu, shown only on `spruce` cards (`🎨 Spruce theme: <name or none>`), opening a single-select `filter_list` over storage's themes with the same preview; an entry to clear it.
- Sync always copies the current theme, whatever the theme list for that sync says.
- After the copies, sync sets `"theme"` to it in every `Saves/*-system.json` on the card that is valid JSON with an object at the top, keeping every other key and the file's formatting style as `spruce_settings.py` does. No such file: a warning that spruceOS hasn't booted on the card yet. A malformed file: warned and skipped. Never creates the file. Set on every sync, so a theme changed on the device goes back.
- A current theme storage doesn't have: a warning, nothing set.

### Sync

- On `spruce` cards: the themes to sync are the default list (or, after `t`, that sync's list) plus the card's `spruce_theme`, limited to what storage has. Their files are jobs into `Themes/<folder>/` through the same path Onion's `themes_dir` uses (`downloads.add_job`, `plan_downloads`, `run_downloads`), so only missing or different files are copied. Size decides, as for other files, except a theme's `config*.json` files, which are compared by content (they are small and are where PyUI saves setting changes), so theme settings always go back to storage's defaults.
- Files PyUI added inside a synced theme folder (its resized copies) are left alone: theme jobs never delete files on the card.
- New card field `spruce_themes_installed`: the theme folders sync installed on this card. A theme is added to it only when sync copied it and the card didn't have that folder before the first copy, so spruceOS's own themes and other downloads are never recorded. A recorded theme that isn't in this sync's list is removed from `Themes/` (the whole folder) unless `--no-delete`, or it's the theme a `Saves/*-system.json` on the card currently selects, or it's the card's `spruce_theme`. Theme removals run after the download question is answered (so a `t` change can keep a theme instead of deleting and re-copying it) and before the downloads; the free space shown counts what they will free.
- The download question on `spruce` cards, with a terminal and without `--yes`, takes a third answer, `t` (via `ui._choose_keys` or the same style): it opens the `themes pick` picker pre-filled with this sync's list (default list; the current theme shown on and locked), titled as for this sync only. On Enter, sync re-plans the theme jobs and removals and asks again. `settings.json` is not changed. On a `spruce` card the question is asked even when nothing else is to be downloaded ("Nothing to download" with `t` offered), so themes can be added on any sync. `--dry-run` uses the default list and never asks.
- The Art Book fixes (`spruce_fixes.run`) run after the theme copies, as now. Since the fixes change theme files, a fixed file differs from storage and would be copied back every sync: theme jobs skip a file a fix module reports as its own output (the fix's `plan` decides from the card's state, so a file already fixed is left as is). The builder picks the mechanism; the requirement is no copy-then-fix churn on repeat syncs.
- The local mirror (`mirroring.py`) mirrors the themes that the default list and any card's `spruce_theme` name.

### Docs and tests

- CLAUDE.md: storage table (`os/` row: `os/spruceos/themes/` by `themes update`), personal data (`spruce_themes` setting), card fields (`spruce_theme`, `spruce_themes_installed`), the spruce row and bullets in "What sync puts on a card". README: options and command help, settings section (`tests/test_readme.py`). `cards.schema.json`: both new fields.
- Tests (with `isolate`): `themes update` against a fake release (new, changed, unchanged, removed asset; bad member paths; custom folder untouched; dry run); `themes pick` saving; sync planning (list plus current theme, missing theme, removals only of recorded themes, `--no-delete`, the selected theme kept, the `t` override re-plans without saving); writing `"theme"` into system JSON files (missing, malformed, other keys kept); fix churn absent on a second sync.

## My calls (not decided by the user)

- Paths `os/spruceos/themes/` and `os/spruceos/themes.json`; names `spruce_themes` (setting), `spruce_theme` and `spruce_themes_installed` (card fields); `t` as the key.
- Setting `"theme"` in every `Saves/*-system.json` on the card instead of mapping each device to its file name.
- Never removing the theme a device currently selects, and asking the download question on spruce cards even with nothing else to download.
- Theme removals after the download question; content comparison only for `config*.json`.
- `7z` as the unpacker (already a known tool here) rather than a new Python dependency.
- A theme new in storage is not added to the default list: it shows off in `themes pick` until picked. No record of seen themes is kept.
