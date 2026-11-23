# sync-roms

Tooling for syncing ROMs to and from storage: an S3 bucket (`roms.valefor.com`, region `us-east-1`) or a local folder such as a mounted share.

## Python environment

Always use `uv`; never bare `python`, `pip`, `pyenv` shims or a system interpreter (the pyenv `python` shim is broken here). `.python-version` pins the latest stable CPython (uv downloads it), `python-preference = "only-managed"` in `pyproject.toml` keeps uv off system pythons, and `uv.lock` plus the `dev` group (Pillow) cover every dependency the tests need. A SessionStart hook (`.claude/settings.json`) runs `uv sync` so each new session, worktrees included, gets a fresh `.venv`.

```bash
uv sync                                      # create/update .venv
uv run python -m unittest discover -s tests  # tests
uv run sync-roms ...                         # the CLI
```

A "module not found" error means the command skipped `uv run`, not that a package is missing: rerun it with `uv run`. Add dependencies with `uv add` (`uv add --dev` for test-only), never `pip install`. When a new stable Python is out, bump `.python-version`, run `uv sync` and the tests, and commit the result with `uv.lock`.

CI tests on Python 3.12 to 3.15 (`requires-python`), so code must run on 3.12 too.

## Tests

- A test module that imports `sync_roms` must import `isolate` first, directly or through `helpers`: it redirects HOME, XDG and the AWS settings to a throwaway folder and fails any test touching the real data folder or `~/.aws`.
- Tests start with no sets, ignore list or scraped names. Sets come from `helpers.storage_sets`.

## Storage access

Storage is the `root` setting (a folder, which wins) or the `bucket` setting (with an optional `endpoint`), each from a flag, a `ROMS_*` variable or `settings.json` (`usersettings.SETTINGS`). Nothing is hardcoded; the first run asks for either.

- **Never put backup or test files in storage.** No `.bak` copies, scratch uploads or test objects. Keep those local.
- Confirm with the user before any command that deletes or overwrites storage files (`rm`, `mv`, `sync --delete`).
- When storage is a bucket, always pass `--profile` to `aws`: `roms-readonly` by default, for anything that only reads; `roms` only when a write is actually needed. Preview a `sync` to the bucket with `--dryrun`, and add `--delete` only when explicitly asked.

## Commits and releases

