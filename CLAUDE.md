# sync-roms

Tooling for syncing ROMs to and from the `roms.valefor.com` S3 bucket (region `us-east-1`).

## Python environment

Always use `uv`; never bare `python`, `pip`, `pyenv` shims or a system interpreter (the pyenv `python` shim is broken here). `.python-version` pins the latest stable CPython (uv downloads it), `python-preference = "only-managed"` in `pyproject.toml` keeps uv off system pythons, and `uv.lock` plus the `dev` group (Pillow) cover every dependency the tests need. A SessionStart hook (`.claude/settings.json`) runs `uv sync` so each new session, worktrees included, gets a fresh `.venv`.

```bash
uv sync                                      # create/update .venv
uv run python -m unittest discover -s tests  # tests
uv run sync-roms ...                         # the CLI
uv run python tools/gen_theme_art.py [id ...]
```

A "module not found" error means the command skipped `uv run`, not that a package is missing: rerun it with `uv run`. Add dependencies with `uv add` (`uv add --dev` for test-only), never `pip install`. When a new stable Python is out, bump `.python-version`, run `uv sync` and the tests, and commit the result with `uv.lock`.

## AWS profiles

Always pass `--profile` explicitly.

| Profile | Use for |
|---|---|
| `roms-readonly` | Anything that only reads: `ls`, `cp` from the bucket, `sync` from the bucket, `head-object` |
| `roms` | Anything that writes: `cp`/`sync` to the bucket, `rm`, `mv` |

Default to `roms-readonly`. Only use `roms` when a write is actually needed, and confirm with the user before any command that deletes or overwrites (`rm`, `mv`, `sync --delete`).

**Never put backup or test files in the bucket.** No `.bak` copies, scratch uploads, or test objects under `roms.valefor.com`. Keep those local.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org) for every commit and for PR titles: `<type>[scope]: <description>` (`feat`, `fix`, `refactor`, `docs`, `chore`, ...), imperative and lowercase. Merge PRs with squash so the PR title becomes the commit message on `main`.

## Bucket layout

Top-level prefixes are one per system, lowercase (`BIOS/`, `gba/`, `genesis/`, `dreamcast/`, `mame/`, `atari2600/`, ...). List them with:

```bash
aws s3 ls s3://roms.valefor.com/ --profile roms-readonly
```

## Common commands

```bash
# List a system
aws s3 ls s3://roms.valefor.com/gba/ --profile roms-readonly

# Download one file
aws s3 cp s3://roms.valefor.com/gba/game.zip . --profile roms-readonly

# Download a system (bucket -> local)
aws s3 sync s3://roms.valefor.com/gba/ ./gba/ --profile roms-readonly

# Upload (local -> bucket) -- needs write profile
aws s3 sync ./gba/ s3://roms.valefor.com/gba/ --profile roms

# Preview any write first
aws s3 sync ./gba/ s3://roms.valefor.com/gba/ --profile roms --dryrun
```

## Data files

Only one bucket layout is supported; don't add support for others. The bucket name is not hardcoded: it is the `bucket` setting in `~/.sync-roms/settings.json`, asked for on first run. BIOS files always live at `BIOS/<file>` in the bucket, so the path is derived, never stored. Whether a file exists comes from listing `BIOS/`.

BIOS lists in `systems.json` cover every emulator a system can use (default and alternate libretro cores, standalone emulators), not just the default one. These files are small, so users get all of them all the time. Don't trim a list down to the default emulator's needs. Redundant extras that no emulator needs (e.g. a dozen regional dumps of one PS1 BIOS) are not kept.

The old single `roms.json` is split by whether the data is personal. Nothing here is read from or written to the bucket.

