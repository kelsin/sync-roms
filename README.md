# 🎮 sync-roms

Interactive script that downloads ROMs and the BIOS files they need from your
S3 bucket into local folders. On first run it asks which bucket to use and saves the
name as `bucket` in `settings.json` in the user data folder. Files you already have (same
size) are skipped, so re-running it only fetches what's new or missing. It can also keep a
[local mirror](#local-mirror---mirror---use-mirror---clear-mirror) of the bucket and sync from that.

## Install

With Homebrew (macOS and Linux):

```bash
brew tap kelsin/tap
brew trust kelsin/tap
brew install sync-roms
```

Recent Homebrew versions refuse to load formulae from a tap you haven't trusted (`Refusing to load formula ... from untrusted tap`), so `brew trust` is needed once per machine. Trusting is your call: it lets Homebrew run this tap's formulae, so read [the formula](https://github.com/kelsin/homebrew-tap/blob/main/Formula/sync-roms.rb) first if you like.

Or with pipx:

```bash
pipx install git+https://github.com/kelsin/sync-roms
```

Then run `sync-roms --help`. The first run asks for your bucket name and saves it.

### Upgrade

```bash
brew update && brew upgrade sync-roms     # Homebrew
pipx upgrade sync-roms                    # pipx
```

Your settings and lists in `~/.sync-roms/` are never touched by an install or upgrade.

### Releasing (maintainers)

Commits and PR titles on `main` use [Conventional Commits](https://www.conventionalcommits.org) and PRs are squash-merged, so the PR title becomes the commit. release-please keeps a release PR open; merging it tags `vX.Y.Z` and attaches the sdist. To publish that version to Homebrew, in a checkout of [kelsin/homebrew-tap](https://github.com/kelsin/homebrew-tap):

```bash
brew bump-formula-pr --version X.Y.Z --url https://github.com/kelsin/sync-roms/releases/download/vX.Y.Z/sync_roms-X.Y.Z.tar.gz kelsin/tap/sync-roms
```

If the Python dependencies changed, run `brew update-python-resources kelsin/tap/sync-roms` first, then `brew test` and `brew audit --strict kelsin/tap/sync-roms`.

## Requirements

- **python3** (3.9+); boto3 is installed with the package
- An AWS profile named **`roms-readonly`** with read access to the bucket
  (set `ROMS_PROFILE` to use a different profile name), defined in `~/.aws/config` and `~/.aws/credentials`
- Only for `--chd`: **7z** and **chdman** (`sync-roms --install-tools` installs them with Homebrew)

## Usage

The examples call the script `sync-roms`. From a clone of the repo, run `python3 -m sync_roms` (with `src/` on `PYTHONPATH`) in its place.

Give the root folder of the card (or any folder to sync into):

```bash
sync-roms BASE_DIR
```

Or give no folder at all. The current directory is used as `BASE_DIR`, so you can
`cd` somewhere and just run:

```bash
sync-roms
```

The ROMs and BIOS folders inside `BASE_DIR` come from the layout you pick (the `layouts` entry in `src/sync_roms/data/layouts.json`):

| Layout | ROMs / BIOS folders | Default for |
| --- | --- | --- |
| `esde` | `ROMs/` `BIOS/` | Anbernic RG Cube, Retroid Pocket Classic, Retroid Pocket 6, Retroid Pocket Nova, Retroid Pocket Flip 2 |
| `knulli` | `roms/` `bios/` (SD card SHARE partition, `/userdata`) | Miyoo Flip V2, Anbernic RG CubeXX, RG40XX V, RG35XX H, RG SP |
| `onion` | `Roms/` `BIOS/` | Miyoo Mini Flip |

Folder names are case-sensitive. Folders that don't exist are shown as
"will be created" and are created after you confirm. If they can't be created
(no permission), the script stops before asking.

The device and layout you pick are remembered by the name of `BASE_DIR`
(e.g. `SHARE`) in `cards.json` in your user data folder
(`$XDG_DATA_HOME/sync-roms` if set, otherwise `~/.sync-roms`, on macOS and Linux;
`%APPDATA%\sync-roms` on Windows). Next time you
sync a folder with that name the saved setup is used without asking. Run with `--ask` (or `-a`) to confirm
it first; answer `n` to pick again, which asks the questions again and saves the new choice. Give cards the
same name if they should share settings.

Then:

1. **Pick a device and a layout** — type to filter, `↑/↓` to move, `Enter` to continue,
   `Esc` to go back. Each device knows the systems that run well on it (`systems` in
   `src/sync_roms/data/device-systems.json`, adjustable with your own overlay; only those are listed) and its default layout (`layout` in
   `src/sync_roms/data/devices.json`, see `layouts`), which is highlighted in the layout list. Or choose Full (every system) and any layout. Systems with no
   folder in the chosen layout are skipped.
2. **Toggle systems** — for a device, its recommended systems that have ROMs start on.
   Otherwise systems whose local folder already has files start on
   (dotfiles ignored), everything else starts off. Systems with no downloadable
   ROMs are hidden and never pre-selected; press `e` to show them (sorted last, dimmed). BIOS files still
   download for any system you select. The status bar shows a running total for the
   selected systems: how much is still left to download (files you already have
   are skipped) and the full size, e.g. `18 selected · 12.3 GB to download (86.1 GB total)`.
   ROMs only; BIOS files aren't counted.

   | Key | Action |
   | --- | --- |
   | `↑` `↓` / `j` `k` | move |
   | `PgUp` `PgDn` | page |
   | `space` `tab` | toggle system |
   | `a` | all on (visible systems) |
   | `n` | all off |
   | `e` | show/hide systems with 0 ROMs |
   | `enter` | start downloading |
   | `q` | quit |

3. Before downloading, a summary shows how many files will be fetched and their
   total size (e.g. `💿 ROMs: 120 to download (3.4 GB), 5 already present`).
4. ROMs download into the layout's ROMs folder (`<system>/`), then the BIOS files for
   the chosen systems download into its BIOS folder (RetroArch system-dir layout).
   Each finished file prints as `[i/N] ✅ gba/Game.gba`. When the local folder name
   differs from the bucket's (e.g. a Knulli device), it prints
   `[i/N] ✅ genesis → megadrive/Game.md` (bucket folder → local folder/file).
5. Scraped data for the chosen systems' games is installed from the bucket's `scrapes/` folder (see
   [Scraped data](#scraped-data---upload-scrapes---clean-scrapes)), converted for the layout:

   | Layout | Media | Metadata |
   | --- | --- | --- |
   | `esde` | `ES-DE/downloaded_media/<system>/<type>/…` (every type) | `ES-DE/gamelists/<system>/gamelist.xml` |
   | `knulli` | `<system>/images`, `videos`, `manuals`, named `Game-image.png`, `-thumb`, `-marquee`, `-fanart`, `-boxback`, `-titleshot`, `-video`, `-manual` | `<system>/gamelist.xml` with name, description, rating, date and the media tags |
   | `onion` | `<system>/Imgs/Game.png`, the 250x360 box art prepared at upload | `<system>/miyoogamelist.xml` with name and image |

   Knulli's main image is the miximage, or the screenshot if there is none. Onion's picture is made
   when the data is uploaded: `--upload-scrapes` resizes the cover (then the 3D box, then the
   screenshot) to a PNG that fits 250x360 and stores it as `scrapes/<system>/onion/<ROM>.png`, so a
   sync just downloads it. The upload also creates any missing Onion art for images that were already
   uploaded earlier. Resizing needs Pillow or macOS `sips` on the machine that uploads. Existing
   gamelists are updated in place: only these tags are set, so favorites, play counts and an
   `<alternativeEmulator>` block stay. Existing files with the same size aren't downloaded again.
   ROMs in subfolders get no Onion art.

   For the `esde` layout every sync also brings the shared extras from `scrapes/esde/`: new or changed
   theme files, collection lines you don't have yet (added to your `.cfg` files), and the shared settings
   (only those keys are set in `es_settings.xml`; close ES-DE first, it rewrites the file when it exits).
6. Finally, media on the card for ROMs the card doesn't have is removed, with no confirmation. It looks at
   every system in the layout, not only the ones you synced, and leaves systems whose ROM folder doesn't
   exist, and folders that aren't systems in `src/sync_roms/data/systems.json` (like ES-DE's `androidapps`), alone.
7. For the `esde` (Android) layout, files in the card's Android media folders (`Alarms`, `Audiobooks`, `DCIM`,
   `Documents`, `Download`, `Movies`, `Music`, `Notifications`, `Pictures`, `Podcasts`, `Recordings`,
   `Ringtones`) are removed and an empty `.nomedia` is put in each of those folders that exists, so Android
   stops indexing them. Missing folders are not created, and `.nomedia` files don't count as files. The first
   time files are found it asks (default no) and remembers the answer for that card name in the same
   `cards.json` as the layout, as `"android_media": "always"` or `"never"`. With `always` it runs every sync
   without asking, even if the folders are already empty; with `never` it is skipped. Saved settings are used
   without asking; with `--ask` they are confirmed first, and answering no asks the question again and saves
   the new answer (or delete that `android_media` entry from `cards.json`).

   Every sync also creates `.metadata_never_index` in the card root, empties `.fseventsd` and puts a
   `.fseventsd/no_log` file in it (on any OS), so macOS doesn't index or log the card.

### Options

| Flag | Description |
| --- | --- |
| `-n`, `--dry-run` | Show what would be downloaded (with total sizes), download nothing. With `--mirror`/`--use-mirror`, show what the mirror would download and delete |
| `-e`, `--edit` | Add/remove games in your local `games.json`, then save it (see below) |
| `-a`, `--ask` | Confirm saved settings (device and layout, Android media folders) instead of using them silently. Answering no asks the question again and saves the new answer |
| `-u`, `--upload-scrapes` | Upload `BASE_DIR/ES-DE` scraped data to the bucket (see below) |
| `-c`, `--clean-scrapes` | Remove scraped data in the bucket for ROMs that aren't available (see below) |
| `--m3u [DIR]` | Create or fix the `.m3u` playlist of every multi-disc game (`Name (Disc 1) (Extra).chd`, `Name (Disc 2).chd`) in `DIR` and its subfolders (default: current directory). The playlist is named after the title without `(Disc N)` or tags the discs don't share (`Name (Sega CD).m3u`). Playlists with the wrong discs are rewritten, ones with some missing files lose those lines, ones with no files left are deleted after asking, and ones listing exactly a game's discs under another name are renamed. Local only; `--dry-run` previews |
| `--chd [DIR]` | Unzip (7z) every `.zip`/`.7z` and convert each disc image (`.cue`, `.gdi`, `.toc`, `.iso`) to a `.chd` with `chdman`, in parallel (up to one file per CPU core; with fewer files than cores each `chdman` gets the spare cores), per the `chd` setting in `systems.json` for the system whose folder it is in (`DIR` is one system folder or a folder of them, default: current directory). The chd is verified before the archive and image files are removed, a failure keeps them, and the `.m3u` playlists of every system folder are fixed afterwards, even when there was nothing to convert (also shown by `--dry-run`). A progress bar (files done and overall percent, from `chdman`'s own progress) shows in a terminal. Mode `cd` uses `createcd`; `dvd` (PS2, PSP) uses `createdvd` for `.iso` files with the system's `args`; `extract` (GameCube, Wii) only unzips and leaves the `.rvz` files. `"m3u": false` skips playlists (3DO). Local only; `--dry-run` previews |
| `--install-tools` | `brew install` the 7z (`sevenzip`) and chdman (`rom-tools`) that `--chd` needs, whichever are missing |
| `--mirror [DIR]` | Make or refresh a local mirror of the bucket (see below). No `DIR`: the saved mirror |
| `--use-mirror DIR` | Same as `--mirror DIR`, then save `DIR` as the local mirror |
| `--clear-mirror` | Forget the saved mirror (its files are left alone) |
| `--devices` | List the supported devices with their chip and the number of systems each one gets, then exit |
| `-h`, `--help` | Show the help screen |

| Environment variable | Description |
| --- | --- |
| `ROMS_PROFILE` | AWS profile to use (default `roms-readonly`) |
| `ROMS_WRITE_PROFILE` | AWS profile used to upload in `--upload-scrapes` and `--clean-scrapes` modes (default `roms`) |
| `NO_COLOR` | Disable colors |

## Scraped data (`--upload-scrapes`, `--clean-scrapes`)

`sync-roms --upload-scrapes [BASE_DIR]` uploads the ES-DE data folder at `BASE_DIR/ES-DE`
(the card root) to `s3://YOUR-BUCKET/scrapes/`. It only reads the ES-DE folder, never
changes it, and never deletes anything in the bucket. Add `--dry-run` to see the plan first;
a real upload asks before it starts (default no).

What goes up, and how it is stored:

| Local | Bucket | Notes |
| --- | --- | --- |
| `gamelists/<system>/gamelist.xml` | `scrapes/<system>/metadata.json` | JSON keyed by ROM path. Only `name`, `desc`, `rating` (0-1), `releasedate` (ISO), `developer`, `publisher`, `genre`, `players`. Favorites, play counts, emulator choices and media tags are dropped. Merged with the bucket's file: local values win, entries only in the bucket stay |
| `downloaded_media/<system>/<type>/…` | `scrapes/<system>/<type>/…` | Only files whose ROM name matches an available ROM. `._` files, dotfiles and `CLEANUP/` are skipped. Uploaded when new or a different size |
| (made from the cover, 3D box or screenshot) | `scrapes/<system>/onion/<ROM>.png` | Onion box art, a PNG that fits 250x360. Created whenever it is missing from the bucket, even if its source image was already uploaded. Not made for ROMs in subfolders. Needs Pillow or `sips` |
| `themes/…` | `scrapes/esde/themes/…` | Per file, same size check. `themes-list` is skipped |
| `collections/*.cfg` | `scrapes/esde/collections/*.cfg` | Union of the lines in both versions |
| `settings/es_settings.xml` | `scrapes/esde/settings.json` | Allowlisted keys only: scraper behavior, miximage generation, theme (not aspect ratio) and gamelist/UI behavior. Credentials are never included. Merged with the bucket's file, local wins |

For uploads, "available ROMs" are the games listed in `games.json` that exist in the bucket, which is
what a sync installs. Scraped files for any other ROM are left out. A `gamelist.xml` that can't be read
is skipped with a warning.

`sync-roms --clean-scrapes` (or `-c`) needs no folder. It compares the bucket's `scrapes/` media and
`metadata.json` entries with every ROM file in the bucket's system folders (not only the games
listed in `games.json`), lists what no longer matches (including whole systems with no folder in the
bucket), and after you confirm (default no) deletes the media and rewrites the metadata files. `--dry-run` only lists. Themes, collections and settings are never
touched.

## Local mirror (`--mirror`, `--use-mirror`, `--clear-mirror`)

`sync-roms --mirror DIR` keeps a local copy of just what the game lists reference, with the bucket's
own key layout: the ROMs a sync installs (every file of a full system), every system's
BIOS files, `scrapes/<system>/` metadata and media for those ROMs, and all of `scrapes/esde/`.
It compares file sizes, so a rerun with nothing changed lists the bucket and downloads nothing.
Anything in the mirror that is no longer referenced (a game removed from `games.json` or from the
bucket) is deleted. `--dry-run` shows the plan. A non-empty folder that isn't already a mirror
(it has no `.sync-roms-mirror` file) is refused.

`sync-roms --use-mirror DIR` does the same and saves `DIR` in `settings.json` in the user data
folder (next to `cards.json`). From then on every sync refreshes the mirror from the bucket first
(if the bucket can't be reached it warns and uses what the mirror has), then does its usual job
with files copied from the mirror instead of downloaded. If `DIR` is missing (an unplugged drive)
it uses the bucket. `--upload-scrapes` and `--clean-scrapes` always work on the bucket itself, and `--edit` lists it;
when one finishes successfully (not with `--dry-run`) the saved mirror is refreshed afterwards, so it picks up the change.
`sync-roms --clear-mirror` removes the setting (the mirror's files stay); `sync-roms --mirror` alone
refreshes the saved mirror. Each flag is its own mode and can't be combined with `--edit`, `--upload-scrapes`
or `--clean-scrapes`.

## Editing the game list (`--edit`)

Edits `~/.sync-roms/games.json`, the list of games you sync. A fresh install starts with no games, so
every system shows 0 ROMs until you add some here. The bucket is only read to show what is in it, so the
read-only profile is enough. No folders are needed:

```bash
sync-roms --edit
```

1. Pick **By system** or **By set**, then type to filter the list (every word you type must
   match) and `Enter` to pick one. `Esc` goes back; `Esc` at the first menu finishes.
2. For a system you see every file in its bucket folder. For a set (a curated list in the
   package's `data/sets/*.json`) you see its games from every system, sorted by system then title.
   `✅` is already in `games.json`, `⬜` is not. Type to filter, `Tab` toggles the game
   under the cursor, `^A` toggles everything currently shown, `Enter` or `Esc` keeps your changes.
   Pending changes show as `➕` / `➖`. `games.json` doesn't record sets: a game is on if it's listed.
3. When you finish, you get a summary of additions and removals per system and a confirmation
   prompt. On yes, `~/.sync-roms/games.json` is saved; on no, nothing is. Nothing is uploaded.

A set file is `{"name": ..., "description": ..., "games": [{"title": ..., "system": "gba", "bucket": "gba/Game.zip"}]}`.
A multi-disc game adds `"files": [...]` with its other bucket keys (the discs); `bucket` is the playlist (`.m3u`) or disc 1.
Toggling the game adds or removes every file, one `games.json` entry each.
Entries for an unknown system are skipped with a warning. Games of a full system show greyed out with a 🔒: they are always synced and can't be toggled.

Removing a game only drops it from `games.json`; the file stays in the bucket.

### Full systems

A system can sync every file in its bucket folder (subfolders included) instead of a game list, so adding
a file to the bucket is enough to publish it. Set its entry in `games.json` to `{"full_system": true}`
instead of a list:

```json
{ "gb": { "full_system": true } }
```

No system is a full system by default. `--edit` skips full systems and keeps their entry.

## Converting to CHD (`--chd`)

Run it on a card or a single system folder after syncing:

```bash
sync-roms --install-tools                # once: brew install sevenzip rom-tools
sync-roms --chd --dry-run /Volumes/SD/ROMs
sync-roms --chd /Volumes/SD/ROMs/psx
```

Each system's behaviour is the `chd` setting in `src/sync_roms/data/systems.json`:

| `mode` | Systems | What happens |
|---|---|---|
| `cd` | Sega CD, Saturn, TurboGrafx-CD, PC-FX, Neo Geo CD, PS1, 3DO, Dreamcast | `chdman createcd` from the `.cue`/`.gdi`/`.toc` (or `.iso`) |
| `dvd` | PS2, PSP | `chdman createdvd` for `.iso` files plus the system's `args` (PS2 `-c zlib`, PSP `-hs 2048`); bin/cue games use `createcd` |
| `extract` | GameCube, Wii | archives are unzipped and the files (e.g. `.rvz`) left as they are; nothing is converted |

`"m3u": false` (3DO) skips the playlist step, since Opera can't load `.m3u` files. Systems without a `chd` setting are ignored.

Every `.chd` is verified with `chdman verify` before its archive, `.cue`, `.bin` and `.iso` files are deleted; on any failure the originals are kept. Each `.chd` is written under a hidden `.part` name and renamed only after it verifies. `Ctrl-C` stops `7z` and `chdman`, removes the partial files and exits (130) without starting anything else; a rerun picks up where it stopped, and also deletes the extraction folders (`.chd-*`) a hard kill left behind.

It is meant for preparing a downloaded rom pack before you upload it to the bucket, so the bucket holds the `.chd` and `.m3u` files and `games.json` lists those names. Running it on a card synced from a bucket that still has the `.zip` files makes the next `sync-roms` run list the `.chd` files as files not in your game list (it asks before deleting, default no) and download the zips again.

## How it works

- Reads the systems, layouts, devices and BIOS requirements from `src/sync_roms/data/` in the package, each device's
  recommended systems (`device-systems.json`) too, and your games (`games.json`) from `~/.sync-roms/`, never from
  the bucket. `games.json` is copied there from the package's starter version on first run. An optional
  `~/.sync-roms/device-systems.json` adjusts a device's recommended systems:
  `{"miyoo-flip-v2": {"add": ["psx"], "remove": ["gba"]}}` (system ids as in `systems.json`; the package's
  order is kept and notes always come from the package). An old full-copy `device-systems.json` from before the overlay does nothing; delete it. BIOS files are always `BIOS/<file>` in the bucket.
- Bucket folders use the ES-DE system name (e.g. `gba/`, `dreamcast/`).
- Lists each chosen system's bucket folder once and compares file sizes, so only
  missing or changed files are downloaded (for `full_system` systems, every file in the folder) (8 in parallel, via boto3).
- Local files in a chosen system's folder that are no longer in its `games.json` list
  are listed and deleted only after you confirm (default **no**; `--dry-run` shows them).
  Folders of systems you didn't pick, BIOS files and dotfiles are never touched.
  Files frontends add to ROM folders are ignored too (never counted as "already has files",
  never deleted): ES-DE `systeminfo.txt` / `noload.txt`, Knulli/Batocera `_info.txt`,
  `gamelist.xml` and the `images/`, `videos/`, `manuals/` folders, Onion `miyoogamelist.xml`
  and `Imgs/` (top level of a system folder only), and Windows `Thumbs.db` / `desktop.ini`.
- Some systems share a local folder on a device (Onion: `WS` = WonderSwan + Color,
  `NGP` = Neo Geo Pocket + Color). A folder's expected files are the
  union of all those systems' lists, so syncing one never offers the other's ROMs for deletion.
- Every BIOS file listed for a chosen system is downloaded; there is no required/optional distinction.
  BIOS lists come from the ES-DE default libretro cores, so they may not match what Knulli
  or Onion use; on Knulli check Game Settings > Missing Bios Check.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `AccessDenied` / `Unable to locate credentials` | Define the `roms-readonly` profile in `~/.aws/config` and `~/.aws/credentials` |
| "listed in manifest but not in bucket" warnings | A game in your `games.json` (or a required BIOS file) isn't in the bucket; it is skipped |
| A system shows `(0 roms)` | Your `games.json` has no games for that system, or none of them are in the bucket (BIOS is still fetched if selected). Add games with `--edit` |
