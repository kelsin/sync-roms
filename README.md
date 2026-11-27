# 🎮 sync-roms

Interactive script that downloads ROMs and the BIOS files they need from your storage (an S3 bucket or a folder) into local folders. Files you already have (same size) are skipped, so re-running it only fetches what's new or missing.

The first run asks where storage is and saves the answer in `settings.json` in the [data folder](#data-folder):

- **A bucket name** is saved as `bucket`. It then asks for an optional custom S3 endpoint URL (blank for AWS), saved as `endpoint`, for S3-compatible storage such as MinIO or Cloudflare R2 (requests then use path-style addressing).
- **An absolute folder path** (a mounted network share, `/Volumes/roms`, or `~/roms`) is saved as `root` and replaces the bucket and AWS entirely, with the same layout (`<system>/…`, `BIOS/…`, `scrapes/…`). An answer with a `/` (other than `s3://…`) or naming an existing folder is a folder, never a bucket name.
- **With no terminal to ask on**, set `ROMS_BUCKET` or `ROMS_ROOT` (or pass `--bucket` or `--root`).

It can also keep a [local mirror](#local-mirror-mirror) of storage and sync from that. The device setup guide (`sync-roms guide` opens it in a browser) lists the steps to finish a device by hand once its card is synced: apps to install and the frontend, RetroArch and emulator settings to change, for the device and layout you pick (or a card, which sets both; Spruce is the first and default layout of a device that doesn't run Android).

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

Then run `sync-roms --help`.

### Upgrade

```bash
brew update && brew upgrade sync-roms     # Homebrew
pipx upgrade sync-roms                    # pipx
```

Your settings and cards in the data folder are never touched by an install or upgrade.

## Requirements

- **python3** (3.12+); boto3, textual and textual-image (which brings Pillow) are installed with the package
- An AWS profile named **`roms-readonly`** with read access to storage (not needed with a storage folder; set `ROMS_PROFILE` to use a different profile name), defined in `~/.aws/config` and `~/.aws/credentials`
- Only for `prepare` (and `cards install`, which needs just the 7z): **7z** and **chdman**, and optionally **unar** (used for `.rar` when installed; `sync-roms install` installs all three with Homebrew), plus **extract-xiso** for Xbox (no Homebrew formula: build it from [XboxDev/extract-xiso](https://github.com/XboxDev/extract-xiso) with `cmake -B build && cmake --build build`) and **iso2zar** for Xbox 360 (no formula: build it from [iso2zar](https://codeberg.org/NeverAnswers/iso2zar) with `cargo build --release`)

### AWS profiles

Create the read-only profile (used for everything that only reads) and, if you write to storage (`upload`, `scrape`, `tags edit` and the like), the write profile. Each asks for an access key, secret, and region (`us-east-1`):

```bash
aws configure --profile roms-readonly
aws configure --profile roms
```

## Syncing a card (`sync`)

```bash
sync-roms sync CARD     # or just: sync-roms CARD
sync-roms               # the current directory is the card
```

`CARD` is the root folder of the card (or any folder to sync into); from a clone of the repo, run `uv run --project CLONE sync-roms` in place of `sync-roms`. You pick a device, then the layout, which is the firmware the card is for (a device with only one isn't asked). The layout decides the ROMs and BIOS folders inside `CARD` (`src/sync_roms/data/layouts.json`), and each device lists its layouts as `firmwares` in `devices.json`, the first being the default:

| Firmware | ROMs / BIOS folders | Notes |
| --- | --- | --- |
| `esde` | `ROMs/` `BIOS/` | Android devices with ES-DE |
| `knulli` | `roms/` `bios/` (SD card SHARE partition, `/userdata`) | Default for the Anbernic H700 handhelds (not the RG SP or RG34XX SP), the Anbernic RG DS Plus, RG353PS, RG353VS and RG503, and the Miyoo Flip |
| `muos` | `ROMS/` `MUOS/bios/` | [muOS](https://muos.dev/) on the Anbernic H700 handhelds and the RG Vita Pro (its default). Folder names are matched ignoring case and separators |
| `onion` | `Roms/` `BIOS/` | Miyoo Mini, Mini Plus and Mini Flip, on [Onion](https://onionui.github.io/) |
| `allium` | `Roms/` `BIOS/` | The same devices, on [Allium](https://github.com/goweiwen/Allium), with the same folders |
| `spruce` | `Roms/` `BIOS/` | Miyoo Mini, Mini Plus, Mini Flip, Flip and A30, the Anbernic H700 handhelds and the MagicX Zero 40, on [Spruce](https://github.com/spruceUI/spruceOS) (spruceOS). Its own upper-case folder names (`SFC`, `MD`, `FC`, `PS`, ...) |
| `rocknix` | `roms/` `roms/bios/` | [ROCKNIX](https://rocknix.org/) on Anbernic, AYANEO, AYN and Retroid handhelds |
| `nextui` | `Roms/` `Bios/` | Anbernic H700 handhelds (the default on the RG SP and RG34XX SP), on [NextUI](https://nextui.loveretro.games/) (MinUI style). System folders are named `<Name> (TAG)`, the tag picking the emulator; BIOS files go in `Bios/<TAG>/`. A multi-disc game gets a folder of its own with its discs and `.m3u` |
| `emudeck` | `Emulation/roms/` `Emulation/bios/` | [EmuDeck](https://emudeck.github.io/) on the Steam Deck and Steam Machine. Wii U, Xbox 360 and Model 2 ROMs go in a `roms/` subfolder of their system folder. Part of its files go on the machine, not the card: see [EmuDeck](#emudeck) |

NextUI multi-disc limits: a game folder left empty after its game is removed stays; `.gdi` and `.ccd` track files aren't moved into the game folder; a `.bin` is matched to its `.cue` by name only.

Folder names are case-sensitive. Folders that don't exist are shown as "will be created" and are created after you confirm. If they can't be created (no permission), sync-roms stops before asking.

The device and layout you pick are saved in `cards.json` in the [data folder](#data-folder), under the name of the `CARD` folder (e.g. `SHARE`). The next sync of a folder with that name uses the saved setup without asking. `--ask` (or `-a`) confirms it first; answer `n` to pick again and save the new choice. Give cards the same name if they should share settings; renaming a card's folder makes it a new card.

### What a sync does

1. **Pick a device and a layout** (a card's first sync). Only the systems that run well on the device are listed: those of the tier it names in `src/sync_roms/data/device-systems.json` (`tiers` is an ordered chain: the first lists its systems, each later one `add`s to the tier before), adjusted by your own overlay. Its first layout is highlighted. Or choose Full (every system) and any layout. Systems with no folder in the chosen layout are skipped.
2. **Edit the card**: every system with games picked on the card syncs. After the [Surprise](#surprise) step, a sync in a terminal opens the [card editor](#editing-a-cards-games-edit-games) on the card; `Esc` there goes on with the sync. Its bottom line also shows how much a sync would download (`⬇️  12.3 GB to download`: ROMs not on the card yet; scraped files and BIOS aren't counted), updated as you add games and collections.
3. **Confirm the plan**: a summary shows how many files will be fetched and their total size (e.g. `💿 ROMs: 120 to download (3.4 GB), 5 already present`). Local ROMs no longer in the card's games are listed and deleted first (after you confirm, default no), so the free space shown is accurate. A card file whose name differs from storage's only in case or Unicode form is renamed, and an unwanted one with the name (compared the same way) and size of a missing file is moved to its place; neither is downloaded or deleted. Then the totals (scraped media included, on layouts that take it) and the card's free space are shown and you confirm. When there isn't enough space and nobody can be asked (`--yes`, or no terminal), the sync fails with exit 1.
4. **ROMs, then BIOS**: ROMs download into the layout's ROMs folder (`<system>/`), then the BIOS files for the card's systems into its BIOS folder (RetroArch system-dir layout). A system's `rom_files` (MAME-style BIOS zips such as `gamate.zip`) are kept in storage's `BIOS/` too, but copied into that system's ROM folder instead, while it has ROMs to sync. Each file prints as soon as it finishes, as `[i/N] ✅ gba/Game.gba` (`i` is the count finished so far, not the file's place in the queue); in a terminal the files downloading right now are listed under the progress bar (fewer when the terminal is short). When the local folder name differs from storage's (e.g. a Knulli device), it prints `[i/N] ✅ genesis → megadrive/Game.md` (storage folder → local folder/file).
5. **The layout's own files**: APKs and [GPU drivers](#gpu-drivers) (`esde`), the PICO-8 app, the Onion Surprise app, RAOfflineProxy and Onion's themes, as listed under [What each layout gets](#what-each-layout-gets). Then come the `.psvita` files of [Vita games](#vita-games).
6. **Scraped data** for the card's games is installed from storage's `scrapes/` folder, converted for the layout (see [Scraped data on the card](#scraped-data-on-the-card)).
7. **Clean-up**: media on the card for ROMs the card doesn't have is removed, with no confirmation, and so are system folders left empty on Onion, Allium and Spruce cards.
8. **Collections** and their art are written for the frontend, then Onion's `surprise.json` and, on Spruce cards, the spruceOS update file (see [What each layout gets](#what-each-layout-gets)).
9. **Card tidy and eject**: a sync that wrote to the card creates `.metadata_never_index` in the card root, empties `.fseventsd` and puts a `.fseventsd/no_log` file in it (on any OS), so macOS doesn't index or log the card. On a Mac it also deletes the card's `._` files and, when Spotlight is indexing the card, offers to turn that off with `sudo mdutil` (with `--yes` or no terminal it only prints the command). `--no-clean` skips this tidy. On a Mac a run with no failures then ends with `diskutil unmountDisk` on the card's disk (removable or external disks only), so every volume on it is unmounted and the card can be pulled, unless `--no-eject` or `"eject": false` in `settings.json` says otherwise.

A run ends with one line: the files and bytes downloaded, the time it took, the listed ROMs not in storage and any failures. A second `Ctrl-C` during downloads stops at once and removes the partly downloaded files.

### Scraped data on the card

| Firmware | Media | Metadata |
| --- | --- | --- |
| `esde` | `ES-DE/downloaded_media/<system>/<type>/…` (every type) | `ES-DE/gamelists/<system>/gamelist.xml` |
| `knulli` | `<system>/images`, `videos`, `manuals`, named `Game-image.png`, `-thumb`, `-marquee`, `-fanart`, `-boxback`, `-titleshot`, `-video`, `-manual` | `<system>/gamelist.xml` with name, description, rating, date and the media tags |
| `rocknix` | same as `knulli` | same as `knulli` |
| `onion` | `<system>/Imgs/Game.png`, the 250x360 box art [made when scraping](#scraping-from-screenscraper-scrape) | `<system>/miyoogamelist.xml` with name and image |
| `spruce` | `<system>/Imgs/`, `Imgs_med/`, `Imgs_small/` QOI box art (`Game.qoi`), [made when scraping](#scraping-from-screenscraper-scrape) or by `scrape art`; never PNG, so PyUI doesn't prompt to convert | `<system>/miyoogamelist.xml` with name and, when the ROM has art, an `image` pointing at the `.qoi` |
| `allium` | same `Imgs/` box art as `onion` | a full `<system>/gamelist.xml`: name, image, rating, date, developer, publisher and genre |
| `muos` | `MUOS/info/catalogue/<system>/box/Game.png` (cover, then 3D box) and `preview/Game.png` (screenshot, then title screen), as uploaded | `text/Game.txt` with the description |
| `nextui` | `Roms/<folder>/.media/<ROM name>.png` (the picture the theme shows) | none |
| `emudeck` | `Emulation/tools/downloaded_media/<system>/<type>/…` (every type) | `gamelists/<system>/gamelist.xml` as for `esde`, on the machine running the sync (see [EmuDeck](#emudeck)) |

- For `esde` and `emudeck`, `<system>` is the system's ES-DE folder name (`sg-1000`, `n3ds`): systems that share a ROM folder, like `3ds` and `n3ds`, share its media and gamelist folders.
- muOS keeps its media in folders of its own, flat even for ROMs in subfolders. An existing `.txt` is rewritten only when the description differs.
- Knulli's main image is the miximage, or the screenshot if there is none.
- Existing gamelists are updated in place: only these tags are set, so favorites, play counts and an `<alternativeEmulator>` block stay.
- ROMs in subfolders get no Onion or Spruce art. NextUI's `.media` picture is the same kind of file, so ROMs of the same name in different subfolders of one system share it.
- A PICO-8 `.p8.png` cart with no scraped picture is used as its own picture (not on muOS or Spruce).

The clean-up of step 7 looks at every system in the layout, not only the ones you synced, and leaves systems whose ROM folder doesn't exist, and folders that aren't systems in `src/sync_roms/data/systems.json` (like ES-DE's `androidapps`), alone. It assumes the card's art comes from this app: on muOS it removes `box`, `preview` and `text` files in `MUOS/info/catalogue/<system>/` (names compared ignoring case; systems that share a catalogue folder, like the arcade ones, are judged together; `grid`, `manual`, `overlay` and the other catalogue areas are left alone). A muOS folder whose ROM folders hold no ROMs is skipped, so art isn't wiped from a card whose ROMs are elsewhere (muOS can keep them on SD2). Art you add by hand or install from a `.muxcat` set for ROMs that aren't on the card is removed too.

### Vita games

On `esde` and `emudeck` cards every Vita game zip in `psvita/` gets a `.psvita` file beside it holding the game's title id (read from the zip's `param.sfo`), which is what ES-DE launches Vita3K with; the zip itself is left as it is for Vita3K to install. The `.psvita` file is kept while its zip is in the selection and deleted with the other unwanted files once it isn't. A synced Vita game also brings its DLC and newest update from `psvita/` (matched by the title id in the file names), on every layout; the editors and Surprise list only games.

### Unattended use

`--yes` answers every prompt with its default (deleting local files stays "no"; `upload`, `clean` commands, `themes publish`, `download pico8`, `cards export` (over an existing file) and `scrape match` go ahead with it, and without it ask (the `clean` commands with default no, the others with default yes) and exit 2 without a terminal). A first sync can skip the setup picker:

```bash
sync-roms sync /Volumes/SD --device anbernic-rg-35xxsp --layout knulli --yes
sync-roms sync /Volumes/SD --dry-run     # preview a saved card
```

Without a terminal and without those flags the pickers fail with the flag to use. Prompts read from a closed stdin take their default.

Exit codes: `0` done (or nothing to do, or you declined), `1` some files failed, `2` bad usage, `3` setup problem (credentials, storage, missing tool, unreadable data file), `130` interrupted. Errors go to stderr.

`--dry-run` shows the same free space as a sync (counting the ROMs it would delete as freed) and says when the downloads would not fit. `sync --dry-run --json` prints `{downloads, delete, kept, theme_remove, rename, missing, stale_media, totals, free_space}`: `downloads` lists every file with its `kind` (scraped media as `scrape`, counted in `totals`), `kept` lists the card's ROMs outside the selection that `--no-delete` keeps (not the retired collections it keeps), `theme_remove` the PyUI theme folders a `spruce` card would lose, `rename` holds `{from, to}` pairs, `missing` has `roms` and `bios`, and `free_space` is in bytes.

The other `--json` documents: `devices` is a list of `{id, name, soc, systems, firmwares}` (`systems` a count), or one device's entry with its `systems` and `system_names`; `layouts` is the `layouts.json` entries plus `id` and `devices`; `games list` is `{full_systems, games}`, each game `{system, bucket, title}`; `cards list` is a list of `{name, device, layout, size, used, sized, full_systems, games, extras, guest, surprise, theme, collections, raofflineproxy}`; `diff` is `{system, only_local, only_bucket}`, the last two lists of `{path, size}`.

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
| `a` `V` `u` | all or none shown / cycle view (all rows, only those that are on, only those you changed) / revert (lists with checkboxes; asks first when more than one row changed, the rows a filter hides included) |
| `o` `O` | sort by a column (a menu of them) / reverse the order (lists with sortable columns; game lists show Name, System and Year columns, sorted by year by default; picked with `o`, size, count and date columns start largest or newest first) |
| `?` | every key of the list, including the list's own (scroll with `j` `k`; `Esc`, `q` or `?` closes it) |

The hint line under the filter starts with `? help`. The bottom line ends with the highlighted row's number and how many rows the filter shows (`row 12 · 340/3700 shown`) when the list's own status (a card's size, say) leaves room for it. Leaving a game list for `s`, `m`, `p` or `v` and coming back keeps your row, filter and view when the list shows the same games.

While typing a filter (or a note, which `w` opens in the game list): `^A` `^E` start/end of line, `^B` `^F` left/right, `^D` delete a character, `^K` kill to end, `^U` kill to start, `^W` kill a word.

## Commands

Every mode is a command (plain `sync-roms [CARD]` syncs a card). A command's aliases run the same command; a bare word that is a command or an alias is that command, so name a card folder like one with a path (`./saves`):

| Command | Does | Aliases |
| --- | --- | --- |
| `sync [CARD]` | download ROMs, BIOS and scraped data to a card | |
| `edit` | [interactive editor](#editing-a-cards-games-edit-games) | |
| `games list\|add\|remove\|full\|export\|import` | [edit a card's games from scripts](#editing-from-scripts-games) | `game` |
| `tags edit\|suggest` | edit the [tags](#tags-tags-edit-tags-suggest) in storage by hand, or add tags from scraped genres | `tag` |
| `collections edit` | edit your [collections](#collections-collections-edit) of favourite games | `collection` |
| `collections import FILE...` | add [collections](#collections-collections-edit) exported from the share page; a taken id asks merge, replace, rename or skip | `collection` |
| `collections page` | write a shareable HTML page of your collections and open it | `collection` |
| `collections publish` | [publish](#publishing-to-github-pages) a public copy of that page to `https://sync-roms.games/collections/<user>/`; `--dry-run` lists what would change | `collection` |
| `collections retitle` | set each game's title in your collections to its scraped name (else its file name); `--dry-run` lists the changes | |
| `collections share\|unshare` | share that page on your tailnet through a local server and `tailscale serve`, or stop | `collection` |
| `collections update` | run `collections share`, then `collections publish` (`--user NAME` passed on), stopping at the first failure | `collection` |
| `themes update` | put the latest Art Book Next for ES-DE (for collections' [theme art](#theme-art)) and every [PyUI theme](#spruce) (needs `7z`) in storage | `theme` |
| `themes build [STYLE...] [--palette NAME\|--all-palettes] [--out DIR]` | build the custom spruce theme styles (Pixel Consoles, Pixel Controllers, ToTK - James, ToTK - Kelsin) in each chosen palette (without a flag: picked in a list, or the saved `custom_theme_palettes`; `ToTK - James` and `ToTK - Kelsin` have no palette and are built once, from the ToTK theme in storage, so naming only it asks for none) from the SPRUCE base theme in storage into the cache, or into `DIR` with `--out`; writes nothing to storage | |
| `themes publish [STYLE...] [--palette NAME\|--all-palettes]` | build the custom spruce themes in each chosen palette (chosen as for `themes build`) and make their `os/spruceos/themes/<theme>/` folders in storage match: upload what changed and delete what the build no longer makes, after one question (default yes; `--yes` answers it, without a terminal and `--yes` it exits 2; `--dry-run` only shows the plan) | |
| `themes palettes` | write the overview image of all 35 palettes (a numbered mock list screen for each) and open it | |
| `themes pick` | choose the PyUI themes every spruce card gets by default (`spruce_themes` setting) | |
| `download pico8` | add the [PICO-8 BBS Featured carts](#pico-8-carts-from-the-bbs-download-pico8) storage doesn't have, and newer revisions of those it has | `downloads` |
| `ports search [TEXT...]` | search PortMaster's catalogue (title, zip name, genres, description) and, with a terminal, pick ports to download | `port` |
| `ports download [ZIP...]` | put PortMaster ports (named as in PortMaster's catalogue, `celeste` or `celeste.zip`) in storage's `ports/`, with the runtimes they need in `os/portmaster/runtimes/` and their titles in `scrapes/ports/metadata.json`; a zip storage has is skipped | `port` |
| `ports done CARD PORT...` | record that the card already has the game data of ports (folder or zip names), so a sync stops listing them and the card leaves the needed list; `--undo` forgets that | `port` |
| `ports needed` | list the ports waiting for game data (title, instructions, where in storage to put the files, the cards); ports storage now has data for are dropped | `port` |
| `flash` | [write a Knulli, BaseOS, muOS, ROCKNIX or OakMoss image](#flashing-an-sd-card-flash) from storage's `os/` to an SD card, macOS only | |
| `format` | [erase an SD card as exFAT or FAT32](#formatting-an-sd-card-format) with a picked label, macOS only | |
| `unmount` | pick an SD card, remove macOS's junk from it as a sync does (`.metadata_never_index`, `.fseventsd`, `._` files) and unmount it, macOS only | `umount` |
| `mount` | pick an SD card that was unmounted (by `unmount` or a sync) but not pulled out and mount it again with `diskutil mountDisk`, macOS only | |
| `cards list\|new\|set\|rename\|layout\|install\|clean\|delete\|copy\|export\|import` | [manage cards](#cards-cards) | `card` |
| `saves stash\|apply [CARD]`, `saves manage` | [copy RetroArch saves and states](#moving-saves-between-cards-saves) off a card, or stashed ones onto a card (Android: over adb); inspect, label, move, prune and delete stashes | `save` |
| `devices [ID]` | list the supported devices with their chip and the number of systems each one gets, or one device's layouts, note and systems | `device` |
| `layouts [ID]` | list the layouts, or one layout's folders and the devices that run it | `layout` |
| `upload [DIR]` | [upload ROMs](#uploading-roms-upload) to storage | |
| `diff [DIR]` | list the ROMs in only `DIR` or only the storage folder of a system you pick (guessed from the folder name, as in `upload`). Same path and size is the same file; the rest are matched by content, as `upload --replace` does | |
| `scrape [SYSTEM \| match SYSTEM ROM GAME \| review [SYSTEM] \| missing [SYSTEM] \| art [SYSTEM]]` / `scrape --set-credentials` | [scrape ROMs](#scraping-from-screenscraper-scrape) with no metadata from ScreenScraper, review the non-game and unknown ones, list them all, or make Onion and Spruce art for what storage holds | `scrapes` |
| `scrape clean` | [remove scrapes](#cleaning-scraped-data-scrape-clean) of ROMs not in storage | |
| `playlist [DIR]` | [fix `.m3u` playlists](#fixing-playlists-playlist) | `playlists` |
| `prepare [DIR]` | [unzip and convert disc images](#preparing-disc-images-prepare) to CHD, xiso or zar | |
| `install` | `brew install` whichever of 7z (`sevenzip`), unar and chdman (`rom-tools`) are missing, and say how to build extract-xiso and iso2zar | |
| `mirror [DIR]` / `mirror use DIR` / `mirror clear` | [local mirror](#local-mirror-mirror) | |
| `cache [update [--full]]` | show the [storage cache](#storage-cache-cache), or read all of storage into it | |
| `config show\|path` / `config set NAME VALUE` / `config unset NAME` / `config apply [CARD]` / `config push USER@HOST` | effective [settings](#settings-config) and where each came from, or the data folder's path; change or remove a setting; apply the saved settings to a spruce, Knulli or EmuDeck card or an Android device; copy the settings and collections to a SteamOS device over SSH | |
| `refresh` | run `cache update`, `scrape --all --yes`, `scrape clean --yes`, `collections retitle` and `scrape art --for both` in order, stopping at the first failure | |
| `guide` | open the device setup guide in a browser | |
| `doctor [--fix]` | check AWS profile, storage, tools and data files; `--fix` runs `install` when tools are missing | |
| `check` | validate your JSON data files (`cards.json`, `surprises.json`, the device overlay, storage's tags and your collections) | |
| `completion bash\|zsh\|fish` | shell completion script | |

Flags that make no sense for a command (`--dry-run` with `edit`, `--replace` without `upload` or `scrape art`) are refused rather than ignored, and abbreviations like `--up` are not accepted. A card folder named like a command or alias: write `./edit`.

### Options

For every command they make sense with:

| Flag | Description |
| --- | --- |
| `-n`, `--dry-run` | Show what would be done (a sync: what would be downloaded, with total sizes; `mirror`: what it would download and delete) and change nothing. Commands that only read (`diff`, `check`, `doctor`, `guide`, `cache`, `refresh`, `config` (except `config apply` and `config push`, which list what they would set), `completion`, `themes pick`/`build`/`palettes`, `games list`/`export`) or can't honor it (`edit`, `scrape review`, `scrape missing`, ...) refuse it with exit 2 |
| `-y`, `--yes` | Answer prompts with their default. It is the confirmation of `upload` (overwrites), `scrape clean`, `prepare` (removes the originals), `cards clean`, `cards layout`, `cards install` (deletes the card's other files), `cards delete`, `cards export` (overwrites FILE), `saves manage` (deletes the picked stashes), `themes publish` (stale theme files), `download pico8` and `scrape match` (`upload`, `prepare`, `scrape clean`, `cards install`, `cards export`, `themes publish`, `download pico8` and `scrape match` ask otherwise, `scrape clean` with default no and the others with default yes, and exit 2 without a terminal) |
| `--json` | `devices`, `layouts`, `games list`, `cards list`, `diff` and `sync --dry-run`: one JSON document on stdout, nothing else (pass `--device`/`--layout` so no picker is needed; `diff` also needs `--system ID` unless the folder is named after a system) |
| `--quiet` | Print only errors (failed files and a sync's failure count included, and `check`'s problems), warnings and `--json` data, all on stderr except the JSON; commands whose whole output is the answer (`doctor`, `config show`, `cache`, `cards list`, `games list`, ...) still print it; prompts are asked on stderr |
| `--verbose` | Also print the effective settings and where each came from, on stderr |
| `--profile P`, `--write-profile P`, `--bucket B`, `--root DIR`, `--endpoint URL` | Override those settings for this run. Precedence: flag, then environment variable, then `settings.json`, then the default |
| `--version` | Print the version |
| `-h`, `--help` | Show the help screen (`sync-roms COMMAND --help` or `sync-roms help COMMAND` for one command) |

For one command:

| Flag | Command | Description |
| --- | --- | --- |
| `-a`, `--ask` | `sync` | Confirm the saved device and layout instead of using them silently |
| `--device ID\|full`, `--layout NAME` | `sync`, `cards new`, `cards set` | Choose the setup without the picker (it is saved for the card). `cards layout` takes `--layout` too |
| `--guest` | `sync` | Make the card a guest card (saved): each sync seeds its picks from the storage ROMs on it (name and size), copies only ROMs, BIOS and scrapes, never overwrites a file and deletes only the seeded ROMs you deselect, with their media |
| `--no-delete`, `--no-clean`, `--no-eject` | `sync` | Never delete from the card (what would have been deleted is listed instead); skip the end-of-run card tidy; leave the card mounted |
| `--size SIZE` | `cards new`, `cards set` | The card's size as people read it (`256`, `512GB`, `1TB`), shown by `cards list` and on sync |
| `--card NAME` | `games` | The card whose games to change (required) |
| `--replace` | `upload`, `scrape art` | `upload`: make the storage folder match `DIR`. `scrape art`: remake the art files that already exist |
| `--system ID` | `diff`, `scrape`, `scrape missing`, `scrape art` | `diff`: the system to compare with, instead of the picker. `scrape`, `scrape missing`, `scrape art`: only that storage folder (the same as `scrape SYSTEM`) |
| `--for onion\|spruce\|both` | `scrape art` | Which art to make (default both) |
| `--workers N` | `scrape art` | How many sources to download at once (default: your CPU count); conversion always uses one process per core |
| `--all` | `scrape`, `scrape missing`, `cards list` | Every ROM in storage, not only the games your cards reference; with `cards list`, guest cards too |
| `--retry` | `scrape` | Also try the ROMs ScreenScraper didn't know before (ROMs whose lookup failed are always tried again; non-games never are) and, with `--fill-media`, the ROMs missing only media it didn't offer |
| `--fill-media` | `scrape` | Also scrape ROMs that have metadata but lack some media type in storage; their metadata is kept. Media types ScreenScraper didn't offer for a ROM are remembered, and a ROM missing only those isn't asked for again until `--retry` |
| `--skip-media TYPES` | `scrape`, `scrape match` | Comma-separated media folders not to download (e.g. `manuals,fanart`) |
| `--translated` | `scrape match` | The ROM is a fan translation |
| `--set-credentials` | `scrape` | Ask for your ScreenScraper username and password and save them in `settings.json` |
| `--full` | `cache update` | List every folder and stat every file of a storage folder |
| `--retroarch DIR` | `saves stash`, `saves apply` | Read or write RetroArch's saves and states in `DIR` instead of a mounted card's RetroArch folder |
| `--user NAME` | `collections publish` | The site folder to publish to, `collections/NAME/` (lowercase letters, digits, `-` and `_`), instead of your login name |
| `--out DIR` | `themes build` | Build into `DIR/<theme name>` (replaced) instead of the cache |
| `--palette NAME`, `--all-palettes` | `themes build`, `themes publish` | The palettes to build each style in (`--palette` repeatable, duplicates ignored), or all 35. Without either, a terminal (without `--yes`) shows the palette picker; otherwise the saved `custom_theme_palettes` are built (none saved: exit 2). The flags never change the saved palettes |
| `--count N` | `download pico8` | Stop after N carts to add or upgrade |
| `--update` | `ports download` | Replace the zips storage has when PortMaster's catalogue has a newer version (another md5); with no ZIP, every such port |
| `--undo` | `ports done` | Forget that the card has the ports' game data |
| `--needs-data`, `--ready` | `ports search` | Only the ports that need game data added by hand, or only the ready-to-run ones (not both) |
| `--refresh` | `ports download`, `ports search` | Fetch PortMaster's catalogue again even when the cached copy is less than a day old |
| `--bucket-keys` | `check` | Also verify with the read-only profile that every game key in your cards and tags exists in storage |
| `--fix` | `doctor` | After the checks, run `install` when 7z, unar or chdman is missing |

| Environment variable | Description |
| --- | --- |
| `ROMS_BUCKET` | S3 bucket name. Overrides `bucket` in `settings.json`; when set, the first-run prompt is skipped |
| `ROMS_ROOT` | Folder (e.g. a mounted network share) used as storage. Overrides `root` in `settings.json`; wins over a bucket setting. Needs no AWS profile |
| `ROMS_ENDPOINT` | Custom S3 endpoint URL. Overrides `endpoint` in `settings.json` (default: AWS) |
| `ROMS_PROFILE` | AWS profile to use. Overrides `profile` in `settings.json` (default `roms-readonly`) |
| `ROMS_WRITE_PROFILE` | AWS profile used to write to storage (`upload`, `scrape clean`, `scrape` and the like). Overrides `write_profile` in `settings.json` (default `roms`) |
| `XDG_DATA_HOME` | The data folder is `$XDG_DATA_HOME/sync-roms` when set (macOS and Linux) |
| `ESDE_APPDATA_DIR` | ES-DE's folder on the machine, for `emudeck` cards (default `~/ES-DE`) |
| `NO_COLOR` | Disable colors (so does `TERM=dumb`) |
| `FORCE_COLOR` | Use colors even when the output isn't a terminal (`CLICOLOR_FORCE` does the same) |

### Settings (`config`)

`sync-roms config set NAME VALUE` saves one setting in `settings.json` and `sync-roms config unset NAME` removes it (it then falls back to its default). The names are `bucket`, `root`, `endpoint`, `profile`, `write_profile`, `mirror`, `screenscraper_user`, `screenscraper_password`, `ra_mode`, `ra_username`, `ra_password` and `ra_api_key` (text), `eject` and `storage_cache_declined`, `ra_offline_proxy`, `ra_proxy_stats` and `syncthing` (`true` or `false`), `surprise_ttl_days` (a positive number of days), `surprise_excluded_systems` (comma-separated system ids, e.g. `gba,snes`) and `pages_repo` (the git URL of the GitHub Pages repo `collections publish` pushes to, default `git@github.com:kelsin/sync-roms.games.git`); `root` and `mirror` must be absolute paths (`~` is expanded). Other names and values that don't fit are refused (exit 2) with the valid ones. The passwords and API key are saved but never printed; `scrape --set-credentials` asks for the ScreenScraper one, which keeps it out of your shell history. The `ra_*` settings are your RetroAchievements settings for spruceOS, Knulli and Android (`ra_mode` is `Manual`, `Disabled`, `Casual`, `Softcore` or `Hardcore`): every sync of a `spruce` card writes the ones that are set into its `Saves/spruce/spruce-config.json` (the other settings in that file stay as they are; a missing or unreadable file is skipped with a warning), so Spruce applies them at the next game launch. `ra_api_key` also goes in the card's `Saves/cheevos/apikey.txt`, where spruceOS's Cheevos app reads it (only a key of 32 letters and digits, and only on a card with a `Saves/` folder; unsetting it leaves the file). `sync-roms config import [CARD]` (a card name from `cards.json`, or its mounted folder) also saves your other spruceOS preferences (for a `spruce` card) (emulator, in-game menu, button, boot and network options, not hardware, LED, battery, audio or proxy ones) from the card into `spruce_settings` in `settings.json` (for a `knulli` card it copies the allowlisted `system/knulli.conf` preferences into `knulli_settings`; other layouts aren't supported yet), after listing the ones that are identical and the ones that differ (saved value -> card value) or are new, and asking Yes, No or Pick one by one (there is no default answer, and without a terminal nothing is saved); a sync then sets those on a card, only where its file already has the section and key. While `syncthing` is on, `raAutoSave`, `raAutoLoad`, `keepSavesBetweenCores` and `enableSyncthing` (WiFi devices only) are set by sync-roms instead, so they aren't imported. `spruce_themes` (the PyUI themes every spruce card gets) is a list, not a `config set` name: `sync-roms themes pick` chooses it. `custom_theme_palettes` (the palettes `themes build` and `themes publish` build without `--palette` or `--all-palettes`) is a list too, saved by their palette picker. `spruce_settings` isn't a `config set` name: import it, or edit `settings.json` by hand (`{"Button Settings": {"menuButton": "L3"}}`, values as the card holds them). `syncthing` is on unless set to `false`: it makes sync set the Syncthing cores and settings on `spruce` cards, and `false` stops that (see the setup guide). `syncthing_server` isn't a `config set` name either: edit `settings.json` by hand (`{"id": "<server device ID>", "address": "tcp://host:22000", "folders": {"saves": "<folder id>", "states": "<folder id>"}}`, `address` optional and `dynamic` without it; a malformed one is warned about and skipped). While `syncthing` is on, a sync of a `spruce` card for a device with WiFi then writes that server and the two folders (`Saves/saves` and `Saves/states` on the card) shared with it into the card's `Saves/syncthing/config/config.xml`: it adds what is missing to an existing config and leaves a server already there as it is, and with no config it writes a new one (web UI on port 8384, login `spruce` / `happygaming`) that spruceOS then keeps, so the device only needs the server to accept it. A card with no `Saves/` folder is skipped with a warning, as is a config that can't be parsed or a folder id already used for another path. `config apply` does the same, and `--dry-run` lists the server and folders. `sync-roms config apply [CARD] [--dry-run] [--yes]` applies the saved settings without a sync: to a mounted `spruce` card (a name from `cards.json`, or its folder) the spruceOS settings, WiFi networks and Syncthing settings a sync writes; to a mounted `knulli` card the `system/knulli.conf` settings a sync writes (RetroAchievements, up to three `wifi_networks`, the hotkey scheme and `knulli_settings`; the file must already exist); over adb to an Android device (an Android card's name, or none to pick the device) RetroArch's and ES-DE's settings, with RetroArch Cloud Sync turned off (and its overlay folder pointed at the card's `Bezels/retroarch` when storage has bezels for the device), and its APKs installed or upgraded, except those that don't fit the device; when RAOfflineProxy is on for the card and installed it gives it All files access and a battery-optimization exemption; while `syncthing` is on it also gives Syncthing-Fork All files access and a battery-optimization exemption and, with `syncthing_server` set, adds the server and the two folders of `syncthing_server` to it through its REST API, reading the API key from its unencrypted export (`backups/syncthing/config.zip`, made in Syncthing-Fork under Settings > Import and Export; a missing export or a stopped app warns and skips the folders); for an `emudeck` card (its folder, the one that holds `Emulation/`, or none when run from it), run on the Steam Deck or Steam Machine itself, the settings of EmuDeck's Flatpak RetroArch (`~/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg`, as on Android but without the hotkeys, overlay folder or save folders, which EmuDeck sets; a missing file skips RetroArch and Syncthing; RetroArch must be closed, which it waits for), ES-DE's emulator per system in this computer's ES-DE (skipped when it doesn't use the card's ROMs; asked first, default no, while ES-DE is open, since it rewrites its gamelists when it quits) and, while `syncthing` is on, Syncthing: the one already running or installed (systemd or Flatpak), else (only with `syncthing_server` set) the official one installed as a systemd user service, given (with `syncthing_server` set) the server and RetroArch's save and state folders (their real paths); it warns when EmuDeck's Cloud Saves are on or a RetroArch core override sets `savefile_directory` or `savestate_directory`. `--dry-run` lists every setting, changed or not. `sync-roms config push USER@HOST [--dry-run]` copies this machine's settings to a Steam Deck or Steam Machine that runs sync-roms, over `ssh` (with `BatchMode`, so key login must already work): `settings.json` without `bucket`, `root`, `endpoint`, `profile`, `write_profile`, `mirror`, `eject` and `storage_cache_declined` (the device keeps its own values of those; its other settings that this machine lacks are removed) and every collection (the device's collections are made to match, removed ones included), into the device's data folder (`$XDG_DATA_HOME/sync-roms`, else `~/.sync-roms`), keeping the device's previous `settings.json` as `settings.json.bak`. It lists the settings and collections it adds, changes or removes by name, never their values (`--dry-run` stops there), and exits 3 without writing when the device's `settings.json` can't be parsed. A `settings.json` that can't be parsed is never overwritten (exit 3); the file from before a run's first change is kept as `settings.json.bak`.

### Data folder

Your own files live in the data folder: `$XDG_DATA_HOME/sync-roms` if that is set, otherwise `~/.sync-roms`, on macOS and Linux; `%APPDATA%\sync-roms` on Windows (`sync-roms config path` prints it). It holds `settings.json`, `cards.json`, `surprises.json`, `collections/`, `saves/`, `cache/` and `storage/` (local copies of the files shared through storage: `ignored.json`, `tags.json`, scrape state). None of it is ever written to storage.

An optional `device-systems.json` there adjusts the systems a device can play: `{"miyoo-flip": {"add": ["psx"], "remove": ["gba"]}}` (system ids as in `systems.json`; the package's order is kept and notes always come from the package).

## Cards (`cards`)

A card is a folder name (the card root's name) with a remembered device, layout and games.

- `cards list` (or just `cards`) shows the space each card's picks take (ROMs, scrapes and BIOS) against its size, how many full systems and games it syncs, and which of Surprise (🎁), theme art (🎨), collections (💖) and RAOfflineProxy (🏆) are on. Guest cards (a friend's card, marked 👤) are hidden unless you pass `--all`.
- `cards new NAME --device ID|full --layout NAME [--size SIZE]` creates a card; `cards set NAME` changes one's device, layout or size.
- `cards rename OLD NEW` and `cards delete NAME` rename and delete one.
- `cards layout [CARD] --layout NAME` moves the mounted card's ROMs, BIOS and RetroArch saves and states to another layout's folders and saves the layout (the device stays). `--dry-run` previews, `--yes` skips the question. A progress bar counts the moves and deletions. Files already at a destination are left; the rest is for a sync to fill in. A change to or from `muos` leaves saves and states where they are and lists them, since muOS uses Pickles' own, not RetroArch's. The old layout's scraped media (gamelists and media folders) is deleted from the old ROM folders; the new layout's own is installed by the next sync.
- `cards install [CARD]` puts storage's newest `os/spruceos/spruceV<version>.7z` on a `spruce` card, for a new setup (for example after `cards layout --layout spruce`; run a sync after). It runs only on a mounted SD card's root, never on another folder named after the card. It downloads the release to a temporary folder and tests it, lists what is kept and what is deleted, and asks first (the answer defaults to yes). It is a clean install: everything at the card root is deleted except `Roms/` and the system folders macOS and Windows keep there (BIOS, saves, themes and the rest go; a sync afterwards puts BIOS, themes and the rest back); the release is then unpacked without replacing files already on the card. The download and the unpacking each show a progress bar (the download with its speed and time left). `--dry-run` downloads, deletes and writes nothing, `--yes` skips the question (without a terminal it is required, or the command exits 2). Only `spruce` cards for now. Needs the 7z (`sync-roms install`); a sync then doesn't stage that 7z again. A sync of a mounted `spruce` card missing `spruce/`, `App/` or `Emu/` offers this install first (with a terminal and without `--yes`).
- `cards clean [CARD]` deletes such media that other layouts left on a card (`--dry-run` previews).
- For `cards layout`, `cards install` and `cards clean`, CARD is a saved card's name or its mounted folder (default: the current directory).
- `cards copy SRC DST` merges games, excluded and collections (not surprises) into DST, skipping systems it can't play.
- `cards export FILE` writes the cards you pick to a file, flattening surprises and collections into games; it asks before overwriting an existing FILE (default yes; `--yes` overwrites, and without a terminal it exits 2 unless `--yes`). `cards import FILE` adds the ones you pick from such a file, keeping size, device, layout, games and excluded and turning Surprise off (`r` renames a card, `p` prefixes all).

### `cards.json`

```json
{ "RGSP": { "device": "anbernic-rg-sp", "layout": "nextui", "games": { "gb": { "full_system": true }, "gba": [ { "title": "Game", "bucket": "gba/Game.zip" } ] } } }
```

| Field | Holds |
| --- | --- |
| `device`, `layout` | the device id (or `full`) and the layout |
| `size` | the card's size, from `--size` |
| `games` | system ids mapped to the games picked there, a multi-disc game with one entry per file |
| a system in `games` set to `{"full_system": true}` | sync every file in the system's storage folder (subfolders included) instead of a list, so adding a file to storage is enough to publish it. No system is one by default. Toggled by `f` in the card editor (🗂️) or `games full SYSTEM on\|off`; the list the system had stays in the entry as `games` and comes back when it is switched off |
| `excluded` | `{"gba": ["gba/A.zip"]}`: collection games (and direct picks) this card opts out of, by switching them off (and back on) in a system's game list, where they show as 📦 or 💖 |
| `collections` | ids of your collections on this card; their games can be switched off one by one in a system's game list (into `excluded`). Single games picked from a collection with `l` → `Enter` are ordinary picks in `games` |
| `systems_off` | system ids turned off on this card with `x` in the card editor: nothing syncs for them and Surprise skips them, while their picks and collections stay saved. Absent when none |
| `surprise` | Surprise on or off, only when it differs from the layout's default |
| `surprises` | the current surprises, `[{"system", "bucket", "title", "files"?}]`, `files` being a multi-disc game's other keys |
| `surprise_excluded_systems` | system ids Surprise never picks from on this card, on top of the setting of the same name |
| `surprise_tags` | tag ids Surprise picks only from on this card (a game with any of them); overrides the setting of the same name. Absent when none |
| `theme` | `false` (like the next two, on when absent and switched in the card editor's `S` menu): a sync doesn't copy Art Book Next, doesn't select it in ES-DE or Knulli and adds no collection art (Surprise's included) |
| `custom_collections` | A collection is written when it is on the card or any of its games is. `false`: a sync writes no collections to the frontend, Surprise's included (and, on Onion, no Surprise app), and removes the ones it wrote before; the games themselves still sync, Surprise's too |
| `raofflineproxy` | `false`: no RAOfflineProxy on the card |
| `muos_storage` | `muos` cards: `"sd1"` (default, mounted at `/mnt/mmc`) or `"sd2"` (`/mnt/sdcard`), the storage muOS reads the ROMs from, which collection entries point at. Set it by hand; there is no editor for it |
| `spruce_theme` | `spruce` cards: the current PyUI theme (a folder name from storage's `os/spruceos/themes/`), picked in the card editor's `S` menu; synced when storage has it and set as the card's selected theme |
| `one_theme` | `spruce` cards: `true` when the card's one-theme mode is on (the card editor's `S` menu), absent otherwise: a sync puts only the card's `spruce_theme` on it, not the default list; the card editor's system-list title shows ` · 🎨 <theme>` (or `one theme: none picked`) while it is on |
| `spruce_themes_installed` | written by sync: the theme folders it installed on a `spruce` card, the only ones it removes when they are no longer synced |
| `spruce_os_kept` | written by sync: the spruceOS 7z files `--no-delete` kept at a `spruce` card's root, which the next sync without it removes |
| `frontend_collections`, `drivers`, `pico8`, `surprise_app`, `raofflineproxy_app`, `spruce_os`, `spruce_emu` | written by sync: the collections, driver zips, PICO-8 zip, Surprise app, RAOfflineProxy file and spruceOS file it put on the card, so each is copied once and only sync's own files are replaced or removed |

## Editing a card's games (`edit`, `games`)

A card syncs exactly what is picked for it (games and full systems), saved in [`cards.json`](#cardsjson). Any old `games.json` in the data folder is no longer read. A fresh install starts with no games, so a card syncs no games until you pick some here. Storage is only read to show what is in it, so the read-only profile is enough. No folders are needed:

```bash
sync-roms edit
```

1. **The menu** has **Cards**, **Tags** ([`tags edit`](#tags-tags-edit-tags-suggest)), **Collections** ([`collections edit`](#collections-collections-edit)) and **🧩 Device systems**, which edits which systems a device can play (saved as the `add`/`remove` overlay in [`device-systems.json`](#data-folder)). Under **Cards**, pick one of your cards, or **➕ New card** (asks for its folder name, then its device and layout, like the first sync does, and saves the card). Each card's row shows its device and layout. `v` changes them instead of opening the card (saved with the review at the end) and drops the card's games for systems the new device or layout doesn't use; `r` renames a card and `d` deletes one (both ask first, and act at once).
2. **A card** opens on every system its device can play, in the usual order. Systems recommended for the device's screen are marked ⭐; each system with picks shows how many games and how much space they take (ROMs plus the scraped files the card's layout installs), and every system shows its size as a full system (🗂️, all its files, scrapes and BIOS). The bottom line shows the card's total (games, scrapes and the BIOS files of the systems it syncs) against its size and the free space, in green below 70% of the card, yellow below 90% and red above (or over). Sizes come from the [storage cache](#storage-cache-cache); without one they show `…` and the total says "not sized". Games save to `cards.json` as you leave a system. `Esc` goes back to the menu. The keys:
   - `Enter` opens a system, `f` makes it a full system (again brings the game list back).
   - `x` turns the system off on this card: nothing of it syncs and Surprise skips it, while its picks and collections stay saved (again turns it back on).
   - `a` lists every game across the card's systems and `s` opens the tag filter first (`Enter` cycles a tag through off, required ✅ and excluded 🚫; games must have every required tag and none of the excluded; `c` clears it), then that list. The filter is sticky: once set it narrows every game list that has `s` and `c` (and shows on its filter line) until `c` clears it; the filter line says how many rows it hides (`2 of 9 shown`), a list with no match says so, and the games switch on and off like any other list. The card's system list, its collections list and the editors' top menus show the filter too and `c` clears it there; while a filter is on the system list adds an `N match` column, and a list that ignores the filter (a tag's own games, a collection's own games, the tag suggestions) says `tag filter paused here`. `c` clears the `/` search along with the filters. Every game list ends each row with the game's tag emoji, and `t` on a game edits its tags. `T` tags every game the list shows (the same checklist, with the tags all of them have already checked; checking adds a tag to each, unchecking one they all have removes it; it asks `Tag N games?` first and reports `Tagged N games`). While a filter is set, `a` in the all-games list switches every shown game on or off (without one it is off: the list is every game). The filter list also has `No tags at all` (only games with no tags; it can't be combined with a required tag, so it is left out while one is set), keeps listing tags you already require or exclude even with no games left, and counts the games the filter still shows.
   - `l` adds a collection to the card (each shows how many of its games are playable on the card's device, `Space`/`Tab` toggles the whole collection, and `Enter` opens its games to pick them one by one, as direct picks; it also shows how many of its games are on the card; collections with no playable games are hidden until `z`, unless they're on the card).
   - `S` opens a settings menu: turn [Surprise](#surprise) (🎁), the card's theme (🎨), its custom collections (💖) and RAOfflineProxy (🏆) on or off, or pick the systems and the tags Surprise may use on every card or on this card. The menu stays open on the row you used until `Esc`.
   - `D` clears every pick and full system from the card.
   - `K` (opened from a sync) picks, in every system that isn't a full one, the files already on the card that match a storage game (names compared ignoring case), so a sync keeps them.
3. **A system** shows every file in its storage folder. `✅` is synced, `⬜` is not; 💖 marks a game that a collection of the card syncs (switching it off excludes it on this card) and 🎁 Surprise a surprise: a surprise is always on and can't be switched off here, and all of them count in the card's budget and size warning. A multi-disc game's playlist and discs (marked 🔗) switch on and off together, even when a filter shows only some of them. Pending changes show as `➕` / `➖` and are counted at the start of the bottom line (`+2 −1`), which updates the card's total and free space as you toggle. `Enter` keeps your changes; `Esc` asks whether to keep or revert them if there are any, those a filter hides included. Besides the [list keys](#list-keys):
   - `s` opens the tag filter: `Enter` cycles the highlighted tag through off, required ✅ and excluded 🚫, and the list shows the games with every required tag and none of the excluded. `t` on a game edits its tags (checked tags are the game's; `Space` toggles, `Enter` saves to storage at once, `n` adds a tag), and each row ends with the game's tag emoji.
   - `m` filters by the system's scraped metadata (`scrapes/<system>/metadata.json`): pick **Developer**, **Publisher**, **Genre** (its first part, so `Sports / Baseball` is `Sports`) or **Year**, then a value (each shows how many games in the list have it). Values are matched ignoring case, so `Capcom` and `capcom` are one value. Picking another value of the same field replaces it. A game with no value for a field never matches a filter on it. The metadata is read in the background once per session, so the menu says it is loading at first.
   - `p` narrows the list to games that were surprises within the last `surprise_ttl_days` (🎁 past surprises only).
   - `c` clears every filter. Filters on different fields, the tag filter and `/` all combine, and the filter line shows what is active.
   - `v` on a game puts one of its variants on other systems (listed on the highlighted row) on the card, or takes it off.
   - `w` writes a note on a picked game.
4. **When you leave the menu**, device, layout and device-system changes are summarized, then **save**, **keep editing** (`Esc` too), **discard**, or **list every change**. Nothing is uploaded.

While an editor is busy between two lists (the screen says `Working...`), `Ctrl-C` takes effect when that step ends: the editor then stops as it does for `Ctrl-C` in a list. Another `Ctrl-C` a second or more later, with the step still running, quits at once, and unsaved changes in the open editor are lost (the screen says when; a double press or a held key counts as one). The same goes for the tag and collection editors.

`Q` in a system's, collection's or all-games list leaves the card editor with what you toggled saved (as `Esc` from its system list does).

A full system has no game list to edit: opening it in the card editor only says so. Removing a game only drops it from the card's games; the file stays in storage.

### Editing from scripts (`games`)

`--card NAME` picks the card and every `games` command needs it; every command that changes the card takes `--dry-run` and prints what it changed.

```bash
sync-roms games add gba 'Metroid*' --card SD      # a name, SYSTEM/name, or a glob matched against storage
sync-roms games remove gba 'Metroid Fusion.zip' --card SD
sync-roms games full psx on --card SD              # sync a whole system (off brings its game list back)
sync-roms games list --json --card SD
sync-roms games export --card SD > list.txt
sync-roms games import list.txt --card SD         # - reads stdin
```

`games export` prints `SYSTEM/file` per line and `SYSTEM/*` for a full system, then `@collections ID`, `@frontend_collections NAME`, `@drivers NAME`, `@pico8 ZIP`, `@surprise true|false` (only when it differs from the layout's default) and `@surprises SYSTEM/file` (one per surprise) lines. `games import` adds the games of such a file; a field with `@` lines in the file replaces the card's value, lines starting with `#` are skipped, and entries for an unknown system are skipped with a warning.

### Tags (`tags edit`, `tags suggest`)

Tags live in storage's `tags.json`, shared by everyone using that storage (each machine keeps a copy in `storage/` in the data folder, checked against storage once a run). A tag put on a game by another machine shows up after `sync-roms cache update`. Tags only help find games: they never put a game on a card.

`tags.json` is `{"tags": {...}, "games": {...}, "declined": {...}}`:

```json
{ "tags": { "shmups": { "name": "Shmups", "emoji": "🚀", "description": "..." } },
  "games": { "gba/Game.zip": { "tags": ["shmups"], "files": [], "variants": [{ "bucket": "gb/Game.gb", "note": "adds a mode" }] } },
  "declined": { "gba/Other.zip": ["sports"] } }
```

A tag has an id (a lowercase slug, never changed), a `name` and an `emoji` (both required; an emoji belongs to one tag), and optionally a `description`. A game is a storage key (`<system>/<file>`) with its `tags`; titles come from the scraped names and the system from the key, so neither is stored. A multi-disc game adds `"files": [...]` with its other storage keys (the discs); the key is the playlist (`.m3u`) or disc 1. Tagging a playlist gives a new record its discs from storage; discs with no playlist are listed, and tagged, one by one. A game may also have `variants` (`[{"bucket", "note"}]`: later versions of the game that add something, shown by the editors, never synced with its tags). `declined` holds the genre suggestions you turned down, so they aren't suggested again.

In the card editor, the collection editor and every other list of games, each row ends with the game's tag emoji, `t` edits its tags and `s` filters by tags (see [Editing a card's games](#editing-a-cards-games-edit-games)). In the tag lists, the tags you added most recently this run (with `t`, `.`, `T` or the tag editor's add lists) come after the game's own, a tag's description is searchable and shown under the list, and `x` leaves a tag out of the filter directly. After a `t` the list says how many tags the game gained and lost (`+2 −1`), and `.` gives the highlighted game the same changes (in every games list and the variants list; `?` lists it); `t` or `.` with no game under the cursor says so. In `tags edit`, the tag list has Tag and Games columns, sortable with `o` and `O` (Games starts with the most; tags with no games are marked); merging or deleting a tag says what it did, and a name another tag has is refused on rename.

`sync-roms tags edit` lists them with their emoji, name and game count; `n` adds one (a name and an emoji; an emoji another tag uses is refused). Opening a tag lists its games, as the collection editor lists a collection's: Space switches one off (it loses the tag when you leave the list and keep the changes: with `Enter`, `A`, `S`, `Q` or `Ctrl-C`, or with `Esc`, which asks first whether to keep or revert them; it stays listed while the tag is open, so you can switch it back on) and `/` finds a game; `t` or `.` on a game that puts this tag on or takes it off moves its check with it. `A` adds games (also to a tag with none yet, whose screen offers Add games and Settings and takes `A`, `+` and `S` too): after a search (not of spaces alone) it opens **🌐 All systems** with that search, else it asks which system first; Enter there comes back to the tag's games on the game added. `S` opens the tag's settings: rename it (its id never changes), change its emoji or description (an empty answer keeps it, as in the collection editor; `x` clears the description), add the games of another tag, merge it into another tag or delete it (both ask first; deleting says how many games lose it). `Q` in a tag's games, its settings or an add list leaves the tag editor with what you toggled saved. The tag's own lists ignore the sticky tag filter, so it never hides the game you look for. Every change is saved to storage as it is made, and a storage error shows as a note on the screen.

`sync-roms tags suggest [SYSTEM ...]` suggests tags from the genres in `scrapes/<system>/metadata.json` (the first part of a genre, so `Sports / Baseball` is `Sports`; which tag each genre suggests is in `genre-tags.json`). It covers every version of each game: scraped games of those systems (all of them without arguments), except discs of a tagged game, and pairs already on the game or declined. The review lists the suggestions grouped by tag, all checked; the checked ones are added to the games (a game with no tags gets its first) and the unchecked ones are remembered in `declined`.

### Collections (`collections edit`)

`sync-roms collections edit` edits your own collections of favourite games. A collection is a file (`{"name": ..., "games": [...]}`) at `collections/<id>.json` in the data folder; opening one lists its games, with the same keys as the card editor's game lists; `A` adds games from a system and `S` opens its settings (name, description and [theme art](#theme-art), with the art's picture shown), and Done or Esc shows the changes; `Q` in a collection's games, its settings or an add list does the same, keeping what you toggled; confirming saves them to that folder (Quit discards). `Ctrl-C` with changes pending asks whether to save them first (a second `Ctrl-C` discards), counting open toggles as the tag editor does. A collection's own games list ignores the sticky tag filter (it says `tag filter paused here`), as the tag editor's own games list does, since switching a game off there removes it (`T` and `a` still act on the games it shows, and `Esc` asks before keeping what they switched); its add lists follow the filter like the card editor's lists. Collections are personal: they never go to storage or into the repo, and no `git` or `gh` is needed. Deleting a collection that cards use asks first and removes it from those cards; the deleted file is kept as `<id>.json.bak`. **Add games from a system** lists the systems as the tag editor does; with a tag filter set, `a` in its all-systems list switches every shown game on or off, so the games a filter shows are added in one go; there, `p` narrows the list to games that were surprises within the last `surprise_ttl_days` and `c` clears the filters, so a surprise you liked is easy to keep.

`sync-roms collections page [--out FILE]` writes your collections as one self-contained HTML page (no network needed) to `share/collections/index.html` in the data folder, or to `FILE` (`~` and missing folders are fine), and opens it. The page holds your game lists and their storage paths, so share it only if you're fine with that.

Each collection on that page (not the public copy `collections publish` makes) has an **Export** button that downloads it as `<id>.json`. `sync-roms collections import FILE... [--dry-run] [--yes]` adds such files to your collections, each under the id of the collection's name (not the file name, so a browser's `Couch (1).json` is still `couch`); a name that can't be a collection (empty, or `Surprise`) is skipped. When the id is taken it lists the games only in the file and only in yours (matched by storage path), then asks: **merge** (the default, and what `--yes` does: your collection gets the file's games it lacks, appended, and keeps its name, description, art and notes), **replace** (the old file is kept as `<id>.json.bak`, and cards using the id keep it), **rename** (asks for a new name; an empty one skips) or **skip**. When nothing differs it skips without asking, and without a terminal or `--yes` a taken id is skipped with a warning. `--dry-run` says what each file would do and writes nothing. A file that can't be read is warned about and skipped; when none can be, it exits 2. Each import is a copy: nothing links it back to the file.

`sync-roms collections share` shares that page on your tailnet (needs `tailscale` on PATH, with Serve and HTTPS enabled for the tailnet): it builds the page if it isn't there yet, runs a small local server for only the `share/collections/` folder (on `127.0.0.1`, port 8737 or a free one), has Tailscale forward `https://<machine>.<tailnet>.ts.net/collections/` to it with `tailscale serve`, and prints the link, copying it to the clipboard when it can. The server stops with `collections unshare` (which also turns off just that path) or a restart; run `share` again after a restart. To refresh a shared page, run `collections page`, which rewrites the served file.

Add one to a card with `l` in the card editor; a sync then writes it as a custom collection of the frontend, where the layout has them (see [What each layout gets](#what-each-layout-gets)).

#### Publishing to GitHub Pages

`sync-roms collections publish [--user NAME] [--dry-run]` publishes a public copy of the page to `https://sync-roms.games/collections/<user>/` (your login name, or `NAME`). The copy has no storage paths, but it does list your games (a game with no scraped name or saved title shows its file name). It also shows each game's scraped box art (a larger picture on hover or tap) and credits ScreenScraper; the local page has neither. When storage can't be reached it publishes nothing (exit 1), rather than a page without tags, sizes or scraped names. It keeps a clone of the Pages repo (`pages_repo`, default `git@github.com:kelsin/sync-roms.games.git`) in `cache/pages/` in the data folder, resets it to the repo's `main`, replaces only your own `collections/<user>/` folder, rewrites the site's list of users at its root, the `/collections/` redirect to it, `CNAME` and `.nojekyll`, and commits and pushes when anything changed (`--dry-run` lists the changed files and pushes nothing). Setting up the repo, Pages and the domain is in [docs/github-pages.md](docs/github-pages.md).

#### Theme art

In the collection editor, **Theme art** picks one of the pictures listed in `art.json` (one for each tag id, and more for genres and the usual kinds of personal collection), drawn in the Outline style of the [Art Book Next](https://github.com/anthonycaccese/art-book-next-es-de) theme (`src/sync_roms/data/themes/art-book-next/art/`; the collection file gets `"art": "<id>"`). `tools/gen_theme_art.py` draws them. When an ES-DE, EmuDeck, Knulli or ROCKNIX card using that theme gets the collection, it shows on its own in the system carousel with that art and a logo of its name, drawn with the theme's logo font (Changa One, SIL Open Font License: `OFL.txt` there). A collection named like a system or one of the frontend's own collections gets no art, and a name the font can't draw (accents are dropped first) gets no logo, so the frontend shows it as text.

### Surprise

Every card gets up to 10 surprises on top of the games you picked: random full English games (no BIOS, prototypes, betas, demos, hacks, re-releases or compilations; a multi-disc game counts as one) from every system the card's device supports, whether or not it has games picked. It is on by default on every layout but `allium`, which has nowhere to show them. Seven of the ten come from the systems recommended for the device and three from the others, spread evenly over the systems; a system with no candidates passes its slots on. Games never surprised come first, then games surprised before, then games another card currently holds. Full systems are used too, but any other game already on the card is left out. Systems listed in `surprise_excluded_systems` (in `settings.json` for every card, or on the card) are never used, and a card's current surprises on them are replaced at the next sync. `surprise_tags` (tag ids, picked in the card editor's `S` menu for every card or for one card; the card's wins) limits Surprise to games with any of those tags; with none it has no limit.

- **In a sync** the surprises are handled in two steps. First, before anything downloads, it asks which of the card's current surprises to keep: each starts marked to be replaced, so the ones you mark are kept and the rest replaced (`Esc` with nothing marked replaces them all). Each row shows the game's size on the card (its ROM files plus the scraped files the card's layout gets), so you can see what keeping it costs. Then it then opens the card editor (also with Surprise off). Last, when the editor is done and the sync starts, the empty slots are filled at random. Without a terminal, with `--yes` or `--json` it replaces all of them. `--dry-run` changes no surprises: it only says whether it would ask or replace all, previews the picks for empty slots and saves nothing. The mirror is refreshed again only when the editor or the new picks changed the card's picks.
- **Turning it off** in the card editor's `S` menu removes the card's surprises at the next sync.
- **History** is kept in `surprises.json` in the data folder (system, bucket, title, card, ISO date) and pruned past `surprise_ttl_days` in `settings.json` (default 183) whenever it is written.
- **On the device** the surprises show as a collection named `Surprise` (that name is reserved, so a collection of yours can't be called Surprise), with a gift-box artwork and logo like any collection with [theme art](#theme-art); Onion cards get the Surprise app instead (see [What each layout gets](#what-each-layout-gets)).
- **Mirror**: picks are made from storage itself, not the mirror, so they can be games the mirror doesn't have yet.

## Guest cards (`--guest`)

For a card that isn't yours (a friend's), run `sync-roms sync CARD --guest` once: the card is remembered as a guest card, and `F` in the [card editor](#editing-a-cards-games-edit-games) turns that off. A guest sync only adds ROMs, their BIOS and their [scraped data](#scraped-data-on-the-card), and leaves the rest of the card alone (no other ROMs or media are deleted or overwritten): no Surprise, apps, themes, collections, drivers, settings or fixes.

- Each sync starts from what the card already holds: every ROM in storage whose file is on the card (same name, ignoring case and Unicode form, and same size) becomes a pick. The editor opens on those picks; add games to copy them.
- A file already on the card is never overwritten, and a gamelist only gains entries for ROMs it doesn't list (one that can't be read is left as it is, with a warning).
- Only the ROMs found on the card at the start that you deselect in the editor are deleted (after you confirm, unless `--no-delete`), with their scraped media. A system turned off with `x` is skipped entirely. Your friend's other files are never deleted or overwritten. The exceptions: on Spruce cards, BIOS zips sync puts in a ROM folder are added to that system's `Emu/<folder>/config.json` ignore list, and the usual end-of-run tidy runs. Loose discs are left where they are.
- Without the editor (`--yes`, `--json`, no terminal) the picks are what the card holds and nothing is deleted.
- `F` in the editor asks before making a card a guest card, since its picks are replaced by the ROMs found on the card (answer No or Esc to leave it alone); turning guest off asks nothing.
- Turning guest off in the editor during a sync takes effect on the next sync.

## What each layout gets

Besides ROMs, BIOS and scraped data, a sync writes the card's [collections](#collections-collections-edit) and copies a few files from storage's `os/` folder:

| Layout | Collections | Collection art | Surprise | PICO-8 app | RAOfflineProxy | Saves (`saves`) | Also from `os/` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `esde` | `ES-DE/collections/custom-<Name>.cfg` | in a copy of the theme | collection | zip in `PICO-8/` | APK in `APKs/` | RetroArch | APKs, bezels in `Bezels/`, [GPU drivers](#gpu-drivers) |
| `emudeck` | as `esde`, on the machine | as `esde`, on the machine | collection | none | none | RetroArch | none |
| `knulli` | `system/configs/emulationstation/collections/custom-<Name>.cfg` | theme customizations | collection | zip in `roms/pico8/` | `roms/tools/RAOfflineProxy Install.sh` | RetroArch | none |
| `rocknix` | staged on the card, installed from Ports | theme customizations | collection | `pico8_64`, `pico8_dyn`, `pico8.dat` in `roms/pico-8/` | `roms/ports/RAOfflineProxy Install.sh` | RetroArch | none |
| `muos` | `MUOS/info/collection/<Name>/` | in the catalogue | collection | `pico8_64`, `pico8.dat` in `MUOS/bios/pico8/` | `MUOS/application/RAOfflineProxy/` | Pickles | none |
| `nextui` | `Collections/<Name>.txt`, one `/Roms/<system folder>/<path on card>` line per game | none | collection | none: carts are plain ROMs | none | RetroArch, MinUI save names | none |
| `spruce` | `Collections/collections.json` | `Collections/Imgs/<Name>.png`, also in `Imgs_med/` and `Imgs_small/` | collection | `pico8_dyn`, `pico8_64`, `pico8.dat` in `BIOS/` | none | RetroArch | spruceOS update file |
| `onion` | none | none | Surprise app | `pico8_dyn`, `pico8.dat` in `RApp/PICO-8/bin/` | `App/RAOfflineProxy/` | RetroArch | themes |
| `allium` | none | none | off by default | `pico8_dyn`, `pico8.dat` in `Apps/pico.pak/bin/` | `Apps/RAOfflineProxy.pak/` | RetroArch | none |

**Collections.** Each sync writes the card's collections, listing the collection games that are on the card; games on systems the card doesn't sync are left out. `--dry-run` lists what would be written.

- `<Name>` is the collection's name without the characters ES-DE rejects (`* " , . / : ; < > \ |`, newline, tab); collections whose names come out alike share one file.
- sync-roms only touches collection files it wrote (recorded as the card's `frontend_collections`). A collection made in the frontend with the same name is skipped with a warning. A collection removed from the card, or renamed, has its old file deleted and its name unlisted.
- The files are rewritten each sync, so edits made to them in the frontend are lost.
- Close the frontend before syncing: it rewrites its settings file from memory.

**Collection art.** With `--no-delete` a sync keeps a retired collection's file and its art (and, on Knulli, its settings), leaves its name in `frontend_collections` and lists it as kept, so the next sync without the flag removes them. A sync removes the art it put on an ES-DE, Knulli or ROCKNIX card (on Knulli its `subset.<Name>.*` settings too) once the collection is renamed, removed or has no art any more. It only removes what it wrote: the names listed in the theme copy's `.sync-roms-collections` (ES-DE) or the customizations folder's `.sync-roms-art` (Knulli, ROCKNIX), so the theme's own art and yours stay, as does art an older sync-roms put on a Knulli or ROCKNIX card before it kept that list. With `"theme": false` nothing is removed. `--dry-run` names the collections whose art would be removed.

**PICO-8 app** (the app itself, not games). Put the official PICO-8 Raspberry Pi zip in storage's `os/pico8/` (the newest `pico-8_*_raspi.zip` is used). A card gets the zip where its frontend's installer looks (run the installer once on the device) or the extracted files, once per zip, whether or not it syncs pico8 games.

**RAOfflineProxy** (the RetroAchievements offline proxy). A sync puts the newest `RAOfflineProxy-<Onion|Allium|muOS|Knulli|Rocknix>-v<version>` file (`.zip` for Onion and Allium, `.muxapp` for muOS, `-Install.sh` for Knulli and ROCKNIX) from storage's `os/onion|allium|muOS|knulli|rocknix/` on the card, once per file.

### ES-DE

- **Collections** are lines of `%ROMPATH%/<system folder>/<path on card>`, enabled through `CollectionSystemsCustom` in `ES-DE/settings/es_settings.xml`: the comma-separated list of enabled custom collections. Sync adds its names and keeps any others there; only that one line is changed (or added), and the file is created if missing.
- **Art** (when `Theme` in `es_settings.xml` is `art-book-next-es-de`): ES-DE on Android keeps downloaded themes off the card, so sync copies the theme from a GitHub archive of it in storage (`os/esde/themes/`, about 200 MB) into `ES-DE/themes/art-book-next-sync-roms/`, adds each collection's files (named for the collection in lower case) and sets `Theme` to that copy. `sync-roms themes update` puts the theme's latest commit in storage; a card's copy is replaced when storage has a newer one. ES-DE's theme downloader doesn't update the copy, and its menu lists both copies as Art Book Next. The art is for the Outline color schemes; others show the theme's default art. When a newer copy of the theme brings art of its own for a name sync wrote, that name leaves the `.sync-roms-collections` list and the theme's art stays.
- **APKs**: everything in storage's `os/android/APKs/` folder (APKs, the Obtainium app list) is copied to an `APKs/` folder on the card so the apps can be installed from the device, skipping files already there with the same size and never deleting anything. RAOfflineProxy's APK is one of them, left out when the card has it off.
- **Bezels**: the device's bezels from storage's `os/android/bezels/<device id>/` are copied to `Bezels/` (RetroArch overlays in `Bezels/retroarch/`, DraStic backgrounds in `Bezels/drastic/`), skipping files already there with the same size.
- **PICO-8**: pick the zip in pico8-android's zip picker.

### EmuDeck

EmuDeck's ES-DE keeps its data on the machine, not the card. So the gamelists, the collections and the theme art go into `~/ES-DE` (or `$ESDE_APPDATA_DIR`) on the machine running the sync, laid out as for `esde`; sync the card on the Steam Machine or Steam Deck to get them. Sync skips them with a warning when ES-DE isn't set up there, or when that ES-DE's `ROMDirectory` (in `settings/es_settings.xml`) isn't the card's `Emulation/roms`, as EmuDeck sets it. The ROMs, BIOS and scraped media go on the card either way.

### Knulli

- **Collections** are lines of `./roms/<system folder>/<path on card>`, enabled through `CollectionSystemsCustom` in `system/configs/emulationstation/es_settings.cfg`, handled as on ES-DE.
- **Art** (when `ThemeSet` in `es_settings.cfg` is unset or Art Book Next): the built-in theme is read-only, so the art goes to `theme-customizations/art-book-next/artwork/<Name>.png` and `logos/<Name>.svg`, and `es_settings.cfg` gets `subset.<Name>.system-view-artwork` and `subset.<Name>.system-logos` set to `custom`, so only that collection uses them (its logo sits a little lower than on the Outline systems). Knulli only shows a custom collection on its own when it isn't grouped under Collections, so `UseCustomCollectionsSystemEx` is set to `false` unless you already chose a value; that shows your other custom collections on their own too.
- **PICO-8**: Device Settings → Install Pico-8.

### ROCKNIX

BIOS files sit flat in `roms/bios`. RetroArch saves sit beside the ROMs: a sync never offers the saves, states and their thumbnails in ROM folders for deletion, `upload` and `diff` leave them out (anywhere), and `cards layout` moves them as saves.

- **Collections and Surprise**: ES reads collections only from the device's internal `/storage/.config/emulationstation/collections`, so a sync can't write them to the card. It stages them in `roms/.sync-roms-collections/` and writes `roms/ports/Install Collections.sh`. Launch **Install Collections** once from Ports on the device: it copies the collections to ES's folder, enables them and their art in `es_settings.cfg` (and turns off the settings of art a sync removed) and restarts ES. Its messages aren't visible on the device. Run it again after a sync changes collections.
- **Art** goes to `roms/_userdata/theme-customizations/art-book-next/artwork/<Name>.png` and `logos/<Name>.svg`.
- **RAOfflineProxy**: enter your RetroAchievements account in ES Game Settings first, then run the install script once from Ports; the app then appears under Tools.

### muOS

- **Collections and Surprise**: a collection's folder holds one `<ROM>-<8 hex digits>.cfg` entry per game on the card (the ROM's path on the device, its folder under `ROMS/`, its name). Only folders sync wrote are touched. The entries point at the storage named by the card's [`muos_storage`](#cardsjson).
- **Art** goes to `MUOS/info/catalogue/Collection/box/<Name>.png` and `grid/<Name>.png` (no logo); sync removes the ones it put there when a collection goes.

### Spruce

- **Collections and Surprise**: the one `Collections/collections.json` holds every collection; collections made on the device are kept as they are.
- **Art**: a sync also removes the picture of a collection it wrote that has no art any more, even with `"theme": false`.
- **spruceOS**: the newest `spruceV<version>.7z` from storage's `os/spruceos/` is copied to the card root, unextracted, for Apps → EZ Updater on the device: once per file, after the card's other writes, and only when the card has room for it with 64 MiB to spare. The one staged before is removed (kept with `--no-delete`). The sync's last line then reminds you to run EZ Updater.
- **Splore carts**: when the card syncs PICO-8, the carts PICO-8's Splore downloaded on the device (its cache in `Emu/PICO8/.lexaloffle/pico-8/bbs/`) that storage's `pico8/` doesn't have, or has an older revision of, are listed and added to storage after one question (default yes; `--yes` adds them, and without a terminal and without `--yes` they are only listed), with their titles from Splore's favourites. New carts are scraped when a ScreenScraper login is saved (else `sync-roms scrape pico8` does it later) and added to the card's games (a full PICO-8 system has them already); the same sync copies them to `Roms/PICO8/`. Copies Splore's import put in `Roms/PICO8/` under another name are renamed to the cart's own file name and, like any cached cart storage already has that is on the card under its own name, added to the card's games, so they aren't asked about as extra files. Not on guest cards; `--dry-run` only lists.
- **PortMaster**: on devices PortMaster runs on, the ports you pick (system `ports`, filled by `ports download`) are put in `Persistent/portmaster/PortMaster/autoinstall/` with their runtimes, and PortMaster installs them at its next start (boot the device once first). Installed ports, their saves and runtimes are never touched. The game data a port needs from you is copied once from storage's `os/portmaster/gamedata/<port folder>/` when storage has it; otherwise the port is listed as waiting, with its instructions (`ports needed`; `ports done CARD PORT` records data you put on the card yourself). `Roms/PORTS` is never swept.
- **Fixes**: a "Spruce fixes" block patches known spruceOS bugs on the card until upstream releases the fix. Until [spruceOS#2070](https://github.com/spruceUI/spruceOS/pull/2070) ships, that includes PyUI's game lists: backing out of a collection or a folder with B highlights it the next time instead of opening it again, and each folder remembers its own last game (PyUI still goes back inside after a game). Four PyUI files are patched, and their line ends are kept; a card patched with an earlier draft of the change, or with the earlier **Reopen last collection** setting, has it taken out again. This happens only when the card's PyUI matches a known version (4.6.0 or the current `Development` code); otherwise the card is left as it is, with a warning. `--dry-run` shows what it would change.

- **Themes**: `themes update` keeps every PyUI theme unpacked in storage's `os/spruceos/themes/`, `themes pick` chooses the default list (`spruce_themes`), and a sync copies that list plus the card's `spruce_theme` into `Themes/` (a card with one-theme mode on, turned on in the `S` menu, gets only its `spruce_theme`: a sync with a terminal and without `--yes` asks for one when none is set, and `t` still picks for that sync) (only missing or different files; each theme's `config*.json` is compared by content, so tweaks made on the device go back to storage's). With a terminal and without `--yes`, the download question takes `t` to pick the themes for that sync only (nothing is saved) and is asked even when nothing else is to download. Themes a sync installed and no longer wants are removed (not with `--no-delete`, and never the card's `spruce_theme` or the theme the device has selected). It then sets `"theme"` in the card's `Saves/*-system.json` files (spruceOS must have booted on the card). A card with no systems to sync gets no themes.

- **Custom themes**: the Pixel Consoles and Pixel Controllers styles (and `ToTK - James` and `ToTK - Kelsin`, below) are drawn by sync-roms itself (`src/sync_roms/custom_themes/`), from the SPRUCE theme in storage (`themes update` puts it there), in any of 35 palettes (`src/sync_roms/custom_themes/palettes.py`: Gruvbox, Arcade, Candy, ..., Monochrome). Each style in each palette is its own theme, `<style> - <palette>` (e.g. `Pixel Consoles - Gruvbox`); `--palette NAME` (repeatable) or `--all-palettes` picks the palettes. Without either, a terminal shows a list of every palette with a bar of its six colors (text, list, selected, accent, dim, bar) and, in terminals that draw images, a preview of a list screen in it; it starts from the palettes saved last time, and the ones you confirm with Enter are saved as `custom_theme_palettes` (saved even with `--dry-run`) and built (Esc builds nothing and saves nothing). With `--yes` or without a terminal, the saved palettes are built; with none saved it exits 2 naming the options. `themes palettes` opens an overview image of all 35. A palette sets the theme's text, list, grid and screensaver colors and the selection bar's color, and the colors of the redrawn frames (below); the icons' pixel art is the same in every palette. `themes build` writes them to the cache to look at; `themes publish` builds them and puts them in `os/spruceos/themes/` (only the themes built that run: other palettes' folders, and the folders of the earlier single-palette `Pixel Consoles` and `Pixel Controllers` themes, are left alone, never adopted), uploading only the files whose content changed (their hashes are in `os/spruceos/custom-themes.json`) and deleting the files a build no longer makes. A folder of the same name already in storage is taken over, unless `themes update` downloaded it, which is left alone. From there `themes pick`, a card's `spruce_theme` and sync treat them like any other theme. `ToTK - James` is the ToTK theme in storage (`os/spruceos/themes/ToTK/`) with the Triforce and "James" as its title picture (pasted into its preview too), Rauru as the main menu's Collections card (cards for Sidon, Riju and Mineru come with it), and no main menu title; it has no palette, so it is built once as `ToTK - James` whatever palettes are chosen, and asks for none. `ToTK - Kelsin` is the same theme with "Kelsin" in its title picture. Other machines see custom themes a publish added or removed after `sync-roms cache update`.
- **Custom theme frames**: the base theme's frames, bars, panels, keys and small glyphs (selection bars and tiles, title and hint bars, pop-up panels, keyboard keys and glyphs, button hints, the favorite and folder glyphs, the loading and charging frames) are redrawn as pixel art in the palette's colors, natively at each screen-size folder's own size (`skin/`, `skin_<W>x<H>/`, `skin_640_480/`), never scaled from another. Each keeps the base file's size and footprint (the box of its opaque pixels), so PyUI places text and images where it did, and follows the margin rules: artwork on a grid of square cells with any leftover pixels split evenly, even insets on opposite sides, equal inner padding, exact mirroring where a frame is symmetric. Some redrawn files (the loading bar, the nav bars, the keyboard glyphs, the spinner and charging frames) are used by older spruce UIs, not by PyUI itself. `tools/frames_sheet.py` is the developer tool for reviewing them: `uv run python tools/frames_sheet.py --base DIR --palette NAME [--palette NAME ...] --out FILE.png [--folder skin_1280x720] [--scale 2] [--only select|panels|keys]` builds the theme from the base folder in a throwaway folder and tiles every frame of one skin folder per palette (files over 300 px wide or tall at 1x, the rest at `--scale`; `--only` limits it to one group of frames).

### Onion and Allium

- **Surprise** (Onion): the newest `os/onion/Surprise-v<version>.zip` in storage is installed as `App/Surprise/`, once per zip, and `Roms/surprise.json` lists the card's surprises for it.
- **Themes** (Onion, not Allium): everything under storage's `os/onion/Themes/` is copied to the card's `Themes/`, skipping files already there with the same size and never deleting anything.

## GPU drivers

Android (`esde`) cards also get suggested GPU drivers. Each Adreno device in `devices.json` has a `gpu`, and `drivers.json` lists the custom drivers (Turnip builds and similar) suggested for each GPU. Every sync checks those drivers' GitHub releases and keeps the newest zip of each in storage's `os/drivers/` (with a `.tag` file naming the release; skipped without write access, a failure only warns), then copies the ones for the card's GPU to `Drivers/<driver>-<release tag>.zip` in the card root. A newer release gets a new file name and the old zip is removed; the card's `drivers` field lists the zips sync put there, so files you add yourself are never touched.

To use one, open the emulator's driver manager (for example the GPU driver settings of Winlator, Eden or another emulator that loads custom drivers), choose to install or import a driver and pick the zip from `Drivers/`. Drivers load per app, so nothing changes system-wide and no root is needed.

## Moving saves between cards (`saves`)

```bash
sync-roms saves stash /Volumes/SHARE     # copy saves and states off the card
sync-roms saves apply /Volumes/RGSP      # copy stashed ones onto another card
```

Both take the folder (default: the current directory) of a card with a layout (`sync-roms cards set NAME --layout NAME`) and need a terminal. `--dry-run` prints what would be copied. An Android card (an `esde` card whose device isn't `windows-pc`) stays in its device, so they reach it over wireless adb instead: pass the card's name (`sync-roms saves stash POCKETNOVA`), or no card from a folder that isn't one to pick the device. Another layout's card name fails: pass its mounted folder.

`stash` lists the card's games that have RetroArch saves (`.srm`, and Gambatte's `.rtc` clock files) or states (`.state`, `.stateN`, `.state.auto`, with their `.png` thumbnails), none picked, then the picked games' files, all picked, and copies those to `saves/<system>/<game>/<YYYYMMDD-HHMMSS>-<card>/` in the data folder with a `stash.json` saying what they are and where they came from. A run only adds stashes, never replaces one. On layouts sorted by core (and EmuDeck's flat folders) a save whose game's ROM isn't on the card (or is in several systems' folders) is skipped and counted; on Knulli and ROCKNIX the folder gives the system (on ROCKNIX saves with no ROM beside them are skipped too).

`apply` lists the stashes of the systems the card syncs (newest first; one per game can be picked), marking games whose ROM isn't on the card and showing each stash's label (set in `saves manage`), and copies them into the folders the card's layout reads. Identical files are skipped; a different file already there is listed and only overwritten after you confirm (default yes). A stash with no core (from Knulli or EmuDeck) going to a layout sorted by core asks which core folder to use, once per system: one already on the card, a typed name, or none (RetroArch with sort by core off); with `--yes` it is skipped.

| Layout | RetroArch folder | Saves | States |
| --- | --- | --- | --- |
| `esde` | `RetroArch` | `saves/<core>` | `states/<core>` |
| `knulli` | `saves` | `<system folder>` | `<system folder>` |
| `rocknix` | `roms` (beside the ROMs) | `<system folder>` | `savestates/<system folder>` |
| `onion`, `allium` | `Saves/CurrentProfile` | `saves/<core>` | `states/<core>` |
| `spruce` | `Saves` | `saves/<core>` | `states/<core>` |
| `nextui` | card root | `Saves/<TAG>` | `.userdata/shared/<TAG>-<core>` |
| `muos` | `MUOS/pickles` (Pickles) | `sram/<core>[/<ROM folder>]` | `state/<core>[/<ROM folder>]/<game>/` |
| `emudeck` | `Emulation/saves/retroarch` | `saves` | `states` |

- **NextUI**: `apply` renames a save to MinUI's `Game.gba.sav` (taken from the card's ROM; PlayStation saves and saves with no ROM there keep their name) and `stash` turns it back into `.srm`. States are copied as they are, so NextUI's own state names aren't converted, and a stash holding a state with no core is skipped.
- **Android**: needs `adb` (`brew install android-platform-tools`). "📱 Which device?" lists the devices adb sees (the wireless ones it finds on the network are connected first) with the card in each; its last row, "➕ Set up a new device", shows how to turn on Wireless debugging and pairs the device with its pairing code. The card's SD card volume is remembered in `cards.json` (`android_volume`), so the card is found in any device; a new one asks which card it is. RetroArch's save and state folders (and whether they're sorted by core) are read from its `retroarch.cfg`; saves or states in the content folder or sorted by content directory aren't supported and fail saying which setting to turn off. RetroArch must be closed on the device: it asks you to save in-game and close it, then checks again. The saves are copied to a temp folder, `apply` writes there and then pushes only the files it wrote (a file that fails is listed and the run exits 1), and the temp folder is removed at the end; `--dry-run` never writes to the device. `--retroarch` only applies to a mounted card.
- **EmuDeck**: its folders are symlinks that only resolve on the Deck; elsewhere pass the real folder with `--retroarch`.
- **muOS**: cards use Pickles' saves and states, copied as they are, not converted from RetroArch's. A stash made on a muOS card applies only to muOS cards, and `--retroarch` is ignored there.
- **ROCKNIX**: only RetroArch's files are covered. Saves of standalone emulators (PSP, PS1 memory cards, N64 and the like) are not stashed or applied.

States only load in the core they were made with (`gpSP` states don't load in `mGBA`); `.srm` saves (and `.rtc`) usually work in any core of the system.

`sync-roms saves manage` lists every stash in the data folder (game, system, card, date, files, size, core, missing files and label; a stash whose `stash.json` can't be read is listed by its folder and can only be inspected and deleted) and needs a terminal. `Space` picks stashes; `m` and `d` act on the picked ones, or on the highlighted one when none are picked. `Enter` lists a stash's files (marking missing ones and files `stash.json` doesn't list), `w` labels it (an empty label removes it), `m` moves it to another system (the game never changes; a muOS stash goes only to a system with a muOS folder), `p` asks how many to keep per game (default 1) and picks the older rest, and `d` deletes the picked stashes after listing them and asking (default no). A delete can't be undone; `--yes` skips the question. `--dry-run` changes nothing and prints what each action would do.

## Uploading ROMs (`upload`)

`sync-roms upload [DIR]` uploads the ROMs in `DIR` (default: the current directory) and its subfolders to the storage folder of one system, keeping the relative paths (`DIR/Disc/a.chd` becomes `<system>/Disc/a.chd`). It asks which system, with the cursor already on a guess: the system whose storage folder or frontend folder name (`gba`, `megadrive`, `ARCADE`...) is the name of `DIR` (the top of the list when none is). Esc cancels.

- It first runs [`prepare`](#preparing-disc-images-prepare) on `DIR` (with `--dry-run` too), so archives are unzipped and disc images converted before they go up; it prints nothing when no folder there converts, and asks as `prepare` does (`--yes` goes ahead).
- Files that already exist with the same size are skipped; a file with a different size overwrites the one in storage. Both counts are shown first, the overwrites are listed, and nothing uploads until you confirm (default yes; `--yes` uploads without asking, and without a terminal and `--yes` it exits 2). `--dry-run` shows the plan and uploads nothing.
- `--replace` makes the storage folder match `DIR`. Renamed files are moved by content (big bucket files without an MD5 are compared on samples, and those renames are marked) and left-over storage files are listed so you tick which to delete (none are ticked at first).
- Storage's [cache](#storage-cache-cache) is updated with every file written. After an upload that wrote files, `upload` runs `sync-roms scrape SYSTEM --all` and `sync-roms scrape art SYSTEM --for both` for that system, so the new games are scraped and have their box art; a failure there is only a warning (`sync-roms refresh` finishes it). So `sync-roms refresh` after an upload has nothing left to do.
- Frontend and OS leftovers (`gamelist.xml`, `images/`, `Thumbs.db`, `.DS_Store`, `._*`...) are never uploaded; other dotfiles are. In a card's ROM folder, the layout's own `.multi-disc/` and `.media/` folders and the playlists a sync pointed into `.multi-disc/` are left out too (also with `--replace`).
- It uploads with the write profile through one shared pool of requests, four per CPU core (at most 16), which the parts of big files share (64MB and up go as 32MB parts). The biggest files start first. To a storage folder, 8 files are copied at once.

## Fixing playlists (`playlist`)

`sync-roms playlist [DIR]` creates or fixes the `.m3u` playlist of every multi-disc game (`Name (Disc 1) (Extra).chd`, `Name (Disc 2).chd`) in `DIR` and its subfolders (default: the current directory). The playlist is named after the title without `(Disc N)` or tags the discs don't share (`Name (Sega CD).m3u`). Playlists with the wrong discs are rewritten, ones with some missing files lose those lines, ones with no files left are deleted after asking, and ones listing exactly a game's discs under another name are renamed. Local only; `--dry-run` previews.

## Preparing disc images (`prepare`)

Run it on a downloaded rom pack, or one system folder of it, before you [upload](#uploading-roms-upload) it to storage:

```bash
sync-roms install                       # once
sync-roms prepare --dry-run ~/roms
sync-roms prepare ~/roms/psx
```

`DIR` is one system folder or a folder of them (default: the current directory). What happens to a file is the `chd` setting in `src/sync_roms/data/systems.json` of the system whose folder it is in; systems without one are ignored:

| `mode` | Systems | What happens |
|---|---|---|
| `cd` | Sega CD, Saturn, TurboGrafx-CD, PC-FX, Neo Geo CD, PS1, 3DO, Dreamcast | `chdman createcd` from the `.cue`/`.gdi`/`.toc` (or `.iso`) |
| `dvd` | PS2, PS3, PSP | `chdman createdvd` for `.iso` files plus the system's `args` (PSP `-hs 2048`) and `-c` with its `codec` (PS2 `zlib`, PS3 `zstd`); bin/cue games use `createcd`, with `cdzl` for `zlib`. A `.chd` already there that isn't in its system's `codec` is recompressed. PS3 archives also keep their `.pkg`, `.rap`, `.dkey` and `.key` files (the system's `keep` list) beside the `.chd`s, so a PSN `.rar` just extracts to its PKG and RAP files for installing and an encrypted disc keeps the key it needs; an archive's other files (covers, readmes) are dropped. PS3 chds only load in ARMSX3 (Android), not in RPCS3, aPS3e or RPCSX |
| `extract` | GameCube, Wii, PC-98 | archives are unzipped and the files (e.g. `.rvz`) left as they are; nothing is converted |
| `xiso` | Xbox | archives are unzipped, then each `.iso` is rewritten as an optimized xiso with `extract-xiso -r` into a hidden folder (a loose `.iso` is copied there first, an unpacked one is rewritten directly), and the result replaces the original only once `extract-xiso -l` lists it cleanly; isos already in xiso format are left alone |
| `zar` | Xbox 360 | archives are unzipped, then each `.iso` is compressed into a zstd [ZArchive](https://github.com/Rucadi/ZArchive) `.zar` with `iso2zar` (written under a hidden `.part` name, renamed once the tool succeeds and the file is not empty) and the iso is removed; Xenia Canary and XenDroid read `.zar` |

- **Archives**: every `.zip`/`.7z`/`.rar` is unzipped with 7z (or unar for `.rar` when installed, since 7-Zip can't decode some RAR 2.9 archives), with the archives inside it, up to 3 levels (not for `extract` systems). A `.chd` already in an archive is just unzipped. An archive that converts is unpacked in the system temp folder when that is on another drive than `DIR` and has room for it with a margin of 10% of its free space or 1 GiB, whichever is larger (the size comes from the `.zip`/`.7z` listing), else beside the archive; the outputs are always written and verified in `DIR`.
- **In parallel**: up to one file per CPU core, and only as many at once as their unpacked files fit in free space; with fewer files than cores each `chdman` gets the spare cores. The biggest files start first.
- **Verified**: every `.chd` is written under a hidden `.part` name and renamed only after `chdman verify` passes; only then are its archive, `.cue`, `.bin` and `.iso` files deleted. On any failure the originals are kept. When a `.chd` of that name is already there (left by a run that was stopped, or made from another archive or image of the same disc name), the file is converted anyway and removed only when both hold the same disc (the same SHA1 in `chdman info`); otherwise it is kept, reported as failed, and the existing `.chd` is left as it is.
- **Playlists**: the `.m3u` playlists of every system folder are fixed afterwards (as [`playlist`](#fixing-playlists-playlist) does), even when there was nothing to convert (also shown by `--dry-run`). `"m3u": false` (3DO, Xbox, Xbox 360, PC-98) skips that step (3DO: Opera can't load `.m3u` files).
- **Progress**: in a terminal a bar shows the files done and the percent of the total size (each file counts by its size, its unpacked size for a `.zip`/`.7z`; an archive counts 20% once unpacked and its discs share the rest, from `chdman`'s own progress), the rate and the time left; each file's result prints as it finishes. Under `--quiet` only failed files and the closing line of a run with failures are shown (on stderr).
- **`Ctrl-C`** stops `7z` and `chdman`, removes the partial files and exits (130) without starting anything else; a rerun picks up where it stopped, and also deletes the extraction folders (`.chd-*`) a hard kill left behind, beside the archives and in the system temp folder.

It is local only, so storage holds the `.chd` and `.m3u` files and the card's games list those names. Running it on a card synced from a storage that still has the `.zip` files makes the next sync list the `.chd` files as files not in the card's games (it asks before deleting, default no) and download the zips again. Before it starts it asks `Convert N file(s) and remove the originals?` (default yes: `--yes` goes ahead, and without a terminal it exits 2 unless `--yes` is given; `--dry-run` only lists). So when a folder in `DIR`'s path is named after a saved card, `prepare` warns and asks first (default no: with `--yes` or without a terminal it stops and exits 1; `--dry-run` only warns). When `DIR` is inside the storage folder and a file converted, it ends by saying to run `sync-roms cache update`.

## PICO-8 carts from the BBS (`download pico8`)

`sync-roms download pico8 [--count N] [--dry-run] [--yes]` fills storage's `pico8/` folder from the [Lexaloffle BBS](https://www.lexaloffle.com/bbs/?cat=7&sub=2&orderby=featured) Featured listing, with the write profile. It reads every page of the listing, lists the carts storage doesn't have (`new:`) and those the BBS has a newer revision of (`upgrade: old → new`), and asks once (default yes; `--yes` adds them without asking, and without a terminal it exits 2 unless `--yes`); `--dry-run` lists them and writes nothing.

- Each cart is checked to be a PNG and uploaded as `pico8/<BBS file name>` (`molemole-1.p8.png`), and its title and author go into `scrapes/pico8/metadata.json` right away, so the editors and frontends show the title. Other entries in that file are kept.
- A cart's revision is its `-<number>` suffix (none is revision 0). An upgrade deletes the old revision, moves its metadata entry and its `scrapes/pico8/` media to the new name, and points your cards, Surprise history, collections and `tags.json` at the new file.
- Carts in `ignored.json` are never downloaded.
- Requests go one at a time. The first HTTP error stops the run with a warning; carts already added stay.

## Scraping from ScreenScraper (`scrape`)

`sync-roms scrape` looks up the available ROMs that have no entry in `scrapes/<system>/metadata.json` on [ScreenScraper](https://www.screenscraper.fr) and writes what it finds to storage (reads use the read profile, writes the write profile). PICO-8 carts that have an entry (from `download pico8`) but no scraped picture are taken too; a scrape only adds to their entry, keeping the BBS title and author.

**Credentials.** You need a ScreenScraper account; sync-roms carries its own developer credentials for the API. `sync-roms scrape --set-credentials` asks for your username and password (the password isn't echoed, a blank answer keeps the saved value) and stores them in `settings.json`, which is kept readable by you only (mode 600); `config show` never prints them. One request then checks the login and shows today's quota and threads, or the error (exit 1 when ScreenScraper refuses it). A run also checks the login before it asks to start, and warns when ScreenScraper sends no account details for it.

**Report.** Before any lookup the run lists the ROMs with no metadata and how each will be matched first, and in a storage folder how much it will read to hash them. `--dry-run` stops there, printing the metadata entries and media folders it would write, with no credentials and no request. `scrape match --dry-run` needs credentials: a name is searched (one request) and you pick a result, while a numeric game id is taken as is, unchecked and with no request; nothing is written.

**Matching.** A ROM saved with `scrape match` is used as is. Otherwise one lookup sends its hashes with its name and size. In a storage folder a file under 64 MB is hashed in place (hashes are remembered while its size and modification time stay the same); a bigger one is looked up by name and size, and hashed for a second lookup only when that finds nothing. In S3 the object's MD5 is sent when the bucket has one; ROMs are never downloaded from S3 to be hashed. A match counts as "by hash" when the ROM ScreenScraper matched has one of the hashes sent, and as "by name+size" otherwise; a name+size match is trusted without further checks. Names, dates and media prefer the regions `wor`, `us`, `eu`, `jp` in a fixed order; there is no setting for it. The response shapes and the search endpoint are written from ScreenScraper's documentation and ES-DE's scraper, not checked against the live API, so unexpected data is skipped.

**Manual match.** `sync-roms scrape match SYSTEM ROM GAME` (e.g. `scrape match gba "Game (USA).zip" 12345`) takes a ScreenScraper game id, or a name to search for and pick from. After you confirm (default yes; `--yes` goes ahead, and without a terminal it exits 2 unless `--yes`, before anything is read or written), the ROM is scraped as that game, and the choice is saved only once that worked; a game id ScreenScraper doesn't have saves nothing and exits with an error. A saved match whose game later disappears from ScreenScraper is forgotten and the ROM is marked unknown. For a ROM that already has metadata, the prompt lists the files involved and asks to replace it: the entry is replaced, and the old game's scraper-written media (including its Onion images) is overwritten or deleted after the new entry is written; `custom/` and the `--skip-media` types are left as they are. ROMs that share the name without extension (`Game.zip`, `Game.7z`) share their media files; the prompt warns about them.

`--translated` says the ROM is a fan translation: its entry is titled `<name> - Translated` and marked `"translated": true`. A ROM in `ignored.json` is taken off that list first so it can be matched; without `--translated` an ignored ROM can't be. The mark sticks across re-scrapes; to remove it, edit the entry in storage's `scrapes/<system>/metadata.json` (delete `"translated"` and the suffix).

**ROMs with no metadata.** `sync-roms scrape missing [SYSTEM]` lists every ROM your cards list (with `--all`, every ROM in storage) that has no entry in `metadata.json`, grouped by system, each marked with why: 🚫 a non-game waiting for review, ❔ not on ScreenScraper, 🔗 a saved match not scraped yet, or ⏳ not looked up yet. A system with no ScreenScraper id says so. It makes no request and writes nothing.

**Unknown ROMs and non-games.** A ROM ScreenScraper doesn't know is remembered and skipped on later runs, until `--retry`. ScreenScraper marks BIOS sets, demos, test carts and other software as non-games (`ZZZ(notgame)`): a run writes nothing for them and keeps them for review, and `--retry` doesn't look them up again. `sync-roms scrape review [SYSTEM]` goes through both kinds any time, so you can search each one under another name (an unknown ROM that has a metadata entry by now, or is gone from storage, is dropped; an unmounted share fails and drops nothing). A run on a terminal asks at its end whether to review its non-games now, and a run that leaves ROMs unmatched ends by naming `scrape review` and `scrape match`. Each ROM shows its position (`3 of 120`):

- `i` ignores it, and `I` ignores it and every one after it.
- `s` searches ScreenScraper under another name (Enter takes the suggested name) and scrapes the game you pick (with the review's login, no quota check and no results list); `t` does the same and scrapes the pick as a fan translation (`--translated`).
- `k` (the default) leaves it for later (ROMs kept for later come after the others in the next review).
- `b` takes back the last `i` and goes back to that ROM (a search already scraped stays: `scrape match` changes it).
- `q` stops.

Every letter but `i` and `I` works in either case.

Ignores are written when the review ends, by `q`, Ctrl-C or the last ROM, to `ignored.json` at the root of storage, shared by everyone using that storage: sync-roms never shows, syncs, uploads or scrapes the ROMs listed there, and never deletes their files. Each run checks the file and keeps a copy in the data folder. To stop ignoring a ROM, remove it from `ignored.json` in storage.

**Progress.** Before it asks to start, the run says the most requests it can make (one lookup and one download per media type for each ROM) and how many are left today. ROMs go in batches of 25. Each batch's heading shows today's requests as ScreenScraper last reported them and, from the second batch on, the time elapsed and left. Each ROM gets a line as it ends: the game it matched, how (hash, name+size or manual) and its media count, or that it isn't on ScreenScraper, is a non-game or failed. The media is then copied or uploaded behind a progress bar that lists only failures.

**Quota.** ScreenScraper limits requests per day, and separately unrecognized ROMs per day. When either is used up the run stops cleanly, with what it finished saved, and says which limit it was; run it again the next day.

**Ctrl-C.** The ROMs still being looked up or downloaded stop, and those that finished, in both batches being worked on, are uploaded and saved. Ctrl-C during an upload drops the files not started yet: in a storage folder the copies in flight finish and the ROMs whose media all made it are kept; in a bucket, ROMs with uploads still in flight are scraped again on the next run. The run then says how many ROMs it saved and how many are left, and exits 130; run it again to continue. A second Ctrl-C aborts at once.

**Errors.** A rate-limited request, a server error (HTTP 5xx) or a network failure is tried 3 more times, waiting 10, 20 and 40 seconds; a ROM that still fails is skipped and tried again on the next run. A media file that still fails on a server error or network failure is skipped on its own when another of the ROM's media files downloaded: the ROM is saved without it, and the run ends by counting the files skipped, which `scrape --fill-media` fetches. When none of the ROM's files downloaded, the ROM counts as one that couldn't reach ScreenScraper: nothing is saved for it and it is tried again on the next run. A ROM that fails because a download can't be saved locally (a full disk) is skipped at once, without retries. The run stops the same clean way as for the quota, and says what to do, when ScreenScraper refuses the login (check it with `scrape --set-credentials`), is closed to non-members or to everyone for now (try again later), or no longer accepts this version of sync-roms (update it), and when 3 ROMs in a row fail to reach ScreenScraper.

**What is written** under `scrapes/<system>/`: the entry in `metadata.json` (merged with what is there) and one folder per media type (`3dboxes`, `backcovers`, `covers`, `fanart`, `manuals`, `marquees`, `miximages`, `physicalmedia`, `screenshots`, `titlescreens`, `videos`), plus the Onion images. Media a ROM already has there is kept: those types aren't downloaded, and the confirm says how many files are kept. Media is downloaded only over https from screenscraper.fr, and only images and PDF manuals (up to 50 MiB each) and MP4 videos (up to 512 MiB) are stored; a file over its limit or outside screenscraper.fr is skipped with a warning and the ROM keeps its other media. `--skip-media TYPES` takes those folder names.

**Onion and Spruce images.** The box art of Onion, Allium and Spruce cards is made when the ROM is scraped: the cover (then the miximage) is resized to a PNG that fits 250x360 and stored as `scrapes/<system>/onion/<ROM>.png`, and to QOI files shrunk to fit and never enlarged: `scrapes/<system>/spruce/<ROM>.qoi` (640x480), `spruce_med/` (400x300) and `spruce_small/` (200x200), the last two only when they differ from the size above. A PICO-8 cart with neither uses its own `.p8.png`. ROMs in subfolders get none. It is made only from art downloaded in the same run; when that art is already in storage, or the ROM already has the image, none is made. `scrape art [SYSTEM | --system ID] [--for onion|spruce|both] [--dry-run] [--replace] [--workers N]` makes them for what storage already holds: `--dry-run` reads only listings and reports counts per system and target, existing files are skipped unless `--replace`, and the conversion runs in one process per core. Spruce's need Pillow; Onion's also work with macOS `sips`. A ROM with no Spruce art gets none on the card, and a sync suggests `scrape art --for spruce`.

**Shared state** in storage's `scrapes/`, so every machine sees it: per system `scrapes/<system>/matches.json` (your manual matches), `unknown.json` (the ROMs ScreenScraper didn't know), `nomedia.json` (the media types ScreenScraper didn't offer for each ROM) and `hashes.json` (file hashes), and `scrapes/notgames.json` (the non-games waiting for review, and the ROMs the review kept for later). Each is read through a copy in `storage/` in the data folder, and a write merges into the file in storage rather than replacing it.

## Cleaning scraped data (`scrape clean`)

`sync-roms scrape clean` needs no folder. It compares storage's `scrapes/` media and `metadata.json` entries with every ROM file in storage's system folders (not only the games listed on your cards), lists what no longer matches (including whole systems with no folder in storage), and after you confirm (default no; `--yes` deletes without asking, and without a terminal it exits 2 unless `--yes`) deletes the media and rewrites the metadata files. `--dry-run` only lists.

## Local mirror (`mirror`)

`sync-roms mirror DIR` keeps a local copy of just what your cards reference, with storage's own key layout: the ROMs a sync installs (every file of a full system), every system's BIOS files, and the `scrapes/<system>/` metadata and media for those ROMs. It also holds storage's Onion themes, ES-DE theme archives, GPU driver zips, PICO-8 zips and Android APKs, the runtimes and game data of the cards' PortMaster ports, the newest Surprise app, RAOfflineProxy files and spruceOS 7z, and the PyUI themes of the default list and the cards' current themes. It compares file sizes (and the ES-DE theme's commit file, always the same size, by checksum), so a rerun with nothing changed lists storage and downloads nothing. Anything in the mirror that is no longer referenced (a game removed from a card's games or from storage) is deleted, after asking (default no) when that is more than 25 files or a tenth of the mirror. A non-empty folder that isn't already a mirror (it has no `.sync-roms-mirror` file) is refused, and so is any mirror command when storage is a folder (`root`): it is already local.

`sync-roms mirror use DIR` does the same and saves `DIR` as `mirror` in `settings.json`. From then on every sync refreshes the mirror from storage first (if storage can't be reached it warns and uses what the mirror has), then copies its files from the mirror instead of downloading them. If `DIR` is missing (an unplugged drive) it uses storage. `upload` and `scrape clean` always work on storage itself, and `edit` lists it; when `edit` or `scrape clean` finishes successfully (not with `--dry-run`) the saved mirror is refreshed afterwards, so it picks up the change. `sync-roms mirror clear` removes the setting (the mirror's files stay); `sync-roms mirror` alone refreshes the saved mirror.

## Storage cache (`cache`)

Every command reads what storage holds (each file's name and size, and for a bucket its ETag) from `cache/storage-cache.json` in the data folder; only the files themselves are downloaded from storage. On a network share this turns minutes of listing and stat calls into an instant read. Nothing refreshes the cache on its own and it never expires: sync-roms's own uploads, moves and deletes keep it up to date, so run `sync-roms cache update` after changing storage any other way.

- `sync-roms cache` shows where the cache was read from, when it was last updated, and its files and size per folder.
- `sync-roms cache update` reads storage again: one listing of a bucket, or a walk of a storage folder that lists only the folders whose modification time changed since the last update and stats only the files the cache doesn't have: new files are added, missing ones dropped, and every other file keeps its cached size. This relies on storage changing a folder's modification time whenever a file is added to, removed from or renamed in it. A folder changed in the last few minutes is listed again on the following update, so a change made just before an update is picked up by the next one at the latest.
- `sync-roms cache update --full` lists every folder and stats every file in a storage folder. Use it for files replaced under the same name (the default keeps their cached size) and for anything a folder's modification time didn't show (say, a tool that sets it back). A bucket listing already has every size, so it's the same as `cache update` there.
- With no cache for the storage in use (none yet, or built from another bucket or folder), the first command that reads storage offers to build it. Saying no is remembered (`storage_cache_declined` in `settings.json`), and commands then list storage on every run as before; `sync-roms cache update` builds it any time.
- `scrape review` and `scrape clean` check storage itself for a ROM the cache doesn't list before they remove its review marks or scraped metadata: one that another machine added since the cache was built is kept, with a note to run `sync-roms cache update`.

## Flashing an SD card (`flash`)

`sync-roms flash [--dry-run]` writes a Knulli image (`os/knulli/knulli-*.img.gz`), a BaseOS image (`os/baseos/baseos-*.img.zip`), a muOS image (`os/muos/muos-*.img.gz`), a ROCKNIX image (`os/rocknix/ROCKNIX-<SoC>.aarch64-<date>[-variant].img.gz`) or an OakMoss image (`os/oakmoss/oakmoss-<device>-v<version>.img.xz`) from storage to an SD card. macOS only.

- You pick a kind of image (asked only when `os/` holds more than one; Knulli and BaseOS count as one), then a device (for Knulli or BaseOS, one that runs Knulli or has a BaseOS image; for muOS or ROCKNIX, one that runs it; for OakMoss, one an image is named after), then an image (the ones matching the device first, newest first), then an external SD card, shown with its volume names.
- Knulli, BaseOS and OakMoss images match a device by its name in theirs. muOS image names aren't documented, so none is marked as matching. A ROCKNIX image matches through the device's `rocknix_image` in `devices.json` (the image's SoC, plus the variant when the device belongs to one), and flash stops when none does; the Allwinner H700 devices match both the DDR3 and DDR4 images, so pick by the device's RAM. ROCKNIX's `.tar` update bundle and OakMoss's `.omupd` update files aren't flashable and aren't listed.
- The boot disk and the disks holding the temp folder or storage are never offered, and flash stops if it can't tell which disks those are.
- You confirm by typing the disk id (`disk4`). `--yes` never skips this. `--dry-run` stops here.
- The image is copied to a local temp folder (free space is checked first). Right before writing, the card must still be the same disk (id, size and name).
- `sudo dd` writes it decompressed (gz, xz or zip) on the fly with 4 MiB blocks. sudo may ask for your password before downloading and writing.
- The temp folder is removed, writes are flushed and the card is ejected. After a failure the card is unmounted instead, so you can retry.

## Formatting an SD card (`format`)

`sync-roms format [--dry-run]` erases an SD card as exFAT or FAT32 with a label you pick. macOS only.

- You pick an external SD card (shown with its volume names), then a filesystem, then a label: your card names, then the layout names uppercased, or type your own. FAT32 labels are uppercase, at most 11 characters; exFAT at most 15. Longer ones are left out of the list, and a typed one with characters the filesystem doesn't allow is asked again.
- The boot disk and the disk holding storage are never offered.
- You confirm by typing the disk id (`disk4`). `--yes` never skips this. `--dry-run` stops here and shows the command.
- Right before erasing, the card must still be the same disk (id, size and name).
- `sudo diskutil eraseDisk <FS> <LABEL> MBR <disk>` erases it. sudo may ask for your password. The card is left mounted.

## Claude Code skills

The repo ships [Claude Code](https://claude.com/claude-code) skills in `.claude/skills/` for upkeep that needs judgment. Run one from the repo root with `/<name>`, or just describe the task. The storage skills show what they would change and write nothing until you approve.

| Skill | Use it to |
|---|---|
| `dedup-names` | Find ROMs of one system shown under the same scraped name (fan translations, regional releases, mis-scrapes) and give each a qualifier, or re-scrape the ones matched to the wrong game. Only edits `scrapes/<system>/metadata.json`. |
| `match-translations` | Match the fan-translated (`[T-En]`) ROMs waiting in `sync-roms scrape review` to ScreenScraper games under their original Japanese titles, titled `<name> - Translated`. |
| `refresh-drivers` | Re-research the suggested Adreno GPU (turnip) drivers in `drivers.json` and the devices' `gpu` ids, and open a PR if anything changed. |
| `update-variants` | After new uploads, find ROMs that are variants of tagged games (remasters, enhanced ports, translations) and add them to the games' `variants`; also flags variants no longer in storage. Remembers judged ROMs in storage's `variants-checked.json`. |

## How it works

- Reads the systems, layouts, devices and BIOS requirements from `src/sync_roms/data/` in the package, each device's playable systems (`device-systems.json`) too, and your cards from the [data folder](#data-folder), never from storage.
- System folders in storage use the ES-DE system name (e.g. `gba/`, `dreamcast/`). BIOS files are always `BIOS/<file>` in storage.
- Reads each synced system's files from the storage cache and compares file sizes, so only missing or changed files are downloaded (for `full_system` systems, every file in the folder) (8 in parallel, via boto3).
- The local ROMs a sync offers to delete (`--dry-run` shows them) are the files in a synced system's folder that are no longer in the card's games, the ROMs of a system the card has no games picked for, and those of a system its device no longer lists (only when the card has something to sync: a card with no games, or none in storage, is left as it is). BIOS files and dotfiles are never touched. Files frontends add to ROM folders are ignored too (never counted as "already has files", never deleted): ES-DE `systeminfo.txt` / `noload.txt`, Knulli/Batocera `_info.txt`, `gamelist.xml` and the `images/`, `videos/`, `manuals/` folders (and, on ROCKNIX, `Install Collections.sh` and `RAOfflineProxy Install.sh` in `ports/`), Onion `miyoogamelist.xml`, `*.db` ROM list caches (on Onion cards only) and `Imgs/` (top level of a system folder only), and Windows `Thumbs.db` / `desktop.ini`.
- Some systems share a local folder on a device (Onion: `WS` = WonderSwan + Color, `NGP` = Neo Geo Pocket + Color). A folder's expected files are the union of all those systems' lists, so syncing one never offers the other's ROMs for deletion.
- Every BIOS file listed for a synced system is downloaded; there is no required/optional distinction. BIOS lists cover every emulator a system can use (default and alternate libretro cores, standalone emulators); on Knulli check Game Settings > Missing Bios Check.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `AccessDenied` / `Unable to locate credentials` | Define the `roms-readonly` profile in `~/.aws/config` and `~/.aws/credentials`; `sync-roms doctor` checks the profile, storage and tools |
| `cards.json isn't valid JSON` (or another data file) | Fix the file (the last good copy of `cards.json` is `cards.json.bak`); sync-roms never overwrites a file it can't parse. `sync-roms check` lists the problems |
| "listed but not in storage" warnings | A game on your card (or a required BIOS file) isn't in storage; it is skipped |
| `<card> has no games picked` or `<card> has nothing to sync` | Your card has no games picked, or none of them are in storage. Add games with `sync-roms edit` |

## Transfer speed (AWS CLI only)

These `s3` settings are read by the `aws s3 cp`/`sync` commands, not by `sync-roms` itself (which uses boto3 and its own worker pool). Set them if you also move files with the AWS CLI. The defaults are 10 concurrent requests and 8MB multipart chunks. `upload` and `scrape` size their own parallelism from your CPU cores and don't need them.

```bash
for p in roms-readonly roms; do
  aws configure set s3.max_concurrent_requests 32 --profile $p
  aws configure set s3.max_queue_size 2000 --profile $p
  aws configure set s3.multipart_threshold 64MB --profile $p
  aws configure set s3.multipart_chunksize 32MB --profile $p
done
```

The threshold and chunk size apply in both directions: large files move as parallel 32MB ranges on download and 32MB parts on upload. Concurrency is the setting that matters most for many small files. Lower it if your router or uplink starts timing out.

## Releasing (maintainers)

Commits and PR titles on `main` use [Conventional Commits](https://www.conventionalcommits.org) and PRs are squash-merged, so the PR title becomes the commit. release-please keeps a release PR open; merging it tags `vX.Y.Z` and attaches the sdist. To publish that version to Homebrew, in a checkout of [kelsin/homebrew-tap](https://github.com/kelsin/homebrew-tap):

```bash
brew bump-formula-pr --version X.Y.Z --url https://github.com/kelsin/sync-roms/releases/download/vX.Y.Z/sync_roms-X.Y.Z.tar.gz kelsin/tap/sync-roms
```

If the Python dependencies changed, run `brew update-python-resources kelsin/tap/sync-roms` first, then `brew test` and `brew audit --strict kelsin/tap/sync-roms`.