| Where | Files | Holds |
|---|---|---|
| Repo, `src/sync_roms/data/` | `layouts.json`, `systems.json`, `devices.json`, `device-systems.json`, `ratio-systems.json`, `drivers.json` | Frontend folder layouts (optional flags: `bios_by_tag` puts BIOS in `Bios/<folder tag>/`, `disc_folders` gives each multi-disc game its own folder, `save_naming: "minui"` names saves `<ROM file>.sav`; `rocknix` is ROMs in `roms/<system>`, BIOS flat in `roms/bios`); systems (name, id, folder per layout, required BIOS filenames, `rom_files` (BIOS files from `BIOS/` that are copied into the system's ROM folder, by file name, e.g. MAME-style BIOS zips), libretro cores, optional `screenscraper` system id, native aspect `ratio`, optional `nextui_bios_tags`: more tags whose `Bios/<tag>/` also gets the BIOS); device hardware (id, name, SoC, optional `"network": false` for devices with no built-in WiFi (absent means it has WiFi), `screen` ratio and optional `screen2` for a second screen, the firmwares it runs, the first being its default; `rocknix_image` on a device that runs ROCKNIX: the SoC part of its image name, plus `-<variant>` when the device belongs to only one variant, e.g. `H700`, `RK3566-Generic`, which `flash` uses to match `os/rocknix/ROCKNIX-<SoC>.aarch64-<date>[-variant].img.gz`; Adreno devices also a `gpu` id); suggested Adreno GPU drivers (`drivers.json`: `drivers` of id, name, GitHub `repo`, `asset` regex that must match exactly one asset of the chosen release, optional pinned `tag`; `gpus` of gpu id to name and driver ids; no `tag` means the newest non-draft release, prereleases as fallback; sync keeps each driver's zip and `.tag` in storage's `os/drivers/`, written by sync only, and `esde` cards get them as `Drivers/<id>-<tag>.zip`, refreshed with the `refresh-drivers` skill); each device's recommended systems and a short note on why (`device-systems.json` is an ordered chain of tiers: the first lists its systems, each later one only `add`s to the tier before it; a device names its tier and only sets `note` when it differs; loaded lists come out in `systems.json` order). Same for everyone. `ratio-systems.json` holds per-ratio overrides and a `dual_screen` list; a device's highlighted systems are those matching its `screen` ratio (exact string), the overrides and, with `screen2`, the dual-screen list, limited to what it can play; the personal overlay never changes them. |
| `~/.sync-roms/` | `cards.json` (per card: device, layout and its `games`; also `surprise`, set only when Surprise differs from the layout's default (on for layouts with frontend collections, `esde`/`knulli`/`rocknix`/`emudeck`/`muos`/`nextui`/`spruce`, for `onion`, which has the Surprise app, and for a card with no layout yet; off for `allium`), and `surprises`, `[{"system","bucket","title","files"?}]`), `surprises.json` (history of picks: system, bucket, title, card, ISO date; pruned past `surprise_ttl_days`, default 183, on write), `device-systems.json` (optional overlay), `collections/<id>.json` (one per collection), `cache/preview-cache/` (the editors' 300 px WebP game pictures, `<image key without extension>.<ETag or s<size>>.webp`), `saves/` (RetroArch saves and states, `<system>/<stem>/<stamp>-<card>/` with `stash.json`, written by `saves stash`, read by `saves apply`; personal, never in storage) | Each card's games to sync per system (with their notes). `--edit` edits a card's games. A list may also hold `"sets": [set ids]` to sync whole sets (live references). A system's entry in a card's `games` may be `{"full_system": true}` instead of a list to sync its whole bucket folder; no card uses it by default. The overlay is `{device id: {"add": [...], "remove": [...]}}` of system ids, applied to the repo defaults; notes always come from the defaults. A collection file is `{"name", "description"?, "games"}` like a set file but with its own loader and schema, without categories, and never lives in the repo or storage. A card's `collections` (top level of the card) lists collection ids synced whole; `excluded` never applies to them. `frontend_collections` lists the names sync wrote to ES-DE/Knulli (and NextUI's `Collections/*.txt`, and Spruce's one `Collections/collections.json`, where other collections, made on the device, are kept as they are) (for `emudeck`, to ES-DE's data folder on the machine running the sync: `$ESDE_APPDATA_DIR` or `~/ES-DE`), so only those files are touched. A card's `drivers` lists the `Drivers/` zip names sync put on the card; only those are removed when they go stale. A card's `pico8` is the PICO-8 zip name sync last put on it (once per zip). A card's `surprise_excluded_systems` (set in the card editor's S menu, absent when empty) lists system ids Surprise never picks from on that card, on top of the global setting. A card's `surprise_app` is the Surprise app zip name sync last installed on it. A card's `raofflineproxy` is `false` when RAOfflineProxy is off for it (on when absent; the card editor's S menu), and `raofflineproxy_app` is the file name sync last installed. A card's `spruce_os` is the spruceOS 7z name sync last staged on it. A `muos` card's `muos_storage` (`sd1`, the default, or `sd2`; edited by hand) picks the mount (`/mnt/mmc` or `/mnt/sdcard`) written into its collection entries. |

`ignored.json` at the root of storage (`{system folder: [ROM paths]}`) lists ROMs sync-roms never shows, syncs, uploads or scrapes; it is shared, not personal. `ignore.py` reads it once per run when its storage tag (ETag, or `<mtime_ns>-<size>` in a storage folder) differs from the tag of its local copy, `~/.sync-roms/storage/ignored.json`, and `scrape review` adds to it. `inventory.py`'s reads and `store.listed` leave ignored ROMs out, so nothing above them sees them; ROM files are never deleted. Scrape state that only references storage ROMs is shared too (`scrape_state.py`, through `shared.py`): per system `scrapes/<system>/matches.json` (manual matches, `{ROM path: ScreenScraper game id}`), `unknown.json` (ROMs ScreenScraper didn't know), `nomedia.json` (media types it didn't offer) and `hashes.json` (file hashes), and `scrapes/notgames.json` (non-game scrape results waiting for review, and the ROMs the review kept for later, keyed `system/rom`). Writes re-read the storage file and apply only their own changes, so machines merge; `~/.sync-roms/storage/` mirrors them. The `update-variants` skill (`.claude/skills/update-variants/`) adds variants for new uploads and remembers the ROMs it judged in storage's `variants-checked.json` (shared, through `shared.py`). The `match-translations` skill (`.claude/skills/match-translations/`) matches the fan-translated ROMs waiting in `scrape review` to ScreenScraper games under their original Japanese titles. A metadata entry's optional `qualifier` sets it apart from other ROMs of the same name: its `name` is `<scraped name> (<qualifier>)`, before ` - Translated`, and re-scrapes keep it; the `dedup-names` skill (`.claude/skills/dedup-names/`) finds ROMs of one system shown under the same name and qualifies or re-scrapes them.

Editors and new game titles name MAME, FBNeo and PICO-8 sets through `names.title`: the scraped `name` from `scrapes/<system>/metadata.json`, else the file name (for pico8, without `.p8.png`). `names.py` keeps the scraped names in `~/.sync-roms/cache/names.json` with each metadata file's storage tag and rereads one only when its tag changes, from storage itself (never the mirror). Sync's own paths (`store.set_games`) keep file names.

The `muos` layout (`ROMS/`, BIOS in `MUOS/bios`) takes scraped art in `MUOS/info/catalogue/<system>/box|preview|text`. Collections, with Surprise as one of them, are written by `muos_collections.py` as `MUOS/info/collection/<name>/<ROM>-<hash>.cfg` entries; their art is `MUOS/info/catalogue/Collection/box|grid` (the folder names sync gave art are listed in `.sync-roms-art`, so only those are removed). `saves stash` and `apply` use Pickles' `MUOS/pickles/sram|state` (`muos_saves.py`), copied as they are; a Pickles stash applies only to muOS cards. PICO-8 isn't installed on muOS (a warning says so). `flash` offers every `muos-*.img.gz` in storage's `os/muos/`, with no device matching.

The `rocknix` layout (`roms/<system>`, BIOS flat in `roms/bios`) takes scraped media like Knulli (`gamelist.xml` and `images`/`videos`/`manuals` in the ROM folder). RetroArch saves sit beside the ROMs and states in `roms/savestates/<system>` (`saves stash`/`apply`; standalone-emulator saves such as PSP, PS1 memory cards and N64 aren't covered). ES reads collections only from the device's `/storage/.config/emulationstation/collections`, so `rocknix_collections.py` stages them (Surprise included) in `roms/.sync-roms-collections/` and writes `roms/ports/Install Collections.sh`, which the user launches once from Ports: it copies them, enables them in `es_settings.cfg` and restarts ES (re-run after a sync changes collections; its messages aren't visible on the device). Collection art goes to `roms/_userdata/theme-customizations/art-book-next/`. `flash` offers the `os/rocknix/ROCKNIX-*.img.gz` images, matched per device by `rocknix_image` (the `.tar` update bundle isn't flashable). No GPU drivers and no Onion Surprise app.

Storage's `os/pico8/` holds the official PICO-8 Raspberry Pi zips. `pico8.py` uses the newest `pico-8_*_raspi.zip` (no version in code) and, on every card of these layouts (not `nextui`, where carts are plain ROMs with no installer, nor `muos`), puts it where the frontend's installer looks (`esde` `PICO-8/`, `knulli` `roms/pico8/`) or extracts `pico8_dyn` and `pico8.dat` (`onion` `RApp/PICO-8/bin/`, `allium` `Apps/pico.pak/bin/`, `rocknix` `roms/pico-8/` with `pico8_64` too); the card's `pico8` field records the zip put there. `sync-roms download pico8` (`bbs.py`) adds the PICO-8 BBS Featured carts to storage's `pico8/` under their BBS file names, upgrades newer revisions (renaming references in cards, surprises and collections), and keeps titles and authors in `scrapes/pico8/metadata.json`. PICO-8 is scraped (ScreenScraper system 234); a plain `scrape` also takes carts that have an entry but no `miximages`/`onion` picture in storage (unless ScreenScraper's last answer didn't offer miximages, until `--retry`). A scrape only adds to `scrapes/pico8/metadata.json`: it never changes a field the BBS (or an earlier scrape) already wrote. A `.p8.png` cart with no scraped picture is its own picture: on `esde` and `emudeck` cards it is copied from storage's `pico8/` into `downloaded_media/pico8/miximages/`, on `onion` and `allium` into `Imgs/` (top-level carts only), on `nextui` into the system folder's `.media/`, and on `knulli` the gamelist's `image` points at the cart in the ROM folder.

Storage's `os/onion/` holds the Onion Surprise app zips. `onion_surprise.py` installs the newest `Surprise-v<version>.zip` (by version) as `App/Surprise/` (and its icon, when the zip has one, as `Icons/Default/app/surprise.png`) on `onion` cards with Surprise on, once per zip (the card's `surprise_app` field), and writes `Roms/surprise.json` for the app from the card's surprises that are on the card (removed when there are none).

Storage's `os/onion/`, `os/allium/`, `os/muOS/` (that spelling) and `os/knulli/` and `os/rocknix/` hold RAOfflineProxy (RetroAchievements offline proxy) files, `RAOfflineProxy-<Onion|Allium|muOS|Knulli|Rocknix>-v<version>...`. `raofflineproxy.py` installs the newest of the card's layout (by version), once per file name (the card's `raofflineproxy_app` field), on cards with `raofflineproxy` on: the Onion and Allium zips extract at the card root (`App/RAOfflineProxy/`, `Apps/RAOfflineProxy.pak/`), the muOS `.muxapp` zip into `MUOS/application/RAOfflineProxy/`, each file overwritten in place (the app keeps its login and settings in that folder, so it is never wiped) and reinstalled when its `launch.sh` is missing; the Knulli install script is copied to `roms/tools/RAOfflineProxy Install.sh` (it deletes itself when run, so that is recorded only); the ROCKNIX `-Install.sh` is copied the same way to `roms/ports/RAOfflineProxy Install.sh` and run once from Ports (the official page says `/storage/.config/modules`, which is internal storage). On `esde` cards the app's APK in `os/android/APKs/` is copied by the APK step, and left out when the setting is off. Other layouts get nothing.

Storage's `os/spruceos/` holds spruceOS release files. `spruce_os.py` copies the newest `spruceV<version>.7z` (by version) unextracted to the card root of `spruce` cards, once per file name (the card's `spruce_os` field), for Apps → EZ Updater on the device, after the card's other writes and only when the card has room for it with 64 MiB to spare; only the previously staged file is removed (kept with `--no-delete`). OTA deltas (`spruceOTA-*`) and installers are ignored. The mirror keeps the newest 7z too.

What storage holds (keys, sizes, a bucket's ETags) is read only through `inventory.py`, from `~/.sync-roms/cache/storage-cache.json` (built by `sync-roms cache update`, patched by sync-roms's own writes in `s3.py`); never call `s3.list_sizes`/`stat_sizes`/`list_with_etags`/`list_folders` from elsewhere. Only file contents come from storage.

Game sets are shared storage files, `sets/<id>.json` (the id is the file name), read through `store.load_sets` (`inventory.files` for the listing, `shared.load` for contents, once per run) and saved by `sync-roms sets edit` and the `update-variants` skill. A set file is `{"name", "description"?, "art"?, "games"}`: games have `title`, `system`, `bucket` and optional `files`, `category`, `series` and `variants`; `art` is an `art.json` id, picked like a collection's, and without it a set uses the art under its own id. A set another machine added appears after `sync-roms cache update`; a card naming a set storage doesn't have keeps the id and is warned about. `sync-roms check` validates the sets in storage and notes sets with no art or sharing art.
`~/.sync-roms/storage/` mirrors files that live in storage and are shared (`ignored.json`, the scrape state files under `scrapes/`, `variants-checked.json` and `sets/`) at their storage path, with each mirror's storage tag in `storage/.tags.json` (`shared.py`). `~/.sync-roms/cache/` holds what can be rebuilt: `storage-cache.json`, `preview-cache/`, `previews/`, `theme-art/` and `names.json`. Neither is ever written to storage.

There is no personal core list: a card's `games` is the only games list, and a card with no picks syncs no games. An old `~/.sync-roms/games.json` is left on disk and never read. Old personal sets in `~/.sync-roms/sets/` are left on disk and never read; sets only come from storage. `device-systems.json` is a shared default read from the repo (never copied); users adjust it with the optional add/remove overlay. Never put a real game list in the repo.

`src/sync_roms/data/themes/art-book-next/` holds the Art Book Next collection art (`art/<id>.png`, with a generated `art/README.md` gallery for GitHub that sync never copies: `surprise` plus the ids listed in `art.json`, which a collection or set picks with `"art"`; the art ids include one per set (a set without `"art"` uses the one under its id), and `tools/gen_theme_art.py` draws them all, following the rules under Theme art below) and the logo font's outlines (`logo-font.json`, OFL). Sync copies them into the card's copy of the theme (ES-DE, and EmuDeck's ES-DE folder on the machine; the theme itself is a GitHub archive in storage's `os/esde/themes/`, refreshed by `sync-roms themes update`) or theme customizations (Knulli, ROCKNIX).

A game appears once across all sets: one version per game (arcade original over home ports; else the original lead platform, then the lighter one to emulate; English for text-heavy games), and every set that has the game uses that version. A later version of the same game that adds something (extra content or modes, an HD or handheld remaster) goes in that game's optional `variants`, `[{"bucket", "note"}]`, the note saying in a few words what it adds; variants aren't synced with the set. The editors show a game's variants on its highlighted row, and `v` in the card editor adds one to the card. A version that plays substantially differently is its own game. A compilation is listed only when it holds a game no set lists on its own. Retro Oddities, Handheld Greatest Hits and System Essentials keep their own versions and only lose straight re-releases.

Games in a set file may have an optional `category` string; the set editor groups rows by it (in file order). Prefer one set with categories over several related top-level sets (e.g. `shmups.json`: Touhou, Psikyo, Cave, Other).

Repo files must not contain notes about the bucket's contents ("not in the bucket", "bucket has..."). Device notes say only why the systems were chosen, concisely.

## Theme art

Rules for changing or adding a picture in `tools/gen_theme_art.py` (run it with a Python that has Pillow: `python tools/gen_theme_art.py [id ...]`). The reference is the theme's own Outline set, `_inc/systems/artwork-outline/*.png` in the archive in storage's `os/esde/themes/`: steady off-white lines about 6px wide with a slightly rough edge, corners joined, shapes closed, nothing drawn through a shape in front of it.

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

- One picture per meaning. Before adding one, check `art.json` for an entry that already means the same thing (a genre and a set of the same genre, two kinds of fist). If two exist, ask which to keep; the kept picture goes under the set's id, and the other id is removed from `ART`, `art.json`, `art/` and the tests.
- Draw the thing from the games, not a real-world lookalike: a console light gun (long thin barrel, boxy body, cable), not a pistol.
- A series may get its character when asked. Get the proportions of the right form: Pikachu has long slim ears with a short tip band, a head smaller than its chubby body, small solid eyes and a large stepped tail; wide triangular ears on a big head is Pichu.
- When asked to redo a picture without a subject, say which subject was chosen. When two concepts are equally plausible, show both and let the user pick.

Checking:

- Never finish without looking at the result. Read the generated PNG (the drawing is in y 600..1050), and also crop that part and enlarge it 2x to check every join, line end and overlap.
- Compare with the pictures next to it in a contact sheet of all of `art/`, and show the user that sheet or the changed pictures. Keep review images out of the commit.
- `python -m unittest discover -s tests` checks that every `art.json` id has a PNG; `sync-roms check` notes sets in storage that have no art or share one.

## Devices

`anbernic-rg-sp` ("Anbernic RG SP") is Anbernic's newer, separate device. It is not the RG35XX SP or the RG34XX SP, which are their own entries.

## Setup guide

`src/sync_roms/data/setup-guide.html` (`sync-roms guide` opens it in a browser) is the user's own record of the steps they take by hand to set up a device after sync-roms writes its card: installing apps, the ES-DE, Knulli and RetroArch settings they change, and the standalone emulators they use (where each is installed from and its settings). It is one self-contained page (no external files, scripts or fonts) that works opened straight from disk; picking a device and layout at the top shows only the steps that apply.

- Content lives in the `SECTIONS` array in the page's script. Sections, items and emulators take an optional `when: {platform, layout}` filter; platforms come from `platformOf` (an `esde` card is Android, except `windows-pc`); `systems` matches when the device supports any listed system, and `tier`, `power` (`low`/`mid`/`high`/`desktop`, grouped from the tier in `POWER`), `device` and `dualscreen` (true with `screen2`) also work). The Shaders section's picks live in `SHADER_CATEGORIES` (a preset and a Knulli Shader Set per power level); the RetroAchievements and Cloud saves sections (RetroArch Cloud Sync against `https://cloud-saves.valefor.com/dav/`) hold login and sync settings, never credentials). The Android "Standalone emulators" and "RAOfflineProxy" sections come from the systems each device supports.
- Only write steps and settings the user gave. Leave a section empty rather than guess which apps or settings they use.
- The device list is a copy of `devices.json`, and each device's tier and systems (the tier chain of `device-systems.json` resolved, repo defaults only) are embedded too: after changing either, run `tools/update_setup_guide.py`; `tests/test_setup_guide.py` fails when they differ.

## Notes

- Use `--dryrun` before any `sync` to the bucket; add `--delete` only when explicitly asked.
- Keep the trailing `/` on prefixes so `sync`/`ls` target the directory, not a name prefix.