Use [Conventional Commits](https://www.conventionalcommits.org) for every commit and for PR titles: `<type>[scope]: <description>` (`feat`, `fix`, `refactor`, `docs`, `chore`, ...), imperative and lowercase. Merge PRs with squash so the PR title becomes the commit message on `main`.

Releases belong to release-please: never hand-edit `__version__`, `CHANGELOG.md` or `.release-please-manifest.json`.

## CLI

- A command is listed in `cli.SUBCOMMANDS` (help and completion) with its help in `cli.TOPICS`. Those in `commands.COMMANDS` are parsed by `commands.build_parser`, their second words listed in `commands.second_words`. The others are rewritten to a flag by `cli.LEGACY` and parsed by `cli.build_parser`; a flag they take also goes in `cli.PLAIN_FLAGS` or `cli.VALUE_FLAGS`.
- `tests/test_readme.py` compares the README's Options table, layout tables and Settings section with the parsers, `layouts.json` and `commands.CONFIG_KINDS`.

## Data files

Only one storage layout is supported; don't add support for others. Repo data and personal data are never read from or written to storage. Never put a real game list in the repo. Repo files must not contain notes about storage's contents ("not in the bucket", "bucket has..."). Device notes say only why the systems were chosen, concisely.

### Storage

| Storage path | Holds | Written by |
|---|---|---|
| `<system>/` | ROMs, one lowercase folder per system (`gba/`, `mame/`, ...): the system's `bucket` | `upload`, `download pico8` |
| `BIOS/` | BIOS files, always `BIOS/<file>`: the path is derived, never stored, and whether a file exists comes from listing `BIOS/` | by hand |
| `scrapes/` | Per system, `<system>/metadata.json`, media, and scrape state by ROM path: `matches.json` (manual matches, `{ROM path: ScreenScraper game id}`), `unknown.json` (ROMs ScreenScraper didn't know), `nomedia.json` (media types it didn't offer), `hashes.json` (file hashes). `notgames.json`: non-game scrape results waiting for review, and the ROMs the review kept for later, keyed `system/rom` | `scrape`, `scrape review`, `clean scrapes`, `download pico8`, the `match-translations` and `dedup-names` skills |
| `sets/<id>.json` | Game sets (the id is the file name) | `sets edit`, the `update-variants` skill |
| `variants-checked.json` | The ROMs the `update-variants` skill already judged | the `update-variants` skill |
| `ignored.json` | `{system folder: [ROM paths]}`: ROMs sync-roms never shows, syncs, uploads or scrapes | `scrape review` (`scrape match --translated` takes ROMs off) |
| `os/` | Firmware images, apps, themes, drivers, PICO-8 zips | by hand; `os/drivers/` by sync only, `os/esde/themes/` by `themes update` |

### Reading and writing storage

- Storage code must work for a bucket and for a folder (`runtime.ROOT`): go through `s3.py`, `inventory.py` and `shared.py`, catch `s3.ERRORS`, and call `s3.check_root()` before treating a missing file as absent (an unmounted share must never read as empty storage).
- Ask only `inventory.py` what storage holds (keys, sizes, a bucket's ETags); never call `s3.list_sizes`/`stat_sizes`/`list_with_etags`/`list_folders` from elsewhere. It answers from `cache/storage-cache.json` (built by `sync-roms cache update`, patched by sync-roms's own writes in `s3.py`) and, without a cache of the storage in use, lists storage itself. `inventory.tag` (a file's ETag, or `<mtime_ns>-<size>` in a folder) and `shared.read` always read storage itself; other file contents come from the local mirror during a sync that uses one (`s3.read_root`).
- Before shared state is removed for a file the cache doesn't list (`scrape review`, `clean scrapes`), `inventory.uncached` checks storage itself, so a file another machine added since the cache was built isn't taken for gone.
- `inventory.py`'s reads and `store.listed` leave ignored ROMs out, so nothing above them sees them. Ignoring a ROM never deletes its file.
- The shared JSON files (`ignored.json`, the scrape state in `scrape_state.py`, `variants-checked.json`, `sets/`) go through `shared.py`: downloaded only when the storage tag differs from the local copy's (the ignore list once per run), and written by re-reading the storage file and applying only the write's own changes, so machines merge.
- "Mirror" means two things: the shared-file mirror, `~/.sync-roms/storage/` (those files at their storage path, their tags in `.tags.json`), and the local mirror, the `mirror` command's copy of what the cards reference (`mirroring.py`).
- `store.py`, `inventory.py` and `s3.py` import some modules inside functions because those modules import them back: a top-level import there is a circular import.
- Personal files are written with `store.write_json` (atomic): `cards.json` only through `store.write_cards` or `store.update_card`, and like `settings.json` and the overlay with `backup=True`. Write text files on a card with `cardfs.write_text` or `store.replace_file`.

### Repo data

`src/sync_roms/data/`, the same for everyone.

- `layouts.json`: each layout's folders (`roms_dir`, `bios_dir`, RetroArch saves) and optional flags: `bios_by_tag` puts BIOS in `Bios/<folder tag>/`, `disc_folders` gives each multi-disc game its own folder, `save_naming: "minui"` names saves `<ROM file>.sav`.
- `systems.json`, per system: `name`, `company`, `bucket` (the system id and storage folder), `folders` (ROM folder, or `null`, for every layout, `rocknix` before `nextui` and `nextui` last), optional `ratio` (native aspect), `screenscraper` (system id), `muos_catalogue` (muOS catalogue folder), `chd` (how `convert` treats it), `nextui_bios_tags` (more tags whose `Bios/<tag>/` also gets the BIOS), and `bios`: `files` (required files, paths under `BIOS/`), `rom_files` (paths under `BIOS/` copied into the system's ROM folder by file name, e.g. MAME-style BIOS zips), `libretro_cores`, `note`.
- `devices.json`, per device: `id`, `name`, `soc`, `screen` ratio, optional `screen2` (second screen), `resolution` (native pixels, `<W>x<H>` as the device is held; the base model's when variants differ) and `resolution2` with `screen2`, `firmwares` (the first is its default, never `rocknix`), optional `"network": false` for no built-in WiFi (absent means it has WiFi), `rocknix_image` on a device that runs ROCKNIX (the SoC part of its image name, plus `-<variant>` when the device belongs to only one variant, e.g. `H700`, `RK3566-Generic`, which `flash` uses to match `os/rocknix/ROCKNIX-<SoC>.aarch64-<date>[-variant].img.gz`), and on Adreno devices a `gpu` id.
- `device-systems.json`: each device's recommended systems and a short note on why. `tiers` is an ordered chain: the first lists its `systems`, each later one only `add`s to the tier before it. A device names its `tier` and sets `note` only when it differs. Loaded lists come out in `systems.json` order. Read from the repo, never copied.
- `ratio-systems.json`: per-ratio overrides and a `dual_screen` list. A device's highlighted systems are those matching its `screen` ratio (exact string), the overrides and, with `screen2`, the dual-screen list, limited to what it can play. The personal overlay never changes them.
- `drivers.json`: suggested Adreno GPU drivers, refreshed with the `refresh-drivers` skill. `drivers` (each used by a GPU): `id`, `name`, GitHub `repo`, `asset` regex that must match exactly one asset of the chosen release, optional pinned `tag` (without it the newest non-draft release, prereleases as fallback). `gpus`: gpu id to `name` and driver ids.
- `series.json`: the series names for a set game's `series`.
- `spruce-fixes.json`: per fix in `spruce_fixes/`, its `title` and full `upstream` PR URL (a test checks both match the registered fixes).
- `spruce-settings.json`: `sections`, spruceOS's `menuOptions` sections to the keys of the user's preferences that are safe on any spruce device (per-device hardware, network and debug settings stay off), and a `note` saying why.
- `syncthing.json`: `note`, `cores` ({system id: libretro core}), `retroarch` ({retroarch.cfg key: value}) and `spruce.settings` ({section: {key: value}} for `spruce-config.json`), the settings that let Syncthing sync saves between devices.
- `cards.schema.json`, `games.schema.json`, `collections.schema.json`: JSON schemas.

BIOS lists cover every emulator a system can use (default and alternate libretro cores, standalone emulators), not just the default one. The files are small, so users get all of them all the time. Don't trim a list down to the default emulator's needs. Redundant extras that no emulator needs (e.g. a dozen regional dumps of one PS1 BIOS) are not kept.

The tests check these shapes.

### Personal data

The data folder is `store.data_dir()`: `$XDG_DATA_HOME/sync-roms`, `%APPDATA%\sync-roms`, by default `~/.sync-roms` (used here).

- `settings.json` (kept mode 600): the storage settings, `mirror`, `eject`, `storage_cache_declined`, `surprise_ttl_days`, `surprise_excluded_systems`, `screenscraper_user`, `screenscraper_password`, `spruce_ra_mode`, `spruce_ra_username`, `spruce_ra_password`, `spruce_ra_api_key`, `spruce_ra_offline_proxy`, `spruce_ra_proxy_stats`, `spruce_syncthing`, `spruce_settings` (`{section: {key: value}}`, written by `config import`).
- `surprises.json`: history of Surprise picks: system, bucket, title, card, ISO date. Pruned past `surprise_ttl_days` (default 183) on write.
- `device-systems.json`: optional overlay, `{device id: {"add": [...], "remove": [...]}}` of system ids, applied to the repo defaults. Notes always come from the defaults.
- `collections/<id>.json`: one per collection (`collections.py`); never in the repo or storage.
- `saves/`: RetroArch saves and states, `<system>/<stem>/<stamp>-<card>/` with `stash.json`, written by `saves stash`, read by `saves apply`.
- `bootlogos/<W>x<H>/`: your own boot logos (`.png`, `.bmp`), one folder per device `resolution`; never in the repo or storage.
- `cache/`: what can be rebuilt: `storage-cache.json`, `preview-cache/` (the editors' 300 px WebP game pictures, `<image key without extension>.<ETag or s<size>>.webp`), `previews/`, `theme-art/`, `names.json`.

Old personal sets in `sets/` are left on disk and never read; a sync reads an old `games.json` only to warn that it is no longer used.

### Card fields

`cards.json` is `{card name: card}`. A card's `games` is the only games list: a card with no picks syncs no games.

| Field | Written by | Meaning |
|---|---|---|
| `device`, `layout` | setup prompt, `cards` commands | Device id (or `full`) and layout. |
| `size` | `cards new`/`set` | Readable card size (`512 GB`). |
| `games` | the editors (`--edit`), `games` commands | Games per system, with their notes. A system's entry may be `{"full_system": true}` (its earlier list kept inside as `games`) to sync its whole storage folder. `"sets": [set ids]` syncs whole sets (live references). |
| `excluded` | card editor | `{system: [keys]}` dropped from what the card's sets bring. Never applies to collections. |
| `collections` | card editor | Collection ids synced whole. |
| `surprise` | card editor's S menu | Stored only when it differs from `surprise.default_on`: on for a card with no layout yet, `frontend.FRONTEND_LAYOUTS`, `onion`, `muos` and `spruce`; off for `allium`. |
| `surprises` | sync | `[{"system","bucket","title","files"?}]`. |
| `surprise_excluded_systems` | S menu | System ids Surprise never picks from on this card, on top of the global setting. Absent when empty. |
| `theme`, `custom_collections`, `raofflineproxy` | S menu | On when absent, stored only as `false`: collection art and the theme copy, collections in the frontend (Surprise's too), the RAOfflineProxy app. |
| `frontend_collections` | sync | The collection names sync wrote to the card's frontend, so only those are touched. |
| `drivers` | sync | The `Drivers/` zip names sync put on the card; only those are removed when they go stale. |
| `boot_logos` | sync | The logo file names sync put in a `spruce` card's `App/BootLogo/Imgs/`; only those are overwritten or removed. |
| `pico8`, `surprise_app`, `raofflineproxy_app`, `spruce_os` | sync | The file sync last put on the card: each is installed once per file name. `store.update_card` drops `pico8` when the layout changes. |
| `spruce_emu` | sync | `{ROM folder: [file names]}`: the BIOS zips sync added to that folder's `Emu/<folder>/config.json` `ignoreList` on a `spruce` card; only these are removed when the file stops being synced. |
| `muos_storage` | by hand | `sd1` (default) or `sd2`: the mount (`/mnt/mmc` or `/mnt/sdcard`) written into a `muos` card's collection entries. |

### Sets and collections

Sets come only from storage, through `store.load_sets` (`inventory.files` for the listing, `shared.load` for contents, once per run). A set another machine added appears after `sync-roms cache update`; a card naming a set storage doesn't have keeps the id and is warned about. `sync-roms check` validates the sets in storage.

A set file is `{"name", "description"?, "art"?, "games"}`. Games have `title`, `system`, `bucket` and optional `files`, `category`, `series` and `variants`. `art` is an `art.json` id; without it a set uses the art under its own id.

A collection file (see Personal data) has the same top-level keys (its games may carry a `note`) but its own loader and schema and no categories.

Rules for sets:

- A game appears once across all sets: one version per game (arcade original over home ports; else the original lead platform, then the lighter one to emulate; English for text-heavy games), and every set that has the game uses that version.
- A later version of the same game that adds something (extra content or modes, an HD or handheld remaster) goes in that game's `variants`, `[{"bucket", "note"}]`, the note saying in a few words what it adds. Variants aren't synced with the set; the editors show them on the game's highlighted row, and `v` in the card editor adds one to the card.
- A version that plays substantially differently is its own game. A compilation is listed only when it holds a game no set lists on its own.
- Retro Oddities, Handheld Greatest Hits and System Essentials keep their own versions and only lose straight re-releases.
- The set editor groups rows by `category` (in file order). Prefer one set with categories over several related top-level sets (e.g. `shmups.json`: Touhou, Psikyo, Cave, Other).

### Scraped names and metadata

- Editors and new game titles name MAME, FBNeo and PICO-8 sets through `names.title`: the scraped `name` from `scrapes/<system>/metadata.json`, else the file name (for pico8, without `.p8.png`). `names.py` keeps the scraped names in `cache/names.json` with each metadata file's storage tag and rereads one, from storage itself (never a mirror), only when its tag changes. Sync's own paths (`store.set_games`) keep file names.
- A metadata entry's optional `qualifier` sets it apart from other ROMs of the same name: its `name` is `<scraped name> (<qualifier>)`, before ` - Translated`, and re-scrapes keep it.
- `download pico8` (`bbs.py`) adds the BBS Featured carts to storage's `pico8/` under their BBS file names, upgrades newer revisions (renaming references in cards, surprises and collections), and keeps titles and authors in `scrapes/pico8/metadata.json`.
- PICO-8 is scraped (ScreenScraper system 234). A plain `scrape` also takes carts that have an entry but no `miximages`/`covers` picture in storage (unless ScreenScraper's last answer didn't offer miximages, until `--retry`). A scrape only adds to `scrapes/pico8/metadata.json`: it never changes a field the BBS (or an earlier scrape) already wrote.

### What sync puts on a card

"ES-DE's folder" is on the card for `esde` and, for `emudeck`, on the machine running the sync (`$ESDE_APPDATA_DIR` or `~/ES-DE`).

| Layout | Collections, Surprise among them | PICO-8 runtime (newest `os/pico8/pico-8_*_raspi.zip`, no version in code) | RAOfflineProxy |
|---|---|---|---|
| `esde`, `emudeck` | ES-DE's folder | `esde`: zip to `PICO-8/` | `esde`: its APK in `os/android/APKs/`, by the APK step |
| `knulli` | its ES `collections/` | zip to `roms/pico8/` | install script to `roms/tools/RAOfflineProxy Install.sh` (it deletes itself when run, so the copy is only recorded) |
| `rocknix` | staged, see below | `pico8_dyn`, `pico8_64`, `pico8.dat` to `roms/pico-8/` | `-Install.sh` to `roms/ports/RAOfflineProxy Install.sh`, run once from Ports (the official page says `/storage/.config/modules`, which is internal storage) |
| `onion`, `allium` | Onion: the Surprise app only | `pico8_dyn`, `pico8.dat` to `RApp/PICO-8/bin/` (Allium: `Apps/pico.pak/bin/`) | zip to `App/RAOfflineProxy/` (Allium: `Apps/RAOfflineProxy.pak/`) |
| `spruce` | the one `Collections/collections.json`; collections made on the device are kept as they are | as `rocknix`, to `BIOS/` | none: spruceOS 4.5.0+ ships it built in |
| `muos` | `MUOS/info/collection/<name>/<ROM>-<hash>.cfg` (`muos_collections.py`) | only `pico8_64`, `pico8.dat` to `MUOS/bios/pico8/`, where muOS's standalone launcher looks (the PICO-8 folder's core is switched to it on the device) | `.muxapp` zip to `MUOS/application/RAOfflineProxy/` |
| `nextui` | `Collections/*.txt` | none: carts are plain ROMs | |

- A `.p8.png` cart with no scraped picture is its own picture: copied from storage's `pico8/` into `downloaded_media/pico8/miximages/` (`esde`, `emudeck`), `Imgs/` (`onion`, `allium`; top-level carts only) or `.media/` in the cart's own folder (`nextui`); on `knulli` and `rocknix` the gamelist's `image` points at the cart in the ROM folder.
- muOS takes scraped art in `MUOS/info/catalogue/<the system's muos_catalogue>/box|preview|text`.
- ROCKNIX's ES reads collections only from internal storage, so `rocknix_collections.py` stages them in `roms/.sync-roms-collections/` and writes `roms/ports/Install Collections.sh`, which the user launches from Ports (again after a sync changes collections; its messages aren't visible on the device).
- Onion and Spruce box art is made into storage: `scrapes/<system>/onion/<ROM>.png` (250x360 at most) from the cover, then the miximage (a PICO-8 cart with neither uses its own `.p8.png`); `scrapes/<system>/spruce/<ROM>.qoi` (fit in 640x480), `spruce_med/` (400x300) and `spruce_small/` (200x200) are QOI RGBA from the same sources, shrunk to fit and never enlarged. `spruce_med`/`spruce_small` exist only when they differ from the tier above (med if the fit in 400x300 differs from the fit in 640x480; small if 200x200 differs from 400x300). ROMs in subfolders get none. Scrapes make them as they go; `sync-roms scrape art [SYSTEM | --system ID] [--for onion|spruce|both] [--dry-run] [--replace] [--workers N]` makes them for what storage holds (`--dry-run` reads only listings and reports counts per system and target, existing files are skipped without `--replace`, one worker process per core; the QOI encoder is pure Python). Pillow is a runtime dependency. A made `onion` file doesn't count as a scraped picture (`PICO8_PICTURES` in `scrape_online.py`). `spruce` cards get `Imgs/<ROM>.qoi`, `Imgs_med/<ROM>.qoi` and `Imgs_small/<ROM>.qoi` (the layout PyUI reads) and never a PNG or JPG in those folders, since any makes PyUI prompt to convert and rewrite images. A ROM with no `spruce` art in storage gets none, and sync hints to run `scrape art --for spruce`; its `miyoogamelist.xml` entry holds the name and, with art, an `image` pointing at the `.qoi` (PyUI strips every extension of the system's list from a name, so a `.p8.png` cart's name finds no art). A PICO-8 cart's own picture isn't copied into Spruce's `Imgs/`.
- On `onion` cards with Surprise and `custom_collections` on, `onion_surprise.py` installs the newest `os/onion/Surprise-v<version>.zip` as `App/Surprise/` (its icon, when the zip has one, as `Icons/Default/app/surprise.png`) and writes `Roms/surprise.json` from the card's surprises that are on the card (removed when there are none).
- `raofflineproxy.py` takes the newest `RAOfflineProxy-<Onion|Allium|muOS|Knulli|Rocknix>-v<version>...` in `os/onion/`, `os/allium/`, `os/muOS/` (that spelling), `os/knulli/` or `os/rocknix/`. An extracted app is overwritten file by file, never wiped (it keeps its login and settings in that folder), and reinstalled when its `launch.sh` is missing. The `esde` APK is left out when the setting is off.
- Sync keeps each GPU driver's zip and `.tag` in `os/drivers/`, and `esde` cards get them as `Drivers/<id>-<tag>.zip`.
- `spruce_emu.py` keeps each ROM folder's BIOS zips (`bios.rom_files` basenames of the systems with ROMs to sync there) in `Emu/<folder>/config.json`'s `ignoreList` on `spruce` cards, so PyUI doesn't list them as games (merged, never overwritten, re-added every sync since a Spruce update can replace the file; skipped with a warning when the config is missing). Spruce's `mame` folder is `MAME2003PLUS` (its core is fixed), `fbneo` shares `ARCADE`; sync clears what an earlier sync left in `Roms/FBNEO` (`spruce_emu.OLD_FOLDERS`).
- `spruce_settings.py` writes the `spruce_ra_*` settings (RetroAchievements mode, login, API key, RAOfflineProxy options; passwords and the key never printed) into a `spruce` card's `Saves/spruce/spruce-config.json` under `menuOptions."RetroAchievements Settings"` as `{"selected": "<string>"}` entries (bools as `"True"`/`"False"`), on every sync. Spruce rewrites RetroArch's cheevos lines from it at each game launch. The file is Spruce's whole settings file: only those entries' `selected` change, and a missing, invalid or `menuOptions`-less file is skipped with a warning, never created. `spruce_settings` (the allowlist in `data/spruce-settings.json`: the user's emulator, in-game menu, button, boot and network preferences, not per-device hardware, LED, audio, proxy or debug ones) is applied in the same write, only to sections and keys the file already has (older spruceOS may lack them), keeping each entry's other fields; other entries and a malformed value are warned about and ignored. While `spruce_syncthing` is on, `spruce_syncthing.forced_settings(card)` (`raAutoSave`, `raAutoLoad`, `keepSavesBetweenCores`, and `enableSyncthing` on WiFi devices) is applied after them in the same write, a missing key warned about, and those keys leave `allowed()` so they're neither imported nor applied from `spruce_settings`. `sync-roms config import [CARD]` fills it from a `spruce` card (the layout comes from cards.json; lists identical vs different settings and asks Yes/No/Pick with no default, nothing saved without an answer; never reads the RetroAchievements block).
- `spruce_wifi.py` merges settings.json's `wifi_networks` (`[{"ssid", "psk"?}]`, edited by hand) into a `spruce` card's `Saves/spruce/wpa_supplicant.conf` by SSID on every sync (networks added on the device kept; passwords never printed).
- `spruce_fixes/` holds temporary fixes for bugs in spruceOS's Art Book themes and for unreleased spruceOS PyUI changes, run on `spruce` cards every sync by `spruce_fixes.run` (one call each in cli.py's dry-run and real paths) and printed as a "Spruce fixes" block, one line per fix: `applied to N file(s)` (`would apply` in a dry run), `skipped, <reason>` with the upstream link (the card is already right: upstream fixed, or an earlier sync did it; the fix can go once every card shows this), `skipped, the theme isn't on the card` (or the module's `MISSING`), or a warning when `plan` returns a `Mismatch` (the card's files aren't a version the fix knows, so nothing is written). Each line ends with the fix's upstream PR URL, from `data/spruce-fixes.json` (`{fix id: {"title", "upstream"}}`). A fix module has an `ID` (its key there) and `plan(base)` returning `(writes, skip)`; `pokemini.py` copies `pokemini.png` to `poke.png` where missing (PyUI-Themes#15), `fds.py` replaces `icons/overlay/fds.png` with `data/themes/spruce-fds/fds.png` (the Family Computer Disk System logo, CC BY-NC-SA, see its `LICENSE.md`) only while it is byte-identical to the theme's `fc.png` (PyUI-Themes#16). `reopen_collection.py` adds PyUI's "Reopen last collection" setting (spruceOS#2070) to the five files under `App/PyUI/`: insertions at anchors that must each appear once, in 4.6.0 and `Development` alike, on LF-normalized text written back with the file's own line ends (CRLF on spruce cards), never a whole file; all five or none (all already have it: skipped; some do, or an anchor or what the change calls in `roms_menu_common.py`/`py_ui_state.py` doesn't match: `Mismatch`). Its tests use copies of the real files in `tests/fixtures/spruce-reopen-collection/` (4.6.0, `Development`, and `patched`, the PR's result, which the Development output must equal byte for byte; a `.gitattributes` there keeps their CRLF). Delete it, its fixture folder and `tests/test_spruce_reopen_collection.py` once a spruceOS release with that PR is on every card. Since PyUI makes its resized copies of a theme (`icons_<W>x<H>/`, read with `bg_<W>x<H>/`) once and never regenerates them, the fixes patch those too (`spruce_fixes/pyui.py`): each copy's own `pokemini.png`, and `fds.png` scaled as PyUI scales icons (screen size over `skin/background.png`'s); the block adds a `Fixing <W>x<H> theme variation` line for each size it wrote to. To add a fix: write its module, add it to `FIXES` and to `spruce-fixes.json`, with a test. To remove one: delete its module, its `FIXES` entry, its `spruce-fixes.json` entry, its test and its data.
- `spruce_bootlogo.py` copies your own boot logos (`bootlogos/<resolution>/*.png|*.bmp`, the card's device `resolution`) into a `spruce` card's `App/BootLogo/Imgs/`, for devices with a `resolution` and not in `UNSUPPORTED` (the Boot Logo app can't run there). `Imgs/` is never created (a card without it gets a warning: spruceOS isn't installed), and a logo named like one of spruce's own (any case) is skipped. A logo that goes from the data folder is removed from the card with its `Yes, flash` copy, unless `--no-delete`. Miyoo Mini cards are staged ahead of the spruce release that shows the app there. Flashing is your step on the device, in Apps → Boot Logo.
- `spruce_os.py` copies the newest `os/spruceos/spruceV<version>.7z` unextracted to the root of `spruce` cards, for Apps → EZ Updater on the device, after the card's other writes and only when the card has room for it with 64 MiB to spare. Only the previously staged file is removed (kept with `--no-delete`). OTA deltas (`spruceOTA-*`) and installers are ignored. The local mirror keeps the newest 7z too.
- `saves stash` and `apply` use Pickles' `MUOS/pickles/sram|state` on muOS (`muos_saves.py`), copied as they are; a Pickles stash applies only to muOS cards.

### Theme art data

`src/sync_roms/data/themes/art-book-next/` holds:

- `art.json`: the art ids, one per set among them (`surprise` has art too).
- `art/<id>.png`, drawn by `tools/gen_theme_art.py`, with a generated `art/README.md` gallery for GitHub that sync never copies.
- `art-spruce/<id>.png`: the same pictures as 300x300 transparent squares for SpruceOS. `tools/gen_spruce_art.py` makes them from `art/`: run it after `gen_theme_art.py` and commit both.
- `emoji.json`: each art id's own emoji, for the editors.
- `logo-font.json`: the logo font's outlines (OFL).

With the card's `theme` on, sync copies the art into the copy of the theme in ES-DE's folder (the theme itself is a GitHub archive in `os/esde/themes/`, refreshed by `sync-roms themes update`), the theme customizations (Knulli, ROCKNIX), `MUOS/info/catalogue/Collection/box|grid` (muOS) or `Collections/Imgs/<name>.png` (Spruce: PyUI shows it by exact name, PNG only; the theme plays no part).

The names sync gave art are listed in the theme copy's `.sync-roms-collections` (ES-DE; not ROCKNIX's staging folder of that name) or in `.sync-roms-art` (Knulli, ROCKNIX, muOS), and only those lose their art (on Knulli their `subset.<name>.*` settings too) when the collection or its art goes; on Spruce, only the collections sync owns do. With no art left to add, the theme isn't copied for that. A theme update that ships metadata for a listed name takes it off the ES-DE list (the theme's from then on, never removed).

## Theme art

Rules for changing or adding a picture in `tools/gen_theme_art.py` (`uv run python tools/gen_theme_art.py [id ...]`). The reference is the theme's own Outline set, `_inc/systems/artwork-outline/*.png` in the archive in storage's `os/esde/themes/`: steady off-white lines about 6px wide with a slightly rough edge, corners joined, shapes closed, nothing drawn through a shape in front of it.

Lines:

- No wobble. Never add drift, jitter or varying thickness to "look hand-drawn"; it reads as loose and messy. The rough edge in `_ink` is the only texture.
- Every line end must land on another stroke, run off the band, or be an obviously free mark (impact dashes, a motion trail, a dashed path). An end that stops a few units short of an outline, or pokes past it, is the main thing that looks messy.
- Don't hand-pick the point where a detail meets a curved outline. Draw the detail too long inside `with p.inside(shape):` and it is cut at the outline.
- Overlap is drawn back to front: the shape in front gets `opaque=True` and hides what is behind it. Don't leave gaps in the back shape by hand, and never let lines cross through a front shape.
- A line may end on a straight edge at computed coordinates, but stay clear of that edge's rounded corners (the corner radius, in units, from each vertex).
- Prefer `arc`, `rounded` polygons and `mirror` of one half over a closed `spline` through a few points, which comes out lumpy. Use `spline` for open curves and for outlines with ten or so evenly spaced points.
- Close shapes. An open-ended fin, flame, cuff or body looks unfinished.

Size and placement:

- Drawings live in a box of about -50..50 units, y down, 3.3px per unit; the stroke is about 1.8 units wide, so keep parallel lines and small details at least 5 units apart. A solid dot is two small concentric circles (radius about 2.2 and 0.8). A larger solid shape, like the eye in `sonic`, is `p.fill(shape)`; keep it to one small feature of a picture.
- The band is slanted and about 340px wide where the picture sits, and `CENTER` is right of its middle. A picture wider than about 75 units runs off the band's right edge, and that look is wanted: the theme's own pictures are cut off on the right, and about 30 of ours lose 10 to 40px there. Don't move or shrink a picture to keep it whole on the right; give a wide one 10 to 20px of cut rather than letting it just touch the edge. Use a smaller `scale` and a negative x offset in `ART` only when more than about 40px would go, and keep the left edge clear.

Subject:

- One picture per meaning. Before adding one, check `art.json` for an entry that already means the same thing (a genre and a set of the same genre, two kinds of fist). If two exist, ask which to keep; the kept picture goes under the set's id, and the other id is removed from `ART`, `art.json`, `emoji.json`, `art/`, `art-spruce/` and the tests.
- Draw the thing from the games, not a real-world lookalike: a console light gun (long thin barrel, boxy body, cable), not a pistol.
- A series may get its character when asked. Get the proportions of the right form: Pikachu has long slim ears with a short tip band, a head smaller than its chubby body, small solid eyes and a large stepped tail; wide triangular ears on a big head is Pichu.
- When asked to redo a picture without a subject, say which subject was chosen. When two concepts are equally plausible, show both and let the user pick.

Checking:

- Never finish without looking at the result. Read the generated PNG (the drawing is in y 600..1050), and also crop that part and enlarge it 2x to check every join, line end and overlap.
- Compare with the pictures next to it in a contact sheet of all of `art/`, and show the user that sheet or the changed pictures. Keep review images out of the commit.
- The tests check that every `art.json` id has a PNG in `art/` and `art-spruce/` and its own emoji; `sync-roms check` notes sets in storage that have no art or share one.

## Devices

`anbernic-rg-sp` ("Anbernic RG SP") is Anbernic's newer, separate device. It is not the RG35XX SP or the RG34XX SP, which are their own entries.

## Setup guide

`src/sync_roms/data/setup-guide.html` (`sync-roms guide` opens it in a browser) is the user's own record of the steps they take by hand to set up a device after sync-roms writes its card: installing apps, the ES-DE, Knulli and RetroArch settings they change, and the standalone emulators they use (where each is installed from and its settings). It is one self-contained page (no external files, scripts or fonts) that works opened straight from disk; picking a device and layout at the top shows only the steps that apply.

- Content lives in the `SECTIONS` array in the page's script. Sections, items and emulators take an optional `when` filter: `platform` (from `platformOf`: an `esde` card is Android, except `windows-pc`), `layout`, `systems` (the device supports any listed system), `tier`, `power` (`low`/`mid`/`high`/`desktop`, grouped from the tier in `POWER`), `device`, `dualscreen` (true with `screen2`) and `gpu` (true with a `gpu` id). The Shaders section's picks live in `SHADER_CATEGORIES` (a preset and a Knulli Shader Set per power level). The RetroAchievements and Cloud saves sections (RetroArch Cloud Sync against `https://cloud-saves.valefor.com/dav/`) hold login and sync settings, never credentials. The Android "Standalone emulators" and "RAOfflineProxy" sections come from the systems each device supports.
- Only write steps and settings the user gave. Leave a section empty rather than guess which apps or settings they use.
- The page embeds each device's `id`, `name`, `soc`, `screen`, `screen2`, `firmwares` and `gpu` from `devices.json`, and its tier and systems (the tier chain of `device-systems.json` resolved, repo defaults only). After changing either file, run `uv run python tools/update_setup_guide.py`; `tests/test_setup_guide.py` fails when they differ.
