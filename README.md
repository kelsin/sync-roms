# 🎮 sync-roms

Interactive script that downloads ROMs and the BIOS files they need from your
S3 bucket into local folders. On first run it asks which bucket to use and saves the
name as `bucket` in `settings.json` in the user data folder. It also asks for an optional custom S3
endpoint URL (blank for AWS), saved as `endpoint`, for S3-compatible storage such as MinIO or Cloudflare R2
(requests then use path-style addressing). Instead of a bucket you can give an absolute folder path (for example a mounted
network share, `/Volumes/roms`, or `~/roms`); it is saved as `root` and replaces the bucket and AWS entirely, with the same
layout (`<system>/…`, `BIOS/…`, `scrapes/…`). An answer with a `/` (other than `s3://…`) or naming an existing folder is a
folder, never a bucket name. With no terminal to ask on, set `ROMS_BUCKET` or `ROMS_ROOT` (or pass `--bucket` or `--root`). Files you already have (same
size) are skipped, so re-running it only fetches what's new or missing. It can also keep a
[local mirror](#local-mirror---mirror---use-mirror---clear-mirror) of storage and sync from that.

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

Then run `sync-roms --help`. The first run asks for your storage (a bucket name or a folder path) and saves it.

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

- **python3** (3.12+); boto3, textual and textual-image (which brings Pillow) are installed with the package
- An AWS profile named **`roms-readonly`** with read access to storage (not needed with a storage folder)
  (set `ROMS_PROFILE` to use a different profile name), defined in `~/.aws/config` and `~/.aws/credentials`
- Only for `--cd`: **7z** and **chdman** (`sync-roms --install-tools` installs them with Homebrew), plus **extract-xiso** for Xbox (no Homebrew formula: build it from [XboxDev/extract-xiso](https://github.com/XboxDev/extract-xiso) with `cmake -B build && cmake --build build`) and **iso2zar** for Xbox 360 (no formula: build it from [iso2zar](https://codeberg.org/NeverAnswers/iso2zar) with `cargo build --release`)

### AWS profiles

Create the read-only profile (used for everything that only reads) and, if you upload
scrapes, the write profile. Each asks for an access key, secret, and region (`us-east-1`):

```bash
aws configure --profile roms-readonly
aws configure --profile roms
```

#### Transfer speed (AWS CLI only)

These `s3` settings are read by the `aws s3 cp`/`sync` commands, not by `sync-roms`
itself (which uses boto3 and its own worker pool). Set them if you also move files with
the AWS CLI. The defaults are 10 concurrent requests and 8MB multipart chunks. `--upload` and
`--upload-scrapes` size their own parallelism from your CPU cores and don't need them.

```bash
for p in roms-readonly roms; do
  aws configure set s3.max_concurrent_requests 32 --profile $p
  aws configure set s3.max_queue_size 2000 --profile $p
  aws configure set s3.multipart_threshold 64MB --profile $p
  aws configure set s3.multipart_chunksize 32MB --profile $p
done
```

The threshold and chunk size apply in both directions: large files move as parallel
32MB ranges on download and 32MB parts on upload.

Concurrency is the setting that matters most for many small files. Lower it if your
router or uplink starts timing out.

## Usage

The examples call `sync-roms`. From a clone of the repo, run `python3 -m sync_roms` (with `src/` on `PYTHONPATH`) in its place.

Give the root folder of the card (or any folder to sync into):

```bash
sync-roms BASE_DIR
```

Or give no folder at all. The current directory is used as `BASE_DIR`, so you can
`cd` somewhere and just run:

```bash
sync-roms
```

You pick a device, then the firmware it runs (a device with only one isn't asked). The firmware decides the ROMs and BIOS folders inside `BASE_DIR` (the `layouts` entry in `src/sync_roms/data/layouts.json`), and each device lists its firmwares in `devices.json`, the first being the default:

| Firmware | ROMs / BIOS folders | Notes |
| --- | --- | --- |
| `esde` | `ROMs/` `BIOS/` | Android devices with ES-DE |
| `knulli` | `roms/` `bios/` (SD card SHARE partition, `/userdata`) | Default for the Anbernic H700, RG Vita Pro and Miyoo Flip V2 handhelds |
| `muos` | `ROMS/` `MUOS/bios/` | [muOS](https://muos.dev/) on the Anbernic H700 handhelds, RG CubeXX and RG Vita Pro. Folder names are matched ignoring case and separators |
| `slot` | `Games/` `BIOS/` | [slot](https://slot-cfw.fyi) on the RG SP, RG34XX, RG34XX SP, RG35XX SP, RG35XX Plus, RG28XX and RG35XX H. Game Boy, Game Boy Color and Game Boy Advance only. ROMs are extracted from their archives and go straight into the system folder, never subfolders |
| `onion` | `Roms/` `BIOS/` | Miyoo Mini Flip, on [Onion](https://onionui.github.io/) |
| `allium` | `Roms/` `BIOS/` | Miyoo Mini Flip, on [Allium](https://github.com/goweiwen/Allium). Same folders and `Imgs/` box art as `onion`, but with a full `gamelist.xml` |
| `emudeck` | `Emulation/roms/` `Emulation/bios/` | [EmuDeck](https://emudeck.github.io/) on the Steam Deck and Steam Machine. Wii U, Xbox 360 and Model 2 ROMs go in a `roms/` subfolder of their system folder. Scraped media only, no gamelists |

Folder names are case-sensitive. Folders that don't exist are shown as
"will be created" and are created after you confirm. If they can't be created
(no permission), sync-roms stops before asking.

The device and firmware you pick are remembered by the name of `BASE_DIR`
(e.g. `SHARE`) in `cards.json` in your user data folder
(`$XDG_DATA_HOME/sync-roms` if set, otherwise `~/.sync-roms`, on macOS and Linux;
`%APPDATA%\sync-roms` on Windows). Next time you
sync a folder with that name the saved setup is used without asking. Run with `--ask` (or `-a`) to confirm
it first; answer `n` to pick again, which asks the questions again and saves the new choice. Give cards the
same name if they should share settings.

Then:

1. **Pick a device and a firmware** — `/` to filter, `j`/`k` to move, `Enter` to continue,
   `Esc` to go back. Each device knows the systems that run well on it (`systems` in
   `src/sync_roms/data/device-systems.json`, adjustable with your own overlay; only those are listed) and its firmwares (`firmwares` in
   `src/sync_roms/data/devices.json`, see `layouts`; the first is highlighted). Or choose Full (every system) and any firmware. Systems with no
   folder in the chosen firmware are skipped.
2. **Edit the card** — every system with games picked on the card syncs. After the [Surprise](#surprise) step,
   a sync in a terminal opens the [card editor](#editing-the-game-list---edit) on the card; `Esc` there goes on with the sync.
   Its bottom line also shows how much a sync would download (`⬇️  12.3 GB to download`: ROMs not on the card yet;
   scraped files and BIOS aren't counted), updated as you add games, sets and collections.

### List keys

Every list works the same way, vim-style with Emacs line editing:

| Key | Action |
| --- | --- |
| `j` `k` `↑` `↓` `^N` `^P` | move |
| `g` `G` | top / bottom |
| `^D` `^U` | half page |
| `^F` `^B` `PgUp` `PgDn` `^V` | page |
| `/` | filter: type words that must all match |
| `Enter` (while filtering) | pick the highlighted row; in lists with checkboxes, keep the filter and go back to moving |
| `Tab` (while filtering) | keep the filter and go back to moving |
| `Esc` / `^G` | clear the filter, then go back / cancel |
| `Space` `Tab` | toggle (lists with checkboxes) |
| `a` `o` `u` | all or none shown / cycle view / revert (lists with checkboxes) |
| `?` | every key of the list, including the list's own (scroll with `j` `k`; `Esc`, `q` or `?` closes it) |

The hint line under the filter starts with `? help`. The bottom line ends with the highlighted row's number and how many
rows the filter shows (`row 12 · 340/3700 shown`) when the list's own status (a card's size, say) leaves room for it. Leaving a game list for
`s`, `m`, `p` or `v` and coming back keeps your row, filter and view when the list shows the same games.

While typing a filter (or a note, which `w` opens in the game list): `^A` `^E` start/end of line, `^B` `^F` left/right, `^D` delete a character, `^K` kill to end, `^U` kill to start, `^W` kill a word.

3. Before downloading, a summary shows how many files will be fetched and their
   total size (e.g. `💿 ROMs: 120 to download (3.4 GB), 5 already present`).
4. ROMs download into the layout's ROMs folder (`<system>/`), then the BIOS files for
   the card's systems download into its BIOS folder (RetroArch system-dir layout). A system's
   `rom_files` (MAME-style BIOS zips such as `gamate.zip`) are kept in storage's `BIOS/` too, but copied
   into that system's ROM folder instead, while it has ROMs to sync.
   Each finished file prints as `[i/N] ✅ gba/Game.gba`. When the local folder name
   differs from storage's (e.g. a Knulli device), it prints
   `[i/N] ✅ genesis → megadrive/Game.md` (storage folder → local folder/file).
5. Scraped data for the card's games is installed from storage's `scrapes/` folder (see
   [Scraped data](#scraped-data---upload-scrapes---clean-scrapes)), converted for the layout:

   | Firmware | Media | Metadata |
   | --- | --- | --- |
   | `esde` | `ES-DE/downloaded_media/<system>/<type>/…` (every type) | `ES-DE/gamelists/<system>/gamelist.xml` |
   | `knulli` | `<system>/images`, `videos`, `manuals`, named `Game-image.png`, `-thumb`, `-marquee`, `-fanart`, `-boxback`, `-titleshot`, `-video`, `-manual` | `<system>/gamelist.xml` with name, description, rating, date and the media tags |
   | `onion` | `<system>/Imgs/Game.png`, the 250x360 box art prepared at upload | `<system>/miyoogamelist.xml` with name and image |
   | `allium` | same `Imgs/` box art as `onion` | `<system>/gamelist.xml` with name, image, rating, date, developer, publisher and genre |
   | `muos` | `MUOS/info/catalogue/<system>/box/Game.png` (cover, then 3D box) and `preview/Game.png` (screenshot, then title screen), as uploaded | `text/Game.txt` with the description |
   | `slot` | `Labels/<system>/Game.png`, the cart label prepared at upload | none |
   | `emudeck` | `Emulation/tools/downloaded_media/<system>/<type>/…` (every type) | none: ES-DE keeps gamelists in `~/ES-DE`, off the card |

   For `esde` and `emudeck`, `<system>` is the system's ES-DE folder name (`sg-1000`, `n3ds`): systems that share a
   ROM folder, like `3ds` and `n3ds`, share its media and gamelist folders, and an upload sends each file back to the
   system whose ROM it matches. muOS and Slot keep their media in folders of their own, flat even for ROMs in subfolders. An existing
   `.txt` is rewritten only when the description differs.

   Knulli's main image is the miximage, or the screenshot if there is none. Onion's picture is made
   when the data is uploaded: `--upload-scrapes` resizes the cover (then the 3D box, then the
   screenshot) to a PNG that fits 250x360 and stores it as `scrapes/<system>/onion/<ROM>.png`, so a
   sync just downloads it. The upload also creates any missing Onion art for images that were already
   uploaded earlier. Resizing needs Pillow or macOS `sips` on the machine that uploads. Existing
   gamelists are updated in place: only these tags are set, so favorites, play counts and an
   `<alternativeEmulator>` block stay. Existing files with the same size aren't downloaded again.
   ROMs in subfolders get no Onion art. Slot's labels are made the same way (cover, then 3D box, then
   screenshot) as a PNG that fits the cart's label: 1280x661 for Game Boy Advance, 1024x901 for Game Boy
   and Game Boy Color, stored as `scrapes/<system>/slot/<ROM>.png`. Labels made in Cart Studio can be uploaded
   straight from a Slot card with `--upload-scrapes CARD`: its `Labels/GB`, `GBC` and `GBA` PNGs named after a ROM
   in storage go to the same place as they are, replacing a label of a different size (the derived one is only
   made when none exists). `--mirror` and a Slot sync pick them up like any other label.

   On `esde`, `knulli`, `onion` and `allium`, `mame` and `fbneo` clones are named after their variant, e.g. `1942 (Revision A)`,
   from `src/sync_roms/data/clones.json` (MAME and FBNeo parent/clone data), replacing the scraped name. On `esde` a
   `sortname` also keeps each parent followed by its clones. ES-DE's "strip extra MAME info" option hides the variant
   in parentheses. Regenerate the file with `tools/gen_clones.py MAME.xml FBNEO.dat` (MAME's `-listxml` output and
   FBNeo's arcade DAT).
6. Finally, media on the card for ROMs the card doesn't have is removed, with no confirmation. It looks at
   every system in the layout, not only the ones you synced, and leaves systems whose ROM folder doesn't
   exist, and folders that aren't systems in `src/sync_roms/data/systems.json` (like ES-DE's `androidapps`), alone.
   This assumes the card's art comes from this app: on muOS it removes `box`, `preview` and `text` files in
   `MUOS/info/catalogue/<system>/` (names compared ignoring case; systems that share a catalogue folder, like
   the arcade ones, are judged together; `grid`, `manual`, `overlay` and the other catalogue areas are left
   alone), and on Slot the labels in `Labels/GBA`, `GB` and `GBC` (names compared the way Slot does, ignoring
   case and bracketed tags). A muOS or Slot folder whose ROM folders hold no ROMs is skipped, so art isn't
   wiped from a card whose ROMs are elsewhere (muOS can keep them on SD2). Art you add by hand or install
   from a `.muxcat` set for ROMs that aren't on the card is removed too.
7. For the `esde` (Android) layout, everything in storage's `os/android/APKs/` folder (APKs, the Obtainium app list) is
   copied to an `APKs/` folder on the card so the apps can be installed from the device. For the `onion` layout
   (not Allium), everything under storage's `os/onion/Themes/` is copied to the card's `Themes/` the same way,
   skipping files already there with the same size and never deleting anything. Also, files in the card's Android media folders (`Alarms`, `Audiobooks`, `DCIM`,
   `Documents`, `Download`, `Movies`, `Music`, `Notifications`, `Pictures`, `Podcasts`, `Recordings`,
   `Ringtones`) are removed and an empty `.nomedia` is put in each of those folders that exists, so Android
   stops indexing them. Missing folders are not created, and `.nomedia` files don't count as files. The first
   time files are found it asks (default no) and remembers the answer for that card name in the same
   `cards.json` as the layout, as `"android_media": "always"` or `"never"`. With `always` it runs every sync
   without asking, even if the folders are already empty; with `never` it is skipped. Saved settings are used
   without asking; with `--ask` they are confirmed first, and answering no asks the question again and saves
   the new answer (or delete that `android_media` entry from `cards.json`).

   Android cards also get suggested GPU drivers. Each Adreno device in `devices.json` has a `gpu`, and
   `drivers.json` lists the custom drivers (Turnip builds and similar) suggested for each GPU. Every sync checks
   those drivers' GitHub releases and keeps the newest zip of each in storage's `os/drivers/` (with a `.tag` file
   naming the release; skipped without write access, a failure only warns), then copies the ones for the card's GPU
   to `Drivers/<driver>-<release tag>.zip` in the card root. A newer release gets a new file name and the old zip is
   removed; the card's `cards.json` entry lists the zips sync put there (`drivers`), so files you add yourself are
   never touched. To use one, open the emulator's driver manager (for example the GPU driver settings of Winlator,
   Eden or another emulator that loads custom drivers), choose to install or import a driver and pick the zip from
   `Drivers/`. Drivers load per app, so nothing changes system-wide and no root is needed.

   Every sync also creates `.metadata_never_index` in the card root, empties `.fseventsd` and puts a
   `.fseventsd/no_log` file in it (on any OS), so macOS doesn't index or log the card.

### Commands

Every mode is a command (`sync-roms COMMAND --help` explains one; plain `sync-roms [CARD]` syncs a card):

| Command | Does | Old flag |
| --- | --- | --- |
| `sync [CARD]` | download ROMs, BIOS and scraped data to a card | (default) |
| `edit`, `games edit`, `cards edit` | interactive list editor | `--edit` |
| `games list\|add\|remove\|full\|sets\|export\|import` | edit lists from scripts, see below | |
| `sets edit` | edit the repo's game sets by hand and open a PR (needs `git` and a logged-in `gh`) | |
| `collections edit` | edit your collections of favourite games (saved in `~/.sync-roms/collections/`) | |
| `themes update` | put the latest Art Book Next for ES-DE (for collections' theme art) in storage | |
| `cards list\|new\|set\|rename\|delete` | manage cards | |
| `devices [ID]` | list devices, or one device's systems (`--json`) | `--devices` |
| `upload roms [DIR]` / `upload scrapes [CARD]` | upload to storage | `--upload`, `--upload-scrapes` |
| `diff [DIR]` | compare a folder with storage | `--diff` |
| `scrape [SYSTEM \| match SYSTEM ROM GAME \| review [SYSTEM] \| missing [SYSTEM]]` / `scrape --set-credentials` | scrape ROMs with no metadata from ScreenScraper, review the non-game and unknown ones, or list them all | `--scrape`, `--scrape-match`, `--scrape-review`, `--scrape-missing` |
| `clean scrapes` | remove scrapes of ROMs not in storage | `--clean-scrapes` |
| `playlist [DIR]` | fix `.m3u` playlists | `--m3u` |
| `convert [DIR]` | convert disc images to CHD | `--cd`, `--chd` |
| `tools install` | install 7z and chdman | `--install-tools` |
| `mirror [DIR]` / `mirror use DIR` / `mirror clear` | local mirror | `--mirror`, `--use-mirror`, `--clear-mirror` |
| `cache [update [--full]]` | show the storage cache, or read all of storage into it (see below) | |
| `config show\|path` | effective settings and where each came from | |
| `doctor` | check AWS profile, storage, tools and data files | |
| `check` | validate your JSON data files | |
| `completion bash\|zsh\|fish` | shell completion script | |

The old flags keep working. Flags that make no sense for a command (`--dry-run` with `games edit`, `--replace` without `upload roms`) are refused rather than ignored, and abbreviations like `--up` are not accepted. A card folder named like a command: write `./edit`.

### Unattended use

`--yes` answers every prompt with its default (deleting local files stays "no"). A first sync can skip the setup picker:

```bash
sync-roms sync /Volumes/SD --device anbernic-rg35xx-sp --layout knulli --yes
sync-roms sync /Volumes/SD --dry-run     # preview a saved card
```

Without a terminal and without those flags the pickers fail with the flag to use. Prompts read from a closed stdin take their default.

Exit codes: `0` done (or nothing to do, or you declined), `1` some files failed, `2` bad usage, `3` setup problem (credentials, storage, missing tool, unreadable data file), `130` interrupted. Errors go to stderr; `NO_COLOR` and `FORCE_COLOR` control colors.

Before downloading, the sync shows the totals (scraped media included, on layouts that take it) and free space on the card and asks. When there isn't enough space and nobody can be asked (`--yes`, or no terminal), the sync fails with exit 1. Local ROMs no longer in the selection are listed and deleted first (after you confirm), so the free space shown is accurate. `--dry-run` shows the same free space (counting the ROMs it would delete as freed) and says when the downloads would not fit; its `--json` document lists scraped media in `downloads` with kind `scrape`, counts them in `totals`, and has the free space in bytes as `free_space`.

A run ends with one line: the files and bytes downloaded, the time it took, the listed ROMs not in storage and any failures. A second `Ctrl-C` during downloads stops at once and removes the partly downloaded files.

On `esde` and `emudeck` cards every Vita game zip in `psvita/` gets a `.psvita` file beside it holding the game's title id (read from the zip's `param.sfo`), which is what ES-DE launches Vita3K with; the zip itself is left as it is for Vita3K to install. The `.psvita` file is kept while its zip is in the selection and deleted with the other unwanted files once it isn't. A synced Vita game also brings its DLC and newest update from `psvita/` (matched by the title id in the file names), on every layout; the editors and Surprise list only games.

### Options

| Flag | Description |
| --- | --- |
| `-n`, `--dry-run` | Show what would be downloaded (with total sizes), download nothing. With `--mirror`/`--use-mirror`, show what the mirror would download and delete. Commands that only read (`diff`, `check`, `doctor`, `cache`, `config`, `completion`, `games list`/`export`/`sets list`) or can't honor it (`edit`, `scrape review`, `scrape missing`, ...) refuse it with exit 2 |
| `-e`, `--edit` | Add/remove games in a card's list, then save (see below) |
| `-a`, `--ask` | Confirm saved settings (device and layout, Android media folders) instead of using them silently. Answering no asks the question again and saves the new answer |
| `-u`, `--upload-scrapes` | (`-u` is deprecated: it is not `--upload`) Upload `BASE_DIR/ES-DE` scraped data to storage (see below) |
| `--upload [DIR]` | Upload the ROMs in `DIR` and its subfolders (default: current directory) to storage folder of a system you pick; the system is guessed from the folder name (see below) |
| `-c`, `--clean-scrapes` | Remove scraped data in storage for ROMs that aren't available (see below) |
| `--m3u [DIR]` | Create or fix the `.m3u` playlist of every multi-disc game (`Name (Disc 1) (Extra).chd`, `Name (Disc 2).chd`) in `DIR` and its subfolders (default: current directory). The playlist is named after the title without `(Disc N)` or tags the discs don't share (`Name (Sega CD).m3u`). Playlists with the wrong discs are rewritten, ones with some missing files lose those lines, ones with no files left are deleted after asking, and ones listing exactly a game's discs under another name are renamed. Local only; `--dry-run` previews |
| `--cd [DIR]`, `--chd [DIR]` | (`--chd` is the old name) Unzip (7z, or unar for `.rar` when installed, since 7-Zip can't decode some RAR 2.9 archives) every `.zip`/`.7z`/`.rar` (and the archives inside it, up to 3 levels, except for `extract` systems) and convert each disc image (`.cue`, `.gdi`, `.toc`, `.iso`) to a `.chd` with `chdman`, in parallel (up to one file per CPU core, and only as many at once as their unpacked files fit in free space; with fewer files than cores each `chdman` gets the spare cores). An archive that converts is unpacked in the system temp folder when that is on another drive than `DIR` and has room for it with a margin of 10% of its free space or 1 GiB, whichever is larger (the size comes from the `.zip`/`.7z` listing), else beside the archive; the outputs are always written and verified in `DIR`, per the `chd` setting in `systems.json` for the system whose folder it is in (`DIR` is one system folder or a folder of them, default: current directory). The chd is verified before the archive and image files are removed, a failure keeps them, and the `.m3u` playlists of every system folder are fixed afterwards, even when there was nothing to convert (also shown by `--dry-run`). The biggest files start first. A progress bar shows in a terminal: files done and the overall percent of the total size (each file counts by its size, its unpacked size for a `.zip`/`.7z`; an archive counts 20% once unpacked and its discs share the rest, from `chdman`'s own progress), with the rate and time left; each file's result prints as it finishes. Mode `cd` uses `createcd`; `dvd` (PS2, PS3, PSP) uses `createdvd` for `.iso` files with the system's `args`; `extract` (GameCube, Wii) only unzips and leaves the `.rvz`/`.iso` files; `xiso` (Xbox) rewrites each `.iso` that isn't already an xiso with `extract-xiso -r` and checks it with `-l`; `zar` (Xbox 360) compresses each `.iso` into a `.zar` with `iso2zar` and removes the iso. `"m3u": false` skips playlists (3DO). Local only; `--dry-run` previews |
| `--install-tools` | `brew install` the 7z (`sevenzip`), unar and chdman (`rom-tools`) that `--cd` needs, whichever are missing, and say how to build extract-xiso |
| `--mirror [DIR]` | Make or refresh a local mirror of storage (see below). No `DIR`: the saved mirror |
| `--use-mirror DIR` | Same as `--mirror DIR`, then save `DIR` as the local mirror |
| `--clear-mirror` | Forget the saved mirror (its files are left alone) |
| `--diff [DIR]` | Compare a folder with a bucket system's folder (the old form of `diff`; see `--system`) |
| `--replace` | `upload roms` only: make the storage folder match `DIR`. Renamed files are moved by content (big bucket files without an MD5 are compared on samples, and those renames are marked) and left-over storage files are listed so you pick which to delete |
| `--devices` | List the supported devices with their chip and the number of systems each one gets, then exit |
| `-y`, `--yes` | Answer prompts with their default |
| `--device ID\|full`, `--layout NAME` | Sync: choose the setup without the picker (it is saved for the card) |
| `--size SIZE` | `cards new` / `cards set`: the card's size as people read it (`256`, `512GB`, `1TB`), saved in `cards.json` and shown by `cards list` and on sync |
| `--no-clean` | Sync: skip the end-of-run card tidy |
| `--no-eject` | Sync: leave the card mounted. By default, on a Mac, a run with no failures ends with `diskutil unmountDisk` on the card's disk (removable or external disks only), so every volume on it is unmounted and the card can be pulled. `"eject": false` in `settings.json` turns it off for every run |
| `--json` | `devices`, `games list`, `cards list`, `diff` and `sync --dry-run`: one JSON document on stdout, nothing else (pass `--device`/`--layout` so no picker is needed; `diff` also needs `--system ID` unless the folder is named after a system) |
| `--card NAME` | `games` commands: the card whose games to change (required; see Editing from scripts) |
| `--system ID` | `diff`: the system to compare with, instead of the picker. `scrape`, `scrape missing`: only that storage folder (the same as `scrape SYSTEM`) |
| `--scrape` | Scrape the ROMs that have no metadata from ScreenScraper (the old form of `scrape`; see Scraping from ScreenScraper) |
| `--scrape-match SYSTEM ROM GAME` | Tell the scraper which ScreenScraper game a ROM is, then scrape it (the old form of `scrape match`) |
| `--scrape-review [SYSTEM]` | Review the ROMs ScreenScraper calls non-games or doesn't know (the old form of `scrape review`) |
| `--scrape-missing [SYSTEM]` | List the ROMs with no metadata and why (the old form of `scrape missing`) |
| `--all` | `scrape`, `scrape missing`: every ROM in the storage, not only the games your lists and sets reference |
| `--retry` | `scrape`: also try the ROMs ScreenScraper didn't know before (ROMs whose lookup failed are always tried again; non-games never are); with `--fill-media`, also the ROMs missing only media ScreenScraper didn't offer |
| `--fill-media` | `scrape`: also scrape ROMs that have metadata but lack some media type in storage; their metadata is kept. Media types ScreenScraper didn't offer for a ROM are remembered, and a ROM missing only those isn't asked for again until `--retry` |
| `--skip-media TYPES` | `scrape`, `scrape match`: comma-separated media folders not to download (e.g. `manuals,fanart`) |
| `--set-credentials` | `scrape`: ask for your ScreenScraper username and password and save them in `settings.json` |
| `--full` | `cache update`: in a storage folder, list every folder and stat every file, not only the changed folders and the files the cache doesn't have (see Storage cache) |
| `--bucket-keys` | `check`: also verify with the read-only profile that every game key in your lists and sets exists in storage |
| `--quiet` | Print only errors (failed files and a sync's failure count included, and `check`'s problems), warnings and `--json` data, all on stderr except the JSON; prompts are asked on stderr |
| `--verbose` | Also print the effective settings and where each came from, on stderr |
| `--profile P`, `--write-profile P`, `--bucket B`, `--root DIR`, `--endpoint URL` | Override those settings for this run. Precedence: flag, then environment variable, then `settings.json`, then the default |
| `--version` | Print the version |
| `-h`, `--help` | Show the help screen (`sync-roms COMMAND --help` or `sync-roms help COMMAND` for one command) |

| Environment variable | Description |
| --- | --- |
| `ROMS_BUCKET` | S3 bucket name. Overrides `bucket` in `settings.json`; when set, the first-run prompt is skipped |
| `ROMS_ROOT` | Folder (e.g. a mounted network share) used instead of storage. Overrides `root` in `settings.json`; wins over a bucket setting. Needs no AWS profile |
| `ROMS_ENDPOINT` | Custom S3 endpoint URL. Overrides `endpoint` in `settings.json` (default: AWS) |
| `ROMS_PROFILE` | AWS profile to use. Overrides `profile` in `settings.json` (default `roms-readonly`) |
| `ROMS_WRITE_PROFILE` | AWS profile used to write in `--upload`, `--upload-scrapes`, `--clean-scrapes` and `scrape` modes. Overrides `write_profile` in `settings.json` (default `roms`) |
| `NO_COLOR` | Disable colors |

## Uploading ROMs (`--upload`)

`sync-roms --upload [DIR]` uploads the ROMs in `DIR` (default: the current directory) and its subfolders to the
storage folder of one system, keeping the relative paths (`DIR/Disc/a.chd` becomes `<system>/Disc/a.chd`). It asks
which system with the same type-to-filter list as the other pickers, with the cursor already on a guess: the system
whose storage folder or frontend folder name (`gba`, `megadrive`, `ARCADE`...) is the name of `DIR`. With no match
the cursor starts at the top of the list. Esc cancels.

- Files that already exist with the same size are skipped; a file with a different size overwrites the one in the
  storage. Both counts are shown first, the overwrites are listed, and nothing uploads until you confirm (default no).
  `--dry-run` shows the plan and uploads nothing.
- Frontend and OS leftovers (`gamelist.xml`, `images/`, `Thumbs.db`, `.DS_Store`, `._*`...) are never uploaded; other
  dotfiles are.
- It uploads with the `ROMS_WRITE_PROFILE` profile (default `roms`) through one shared pool of requests, four per CPU
  core (at most 16), so many small files and the parts of big ones (64MB and up go as 32MB parts) all keep the
  connection busy. The biggest files start first. `--upload-scrapes` uses the same pool for its media, and
  resizes Onion box art and Slot labels on every CPU core while the other files upload. To a storage folder, 8 files
  are copied at once.

## Scraped data (`--upload-scrapes`, `--clean-scrapes`)

`sync-roms --upload-scrapes [BASE_DIR]` uploads the ES-DE data folder at `BASE_DIR/ES-DE`
(the card root) to `s3://YOUR-BUCKET/scrapes/`. It only reads the ES-DE folder, never
changes it, and never deletes anything in storage. Add `--dry-run` to see the plan first;
a real upload asks before it starts (default no).

What goes up, and how it is stored:

| Local | Storage | Notes |
| --- | --- | --- |
| `gamelists/<system>/gamelist.xml` | `scrapes/<system>/metadata.json` | JSON keyed by ROM path. Only `name`, `desc`, `rating` (0-1), `releasedate` (ISO), `developer`, `publisher`, `genre`, `players`. Favorites, play counts, emulator choices and media tags are dropped. Merged with storage's file: local values win, entries only in storage stay |
| `downloaded_media/<system>/<type>/…` | `scrapes/<system>/<type>/…` | Only files whose ROM name matches an available ROM. `._` files, dotfiles and `CLEANUP/` are skipped. Uploaded when new or a different size |
| (made from the cover, 3D box or screenshot) | `scrapes/<system>/onion/<ROM>.png` | Onion box art, a PNG that fits 250x360. Created whenever it is missing from storage, even if its source image was already uploaded. Not made for ROMs in subfolders. Needs Pillow or `sips` |
| (a Slot card's `Labels/`, or made from the cover, 3D box or screenshot) | `scrapes/<system>/slot/<ROM>.png` | Slot cart label for the Game Boy systems, a PNG that fits 1280x661 (GBA) or 1024x901 (GB, GBC). A card's label is uploaded as is and replaces one of a different size; a derived one is created only when none exists, subfolders included, and needs Pillow or `sips` |

For uploads, "available ROMs" are the games your cards list that exist in storage, which is
what a sync installs. Scraped files for any other ROM are left out. A `gamelist.xml` that can't be read
is skipped with a warning.

`sync-roms --clean-scrapes` (or `-c`) needs no folder. It compares storage's `scrapes/` media and
`metadata.json` entries with every ROM file in storage's system folders (not only the games
listed on your cards), lists what no longer matches (including whole systems with no folder in the
bucket), and after you confirm (default no) deletes the media and rewrites the metadata files. `--dry-run` only lists.

## Scraping from ScreenScraper (`scrape`)

`sync-roms scrape` looks up the available ROMs that have no entry in `scrapes/<system>/metadata.json` on
[ScreenScraper](https://www.screenscraper.fr) and writes what it finds to the storage (bucket or folder). Reads use the
read profile and writes the write profile.

**Credentials.** You need a [ScreenScraper](https://www.screenscraper.fr) account; sync-roms carries its own developer
credentials for the API. Run `sync-roms scrape --set-credentials` to enter your username and password (the password isn't
echoed, a blank answer keeps the saved value). They are stored in `settings.json` as `screenscraper_user` and
`screenscraper_password`; the file is kept readable by you only (mode 600) and `config show` never prints them. After
saving, one request checks the login and shows today's quota and threads, or the error; when ScreenScraper refuses it
the command exits 1. A run also checks the login
before it asks to start, and warns when ScreenScraper sends no account details for it.

**Report.** Before looking anything up, the run lists the ROMs with no metadata and how each will be matched first, and
in a storage folder how much it will read to hash them.
`--dry-run` stops there, printing the metadata entries and media folders it would write; it needs no ScreenScraper
credentials and makes no ScreenScraper request. `scrape match --dry-run` needs credentials: a name is searched (one
request) and you pick a result, while a numeric game id is taken as is, with no request and no check that it exists;
nothing is written. `--system ID` limits a run to one storage folder.

**Matching.** A ROM saved with `scrape match` is used as is. Otherwise one lookup sends its hashes together with its
name and size. In a storage folder a file up to 64 MB is hashed in place (hashes are remembered while its size and
modification time stay the same); a bigger one is looked up by name and size, and hashed for a second lookup only when that
finds nothing. In S3 the object's MD5 is sent when the bucket has one. ROMs are never downloaded from S3 to be hashed. The
report counts a match as "by hash" when the ROM ScreenScraper matched has one of the hashes sent, and as "by name+size"
otherwise; a name+size match is trusted without further checks. Names, dates and media prefer the regions `wor`, `us`,
`eu`, `jp` in a fixed order; there is no setting for it. The response shapes and the search endpoint are written from
ScreenScraper's documentation and ES-DE's scraper, not checked against the live API, so unexpected data is skipped.

**Manual match.** `sync-roms scrape match SYSTEM ROM GAME`, e.g. `scrape match gba "Game (USA).zip" 12345`. `GAME` is a
ScreenScraper game id, or a name to search for and pick from. After you confirm, the ROM is scraped as that game, and the
choice is saved only once that worked; a game id ScreenScraper doesn't have saves nothing and exits with an error. A saved
match whose game later disappears from ScreenScraper is forgotten and the ROM is marked unknown. When the ROM already has
metadata, the prompt lists the files involved and asks to replace it: the entry is replaced, and the old game's
scraper-written media (including its Onion and Slot images) is overwritten or deleted after the new entry is written.
`custom/` and the `--skip-media` types are left as they are. ROMs that share the name without extension (`Game.zip`,
`Game.7z`) share their media files; the prompt warns about them.

**Unknown ROMs.** A ROM ScreenScraper doesn't know is remembered and skipped on later runs. `--retry` tries them again;
`sync-roms scrape review [SYSTEM]` goes through them with non-games (see below), so you can search each one under
another name.

**Finding ROMs with no metadata.** `sync-roms scrape missing [SYSTEM]` lists every ROM your cards list (with `--all`,
every ROM in storage) that has no entry in `metadata.json`, grouped by system, each marked with why: 🚫 a non-game
waiting for review, ❔ not on ScreenScraper, 🔗 a saved match that wasn't scraped yet, or ⏳ not looked up yet. A
system with no ScreenScraper id says so. It makes no ScreenScraper request and writes nothing.

**Non-games.** ScreenScraper marks BIOS sets, demos, test carts and other software as non-games (`ZZZ(notgame)`). A
run writes nothing for them and keeps them for review, and `--retry` doesn't look them up again. At the end of a run on
a terminal you're asked whether to review them now; `sync-roms scrape review [SYSTEM]` reviews them, and the unknown
ROMs, any time (an unknown ROM that has a metadata entry by now, or is gone from storage, is dropped; an unmounted
share fails and drops nothing). A run that leaves ROMs unmatched ends with both commands. Each ROM shows its position
(`3 of 120`); `i` ignores it, `s` searches ScreenScraper under another name (Enter takes the suggested name) and
scrapes the game you pick (with the review's login, no quota check and no results list), `k` (the default) leaves it
for later (ROMs kept for later come after the others in the next review), `b` takes back the last `i` and goes back to
that ROM (a search already scraped stays: `scrape match` changes it), `q` stops, and `I` ignores it and every one
after it. Ignores are written when the review ends, by `q`, Ctrl-C or the last ROM. Ignored ROMs are listed in
`ignored.json` at the root of storage, shared by everyone using that storage: sync-roms never shows, syncs, uploads or
scrapes them, and never deletes their files. Each run checks the file and keeps a copy in the data folder. To stop
ignoring a ROM, remove it from `ignored.json` in storage.

**Progress.** Before it asks to start, the run says the most requests it can make (one lookup and one download per
media type for each ROM) and how many are left today. ROMs go in batches of 25; each batch's heading shows today's
requests as ScreenScraper last reported them and, from the second batch on, the time elapsed and left, and each ROM
gets a line as it ends: the game it matched and how (hash, name+size or manual) and how many media files it got, or
that it isn't on ScreenScraper, is a non-game or failed. The media is then copied or uploaded behind a progress bar
that lists only failures.

**Quota.** ScreenScraper limits requests per day, and separately the number of unrecognized ROMs per day. When either is
used up the run stops cleanly with what it finished already saved and says which limit it was; run it again the next day.

**Ctrl-C.** The ROMs still being looked up or downloaded stop, and those that finished, in both batches being worked on,
are uploaded and saved. Ctrl-C during an upload drops the files not started yet: in a storage folder the copies in
flight finish and the ROMs whose media all made it are kept; in a bucket, ROMs with uploads still in flight are scraped
again on the next run. The run then says how many ROMs it saved and how many are left, and exits 130; run it again to
continue. A second Ctrl-C aborts at once.

**Errors.** A rate-limited request, a server error (HTTP 5xx) or a network failure is tried 3 more times, waiting 10, 20
and 40 seconds; a ROM that still fails is skipped and tried again on the next run. The run stops the same clean way, and
says what to do, when ScreenScraper refuses the login (check it with `sync-roms scrape --set-credentials`), is closed to
non-members or to everyone for now (try again later), or no longer accepts this version of sync-roms (update it), and
when 3 ROMs in a row fail to reach ScreenScraper. A ROM that fails because a download can't be saved locally (a full disk)
is skipped at once, without retries.

**What is written** under `scrapes/<system>/`: the entry in `metadata.json` (merged with what is there) and one folder per media
type (`3dboxes`, `backcovers`, `covers`, `fanart`, `manuals`, `marquees`, `miximages`, `physicalmedia`, `screenshots`,
`titlescreens`, `videos`), plus the Onion and Slot images made the same way as when uploading (they need Pillow or macOS
`sips`). Media a ROM already has there (for example from `upload scrapes`) is kept: those types aren't downloaded, and the
confirm says how many files are kept. Onion and Slot images are made only from art downloaded in the same run, from the
first of covers, 3D boxes and screenshots the ROM has; when that art is already in storage, or the ROM already has the
Onion or Slot image, none is made. Media is downloaded only over https from screenscraper.fr, and only images and PDF manuals
(up to 50 MiB each) and MP4 videos (up to 512 MiB) are stored; a file over its limit or outside screenscraper.fr is
skipped with a warning and the ROM keeps its other media. `--skip-media TYPES` takes a comma-separated list of those
folder names and downloads none of them.

**Local state** in the data folder (`~/.sync-roms/`): `scrape-hashes.json` (file hashes), `scrape-matches.json` (your manual
matches), `scrape-unknown.json` (the ROMs ScreenScraper didn't know), `scrape-nomedia.json` (the media types
ScreenScraper didn't offer for each ROM) and `scrape-notgames.json` (the non-games waiting for review, and the ROMs the review kept for later). Delete one to forget it.

## Local mirror (`--mirror`, `--use-mirror`, `--clear-mirror`)

`sync-roms --mirror DIR` keeps a local copy of just what the game lists reference, with storage's
own key layout: the ROMs a sync installs (every file of a full system), every system's
BIOS files, `scrapes/<system>/` metadata and media for those ROMs.
It compares file sizes (and the ES-DE theme's commit file, always the same size, by checksum), so a rerun with
nothing changed lists storage and downloads nothing.
Anything in the mirror that is no longer referenced (a game removed from a card's games or from the
bucket) is deleted. `--dry-run` shows the plan. A non-empty folder that isn't already a mirror
(it has no `.sync-roms-mirror` file) is refused.

`sync-roms --use-mirror DIR` does the same and saves `DIR` in `settings.json` in the user data
folder (next to `cards.json`). From then on every sync refreshes the mirror from storage first
(if storage can't be reached it warns and uses what the mirror has), then does its usual job
with files copied from the mirror instead of downloaded. If `DIR` is missing (an unplugged drive)
it uses storage. `--upload`, `--upload-scrapes` and `--clean-scrapes` always work on storage itself, and `--edit` lists it;
when `--edit`, `--upload-scrapes` or `--clean-scrapes` finishes successfully (not with `--dry-run`) the saved mirror is refreshed afterwards, so it picks up the change.
`sync-roms --clear-mirror` removes the setting (the mirror's files stay); `sync-roms --mirror` alone
refreshes the saved mirror. Each flag is its own mode and can't be combined with `--edit`, `--upload`, `--upload-scrapes`
or `--clean-scrapes`.

## Editing the game list (`--edit`)

A card's games are saved in `cards.json` under the card's folder name, next to its device and layout; a card
syncs exactly what is picked for it (games, whole sets, full systems). Any old `~/.sync-roms/games.json` is no longer read.
A fresh install starts with no games, so a card syncs no games until you pick some here. Storage is only
read to show what is in it, so the read-only profile is enough. No folders are needed:

```bash
sync-roms --edit
```

0. The menu has **Cards**, **Sets**, **Collections** and **Device systems**. **Sets** is `sync-roms sets edit` (see below; it needs `git` and a logged-in `gh`, and returns here if they are missing). **Collections** is `sync-roms collections edit` (see below). **Device systems** is described at the end of this section. Under **Cards**, pick one of your cards, or **➕ New card** (asks for its folder name, then its device and
   firmware, like the first sync does, and saves the card). On a card, `v` changes its device and firmware instead of opening it (saved with the review at the end) and drops the card's games for systems the new device or firmware doesn't use. Each card's row shows its current device and firmware.
1. A card opens on every system its device can play, in the usual order. Systems recommended for the device's screen
   are marked ⭐; each system with picks shows how many games and how much space they take (ROMs plus the scraped
   files the card's firmware installs). The bottom line shows the card's total (games, scrapes and the BIOS files of
   the systems it syncs) against its size, in green below 70% of the card, yellow below 90% and
   red above (or over). Opened from a sync, it also shows how much of the card's ROMs aren't on it yet
   (`⬇️  … to download`). Sizes come from the storage cache (see [Storage cache](#storage-cache)); without one they show
   `…` and the total says "not sized". `/` filters, `Enter` opens a system, `l` adds a collection to the card (each shows how many of its games are playable on the card's device, and `Space`/`Enter` toggles the whole collection), `f` makes it a full system (every file in its folder; `f` again brings the
   game list back), `S` opens a [Surprise](#surprise) menu: turn it on or off for the card (the title says which), or pick the systems it may use on every card. Games save to `cards.json` as you leave a
   system (the previous file is kept as `cards.json.bak`). `Esc` goes back to the menu.
2. A system shows every file in its storage folder. `✅` is synced, `⬜` is not; a 📦 next to a game says a set the
   card references syncs it (switching it off excludes it from that set on this card). `/` searches, `Space` (or `Tab`)
   toggles the game under the cursor, `a` toggles everything shown, `u` reverts, `o` cycles the view between all
   rows, only those that are on, and only those you changed. A multi-disc game's playlist and discs (marked 🔗) switch
   on and off together, even when a filter shows only some of them. `s` lists the sets with games on this system: `Enter`
   narrows the list to that set's games here, `Space` (or `Tab`) picks that set's games on this system one by one (or
   unpicks them when all are picked already); other systems are untouched. `m` filters by the system's
   scraped metadata (`scrapes/<system>/metadata.json`): pick **Developer**, **Publisher**, **Genre** (its first part,
   so `Sports / Baseball` is `Sports`) or **Year**,
   then a value (each shows how many games in the list have it) to narrow the list to those games. Values are
   matched ignoring case, so `Capcom` and `capcom` are one value. Picking another
   value of the same field replaces it; filters on different fields, the set filter and `/` all combine, and the filter
   line shows what is active. A game with no value for a field never matches a filter on it. The metadata is read in the
   background once per session, so the menu says it is loading at first. `p` narrows the list to games that were surprises within the last `surprise_ttl_days` (🎁 past surprises only), `c` clears every filter and shows every game again.
   Pending changes show as `➕` / `➖` and are counted at the start of the bottom line (`+2 −1`), which updates the card's total as you toggle. `w` writes a note on a
   picked game. A 💖 next to a game says one of the card's collections syncs it: it is always on, can't be switched off here, per-card exclusions don't apply to it, and it counts in the card's budget. `Enter` keeps your changes; `Esc` asks whether to keep or revert them if there are any.
3. When you leave the menu, device/firmware and device-system changes are summarized, then **save**, **keep
   editing**, **discard**, or **list every change**. Nothing is uploaded.

On the Cards list, `v` changes a card's device and firmware, `r` renames a card and `d` deletes one (both ask first, and act at once). **🧩 Device systems** edits which systems a device can play: it is saved as the `add`/`remove` overlay in `device-systems.json`, relative to the repo defaults. A file that isn't valid JSON is never overwritten: sync-roms says so and leaves it for you to fix (`sync-roms check` lists the problems).

### Editing from scripts

`--card NAME` picks the card and every `games` command needs it; every command that changes the card takes `--dry-run` and prints what it changed (`games list`, `games export` and `games sets list` change nothing and refuse it).

```bash
sync-roms games add gba 'Metroid*' --card SD      # a name, SYSTEM/name, or a glob matched against storage
sync-roms games remove gba 'Metroid Fusion.zip' --card SD
sync-roms games full psx on --card SD              # sync a whole system
sync-roms games sets add pinball --card SD
sync-roms games list --json --card SD
sync-roms games export --card SD > list.txt      # SYSTEM/file per line, SYSTEM/* for a full system, then @collections ID, @frontend_collections NAME, @surprise false (only when Surprise is off) and @surprises SYSTEM/file (one per surprise) lines
sync-roms games import list.txt --card SD         # a field with @ lines in the file replaces the card's value
sync-roms cards new SD --device anbernic-rg35xx-sp --layout knulli --size 256GB   # --size is optional; shown in `cards list` and on sync
```

A set file (in the package's `data/sets/`) is `{"name": ..., "description": ..., "games": [{"title": ..., "system": "gba", "bucket": "gba/Game.zip"}]}`.
A multi-disc game adds `"files": [...]` with its other storage keys (the discs); `bucket` is the playlist (`.m3u`) or disc 1.
Toggling the game adds or removes every file, one card entry each.
Entries for an unknown system are skipped with a warning. A full system has no game list to edit: every file is always synced, so opening it in the card editor only says so (press `f` on it in the system list to turn the list back on).

Removing a game only drops it from the card's games; the file stays in storage.

### Editing the built-in sets

`sync-roms sets edit` edits the sets in this repo's `data/sets/` and opens a PR with the changes, so it works from any install. Pick a set to switch games off, add games from a system or from another set across all its systems (you're asked for a category; existing ones are listed), change a game's category, or rename it. **➕ New set** creates a set and `d` deletes the highlighted one (it warns if a card still references it). Esc shows the changes; confirming clones `kelsin/sync-roms` to a temporary folder, writes the changed set files, pushes a branch and runs `gh pr create`. `Ctrl-C` with changes pending shows the same review first. It needs `git` and a logged-in `gh`, and writes nothing to storage or to `~/.sync-roms`.

### Collections

`sync-roms collections edit` edits your own collections of favourite games. A collection is a file like a set file (`{"name": ..., "games": [...]}`) at `~/.sync-roms/collections/<id>.json`; the editor has the same keys as the set editor and saves straight to that folder when you pick Done (Quit discards). `Ctrl-C` with changes pending asks whether to save them first (a collection with no games is not saved; a second `Ctrl-C` discards). They are personal: they never go to storage or into the repo, and no `git` or `gh` is needed. Deleting a collection that cards use asks first and removes it from those cards. In **Add games from a system**, `p` narrows the list to games that were surprises within the last `surprise_ttl_days` and `c` shows every game again, so a surprise you liked is easy to keep.

#### Theme art for collections

In the collection editor, **Theme art** picks a picture for the collection: one for every set (under the set's id),
RPG and Horror, and ones for the usual kinds of personal collection (Favorites, Now Playing, Backlog, Completed,
Kids & Family, Hard Mode, Late Night & Chill, Great Soundtracks, ROM Hacks & Homebrew, Imports, Years & Decades,
Holidays, Device Benchmarks), drawn in the Outline style of the
[Art Book Next](https://github.com/anthonycaccese/art-book-next-es-de) theme (`src/sync_roms/data/themes/art-book-next/art/`;
the collection file gets `"art": "<id>"`). `tools/gen_theme_art.py` draws them (it needs Pillow). When an ES-DE or Knulli card using that theme gets the collection, it shows on
its own in the system carousel with that art and a logo of its name, drawn with the theme's logo font (Changa One, SIL
Open Font License: `OFL.txt` there). The Surprise collection always gets the gift-box art. A collection named like a
system or one of the frontend's own collections gets no art, and a name the font can't draw (accents are dropped first)
gets no logo, so the frontend shows it as text.

- **ES-DE** (when `Theme` in `es_settings.xml` is `art-book-next-es-de`): ES-DE on Android keeps downloaded themes off
  the card, so sync copies the theme from a GitHub archive of it kept in storage (`os/esde/themes/`, about 200 MB, and
  in the mirror) into `ES-DE/themes/art-book-next-sync-roms/`, adds each collection's files (named for the collection in
  lower case) and sets `Theme` to that copy. `sync-roms themes update` puts the theme's latest commit in storage; a
  card's copy is replaced when storage has a newer one. ES-DE's theme downloader doesn't update the copy, and its menu
  lists both copies as Art Book Next. The art is for the Outline color schemes; others show the theme's default art.
- **Knulli** (when `ThemeSet` in `es_settings.cfg` is unset or Art Book Next): the built-in theme is read-only, so the
  art goes to `theme-customizations/art-book-next/artwork/<Name>.png` and `logos/<Name>.svg`, and `es_settings.cfg`
  gets `subset.<Name>.system-view-artwork` and `subset.<Name>.system-logos` set to `custom`, so only that collection
  uses them (its logo sits a little lower than on the Outline systems). Knulli only shows a custom collection on its own
  when it isn't grouped under Collections, so `UseCustomCollectionsSystemEx` is set to `false` unless you already chose
  a value; that shows your other custom collections on their own too.
- Art for a collection that is renamed or removed stays in the theme folders; it is unused.

### Full systems

A system can sync every file in its storage folder (subfolders included) instead of a game list, so adding
a file to storage is enough to publish it. Set its entry in a card's `games` to `{"full_system": true}`
instead of a list:

```json
{ "gb": { "full_system": true } }
```

No system is a full system by default. In `--edit`, press `f` on a system in a card's system list to
toggle it (🗂️). A full system's games can't be toggled one by one.

### Full sets

A list can sync every game of a set (from `data/sets/*.json`) without listing the games, with a `"sets"` key
holding the set file names without `.json`:

```json
{ "sets": ["mario", "zelda"], "gba": [ { "title": "Game", "bucket": "gba/Game.zip" } ] }
```

It works in a card's `games` entry in `cards.json`. A set reference is live: games added
to the set in a later release are synced too, for the systems the card has enabled. `sync-roms games sets add ID --card NAME` adds one
(the card editor's `s` picks a set's games one by one instead); in `--edit` the games a referenced set syncs show 📦,
and switching one off excludes it on that card. Unknown set names are skipped with a warning.

### Surprise

Every card gets up to 10 surprises: random full English games (no BIOS, prototypes, betas, demos, hacks, re-releases or
compilations; a multi-disc game counts as one) from the systems of the run, in addition to the games you picked. It is on by default. Seven of the ten come from
the systems recommended for the card's device and three from the others, spread evenly over the systems; a system with no
candidates passes its slots on. Games never surprised, then games surprised before, then games another card currently
holds are used in that order. Full systems are left out, and so is any game already on the card. Systems listed in
`surprise_excluded_systems` in `settings.json` (system ids, for every card) are never used, and a card's current surprises
on them are replaced at the next sync.

- **In a sync** the step runs before anything downloads, over the systems with games picked. Interactively it first asks which of the card's current
  surprises to replace (`Esc` there behaves as it does in any picker: it keeps them all), fills the empty slots, and opens
  the card editor so you can adjust the card (with Surprise off, the editor still opens). Without a terminal, with `--yes` or `--json` it replaces all of them. `--dry-run`
  changes no surprises: it only says whether it would ask or replace all, previews the picks for empty slots and saves nothing.
  The mirror is refreshed a second time only when this step or the editor changed the card's picks.
- **In the card editor**, `S` in the system list opens a menu: turn Surprise on or off for the card (off removes its surprises
  at the next sync), or check the systems Surprise may use (saved as `surprise_excluded_systems`, for every card), and `p` in a game list shows only the games surprised within `surprise_ttl_days`. A surprise shows in the
  game list as 🎁 Surprise and can't be switched off there, like a collection game; it counts in the card's budget and size warning.
- **History** is kept in `~/.sync-roms/surprises.json` (system, bucket, title, card, ISO date) and pruned past
  `surprise_ttl_days` in `settings.json` (default 183) whenever it is written. It is how a game comes around again only later.
- **Frontends**: ES-DE and Knulli cards get the surprises as a custom collection named `Surprise`, written like any
  other [collection](#collections-in-es-de-and-knulli); that name is reserved, so a collection can't be called Surprise.
- **Art Book Next**: Surprise gets a gift-box artwork and logo in the theme's Outline style, like any
  [collection with theme art](#theme-art-for-collections).
- **Mirror**: picks are made from storage itself, not the mirror, so they can be games the mirror doesn't have yet.
- `cards.json` holds `"surprise": false` when it is off and `"surprises"` (`[{"system", "bucket", "title", "files"?}]`, `files` being
  a multi-disc game's other keys); `games export` and `import` carry both, and `sync-roms check` validates them.

### A card's games in `cards.json`

```json
{ "RGSP": { "device": "anbernic-rg-sp", "layout": "muos", "games": { "gba": { "full_system": true } } } }
```

`games` maps system ids to games (or `{"full_system": true}`), and may hold `"sets"`. A card is identified by its folder name, so
renaming the folder makes it a new card. The local mirror (`--mirror`) holds every card's games.

`excluded` (`{"gba": ["gba/A.zip"]}`) lists set games this card opts out of. Press `e` on a system in the
picker: games its sets sync show as on and can be switched off (and back on); the choice is saved
for that card only. In the systems picker, `o` shows only the selected systems.

## Converting to CHD and xiso (`--cd`, formerly `--chd`)

Run it on a downloaded rom pack, or one system folder of it, before you upload it to storage (see below):

```bash
sync-roms --install-tools                # once: brew install sevenzip unar rom-tools
sync-roms --cd --dry-run ~/roms
sync-roms --cd ~/roms/psx
```

Each system's behaviour is the `chd` setting in `src/sync_roms/data/systems.json`:

| `mode` | Systems | What happens |
|---|---|---|
| `cd` | Sega CD, Saturn, TurboGrafx-CD, PC-FX, Neo Geo CD, PS1, 3DO, Dreamcast | `chdman createcd` from the `.cue`/`.gdi`/`.toc` (or `.iso`) |
| `dvd` | PS2, PS3, PSP | `chdman createdvd` for `.iso` files plus the system's `args` (PS2 `-c zlib`, PS3 `-c zstd`, PSP `-hs 2048`); bin/cue games use `createcd`. PS3 archives also keep their `.pkg`, `.rap`, `.dkey` and `.key` files (the system's `keep` list) beside the `.chd`s, so a PSN `.rar` just extracts to its PKG and RAP files for installing and an encrypted disc keeps the key it needs; an archive's other files (covers, readmes) are dropped. PS3 chds only load in ARMSX3 (Android), not in RPCS3, aPS3e or RPCSX |
| `extract` | GameCube, Wii | archives are unzipped and the files (e.g. `.rvz`) left as they are; nothing is converted |
| `xiso` | Xbox | archives are unzipped, then each `.iso` is rewritten as an optimized xiso with `extract-xiso -r` into a hidden folder (a loose `.iso` is copied there first, an unpacked one is rewritten directly), and the result replaces the original only once `extract-xiso -l` lists it cleanly; isos already in xiso format are left alone |
| `zar` | Xbox 360 | archives are unzipped, then each `.iso` is compressed into a zstd [ZArchive](https://github.com/Rucadi/ZArchive) `.zar` with `iso2zar` (written under a hidden `.part` name, renamed once the tool succeeds and the file is not empty) and the iso is removed; Xenia Canary and XenDroid read `.zar` |

`"m3u": false` (3DO) skips the playlist step, since Opera can't load `.m3u` files. Systems without a `chd` setting are ignored.

Every `.chd` is verified with `chdman verify` before its archive, `.cue`, `.bin` and `.iso` files are deleted; on any failure the originals are kept. Each `.chd` is written under a hidden `.part` name and renamed only after it verifies. `Ctrl-C` stops `7z` and `chdman`, removes the partial files and exits (130) without starting anything else; a rerun picks up where it stopped, and also deletes the extraction folders (`.chd-*`) a hard kill left behind, beside the archives and in the system temp folder.

It is meant for preparing a downloaded rom pack before you upload it to storage, so storage holds the `.chd` and `.m3u` files and the card's games list those names. Running it on a card synced from storage that still has the `.zip` files makes the next `sync-roms` run list the `.chd` files as files not in your game list (it asks before deleting, default no) and download the zips again. So when a folder in `DIR`'s path is named after a saved card, convert warns and asks first (default no: with `--yes` or without a terminal it stops and exits 1; `--dry-run` only warns). When `DIR` is inside the storage folder and at least one file converted, it ends by saying to run `sync-roms cache update`, since storage's files changed. Under `--quiet` only failed files and the closing line of a run with failures are shown (on stderr).

## Storage cache

Every command reads what storage holds (each file's name and size, and for a bucket its ETag) from
`~/.sync-roms/storage-cache.json`; only the files themselves are downloaded from storage. On a network share this
turns minutes of listing and stat calls into an instant read.

- `sync-roms cache` shows where the cache was read from, when it was last updated, and its files and size per folder.
- `sync-roms cache update` reads storage again: one listing of a bucket, or a walk of a storage folder that checks
  each folder's modification time and lists only the folders whose time changed since the last update, statting only
  the files the cache doesn't have: new files are added, missing ones dropped, and every other file keeps its cached
  size. In a storage folder this relies on storage changing a folder's modification time whenever a file is added to,
  removed from or renamed in it. A folder changed in the last few minutes is listed again on the following update, so
  a change made just before an update is picked up by the next one at the latest. Run it after changing storage
  outside sync-roms. Nothing refreshes the cache on its own and it never expires; sync-roms's own uploads, moves and
  deletes keep it up to date.
- `sync-roms cache update --full` lists every folder and stats every file in a storage folder. Use it for files
  replaced under the same name (the default keeps their cached size) and for anything a folder's modification time
  didn't show (say, a tool that sets it back). A bucket listing already has every size, so it's the same as
  `cache update` there.
- With no cache for the storage in use (none yet, or built from another bucket or folder), the first command that reads
  storage offers to build it. Saying no is remembered (`storage_cache_declined` in `settings.json`), and commands then
  list storage on every run as before. `sync-roms cache update` builds it any time.

An old `~/.sync-roms/sizes.json` is no longer read; delete it.

## How it works

- Reads the systems, layouts, devices and BIOS requirements from `src/sync_roms/data/` in the package, each device's
  playable systems (`device-systems.json`) too, and your cards (`cards.json`) from `~/.sync-roms/`, never from
  storage. An optional
  `~/.sync-roms/device-systems.json` adjusts the systems a device can play:
  `{"miyoo-flip-v2": {"add": ["psx"], "remove": ["gba"]}}` (system ids as in `systems.json`; the package's
  order is kept and notes always come from the package). An old full-copy `device-systems.json` from before the overlay does nothing; delete it. BIOS files are always `BIOS/<file>` in storage.
- System folders in storage use the ES-DE system name (e.g. `gba/`, `dreamcast/`).
- Reads each synced system's files from the storage cache and compares file sizes, so only
  missing or changed files are downloaded (for `full_system` systems, every file in the folder) (8 in parallel, via boto3).
- Local files in a synced system's folder that are no longer in the card's games
  are listed and deleted only after you confirm (default **no**; `--dry-run` shows them).
  Folders of systems you didn't pick, BIOS files and dotfiles are never touched.
  Files frontends add to ROM folders are ignored too (never counted as "already has files",
  never deleted): ES-DE `systeminfo.txt` / `noload.txt`, Knulli/Batocera `_info.txt`,
  `gamelist.xml` and the `images/`, `videos/`, `manuals/` folders, Onion `miyoogamelist.xml`,
  `*.db` ROM list caches (on Onion cards only) and `Imgs/` (top level of a system folder only), and Windows `Thumbs.db` / `desktop.ini`.
- Some systems share a local folder on a device (Onion: `WS` = WonderSwan + Color,
  `NGP` = Neo Geo Pocket + Color). A folder's expected files are the
  union of all those systems' lists, so syncing one never offers the other's ROMs for deletion.
- Slot can't read archives or subfolders, so a Slot sync extracts each downloaded `.zip` (and `.7z`, which needs `7z`, see `--install-tools`) into the system folder and deletes the archive. It assumes the archive is named like the ROM inside; an archive whose ROM has another name is downloaded again each sync.
- Every BIOS file listed for a synced system is downloaded; there is no required/optional distinction.
  BIOS lists come from the ES-DE default libretro cores, so they may not match what Knulli
  or Onion use; on Knulli check Game Settings > Missing Bios Check.

### Collections in ES-DE and Knulli

Only ES-DE and Knulli cards get them. Each sync writes the card's collections (see [Collections](#collections)) as the
frontend's custom collections, listing the collection games that are on the card; games on systems the card doesn't
sync are left out. `--dry-run` lists what would be written.

| | ES-DE | Knulli |
|---|---|---|
| File | `ES-DE/collections/custom-<Name>.cfg` | `system/configs/emulationstation/collections/custom-<Name>.cfg` |
| Line | `%ROMPATH%/<system folder>/<path on card>` | `./roms/<system folder>/<path on card>` |
| Enable | `CollectionSystemsCustom` in `ES-DE/settings/es_settings.xml` | `CollectionSystemsCustom` in `system/configs/emulationstation/es_settings.cfg` |

- `<Name>` is the collection's name without the characters ES-DE rejects (`* " , . / : ; < > \ |`, newline, tab);
  collections whose names come out alike share one file.
- `CollectionSystemsCustom` is the comma-separated list of enabled custom collections. Sync adds its names and keeps
  any others there; only that one line is changed (or added), and the file is created if missing.
- sync-roms only touches collection files it wrote (recorded as the card's `frontend_collections`). A collection made
  in the frontend with the same name is skipped with a warning. A collection removed from the card, or renamed, has
  its old file deleted and its name unlisted.
- The files are rewritten each sync, so edits made to them in the frontend are lost.
- Close the frontend before syncing: it rewrites its settings file from memory.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `AccessDenied` / `Unable to locate credentials` | Define the `roms-readonly` profile in `~/.aws/config` and `~/.aws/credentials`; `sync-roms doctor` checks the profile, storage and tools |
| `cards.json isn't valid JSON` | Fix the file (the last good copy is `cards.json.bak`); sync-roms refuses to overwrite it. `sync-roms check` finds the problem |
| "listed in manifest but not in storage" warnings | A game on your card (or a required BIOS file) isn't in storage; it is skipped |
| A system shows `(0 roms)` | Your card has no games for that system, or none of them are in storage (BIOS is still fetched if selected). Add games with `--edit` |
