"""Download ROMs and BIOS files from your ROM storage."""
import argparse
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from . import __version__, budget, cardedit, cardfs, clean, commands, downloads, drivers, edit, external, frontend, inventory, m3u, mirroring, picker, runtime, s3, scrape_plan, store
from . import muos_collections, nextui_folders, onion_surprise, pico8, raofflineproxy, rocknix_collections, saves, spruce_collections, spruce_bootlogo, spruce_emu, spruce_os, spruce_fixes, spruce_settings, spruce_wifi, surprise, themeart, ui, usersettings, vita
from . import collections as colls


SUBCOMMANDS = {  # name -> (usage, one-line summary)
    "sync": ("[CARD]", "download the ROMs, BIOS and scraped data for a card (this is what plain `sync-roms CARD` does)"),
    "edit": ("", "interactive editor: cards, sets, collections, device systems (same as `games edit`)"),
    "games": ("edit|list|add|remove|full|sets|export|import", "edit a card's games, interactively or from scripts"),
    "sets": ("edit", "edit the game sets in storage by hand and save the changes there"),
    "collections": ("edit", "edit your collections of favourite games (saved in ~/.sync-roms/collections/)"),
    "themes": ("update", "copy the latest Art Book Next for ES-DE from GitHub into storage"),
    "download": ("pico8", "add the PICO-8 BBS Featured carts storage doesn't have, and newer revisions of those it has"),
    "flash": ("", "write a Knulli, BaseOS, muOS, ROCKNIX or OakMoss image from storage's os/ to an SD card"),
    "cards": ("[edit|list|new|set|rename|convert|clean|delete|copy|export|import]", "list and manage the cards you've synced"),
    "saves": ("stash|apply [CARD] [--retroarch DIR]", "copy RetroArch saves and states off a card, or onto one"),
    "devices": ("[ID]", "list the supported devices, or one device's systems"),
    "layouts": ("[ID]", "list the firmware card layouts, or one layout's folders and devices"),
    "upload": ("[DIR]", "upload ROMs to the storage folder of a system you pick"),
    "diff": ("[DIR]", "list the ROMs in only DIR or only the bucket, ignoring renames"),
    "scrape": ("[SYSTEM | match SYSTEM ROM GAME | review [SYSTEM] | missing [SYSTEM] | art [SYSTEM]]", "scrape the ROMs that have no metadata from ScreenScraper into storage's scrapes/ folder"),
    "clean": ("scrapes", "remove scrapes/ media and metadata for ROMs that aren't in storage"),
    "playlist": ("[DIR]", "create or fix the .m3u playlist of every multi-disc game"),
    "convert": ("[DIR]", "unzip archives and convert disc images to verified .chd"),
    "tools": ("install", "brew install the 7z, unar and chdman that `convert` needs"),
    "mirror": ("[DIR] | use DIR | clear", "make or refresh a local copy of everything your lists reference"),
    "cache": ("[update [--full]]", "show the storage cache every command reads file lists and sizes from, or update it"),
    "config": ("show|path|set NAME VALUE|unset NAME|import [CARD]", "show the effective settings and where each comes from, or change one"),
    "guide": ("", "open the device setup guide (steps to finish a device by hand) in a browser"),
    "doctor": ("", "check the AWS profile, storage access, tools and your data files"),
    "check": ("", "validate cards.json, surprises.json, the device overlay, the sets and your collections"),
    "completion": ("bash|zsh|fish", "print a shell completion script"),
}

TOPICS = {
    "sync": """
  sync-roms [sync] [CARD] [--dry-run] [--ask] [--yes] [--device ID|full] [--layout NAME] [--no-delete] [--no-clean] [--no-eject]

  CARD is the card or folder root (default: the current directory); the chosen firmware decides the folders inside
  it (ES-DE ROMs/ BIOS/, Knulli roms/ bios/, Onion Roms/ BIOS/). Missing folders are created after you confirm.

  FLOW
   1. Pick a device (its recommended systems come from device-systems.json plus your overlay) or Full, then its
      firmware. Remembered per card folder name and used without asking next time; --ask confirms it first.
      --device/--layout set it without the picker (and save it).
   2. Interactively, you pick which of the card's surprises to keep, then the card editor opens, showing the
      card's size and how much isn't on it yet as you add games and collections; otherwise every surprise is
      replaced. Then, with Surprise on, the empty slots are filled.
   3. Every system with games picked on the card is synced. The totals to download are shown: ROMs, BIOS, scraped
      data and, where the card gets them, Android APKs, GPU drivers and Onion themes.
   4. Card files spelled differently from storage are renamed, and unwanted ones that match a missing file are
      moved to its place.
      Local ROMs no longer in a system's list, in a system with no games listed, or in a system the card's device no longer lists, are listed and, after you confirm (default no), deleted first so the free space shown is accurate.
      Then free space is shown and you confirm the download.
   5. ROMs download, then BIOS: BIOS for every system with ROMs on the card is installed, games picked or not.
      Then what the card's layout gets: Android APKs, GPU drivers (old ones are removed), PICO-8, the Onion
      Surprise app, RAOfflineProxy and Onion themes.
   6. Scraped data for the card's games is installed from storage's scrapes/ folder, then media on the
      card for ROMs it doesn't have is removed, in every system's folder, synced or not.
   7. Onion, Allium and Spruce system folders left with no ROMs and nothing else are removed, synced or not. The
      card's collections and their art are written, a Spruce card gets the newest spruceOS 7z, and last the card
      is ejected.

  --dry-run   show what would be downloaded and deleted, change nothing
  --yes       answer every prompt with its default (a default-no prompt, like deleting files, stays no)
  --no-delete never delete anything from the card: ROMs no longer in the lists, their media, old drivers and empty
              system folders are listed as kept and the delete prompt is skipped (for adding games to a card
              someone set up by hand)
  --no-clean  skip the end-of-run card tidy (.metadata_never_index, .fseventsd, ._ files)
  --no-eject  leave the card mounted (by default a Mac unmounts all of its volumes after a run with no failures;
              "eject": false in settings.json turns that off for every run)

  A run that wrote to the card (not --dry-run) creates .metadata_never_index in CARD, empties its .fseventsd, and on a Mac deletes
  its ._ files (and offers sudo mdutil to turn Spotlight off, which asks for your password).
""",
    "games": """
  sync-roms games edit                        interactive editor (cards, sets, collections, device systems)
  sync-roms games list --card NAME [--json]
  sync-roms games add SYSTEM KEY... --card NAME [-n]      KEY: file name, SYSTEM/file key, or a glob like 'Mario*'
  sync-roms games remove SYSTEM KEY... --card NAME [-n]
  sync-roms games full SYSTEM on|off --card NAME [-n]
  sync-roms games sets list | add ID | remove ID --card NAME [-n]
  sync-roms games export --card NAME        one SYSTEM/file per line (full systems as 'SYSTEM/*'), then '@collections ID', '@frontend_collections NAME', '@drivers NAME', '@pico8 ZIP', '@surprise true|false' (only when it differs from the layout's default: on for esde/knulli/rocknix/emudeck/muos/nextui/onion/spruce, off for allium) and '@surprises SYSTEM/file' lines
  sync-roms games import FILE --card NAME [-n]            add the games in such a file (- reads it from standard input); '@' lines replace the card's collections / frontend_collections / drivers / surprises and set pico8, and set Surprise on or off

  --card NAME is required: a card's games are saved in ~/.sync-roms/cards.json with the previous version kept as .bak. Removing only drops a game from the list.
  In the editor: / filters, Space toggles a row, a all/none shown, u reverts the list, o cycles all/on/changed,
  f toggles a full system, S opens the settings menu (Surprise, theme, collections, RAOfflineProxy); in a system's games, s lists its sets and Space there picks
  (or unpicks) a set's games. ? in any list shows all its keys.
""",
    "sets": """
  sync-roms sets edit                         edit the sets in storage (games, categories, new and deleted sets), then save them

  The sets are shared by everyone using this storage: each set is storage's sets/<id>.json. Saving writes the new and
  changed sets there and deletes the deleted ones; nothing else in storage or ~/.sync-roms changes.
  Pick a set to switch games off, add games from a system or from another set across its systems (you're asked for a
  category), change a game's category or rename it. ➕ New set creates one; d deletes the highlighted one. Esc reviews the changes before they're saved.
""",
    "collections": """
  sync-roms collections edit                  edit your collections of favourite games

  Your own lists of games (like a set, but personal), saved to ~/.sync-roms/collections/<id>.json after Done or Esc
  shows the changes; Quit discards. No git or gh needed, and nothing goes to storage or the repo. Same keys as the set
  editor. Deleting a collection that cards use asks first, then removes it from them (the file is kept as
  <id>.json.bak). In a card's system list, l adds a collection to that card. Theme art picks the picture (Action, RPG, ...) the collection gets on ES-DE, Knulli and ROCKNIX cards
  that use Art Book Next.
""",
    "themes": """
  sync-roms themes update [--dry-run]         put the latest Art Book Next for ES-DE in storage

  Downloads the GitHub archive of the theme's latest commit (about 200 MB) and replaces os/esde/themes/ in storage
  (write profile). Syncs copy it from there onto ES-DE cards that use Art Book Next, so the Surprise collection has its
  art; a card's copy is replaced when storage has a newer commit. Does nothing when storage already has the latest.
""",
    "download": """
  sync-roms download pico8 [--count N] [--dry-run] [--yes]   add the BBS Featured carts to storage's pico8/

  Reads every page of the Lexaloffle BBS Featured PICO-8 listing (--count N: stops after N carts to add or upgrade),
  lists the carts storage doesn't have and those the BBS has a newer revision of, and asks once (write profile).
  Each cart goes to pico8/<BBS file name> with its title and author in scrapes/pico8/metadata.json. An upgrade
  removes the old revision, moves its metadata and scraped media to the new name and points your cards, Surprise
  history and collections at it; sets that name the old file are listed to change with sets edit. Carts in
  ignored.json are skipped. Requests go one at a time; the first HTTP error stops it, keeping what was added.
""",
    "flash": """
  sync-roms flash [--dry-run]                 write a Knulli, BaseOS, muOS, ROCKNIX or OakMoss image to an SD card (macOS only)

  Pick a firmware (only when storage's os/ has images of more than one: Knulli or BaseOS, muOS, ROCKNIX, OakMoss), then a
  device, then an image from storage's os/knulli/knulli-*.img.gz or os/baseos/baseos-*.img.zip (the ones matching the
  device first, newest first), os/muos/muos-*.img.gz (muOS image names aren't documented, so they are never matched)
  or os/rocknix/ROCKNIX-*.img.gz (not the update .tar files; matched by the device's SoC image, H700 devices matching
  both DDR3 and DDR4: pick the one for your device's RAM)
  or os/oakmoss/oakmoss-*.img.xz (not the .omupd files; matched by the device name in the file), then an
  external SD card (shown with its volume names); the boot disk and the disks holding the temp folder
  or storage are never offered, and flash stops if it can't tell which disks those are. Type the disk id (disk4) to
  confirm: --yes never skips that. --dry-run stops there. The image is copied to a local temp folder (free space is
  checked first); right before writing, the card must still be the same disk (id, size and name). Then `sudo dd`
  writes it, decompressed (gz, xz or zip) on the fly, with 4 MiB blocks (sudo may ask for your password before downloading and
  writing). Last, the temp folder is removed and the card is ejected; after a failure it is unmounted instead, so you can retry.
""",
    "edit": """
  sync-roms edit                              main menu: Cards, Sets (saved to storage), Collections, Device systems; same as `games edit`

  ? in any list shows all its keys. In a card's system list: Enter opens a system's games, f makes it a full system,
  l picks collections, S opens the settings menu (Surprise, theme, collections, RAOfflineProxy), D clears the card. After / in any list, Enter keeps the filter and
  goes back to moving; Esc clears it.
  Ctrl-C while an editor is busy between two lists ("Working...") stops it when that step ends, as Ctrl-C in a list
  does; another Ctrl-C a second or more later, with the step still running, quits at once, and unsaved changes in
  the open editor are lost.
""",
    "cards": """
  sync-roms cards edit                        same as `games edit`
  sync-roms cards [list] [--json]             list is the default
  sync-roms cards new NAME --device ID|full --layout NAME [--size 512GB]
  sync-roms cards set NAME [--device ID|full] [--layout NAME] [--size 512GB]
  sync-roms cards rename OLD NEW
  sync-roms cards convert [CARD] --layout NAME [--dry-run] [--yes]   move the card's ROMs, BIOS and saves to another layout's folders
  sync-roms cards clean [CARD] [--dry-run] [--yes]   delete the media other layouts' scrapes left in the card's ROM folders
  sync-roms cards delete NAME [--yes]
  sync-roms cards copy SRC DST                merge SRC's games, sets, excluded and collections into DST (not surprises); skips systems DST can't play
  sync-roms cards export FILE [--yes]         surprises and collections go into the file as plain games; asks before overwriting FILE (--yes overwrites)
  sync-roms cards import FILE                 keeps size, device, layout, games and excluded; Surprise off; r renames, p prefixes all

  A card is a folder name (the card root's basename) with a remembered device, firmware and games.
  new, set, rename, delete, copy, export and import take --dry-run (-n): they say what they would do and save nothing.
""",
    "saves": """
  sync-roms saves stash [CARD] [--retroarch DIR] [--dry-run]    copy picked saves and states off the card
  sync-roms saves apply [CARD] [--retroarch DIR] [--dry-run]    copy picked stashed ones onto the card

  CARD is the card's folder (default: the current directory); it needs a layout (`sync-roms cards set NAME --layout`).
  stash lists the card's games that have RetroArch saves (.srm and .rtc) or states (.state, .stateN, .state.auto and their
  .png), then their files, and copies them to ~/.sync-roms/saves/<system>/<game>/<time>-<card>/ (with stash.json).
  On layouts sorted by core and flat folders a save whose game isn't on the card is skipped; on Knulli and ROCKNIX the folder
  gives the system (on ROCKNIX, where saves sit beside the ROMs, a save or state whose game isn't in the system's ROM
  folder is skipped too).
  apply lists the stashes of systems the card syncs (one per game) and copies them into the card's RetroArch folders.
  A different file already there is only overwritten after you confirm (default no); identical ones are skipped.
  A stash without a core going to a layout sorted by core asks which core folder to use (skipped with --yes).

  Layout    RetroArch folder             saves            states
  esde      RetroArch                    saves/<core>     states/<core>
  knulli    saves                        <system folder>  <system folder>
  rocknix   roms (beside the ROMs)       <system folder>  savestates/<system folder>
  onion     Saves/CurrentProfile         saves/<core>     states/<core>
  allium    Saves/CurrentProfile         saves/<core>     states/<core>
  spruce    Saves                        saves/<core>     states/<core>
  muos      MUOS/pickles                 sram/<core>      state/<core>                    (Pickles, not RetroArch)
  emudeck   Emulation/saves/retroarch    saves            states
  nextui    (card root)                  Saves/<TAG>      .userdata/shared/<TAG>-<core>   (MinUI .sav naming)

  --retroarch DIR   read or write that folder instead of the card's RetroArch folder: a copy of Android's internal
                    /storage/emulated/0/RetroArch for ES-DE, or the real folder EmuDeck's symlinks point to.
  nextui: apply renames saves to MinUI's Game.gba.sav (from the card's ROM; PlayStation and saves with no ROM there keep
  their name), stash turns .sav back into .srm. States are stashed and applied as they are, so NextUI's own state
  names aren't converted.
  muos: the saves and states are Pickles' own, copied as they are; --retroarch is ignored (with a warning), and a
  Pickles stash is only applied to a muOS card, which takes no other stash.
  States only load in the core they were made with; .srm (and .rtc) saves usually work in any core of the system.
""",
    "devices": """
  sync-roms devices [ID] [--json]

  Without an ID: every device with its chip and system count. With one: its firmwares, note and systems.
""",
    "layouts": """
  sync-roms layouts [ID] [--json]

  Without an ID: every firmware layout with its ROMs and BIOS folders and how many devices run it.
  With one: its folders, note and the devices that run it (marked where it's their default firmware).
""",
    "upload": """
  sync-roms upload [DIR] [--replace] [--dry-run]    upload the ROMs in DIR (default: current directory) to storage folder of a system you pick

  The system is guessed from the folder name; same-size files are skipped, a different size overwrites after you confirm.
  --replace makes the storage folder match DIR: renamed files are moved by content (big bucket files without an MD5 are
  compared on samples, and those renames are marked), and left-over storage files are listed so you tick which to delete (none are ticked at first).
  Uploads use the write profile (ROMS_WRITE_PROFILE, default 'roms').
""",
    "diff": """
  sync-roms diff [DIR] [--system ID] [--json]

  Lists the ROMs in only one of DIR and storage folder of a system you pick. Same path and size is the same file;
  the rest are matched by content (the CRCs inside zips, the bytes of other files, as upload --replace does).
  It only reads, so --dry-run is refused.
  --system ID   compare with that storage folder instead of picking one
  --json        print the result as one JSON document (needs --system unless DIR is named after a system)
""",
    "scrape": """
  sync-roms scrape [SYSTEM | --system ID] [--all] [--retry] [--fill-media] [--skip-media TYPES] [--dry-run]
  sync-roms scrape match SYSTEM ROM GAME_ID_OR_NAME [--skip-media TYPES] [--translated] [--dry-run]
  sync-roms scrape review [SYSTEM]
  sync-roms scrape missing [SYSTEM | --system ID] [--all]
  sync-roms scrape art [SYSTEM | --system ID] [--for onion|spruce|both] [--dry-run] [--replace] [--workers N]
  sync-roms scrape --set-credentials

  Looks up every available ROM with no entry in scrapes/<system>/metadata.json on ScreenScraper and writes its
  metadata and media (and the Onion images) to storage; pico8 carts with an entry but no scraped picture are taken
  too (their BBS title and author are kept). The ROMs and how each will be
  looked up are listed first, then the most requests the run can make against what is left of today's quota. ROMs
  ScreenScraper doesn't know are remembered and skipped until --retry. Each batch of ROMs shows today's requests and
  the time elapsed and left; each ROM gets a line as it ends (the game it matched, how, and its media count).
  SYSTEM             only that storage folder (e.g. gba); --system ID is the same
  --retry            also look up the ROMs ScreenScraper didn't know before (ROMs whose lookup failed are always
                     tried again; non-games never are: see review) and, with --fill-media, the media it didn't offer
  --all              every ROM in the storage, not just those your cards list (games, sets, full systems)
  --fill-media       also scrape ROMs that have metadata but lack some media type in storage; their existing metadata
                     is kept. Types ScreenScraper didn't offer for a ROM are remembered and not asked for again
                     until --retry
  --skip-media TYPES comma-separated media folders not to download (covers, 3dboxes, backcovers, fanart, manuals,
                     marquees, ...); other values are refused with the list
  --dry-run          list the ROMs and the metadata and media folders that would be written; no ScreenScraper
                     credentials or requests (scrape match --dry-run needs credentials and searches when given
                     a name; a game id is not checked)
  match              say which ScreenScraper game a ROM is (a game id, or a name to search and pick from), then scrape it;
                     for a ROM that already has metadata it asks before replacing the entry and deleting its old media.
                     --translated: the ROM is a fan translation: title '<name> - Translated'; an ignored ROM is taken
                     off ignored.json first
  review             go through the ROMs ScreenScraper calls non-games or doesn't know, each with its position (3 of
                     120): i ignore, s search under another name and scrape the game picked, t search like s and
                     scrape the pick as a fan translation, k keep for later (listed after the others next time),
                     b take back the last ignore, q quit, I ignore all the rest
  missing            list every ROM with no metadata and why (non-game, not on ScreenScraper, matched but not scraped,
                     not looked up yet); nothing is looked up. --all: every ROM in the storage
  art                make the Onion (PNG) and Spruce (QOI, up to three sizes) box art for the ROMs that have a cover or
                     miximage in storage (a PICO-8 cart is its own picture), from the cover, else the miximage; files that
                     exist are kept. --for picks Onion, Spruce or both (default). --dry-run lists what would be made with
                     an estimated size and reads no image; --replace remakes existing files; --workers N bounds the
                     parallel downloads (default: your CPU count). Spruce art needs Pillow
  --set-credentials  ask for your ScreenScraper username and password (saved in settings.json,
                     readable only by you; blank keeps the current value), then check them with one request
                     and show today's quota and threads, or the error (exit 1 when ScreenScraper refuses them)
  A rate-limited request, a server error (HTTP 5xx) or a network failure is tried 3 more times, waiting 10, 20 and 40 seconds.
  The run stops cleanly, keeping what it finished, when ScreenScraper's daily quota runs out (run it again tomorrow),
  when ScreenScraper refuses the login, is closed or no longer accepts this version (the message says what to do), or
  when 3 ROMs in a row can't reach it. Ctrl-C stops it too: the ROMs that finished are uploaded and saved, it says how
  many were saved and how many are left, and it exits 130 (a second Ctrl-C aborts at once). Writes use the write profile.
""",
    "clean": """
  sync-roms clean scrapes [--dry-run]

  Removes scrapes/ media and metadata for ROMs that aren't in storage at all (asks first; --yes deletes without asking).
""",
    "playlist": """
  sync-roms playlist [DIR] [--dry-run]

  Creates or fixes the .m3u of every multi-disc game ("Name (Disc 1).chd", "Name (Disc 2).chd") in DIR and its
  subfolders. Playlists whose files are all missing are deleted (asks first). Local only. (Old name: --m3u)
""",
    "convert": """
  sync-roms convert [DIR] [--dry-run]

  Unzips (7z, or unar for .rar) every .zip/.7z/.rar, and the archives inside them, and converts each disc image (.cue, .gdi, .toc, .iso) to a verified .chd (Xbox .iso to xiso, Xbox 360 .iso to .zar),
  per the `chd` key in systems.json of the system whose folder it is in. Archives and images are removed once their chd verifies,
  then the .m3u playlists are fixed. Archives that convert unpack in the system temp folder when it is on another drive with room, else beside
  themselves; as many files convert at once as there are CPU cores and free space for, biggest first. The progress bar goes by size, with the rate and time left,
  and each file's result shows as it finishes. Inside a saved card's folder it warns that the next sync downloads the archives again and asks first (default no,
  so --yes or no terminal stops it). Inside the storage folder, once a file converts, it ends by saying to run `sync-roms cache update`.
  Needs 7z, chdman and, for Xbox, extract-xiso and, for Xbox 360, iso2zar (see `tools install`). (Old names: --cd, --chd)
""",
    "tools": """
  sync-roms tools install

  brew install the 7z (sevenzip), unar and chdman (rom-tools) that `convert` needs, and say how to build extract-xiso and iso2zar.
""",
    "mirror": """
  sync-roms mirror [DIR] [--dry-run]     make or refresh a local copy of everything the lists reference (no DIR: the saved mirror)
  sync-roms mirror use DIR               refresh DIR, then save it so every sync refreshes it first and copies from it
  sync-roms mirror clear                 forget the saved mirror (its files stay)

  Files no longer referenced are deleted (after confirming when it is a lot).
""",
    "config": """
  sync-roms config show                 the effective bucket, endpoint, profiles and mirror, and where each came from
  sync-roms config path                 the data folder
  sync-roms config set NAME VALUE       save one setting in settings.json
  sync-roms config unset NAME           remove it (back to its default)
  sync-roms config import [CARD]        save a card's own settings (spruceOS preferences) in settings.json

  NAME is bucket, root, endpoint, profile, write_profile, mirror, screenscraper_user or screenscraper_password (text),
  eject or storage_cache_declined (true or false), surprise_ttl_days (a positive number of days) or
  surprise_excluded_systems (comma-separated system ids, e.g. gba,snes). root and mirror must be absolute
  paths (~ is expanded). The password is saved but never printed;
  `scrape --set-credentials` asks for it without echoing it.

  spruce_ra_mode (Manual, Disabled, Casual, Softcore or Hardcore), spruce_ra_username, spruce_ra_password and
  spruce_ra_api_key (text, the last two never printed), spruce_ra_offline_proxy and spruce_ra_proxy_stats (true or
  false): the RetroAchievements settings every sync writes into a spruce card's Saves/spruce/spruce-config.json.
  Set them with `config set`; `config import` doesn't read them from the card.

  config import takes CARD (a card name from cards.json, found at /Volumes/<name>, or the card's folder; default the current
  folder) and picks what to import from the card's saved layout (only spruce so far). For a spruce card it copies the current values of the spruceOS settings that are your preferences (emulator, in-game menu,
  button, boot and network options; not hardware, LED, battery, audio or proxy ones) from Saves/spruce/spruce-config.json
  into settings.json's spruce_settings, merged with what is there. It lists the settings identical to the saved ones and
  those that differ or are new, then asks Yes (all of them), No or Pick (one by one); no answer is assumed, and with no
  terminal input nothing is saved. Every sync of a spruce card then sets those that the card's file already has. spruce_settings isn't a `config set` name: import it, or edit settings.json by hand
  ({"section": {"key": value}}, values as the card holds them).
""",
    "cache": """
  sync-roms cache [update [--full]]

  Every command reads what storage holds (file names, sizes and, for a bucket, ETags) from a cache in
  ~/.sync-roms/cache/storage-cache.json; only the files themselves are downloaded from storage. Nothing refreshes it on its
  own: sync-roms's own uploads, moves and deletes keep it up to date, and after changing storage any other way run
  `sync-roms cache update`.

  cache          where the cache was read from, when it was last updated, and its files and size per folder
  cache update   read storage again: one listing of a bucket, or a walk of a folder that lists only subfolders
                 whose modification time changed and stats only files the cache doesn't have; the rest keep their
                 cached files and sizes. This relies on storage changing a folder's modification time when a file is
                 added, removed or renamed in it; a change made in the last few minutes is picked up on the
                 following update
  --full         in a folder, list every subfolder and stat every file: covers files replaced under the same name
                 and anything a folder's modification time didn't show (a bucket listing is the same either way)

  With no cache for the storage in use, the first command that reads storage offers to build it. Saying no is
  remembered (storage_cache_declined in settings.json), and commands then list storage each run.
""",
    "doctor": """
  sync-roms doctor

  Checks the AWS profile and storage access, the tools `convert` needs, and that your data files parse.
""",
    "guide": """
  sync-roms guide

  Opens the device setup guide in your browser: the apps to install and the frontend, RetroArch and emulator
  settings to change after a card is synced. Pick a device and layout at the top of the page.
""",
    "check": """
  sync-roms check [--bucket-keys]

  Validates cards.json, surprises.json, device-systems.json, the sets in storage and your collections: bad JSON,
  unknown systems, devices, sets and art. Exits 1 if anything is wrong. Sets with no art of their own, or sharing
  art, are noted without failing.
  --bucket-keys also reports every game or set file storage doesn't have (read-only profile). It goes by the storage
                cache: run `sync-roms cache update` first, since a stale cache reports files that are there.
""",
    "completion": """
  sync-roms completion bash|zsh|fish
  sync-roms completion list cards|systems|devices|layouts

  Prints a completion script, e.g.  sync-roms completion zsh > ~/.zfunc/_sync-roms
  list prints those names one per line (the scripts call it; handy for --card, --system, --device and --layout).
""",
}


def help_text(topic=None):
    if topic in TOPICS:
        return f"\n{ui.bold('🎮 sync-roms ' + topic)} — {SUBCOMMANDS[topic][1]}\n{TOPICS[topic]}"
    rows = "\n".join(f"  {ui.green(name):<{20 + len(ui.green(''))}} {ui.cyan(usage) if usage else ''}\n      {summary}"
                     for name, (usage, summary) in SUBCOMMANDS.items())
    return f"""
{ui.bold('🎮 sync-roms')} — download ROMs and BIOS files from your ROM storage (an S3 bucket or a folder)

{ui.bold('USAGE')}
  {ui.green('sync-roms')} [{ui.cyan('CARD')}]                 sync a card (same as `sync-roms sync CARD`)
  {ui.green('sync-roms')} {ui.cyan('COMMAND')} [options]      one of the commands below; `sync-roms COMMAND --help` explains it
  {ui.green('sync-roms')} help [{ui.cyan('COMMAND')}]         the same as --help

{ui.bold('COMMANDS')}
{rows}

{ui.bold('GLOBAL OPTIONS')}
  {ui.yellow('-n, --dry-run')}   show what would happen, change nothing (commands that can't honor it refuse it)
  {ui.yellow('-y, --yes')}       answer prompts with their default (deleting stays "no"). In these commands --yes is the
                  confirmation, so they delete: `clean scrapes`, `cards clean`, `cards convert` (the old layout's
                  media), `cards delete` and `download pico8` (old cart revisions)
  {ui.yellow('--quiet')}         print only errors, warnings and --json data (prompts go to stderr)
  {ui.yellow('--verbose')}       also print the effective settings
  {ui.yellow('--json')}          machine-readable output for devices, layouts, diff, games list, cards list and `sync --dry-run` (use --device/--layout to skip the pickers)
  {ui.yellow('--profile P')} {ui.yellow('--write-profile P')} {ui.yellow('--bucket B')} {ui.yellow('--root DIR')} {ui.yellow('--endpoint URL')}   override those settings for this run
  {ui.yellow('-a, --ask')}       sync: confirm the saved device/firmware instead of using it silently
  {ui.yellow('--version')}       print the version      {ui.yellow('-h, --help')}   this screen

{ui.bold('ENVIRONMENT')}
  {ui.yellow('ROMS_BUCKET')}  {ui.yellow('ROMS_ROOT')}  {ui.yellow('ROMS_ENDPOINT')}  {ui.yellow('ROMS_PROFILE')} (default roms-readonly)  {ui.yellow('ROMS_WRITE_PROFILE')} (default roms)
  override settings.json "bucket", "root" (a folder, e.g. a mounted network share, used instead of storage), "endpoint", "profile", "write_profile"; the flags above override these. {ui.yellow('NO_COLOR')} / {ui.yellow('FORCE_COLOR')} control colors.

{ui.bold('EXIT CODES')}
  0 done (or nothing to do, or you declined)   1 some files failed   2 bad usage   3 setup problem (credentials, bucket, tools, bad data file)   130 interrupted

{ui.bold('EXAMPLES')}
  sync-roms /Volumes/SD                          sync the card
  sync-roms sync /Volumes/SD --device anbernic-rg35xx-sp --layout knulli --yes --dry-run
  sync-roms games add gba 'Metroid*' --card SD   add games to a card
  sync-roms upload ~/roms/gba                    upload ROMs to storage

  {ui.dim('The old flags (--edit/-e, --upload, --clean-scrapes/-c, --diff, --scrape, --scrape-match, --scrape-review,')}
  {ui.dim('--scrape-missing, --m3u, --cd, --install-tools, --mirror, --use-mirror, --clear-mirror, --devices) still work.')}
  {ui.dim('A card folder named like a command: write ./edit.')}
"""


def check_dir(path, label):
    """Fail early if `path` can't be used or created. Returns True if it must be created."""
    if os.path.exists(path):
        if not os.path.isdir(path):
            ui.fail(f"{label} {path} exists but is not a directory", 3)
        if not os.access(path, os.W_OK | os.X_OK):
            ui.fail(f"No write permission for {label} {path}", 3)
        return False
    parent = os.path.dirname(path)
    while not os.path.exists(parent):
        parent = os.path.dirname(parent)
    if not os.path.isdir(parent) or not os.access(parent, os.W_OK | os.X_OK):
        ui.fail(f"Can't create {label} {path}: no write permission in {parent}", 3)
    return True


def prepare_dirs(base, layout, dry_run, ask=True):
    """Show, validate and (after confirmation, unless ask is False) create the layout's ROM and BIOS folders under base,
    and its RetroArch saves and states folders when the layout's retroarch says create.

    Returns (roms, bios), or None if declined.
    """
    roms = os.path.join(base, layout["roms_dir"])
    bios = os.path.join(base, layout["bios_dir"])
    folders = [("💿", "ROMs", roms), ("🧠", "BIOS", bios)]
    ra = layout.get("retroarch") or {}
    if ra.get("create"):  # the folders above {core}, for RetroArch's Save Files / Save States directories
        folders += [("💾", name.capitalize(), os.path.join(base, *ra["dir"].split("/"), *ra[name].split("/{core}")[0].split("/")))
                    for name in ("saves", "states")]
    # check everything before asking anything
    missing = {path for _, name, path in folders if check_dir(path, f"{name} folder")}
    print(ui.bold(f"📁 {layout['label']} layout in {base}:"))
    for icon, name, path in folders:
        print(f"  {icon} {name} → {ui.cyan(path)}" + (ui.dim("  (will be created)") if path in missing else ""))
    if ask and not dry_run and not ui.confirm("Continue with these folders?"):
        return None
    for path in sorted(missing):
        if dry_run:
            print(ui.yellow(f"🧪 Would create {path}"))
        else:
            os.makedirs(path)
    return roms, bios


def main():
    os.environ["COPYFILE_DISABLE"] = "1"  # macOS: no ._ AppleDouble files on non-HFS volumes, also for child tools
    if not sys.stdout.isatty():  # logs and pipes get plain text
        sys.stdout = ui.PlainOut(sys.stdout)
    try:
        return sync(reset=False)
    except KeyboardInterrupt:
        print(ui.yellow("\n🛑 Interrupted"), file=sys.stderr)
        return 130
    except NoCredentialsError:
        ui.fail(f"No AWS credentials for profile '{runtime.PROFILE}'. Run: aws configure --profile {runtime.PROFILE}", 3)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        hint = {
            "ExpiredToken": f"the session expired: aws sso login --profile {runtime.PROFILE}",
            "InvalidAccessKeyId": f"the access key is wrong: aws configure --profile {runtime.PROFILE}",
            "SignatureDoesNotMatch": f"the secret key is wrong: aws configure --profile {runtime.PROFILE}",
            "NoSuchBucket": f"bucket '{runtime.BUCKET}' doesn't exist: check --bucket, ROMS_BUCKET or {os.path.join(store.data_dir(), 'settings.json')}",
            "AccessDenied": f"profile '{runtime.PROFILE}' can't read bucket '{runtime.BUCKET}'",
            "403": f"profile '{runtime.PROFILE}' can't read bucket '{runtime.BUCKET}'",
        }.get(code, "")
        ui.fail(f"S3 said {code or 'an error'}: {e.response.get('Error', {}).get('Message', e)}" + (f"\n   → {hint}" if hint else ""), 3)
    except BotoCoreError as e:
        ui.fail(f"Couldn't reach S3: {e}\n   → check your network, ROMS_ENDPOINT, and `aws sts get-caller-identity --profile {runtime.PROFILE}`", 3)
    except OSError as e:  # e.g. the storage share dropped mid-run
        ui.fail(str(e), 1)
    finally:
        inventory.flush()
        clean.clean_dirs()
        clean.eject()
        ui.reset()  # after the card finalize, so --quiet hides it too


def list_devices(args=None):
    """Print a table of the devices (name, chip, number of recommended systems), or one device's details given its id."""
    catalog = store.load_catalog()
    return commands.show_devices(catalog["devices"], catalog["systems"], getattr(args, "device_id", None), getattr(args, "json", False))


class Parser(argparse.ArgumentParser):
    literal = frozenset()  # the values after --scrape-match that start with a dash: values, never options

    def error(self, message):
        if TYPED:  # name the command the user typed, not the legacy flag translate() made of it
            words, flag = TYPED
            message = message if flag is None else re.sub(rf"argument {re.escape(flag)}(/\S+)?:", f"`{words}`:", message)
            ui.fail(f"{message}\n   Try 'sync-roms {words.split()[0]} --help'.", 2)
        ui.fail(f"{message}\n   Try 'sync-roms --help'.", 2)

    def parse_known_args(self, args=None, namespace=None):
        args = list(sys.argv[1:] if args is None else args)
        if "--scrape-match" in args:
            i = args.index("--scrape-match")
            self.literal = frozenset(a for a in args[i + 1:i + 4] if a.startswith("-"))
        return super().parse_known_args(args, namespace)

    def _parse_optional(self, arg_string):
        return None if arg_string in self.literal else super()._parse_optional(arg_string)


# subcommand -> the legacy flags it stands for. {rest} are its remaining arguments.
LEGACY = {
    ("sync",): [], ("devices",): ["--devices"], ("diff",): ["--diff"], ("playlist",): ["--m3u"], ("convert",): ["--cd"],
    ("tools", "install"): ["--install-tools"], ("clean", "scrapes"): ["--clean-scrapes"],
    ("scrape", "match"): ["--scrape-match"], ("scrape", "review"): ["--scrape-review"],
    ("scrape", "missing"): ["--scrape-missing"], ("scrape", "art"): ["--scrape-art"], ("scrape",): ["--scrape"],
    ("upload",): ["--upload"],
    ("mirror", "use"): ["--use-mirror"], ("mirror", "clear"): ["--clear-mirror"], ("mirror",): ["--mirror"],
    ("games", "edit"): ["--edit"], ("cards", "edit"): ["--edit"], ("edit",): ["--edit"],
}
WORDS = {flags[0]: " ".join(words) for words, flags in LEGACY.items() if flags}  # mode flag -> its command, for messages
TYPED = None  # (command words, mode flag) of the command translate() last rewrote, for Parser.error
BOOL_FLAGS = {"-n", "--dry-run", "-y", "--yes", "-a", "--ask"}
PLAIN_FLAGS = BOOL_FLAGS | {"--replace", "--json", "--no-clean", "--no-delete", "--no-eject", "--retry", "--all", "--fill-media", "--set-credentials",
                            "--translated"}
VALUE_FLAGS = {"--system", "--device", "--layout", "--device-id", "--skip-media", "--for", "--workers"}


def translate(argv):
    """Rewrite `sync-roms COMMAND ...` into the flag form the rest of the code reads. Global flags may come first."""
    global TYPED
    TYPED = None
    i = 0
    while i < len(argv) and argv[i] in BOOL_FLAGS | {"--json"}:
        i += 1
    if i >= len(argv) or argv[i] not in SUBCOMMANDS:
        return argv
    head, rest = argv[:i], argv[i + 1:]
    name = argv[i]
    for words in sorted(LEGACY, key=len, reverse=True):
        if words[0] == name and tuple(rest[:len(words) - 1]) == words[1:]:
            tail = rest[len(words) - 1:]
            flags = LEGACY[words]
            TYPED = (" ".join(words), flags[0] if flags else None)
            if not flags:
                return head + tail
            if words == ("scrape", "match"):  # three values that must stay together, behind the flag
                n = 0  # flags may come first; from the first value on, the next three words are the values
                while n < len(tail) and tail[n].startswith("-"):
                    n += 2 if tail[n] in VALUE_FLAGS else 1
                return head + flags + tail[n:n + 3] + tail[:n] + tail[n + 3:]
            n = 0  # flags (and the values of value flags) before the mode's value (`diff -n /x`) move behind it
            while n < len(tail) and (tail[n] in PLAIN_FLAGS or tail[n] in VALUE_FLAGS):
                n += 1 if tail[n] in PLAIN_FLAGS else 2
            if n < len(tail) and not tail[n].startswith("-"):
                value = ["--device-id", tail[n]] if name == "devices" else [tail[n]]
                return head + flags + value + tail[:n] + tail[n + 1:]
            return head + flags + tail
    if name == "clean" or name == "tools":
        ui.fail(f"'{name}' needs a subcommand: " + ", ".join(
            f"{w[0]} {w[1]}" for w in LEGACY if w[0] == name and len(w) > 1), 2)
    return argv


def build_parser():
    ap = Parser(add_help=False, allow_abbrev=False)
    ap.add_argument("base_dir", nargs="?")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("-y", "--yes", action="store_true")
    ap.add_argument("-e", "--edit", action="store_true")
    ap.add_argument("-a", "--ask", action="store_true")
    ap.add_argument("-c", "--clean-scrapes", action="store_true")
    ap.add_argument("--upload", nargs="?", const="")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--scrape", action="store_true")
    ap.add_argument("--scrape-match", nargs=3, metavar=("SYSTEM", "ROM", "GAME"))
    ap.add_argument("--scrape-review", nargs="?", const="", metavar="SYSTEM")
    ap.add_argument("--scrape-missing", nargs="?", const="", metavar="SYSTEM")
    ap.add_argument("--scrape-art", nargs="?", const="", metavar="SYSTEM")
    ap.add_argument("--for", dest="target")
    ap.add_argument("--workers", type=commands._positive_int)
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fill-media", action="store_true")
    ap.add_argument("--skip-media")
    ap.add_argument("--translated", action="store_true")
    ap.add_argument("--set-credentials", action="store_true")
    ap.add_argument("--diff", nargs="?", const="")
    ap.add_argument("--m3u", nargs="?", const="")
    ap.add_argument("--cd", "--chd", dest="chd", nargs="?", const="")
    ap.add_argument("--install-tools", action="store_true")
    ap.add_argument("--mirror", nargs="?", const="")
    ap.add_argument("--use-mirror")
    ap.add_argument("--clear-mirror", action="store_true")
    ap.add_argument("--devices", action="store_true")
    ap.add_argument("--device-id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--system")
    ap.add_argument("--device")
    ap.add_argument("--layout")
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--no-delete", action="store_true")
    ap.add_argument("--no-eject", action="store_true")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    return ap


def check_modes(args):
    """Refuse flag combinations that would silently do nothing. Returns the active mode's name (None for a plain sync)."""
    modes = [name for name, on in (
        ("--edit", args.edit), ("--upload", args.upload is not None), ("--diff", args.diff is not None),
        ("--clean-scrapes", args.clean_scrapes),
        ("--scrape", args.scrape), ("--scrape-match", args.scrape_match is not None),
        ("--scrape-review", args.scrape_review is not None), ("--scrape-missing", args.scrape_missing is not None),
        ("--scrape-art", args.scrape_art is not None),
        ("--mirror", args.mirror is not None), ("--use-mirror", bool(args.use_mirror)), ("--clear-mirror", args.clear_mirror),
        ("--m3u", args.m3u is not None), ("--cd", args.chd is not None), ("--install-tools", args.install_tools),
        ("--devices", args.devices)) if on]
    if len(modes) > 1:
        ui.fail(f"{' and '.join(modes[:2])} can't be combined: use one command at a time", 2)
    mode = modes[0] if modes else None
    name = WORDS.get(mode)
    if args.replace and mode not in ("--upload", "--scrape-art"):
        ui.fail("--replace only works with `upload` and `scrape art`", 2)
    if args.dry_run and mode in ("--edit", "--install-tools", "--clear-mirror", "--devices", "--scrape-missing", "--scrape-review", "--diff"):
        ui.fail(f"--dry-run has no effect on `{name}`", 2)
    if args.ask and mode:
        ui.fail(f"--ask only applies to syncing a card, not `{name}`", 2)
    if (args.device or args.layout or args.no_clean or args.no_delete or args.no_eject) and mode:
        ui.fail(f"--device, --layout, --no-clean, --no-delete and --no-eject only apply to syncing a card, not `{name}`", 2)
    if args.base_dir and mode == "--clean-scrapes":
        ui.fail(f"`clean scrapes` doesn't take a folder ({args.base_dir!r})", 2)
    if mode == "--scrape" and args.base_dir:  # `scrape gba`, like `scrape missing gba`
        if args.system:
            ui.fail("`scrape` takes one system: `scrape SYSTEM` or `scrape --system SYSTEM`", 2)
        args.system, args.base_dir = args.base_dir, None
    if mode == "--scrape-missing" and args.system:
        if args.scrape_missing:
            ui.fail("`scrape missing` takes one system: `scrape missing SYSTEM` or `scrape missing --system SYSTEM`", 2)
        args.scrape_missing, args.system = args.system, None
    if mode == "--scrape-art" and args.system:
        if args.scrape_art:
            ui.fail("`scrape art` takes one system: `scrape art SYSTEM` or `scrape art --system SYSTEM`", 2)
        args.scrape_art, args.system = args.system, None
    given = {"--scrape": args.system, "--scrape-missing": args.scrape_missing, "--scrape-art": args.scrape_art, "--scrape-review": args.scrape_review,
             "--scrape-match": (args.scrape_match or [None])[0]}.get(mode)
    if given and any(sep and sep in given for sep in (os.sep, os.altsep)):
        ui.fail(f"`{name}` expects a system id, not a path ({given!r})", 2)
    if args.base_dir and mode is not None:
        ui.fail(f"`{name}` doesn't take a card folder ({args.base_dir!r}); give the directory right after the command", 2)
    if args.device_id and mode != "--devices":
        ui.fail("a device id only applies to `devices`", 2)
    if args.json and not (mode in ("--devices", "--diff") or (mode is None and args.dry_run)):
        ui.fail("--json only applies to `devices`, `layouts`, `diff`, `games list`, `cards list` and `sync --dry-run`", 2)
    if args.system and mode not in ("--diff", "--scrape"):
        ui.fail("--system only applies to `diff`, `scrape`, `scrape missing` and `scrape art`", 2)
    if args.retry and mode != "--scrape":
        ui.fail("--retry only applies to `scrape`", 2)
    if args.all and mode not in ("--scrape", "--scrape-missing"):
        ui.fail("--all only applies to `scrape` and `scrape missing`", 2)
    if args.fill_media and mode != "--scrape":
        ui.fail("--fill-media only applies to `scrape`", 2)
    if args.set_credentials and (mode != "--scrape" or args.system or args.retry or args.all or args.fill_media or args.skip_media or args.dry_run):
        ui.fail("--set-credentials only goes with `scrape`, on its own", 2)
    if args.target is not None and mode != "--scrape-art":
        ui.fail("--for only applies to `scrape art`", 2)
    if args.workers is not None and mode != "--scrape-art":
        ui.fail("--workers only applies to `scrape art`", 2)
    if mode == "--scrape-art":
        args.target = args.target or "both"
        if args.target not in ("onion", "spruce", "both"):
            ui.fail(f"--for takes onion, spruce or both, not {args.target!r}", 2)
    if args.translated and mode != "--scrape-match":
        ui.fail("--translated only applies to `scrape match`", 2)
    if args.skip_media is not None:
        if mode not in ("--scrape", "--scrape-match"):
            ui.fail("--skip-media only applies to `scrape` and `scrape match`", 2)
        args.skip_media = [t.strip() for t in args.skip_media.split(",") if t.strip()]
        from . import scrape_online
        scrape_online._check_skip(args.skip_media)
    return mode


GLOBAL_VALUE_FLAGS = {"--profile": "profile", "--write-profile": "write_profile", "--bucket": "bucket", "--root": "root", "--endpoint": "endpoint"}
DATA_COMMANDS = {("devices",), ("layouts",), ("completion",), ("games", "list"), ("games", "export"), ("cards", "list"), ("config", "path")}


def extract_globals(argv):
    """Remove --profile/--write-profile/--bucket/--root/--endpoint (set in runtime.OVERRIDES) and --quiet/--verbose from argv.
    Returns (the rest of argv, quiet, verbose)."""
    runtime.OVERRIDES.clear()
    rest, flags, i = [], set(), 0
    while i < len(argv):
        arg = argv[i]
        name, eq, value = arg.partition("=")
        if name in GLOBAL_VALUE_FLAGS:
            if not eq:
                if i + 1 >= len(argv):
                    ui.fail(f"{name} needs a value", 2)
                i += 1
                value = argv[i]
            runtime.OVERRIDES[GLOBAL_VALUE_FLAGS[name]] = value
        elif arg in ("--quiet", "--verbose"):
            flags.add(arg)
        else:
            rest.append(arg)
        i += 1
    if len(flags) == 2:
        ui.fail("--quiet and --verbose can't be combined", 2)
    return rest, "--quiet" in flags, "--verbose" in flags


def is_data_command(argv):
    """Whether the command's stdout is its result (so --quiet must not discard it)."""
    words = tuple(a for a in argv if not a.startswith("-"))
    return "--devices" in argv or words == ("cards",) or any(words[:len(d)] == d for d in DATA_COMMANDS)


def sync(reset=True):
    """Run the command in sys.argv. reset=False leaves --quiet/--verbose in place for the caller to undo with ui.reset()."""
    argv, quiet, verbose = extract_globals(sys.argv[1:])
    ui.set_output(quiet and not is_data_command(argv), verbose)
    try:
        usersettings.apply_settings()
        if ui.VERBOSE:
            saved = {} if usersettings.settings_problem() else None  # like apply_settings: a bad file is doctor's to report
            for name, (value, source) in usersettings.resolve_settings(saved).items():
                ui.debug(f"{name} = {value} ({source})")
        return run(argv)
    finally:
        if reset:
            ui.reset()


def run(argv):
    lead = 0
    while lead < len(argv) and argv[lead] in BOOL_FLAGS | {"--json"}:
        lead += 1
    if lead < len(argv) and argv[lead] in commands.COMMANDS and argv[lead:lead + 2] not in (["games", "edit"], ["cards", "edit"]):
        cmd = argv[lead:] + argv[:lead]  # leading global flags go after the command, where its parser reads them
        if "-h" in cmd or "--help" in cmd:
            print(help_text(cmd[0]))
            return 0
        return commands.run(cmd)
    if argv and argv[0] == "help":
        print(help_text(argv[1] if len(argv) > 1 else None))
        return 0
    topic = next((a for a in argv if a in SUBCOMMANDS), None) if ("-h" in argv or "--help" in argv) else None
    if topic:  # before translate(), which refuses `upload` and the others without their subcommand
        print(help_text(topic))
        return 0
    argv = translate(argv)
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"sync-roms {__version__}")
        return 0
    if args.help:
        print(help_text(topic))
        return 0
    ui.ASSUME_YES = args.yes
    mode = check_modes(args)
    if args.json and mode in (None, "--diff"):  # the JSON document is all that reaches stdout
        ui.set_output(True, ui.VERBOSE)
    handled, code = dispatch_mode(args, mode)
    return code if handled else sync_card(args)


def dispatch_mode(args, mode):
    """Run the command a flag stands for. Returns (True, its exit code), or (False, None) for a plain sync.

    The modules a command needs are imported here, so the other commands (and --help) don't pay for them."""
    if args.devices:
        return True, list_devices(args)
    if mode in ("--m3u", "--cd", "--install-tools"):
        if args.install_tools:
            return True, external.install_tools_command()
        if args.chd is not None:
            from . import chd
            return True, chd.chd_command(args)
        return True, m3u.m3u_command(args)
    if args.set_credentials:
        from . import scrape_online
        return True, scrape_online.set_credentials()
    usersettings.ensure_bucket()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT) and not args.edit:  # the editor goes by the cache alone
        ui.fail(f"The storage folder {runtime.ROOT} isn't there (is the share mounted?)", 3)
    if not args.json:  # the JSON document is all that reaches stdout: no question
        inventory.prepare()
    if args.scrape:
        from . import scrape_online
        return True, scrape_online.scrape_command(args)
    if args.scrape_match:
        from . import scrape_online
        args.system, args.rom, args.game = args.scrape_match
        return True, scrape_online.match_command(args)
    if args.scrape_review is not None:
        from . import scrape_review
        args.system = args.scrape_review or None
        return True, scrape_review.review_command(args)
    if args.scrape_missing is not None:
        from . import scrape_online
        args.system = args.scrape_missing or None
        return True, scrape_online.missing_command(args)
    if args.scrape_art is not None:
        from . import scrape_art
        args.system = args.scrape_art or None
        return True, scrape_art.art_command(args)
    if args.upload is not None:
        from . import upload
        return True, upload.upload_command(args)
    if args.diff is not None:
        from . import diff
        return True, diff.diff_command(args)
    if args.mirror is not None or args.use_mirror or args.clear_mirror:
        from . import mirroring
        return True, mirroring.mirror_command(args)
    if args.edit or args.clean_scrapes:
        if args.edit:
            code = edit.edit_manifest()
        else:
            from . import scrape_files
            code = scrape_files.clean_scrapes(args)
        mirror = usersettings.load_settings().get("mirror")
        if mirror and not code and not args.dry_run:  # pick up the games just added
            from . import mirroring
            print()
            mirroring.use_mirror(mirror, False)
        return True, code
    return False, None


def choose_card_setup(args, base, card, manifest, saved):
    """(device or None for Full, layout name, (roms dir, bios dir)) from --device/--layout, the saved setup or the picker.
    None if the user cancelled."""
    devices, layouts = manifest["devices"], manifest["layouts"]
    dirs = None
    setup = picker.saved_setup(saved, devices, layouts, card)
    if args.device or args.layout:
        setup = commands.setup_from_flags(manifest, setup, args.device, args.layout)
        print(ui.bold(f"🎛️  {ui.cyan(card)}: ") + f"{setup[0]['name'] if setup[0] else 'Full'} · {layouts[setup[1]]['label']}")
        device, layout_name = setup
        dirs = prepare_dirs(base, layouts[layout_name], args.dry_run, ask=False)
        if dirs and not args.dry_run:
            store.save_card(card, device, layout_name)
    elif setup:
        device, layout_name = setup
        print(ui.bold(f"💾 Remembered {ui.cyan(card)}: ")
              + f"{device['name'] if device else 'Full'} · {layouts[layout_name]['label']}"
              + ui.dim("  (saved under this folder name; --ask or --device/--layout changes it)"))
        if not args.ask or ui.confirm("Use this saved setup?"):
            dirs = prepare_dirs(base, layouts[layout_name], args.dry_run, ask=False)
    if dirs is None:
        device, layout_name = picker.choose_setup(manifest)
        dirs = prepare_dirs(base, layouts[layout_name], args.dry_run)
        if dirs is None:
            print(ui.yellow("👋 Cancelled."))
            return None
        if not args.dry_run:
            store.save_card(card, device, layout_name)
    return device, layout_name, dirs


def total_bytes(jobs):
    return sum(j[2] or 0 for j in jobs)


def delete_extras(extras):
    """List the local ROMs that are no longer wanted and, after confirming, delete them."""
    print(ui.bold(f"\n🗑️  {len(extras)} local ROM(s) are no longer in the selection"))
    ui.print_head(extras, 10, indent=5)
    answer = ui.choose(f"Delete these {len(extras)} local file(s) ({ui.human_size(sum(os.path.getsize(p) for p in extras))})?", "ynl", "n", "y yes · n no · l list all")
    while answer == "l":
        for path in extras:
            print(ui.dim(f"     {path}"))
        answer = ui.choose(f"Delete these {len(extras)} local file(s)?", "yn", "n")
    if answer == "y":
        deleted = 0
        for path in dict.fromkeys(extras):
            try:
                os.remove(path)
                deleted += 1
            except FileNotFoundError:  # already gone (a duplicate entry, or removed meanwhile)
                pass
            except OSError as e:
                ui.failure(ui.red(f"  ❌ {path}: {e}"))
        print(ui.green(f"  🧹 Deleted {deleted} file(s)"))
    else:
        print(ui.yellow("  ↩️  Keeping them"))


def list_kept(paths, what):
    """With --no-delete: list the files a sync would have deleted and says they stay."""
    if paths:
        print(ui.yellow(f"\n🔒 --no-delete: keeping {len(paths)} {what}"))
        for path in paths:
            print(ui.dim(f"     {path}"))


def remove_stale_media(stale):
    """Delete the media files left for ROMs that aren't on the card, saying so."""
    if stale:
        print(ui.bold(f"\n🧹 Removing {len(stale)} media file(s) for ROMs that aren't on this card"))
        ui.print_head(stale, 5, indent=5)
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            ui.failure(ui.red(f"  ❌ {path}: {e}"))
    if stale:
        print(ui.green(f"🧹 Removed {len(stale)} media file(s) for ROMs that aren't on this card"))


def report_failures(failures):
    ui.failure(ui.red(f"\n❌ {len(failures)} file(s) failed:"))
    for key, reason in failures[:20]:
        ui.failure(f"   {key}: {ui.dim(reason)}")
    if len(failures) > 20:
        ui.failure(ui.dim(f"   … and {len(failures) - 20} more"))
    if all(reason.endswith(downloads.STALE_HINT) for _, reason in failures):
        ui.failure(ui.dim(f"   These are gone from storage since the cache was built: run {inventory.UPDATE_HINT}, then sync again."))
    else:
        ui.failure(ui.dim("   Files already downloaded are skipped, so run the same command again to retry just these."))


@cardfs.caching()  # the card's folder listings, kept until sync changes the card
def sync_card(args):
    store.preload_repo_data()
    base = os.path.abspath(os.path.expanduser(args.base_dir or os.getcwd()))
    if not os.path.isdir(base):
        ui.fail(f"{base} isn't a folder (is the card mounted?)\n   See sync-roms --help for the commands.", 2)

    tree = inventory.current()
    age = f"  ·  cache updated {inventory._ago(max(0, inventory._clock() - tree.updated))}" if tree and tree.updated else ""
    print(ui.bold("🎮 sync-roms") + ui.dim(f"  {s3.access()}{age}"))
    mirror = usersettings.load_settings().get("mirror")
    if mirror:
        mirroring.use_mirror(mirror, args.dry_run)
    print("📄 Fetching manifests...")
    card = os.path.basename(base) or base
    manifest = store.load_manifest([card])
    systems, layouts = manifest["systems"], manifest["layouts"]
    if not any(s["games"] or s.get("full_system") for s in systems):
        print(ui.dim(f"  {card} has no games picked"))
    old_list = os.path.join(store.data_dir(), "games.json")  # the core list from before cards had their own games
    if os.path.exists(old_list) and store.personal_json("games.json"):
        ui.warn(f"{old_list} is no longer read; pick its games for {card} in 'sync-roms edit'.")
    cards = store.load_cards()
    saved = store.saved_card(card, cards)
    chosen_setup = choose_card_setup(args, base, card, manifest, cards.get(card))
    if chosen_setup is None:
        return 0
    device, layout_name, dirs = chosen_setup
    layout = layouts[layout_name]
    disc_dir = layout.get("disc_dir")  # multi-disc games' discs go in this hidden folder, their playlist beside it (Onion)
    disc_folders = layout.get("disc_folders")  # each disc game goes in a folder of its own (NextUI)
    onion = layout_name in scrape_plan.ONION_LAYOUTS
    roms_dir, bios_dir = dirs
    if layout_name == "nextui":  # folders an earlier sync named differently from NextUI move rather than download again
        for old, new in nextui_folders.migrate(roms_dir, args.dry_run):
            print(ui.dim(f"  📦 {'would rename' if args.dry_run else 'Renamed'} {old} → {new}"))
        cardfs.clear()
    clean_card = not args.dry_run and not args.no_clean

    def synced(all_systems):
        """The systems of all_systems this card syncs, by name: its device runs them and its layout has a folder for them."""
        return sorted((s for s in all_systems if store.system_applies(s, device, layout_name)), key=lambda s: s["name"].lower())

    dropped = []  # systems the device no longer lists: whatever they left on the card is unwanted
    if device:
        dropped = [s for s in systems if s["bucket"] not in device["systems"]]
        if device["note"]:
            print(ui.dim(f"  {device['name']}: {device['note']}"))
    unsupported = len(systems) - len(dropped) - len(synced(systems))  # of the systems the device runs
    if unsupported:
        print(ui.dim(f"  {unsupported} system(s) have no {layout['label']} folder and are skipped"))
    systems = synced(systems)
    if layout_name == "spruce":  # the folders an earlier sync used for a system that now uses another: all of it is unwanted
        legacy = spruce_emu.legacy_systems(systems)
        dropped += legacy
        manifest["systems"] = [*manifest["systems"], *legacy]
    if not device and not unsupported:  # as it always was: a card that syncs every system has the manifest's own list,
        manifest["systems"] = systems  # which the stale-media check reads, in name order too

    print("📏 Reading ROM sizes...")
    listings = {}  # {system id: {key: size}}, kept until the system's games change
    avail, discs, game_dirs = {}, {}, {}  # per system id: the keys to sync, their multi-disc keys, their game folders

    sized = not runtime.ROOT or inventory.current() is not None  # sizes are known up front

    def available(s):
        return avail[s["bucket"]]

    def discs_of(s):
        return discs[s["bucket"]]

    def folders_of(s):
        return game_dirs[s["bucket"]]

    def listing_of(s):
        """{key: size} of a system's bucket folder. From a root folder with no storage cache, names only (a share is slow
        to stat): a full system's files are listed, a game list needs no listing, and sizes are read for what gets synced."""
        if not sized:
            return inventory.files(s["bucket"] + "/", sizes=False) if s.get("full_system") else {}
        return store.list_system(s)

    def relist():
        """List the systems not listed yet and work out every system's keys to sync."""
        todo = [s for s in systems if s["bucket"] not in listings]
        with ThreadPoolExecutor(runtime.WORKERS) as ex:
            listings.update(zip((s["bucket"] for s in todo),
                                ex.map(lambda s: listing_of(s)
                                       if s.get("full_system") or store.listed(s) else {}, todo)))
        for s in systems:
            avail[s["bucket"]] = store.available_keys(s, listings[s["bucket"]])
            discs[s["bucket"]] = m3u.disc_keys(avail[s["bucket"]]) if disc_dir else ()
            game_dirs[s["bucket"]] = m3u.game_folders(avail[s["bucket"]]) if disc_folders else {}

    fetching = {}  # {system id: {key: whether it isn't on the card yet}}: the card's files don't change while editing

    def to_fetch(s, keys):
        """The keys of a system's ROMs that aren't on the card yet, for the card editor's size preview."""
        bucket = s["bucket"]
        seen = fetching.setdefault(bucket, {})
        todo = [k for k in keys if k not in seen]
        if todo:
            sizes = inventory.cached(f"{bucket}/") or {}
            disc_keys = m3u.disc_keys(keys) if disc_dir else ()
            folders = m3u.game_folders(keys) if disc_folders else None
            jobs = []
            for k in todo:
                try:
                    path = s3.safe_join(os.path.join(roms_dir, s["folders"][layout_name]),
                                        downloads.rom_rel(k, disc_dir, disc_keys, folders))
                except ValueError:
                    seen[k] = False
                    continue
                jobs.append((k, path, sizes.get(k)))
            need = {j[0] for j in downloads.plan_downloads(jobs, disc_dir)}
            seen.update((k, k in need) for k, _, _ in jobs)
        return {k for k in keys if seen[k]}

    def card_match(s, keys):
        """Which of keys are on the card already, for the card editor's keep key. Names match like the card does:
        case and Unicode form left out."""
        folder = s["folders"].get(layout_name)
        if not folder:
            return set()
        dest = os.path.join(roms_dir, folder)
        walks = list(downloads.walk_roms(dest, rename_temps=True))
        if disc_dir:
            walks += downloads.walk_roms(os.path.join(dest, disc_dir), rename_temps=True)
        names = {downloads.name_key(os.path.relpath(os.path.join(root, f), dest)) for root, files in walks for f in files}
        disc_keys = m3u.disc_keys(keys) if disc_dir else ()
        folders = m3u.game_folders(keys) if disc_folders else None
        return {k for k in keys if downloads.name_key(downloads.rom_rel(k, disc_dir, disc_keys, folders)) in names}

    relist()
    interactive = not (ui.ASSUME_YES or args.json) and ui.has_terminal()
    def reload_changes():
        """Pick up the card's games as saved now: refresh the mirror and the listings for the systems that changed."""
        nonlocal systems, saved

        def picks(s):
            return s.get("full_system"), store.listed(s)
        before = {s["bucket"]: picks(s) for s in systems}
        systems = synced(store.load_manifest([card])["systems"])  # with the card's games as they are saved now
        changed = [s["bucket"] for s in systems if picks(s) != before.get(s["bucket"])]
        if changed and runtime._mirror_root:  # the new picks reach the mirror before they are copied from it
            root = runtime._mirror_root
            try:
                with mirroring.storage_reads():
                    failed = mirroring.refresh_mirror(root)
                if failed:
                    ui.warn(f"{failed} mirror download(s) failed; files missing from the mirror will fail to copy. Re-run to retry")
            except (*s3.ERRORS, SystemExit) as e:  # S3 failed, or the folder isn't a mirror
                ui.warn(f"Couldn't refresh the mirror ({e}); using what it has")
        for bucket in changed:
            listings.pop(bucket, None)
        relist()
        saved = store.saved_card(card)

    # surprises come in two steps: which ones to replace first (then the card editor, which shows the ones kept), and
    # the empty slots last, right before the sync, from every system the card's device supports, games picked or not
    surprise.run_surprise(card, (device, layout_name), systems, interactive, args.dry_run, to_fetch=to_fetch,
                       card_match=card_match)
    if not args.dry_run:  # the step (and the card editor it opens) may have changed the card's games
        reload_changes()
    surprise.fill_surprises(card, (device, layout_name), systems, args.dry_run)
    if not args.dry_run:
        reload_changes()

    def install_apps(dry_run, wrote=None):
        """Put PICO-8 (wrote, a list, gets what it put), the Surprise app and RAOfflineProxy on the card. The failure count."""
        return (pico8.run(card, layout_name, base, dry_run, wrote) + onion_surprise.install(card, layout_name, base, dry_run)
                + raofflineproxy.install(card, layout_name, base, dry_run))

    def stage_spruce(dry_run):
        """Stage boot logos, the newest spruceOS, the saved settings and WiFi networks on a spruce card. The failure count."""
        wrote = []
        failed = spruce_bootlogo.install(card, layout_name, device, base, dry_run, wrote, keep=args.no_delete)
        failed += spruce_os.install(card, layout_name, base, dry_run, wrote, keep=args.no_delete)
        failed += spruce_settings.install(card, layout_name, base, dry_run)
        failed += spruce_wifi.install(card, layout_name, base, dry_run)
        if clean_card and wrote:
            clean._clean_root = base
        return failed

    chosen = [s for s in systems if available(s)]
    if not chosen:
        failed = install_apps(args.dry_run)
        if onion_surprise.write_list(card, layout_name, base, roms_dir, systems, args.dry_run) and clean_card:
            clean._clean_root = base
        failed += stage_spruce(args.dry_run)
        print(ui.yellow(f"👋 {card} has nothing to sync."))
        return 1 if failed else 0
    print(ui.bold(f"\n🔎 Checking {len(chosen)} system(s) against storage..."))

    def dest_of(s):
        return os.path.join(roms_dir, s["folders"][layout_name])

    def rom_bios_names(s):
        """The names the system's ROM-folder BIOS files have on the card."""
        return {os.path.basename(f) for f in s["bios"].get("rom_files", [])}

    rom_jobs, missing, extras, moved, renames = [], [], [], set(), []
    for s in chosen:
        wanted = available(s)
        if not wanted:
            continue
        if not sized:  # sizes are read now, only for the ROMs being synced
            listings[s["bucket"]] = inventory.stat(wanted)
        have = listings[s["bucket"]]
        dest = dest_of(s)
        disc_keys = discs_of(s)
        if disc_keys:  # discs a past sync left loose go where they belong rather than being downloaded again
            moved.update(downloads.hide_discs(dest, disc_dir, disc_keys, args.dry_run))
        for key in wanted:
            if key in have:
                downloads.add_job(rom_jobs, key, dest, downloads.rom_rel(key, disc_dir, disc_keys, folders_of(s)), have[key])
            else:
                missing.append(key)
    ui.report_missing(missing, "ROM(s)")
    # systems can share a folder (Onion: WS, NGP), so a folder's expected files are the union over all of them
    # a system with nothing to sync is always scanned, selected or not: whatever it has on the card is unwanted
    chosen_ids = {s["bucket"] for s in chosen}
    dropped_dests = {os.path.join(roms_dir, s["folders"][layout_name]) for s in dropped if s["folders"].get(layout_name)}
    # a system's rom_files are BIOS files that go in its ROM folder (MAME-style BIOS zips), kept while it has ROMs to sync
    dest_keys, dest_discs, dest_bios, dest_folders = defaultdict(list), defaultdict(set), defaultdict(set), defaultdict(dict)
    for t in systems:
        dest_keys[dest_of(t)] += available(t)
        dest_discs[dest_of(t)].update(discs_of(t))
        dest_folders[dest_of(t)].update(folders_of(t))
        if available(t):
            dest_bios[dest_of(t)].update(rom_bios_names(t))
    pico8_dests = {os.path.join(roms_dir, t["folders"][layout_name]) for t in systems + dropped
                   if t["bucket"] == "pico8" and t["folders"].get(layout_name)}
    own_files = defaultdict(set)  # sync-roms's own files at the top of a ROM folder (ROCKNIX's Ports scripts)
    for t in systems + dropped:
        if t["folders"].get(layout_name):
            own_files[os.path.join(roms_dir, t["folders"][layout_name])].update(downloads.layout_files(layout_name, t))
    cardfs.clear()  # the discs moved above, and the card editor's previews listed the card a while ago
    for dest in sorted({dest_of(s) for s in systems if s["bucket"] in chosen_ids or not available(s)} | dropped_dests):
        extras += downloads.find_extras(dest, dest_keys[dest], onion, disc_dir, dest_discs[dest], dest_bios[dest] | own_files[dest] | (pico8.keep_in(dest, card, layout_name) if dest in pico8_dests else set()), renames=renames, folders=dest_folders[dest], skip_saves=saves.beside_roms(layout))

    # BIOS for every system with ROMs already on the card too, even when this sync doesn't touch that system
    bios_systems = chosen + [s for s in systems if s["bucket"] not in chosen_ids
                             and downloads.has_local_files(dest_of(s), onion, rom_bios_names(s) | own_files[dest_of(s)])]
    # (bucket key, folder, path in it) of each BIOS file: in the BIOS folder, or in the ROM folder of a system with ROMs to sync
    bios_dests = {("BIOS/" + f, folder, f) for s in bios_systems for folder in downloads.bios_folders(s, layout_name, layout, bios_dir)
                  for f in s["bios"]["files"]}
    bios_dests |= {("BIOS/" + f, dest_of(s), os.path.basename(f))
                   for s in bios_systems if available(s) for f in s["bios"].get("rom_files", [])}
    bios_keys = sorted({k for k, _, _ in bios_dests})
    bios_have = (inventory.stat(bios_keys) if s3.read_root() else inventory.files("BIOS/")) if bios_keys else {}
    bios_jobs = []
    for k, folder, rel in sorted(bios_dests):
        if k in bios_have:
            downloads.add_job(bios_jobs, k, folder, rel, bios_have[k])
    ui.report_missing([k for k in bios_keys if k not in bios_have], "BIOS file(s)")
    # Android cards also get storage's os/android/APKs/ files (APKs, the Obtainium app list) in an APKs/ folder to install from
    apk_dir = os.path.join(base, "APKs")
    apk_jobs = ([(k, os.path.join(apk_dir, k[len(runtime.APKS_PREFIX):]), size) for k, size in sorted(inventory.files(runtime.APKS_PREFIX, sizes=False).items())
                 if not k.endswith("/") and (store.card_flag(store.saved_card(card), "raofflineproxy")
                                             or not re.fullmatch(r"RAOfflineProxy.*\.apk", os.path.basename(k)))] if layout_name == "esde" else [])
    apk_jobs = downloads.with_sizes(apk_jobs)
    # and the suggested GPU drivers for the device's Adreno GPU, kept up to date in storage first, in a Drivers/ folder
    driver_entries = drivers.for_device(device, layout_name)
    drivers_dir = os.path.join(base, "Drivers")
    if driver_entries:
        if drivers.can_write():
            drivers.refresh(driver_entries, args.dry_run)
        else:
            print(ui.dim("🎮 no write access to storage: copying the drivers it has"))
    driver_jobs = downloads.with_sizes(drivers.jobs(driver_entries, drivers_dir)) if driver_entries else []

    # Onion cards also get storage's os/onion/Themes/ folders in the card's Themes/
    themes_dir = layout.get("themes_dir")
    theme_jobs = []
    if themes_dir:
        for k, size in sorted(inventory.files(runtime.THEMES_PREFIX, sizes=False).items()):
            rel = k[len(runtime.THEMES_PREFIX):]
            if k.endswith("/") or os.path.basename(rel) == ".DS_Store":
                continue
            downloads.add_job(theme_jobs, k, os.path.join(base, themes_dir), rel, size)

    theme_jobs = downloads.with_sizes(theme_jobs)

    rom_todo, bios_todo = downloads.plan_downloads(rom_jobs, disc_dir), downloads.plan_downloads(bios_jobs)
    apk_todo = downloads.plan_downloads(apk_jobs)
    driver_todo = downloads.plan_downloads(driver_jobs)
    theme_todo = downloads.plan_downloads(theme_jobs)
    if args.dry_run:  # the real run moves these first, so they are already there and not extras
        rom_todo = [j for j in rom_todo if j[1] not in moved]
        extras = [p for p in extras if not moved or os.path.join(os.path.dirname(p), disc_dir, os.path.basename(p)) not in moved]
    elif moved:
        print(ui.dim(f"  📦 Moved {len(moved)} loose disc file(s) into {disc_dir}/"))
    # card files spelled differently from storage are renamed, and unwanted ones that match a missing file are moved
    # there, before the downloads: neither is downloaded or deleted
    rom_todo, bios_todo = downloads.after_renames(rom_todo, renames, disc_dir), downloads.after_renames(bios_todo, renames)
    card_moves = downloads.plan_moves(rom_todo + bios_todo, {p: cardfs.size(p) for p in extras})
    moved_jobs, moved_from = {j for _, j in card_moves}, {p for p, _ in card_moves}
    bios_moves = moved_jobs.intersection(bios_todo)
    extras = [p for p in extras if p not in moved_from]
    kept_extras = []  # --no-delete: the ROMs that would have been deleted
    if args.no_delete:
        kept_extras, extras = list(dict.fromkeys(extras)), []
    rom_todo, bios_todo = [j for j in rom_todo if j not in moved_jobs], [j for j in bios_todo if j not in moved_jobs]
    es_dir = frontend.esde_dir(layout_name, base)
    # EmuDeck's ES-DE is on this computer: the card's gamelists and collections go there only when it uses the card's ROMs
    esde_problem = frontend.emudeck_problem(base, os.path.join(base, layout["roms_dir"])) if layout_name == "emudeck" else None
    stale_es_dir = None if esde_problem else es_dir
    warned = []

    def skipped():
        """Say (once) that the card's gamelists and collections were skipped, and why."""
        if not warned:
            warned.append(esde_problem)
            ui.warn(f"{esde_problem}, so the card's gamelists and collections were skipped; "
                    "sync on the Steam Machine or Steam Deck to get them")
    scrapes = layout_name in scrape_plan.SCRAPE_LAYOUTS
    scraped = {}

    def build_plan(present, recheck=None):
        if not scraped:
            print("🖼️  Reading scraped data...")
            scraped["data"] = scrape_plan.load_scrape_data(chosen)
            scraped["rels"] = {s["bucket"]: [k.split("/", 1)[1] for k in available(s) if k in listings[s["bucket"]]]
                               for s in chosen}
        if disc_folders:  # scrapes name a ROM by its storage path; a disc game is in its own folder on the card
            moved_to = {os.path.join(dest_of(s), k.split("/", 1)[1]): os.path.join(dest_of(s), downloads.rom_rel(k, folders=folders_of(s)))
                        for s in chosen for k in folders_of(s)}
            found = present

            def present(path):
                return found(moved_to.get(path, path))
        plan = scrape_plan.build_scrape_plan(layout_name, chosen, scraped["data"], scraped["rels"], dest_of, es_dir, present, base,
                                             recheck=recheck)
        if esde_problem and plan["gamelists"]:
            skipped()
            plan["gamelists"] = {}
        return plan

    # the media of every ROM that will be on the card, so the totals and the space check count it
    planned = build_plan(lambda path: True) if scrapes else None
    scrape_todo = planned["jobs"] if planned else []
    summary = [f"{icon} {label}: {ui.bold(str(len(todo)))} to download ({ui.human_size(total_bytes(todo))}), "
               f"{len(jobs) - len(todo)} already present"
               for icon, label, todo, jobs, always in (("💿", "ROMs", rom_todo, rom_jobs, True), ("🧠", "BIOS", bios_todo, bios_jobs, True),
                                                       ("🤖", "Android", apk_todo, apk_jobs, False), ("🎮", "Drivers", driver_todo, driver_jobs, False),
                                                       ("🎨", "Themes", theme_todo, theme_jobs, False))
               if always or jobs]
    print("\n" + "\n".join(summary))
    if planned:
        scrape_plan.describe_scrape_plan(planned)
    if extras:
        print(f"🗑️  Local ROMs no longer in the selection: {ui.bold(str(len(extras)))}")
    list_kept(kept_extras, "local ROM(s) no longer in the selection")
    if renames or card_moves:
        print(f"📦 Card files to rename or move instead of downloading: {ui.bold(str(len(renames) + len(card_moves)))}")
    todo_all = rom_todo + bios_todo + apk_todo + driver_todo + theme_todo + scrape_todo
    size = saved.get("size")

    def space(free):
        """Show the card's free space; the "Not enough space" text when the downloads don't fit."""
        print(f"💾 Free on the card: {ui.human_size(free)}" + (f" ({size} card)" if size else ""))
        need = total_bytes(todo_all)
        return f"Not enough space: {ui.human_size(need)} to download, {ui.human_size(free)} free" if need > free else None

    def frontend_step(dry_run):
        """Write the card's collections as the frontend's custom collections (ES-DE, Knulli, ROCKNIX, EmuDeck's ES-DE)."""
        if layout_name not in frontend.FRONTEND_LAYOUTS and layout_name not in ("muos", "spruce"):
            return
        entry = store.saved_card(card)

        def names(field):
            """The card's list field as its text items (anything else stored there is ignored)."""
            values = entry.get(field)
            return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []
        by_id = {c["id"]: c for c in colls.load_collections()}
        collections_on = store.card_flag(entry, "custom_collections")
        card_colls = [by_id[i] for i in names("collections") if i in by_id] if collections_on else []
        surprises = [x for x in entry.get("surprises") or () if isinstance(x, dict)
                     and isinstance(x.get("system"), str) and isinstance(x.get("bucket"), str)]
        if collections_on and surprise.enabled(entry) and surprises:  # as saved now: the card editor may have changed them
            card_colls.append({"name": surprise.COLLECTION, "games": surprises})  # its art is added below
        owned = names("frontend_collections")
        if not card_colls and not owned:
            return
        mount = muos_collections.mount(entry) if layout_name == "muos" else None
        if layout_name == "muos" and mount is None:
            ui.warn("muos_storage must be sd1 or sd2: collections skipped")
            return
        if esde_problem:
            skipped()
            return
        coming = {(s["bucket"], downloads.rom_rel(k, folders=folders_of(s))) for s in chosen
                  for k in available(s) if k in listings[s["bucket"]]} if dry_run else set()

        def on_card(s, rel):
            return (s["bucket"], rel) in coming or cardfs.exists(os.path.join(dest_of(s), rel))

        if layout_name == "muos":
            plan = muos_collections.plan(base, muos_collections.wanted(card_colls, systems, on_card, mount), owned)
        elif layout_name == "spruce":
            plan = spruce_collections.plan(base, spruce_collections.wanted(card_colls, systems, on_card), owned)
        else:
            wanted = frontend.wanted_collections(layout_name, card_colls, systems, on_card,
                                                 {k: d for s in systems for k, d in folders_of(s).items()})
            plan = frontend.plan_collections(layout_name, base, wanted, owned)
        arts = {frontend.safe_name(c["name"]): c["art"] for c in card_colls if c.get("art")}
        if surprise.COLLECTION in plan["enable"]:
            arts[surprise.COLLECTION] = themeart.SURPRISE_ART
        arts = {name: art for name, art in arts.items() if name in plan["enable"]}
        if not store.card_flag(entry, "theme"):  # no Art Book Next copy, no ES-DE theme and no custom art
            arts = {}
        if dry_run:
            if layout_name == "muos":
                muos_collections.describe(plan)
            elif layout_name == "spruce":
                spruce_collections.describe(plan)
            else:
                frontend.describe_collections(plan, layout_name)
            if layout_name == "spruce":
                themeart.describe(layout_name, base, arts, {*owned, *plan["owned"]})
            elif arts or store.card_flag(entry, "theme"):  # with no art to add it still names the art that would go
                themeart.describe(layout_name, base, arts)
            return
        for warning in plan["warnings"]:
            ui.warn(warning)
        if layout_name == "muos":
            muos_collections.apply(plan)
            listed = False
        elif layout_name == "spruce":
            spruce_collections.apply(plan)
            listed = False
        else:
            listed = frontend.apply_collections(plan, layout_name, base)
        if plan["owned"] != owned:
            store.update_card(card, frontend_collections=plan["owned"])
        if layout_name == "spruce":  # also removes the pictures of collections that lost their art
            art = themeart.install(layout_name, base, arts, {*owned, *plan["owned"]})
        else:  # with no art to add it still removes the art sync-roms wrote before
            art = (bool(arts) or store.card_flag(entry, "theme")) and themeart.install(layout_name, base, arts)
        # EmuDeck's ES-DE is on this computer, not the card, so its writes leave the card as it was
        if clean_card and layout_name != "emudeck" and (plan["writes"] or plan["deletes"] or listed or art):
            clean._clean_root = base
        if plan["writes"]:
            count = (len({os.path.dirname(p) for p, _ in plan["writes"]}) if layout_name == "muos"
                     else len(plan["enable"]) if layout_name == "spruce" else len(plan["writes"]))
            print(ui.green(f"💖 Wrote {count} collection(s) for {layout['label']}"))
        if layout_name == "rocknix" and (plan["writes"] or plan["deletes"] or art):
            print(f"💖 Run {os.path.basename(rocknix_collections.SCRIPT)[:-3]} from Ports on the device to install them")

    def spruce_emu_step(dry_run):
        """On a spruce card: hide the BIOS zips in the ROM folders from PyUI's game list (Emu/<folder>/config.json)."""
        if layout_name != "spruce":
            return
        owned = store.saved_card(card).get("spruce_emu")
        plan = spruce_emu.plan(base, spruce_emu.wanted(chosen, lambda s: bool(available(s))), owned)
        if dry_run:
            spruce_emu.describe(plan)
            return
        for warning in plan["warnings"]:
            ui.warn(warning)
        spruce_emu.apply(plan)
        if plan["owned"] != (owned if isinstance(owned, dict) else {}):
            store.update_card(card, spruce_emu=plan["owned"])
        if plan["writes"]:
            print(ui.green(f"🎮 Updated {len(plan['writes'])} Spruce emulator config(s)"))
            if clean_card:
                clean._clean_root = base

    def prune_drivers(dry_run):
        """Remove the drivers an earlier sync copied that the card doesn't get now, saying which (kept with --no-delete)."""
        old = drivers.prune(card, drivers_dir, [os.path.basename(p) for _, p, _ in driver_jobs], dry_run, keep=args.no_delete)
        if args.no_delete:
            list_kept([os.path.join(drivers_dir, name) for name in old], "old driver(s)")
        else:
            for name in old:
                print(f"  {ui.red('would delete')} {os.path.join(drivers_dir, name)}" if dry_run else ui.green(f"🧹 Removed old driver {name}"))

    capacity = budget.card_capacity(saved) if surprise.enabled(saved) else None
    if capacity:
        used = budget.card_usage(cardedit.card_entry(card, (device, layout_name)), systems).bytes
        if used > capacity:
            ui.warn(f"{card}'s picks take {cardedit.size_text(used)} of its {saved['size']}: "
                    f"{cardedit.size_text(used - capacity)} over")

    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing downloaded or deleted"))
        free = free_space(base) + sum(cardfs.size(p) or 0 for p in extras)  # the real run deletes these first
        plan_json = {
            "downloads": [{"kind": kind, "key": key, "path": path, "size": size or 0}
                          for kind, todo in (("rom", rom_todo), ("bios", bios_todo), ("android", apk_todo), ("driver", driver_todo),
                                          ("theme", theme_todo), ("scrape", scrape_todo))
                          for key, path, size in todo],
            "delete": list(extras), "kept": kept_extras, "rename": [{"from": a, "to": b} for a, b in renames + [(p, j[1]) for p, j in card_moves]],
            "missing": {"roms": missing, "bios": [k for k in bios_keys if k not in bios_have]},
            "free_space": free}
        for key, path, _ in todo_all:
            print(f"  {key} {ui.dim('→')} {path}")
        short = space(free) if todo_all else None
        if short:
            ui.failure(ui.red(f"❌ {short}"))
        for path, new in renames:
            print(f"  {ui.yellow('would rename')} {path} {ui.dim('→')} {new}")
        for path, job in card_moves:
            print(f"  {ui.yellow('would move')} {path} {ui.dim('→')} {job[1]}")
        for path in extras:
            print(f"  {ui.red('would delete')} {path}")
        prune_drivers(True)
        install_apps(True)
        stage_spruce(True)
        stale_count = 0
        if scrapes:
            stale_files = scrape_plan.stale_media(layout_name, manifest['systems'], roms_dir, stale_es_dir, base)
            if args.no_delete:
                list_kept(stale_files, "media file(s) for ROMs that aren't on this card")
            else:
                stale_count = len(stale_files)
                print(f"🧹 Media on the card for ROMs it doesn't have: {stale_count} file(s) to remove")
        frontend_step(True)
        spruce_emu_step(True)
        spruce_fixes.run(layout_name, base, True)
        onion_surprise.write_list(card, layout_name, base, roms_dir, systems, True)
        plan_json["stale_media"] = stale_count
        plan_json["totals"] = {"files": len(todo_all), "bytes": total_bytes(todo_all), "delete": len(extras),
                               "stale_media": stale_count, "missing": len(missing)}
        if args.json:
            ui.emit_json(plan_json)
        print(ui.bold(f"\n🧪 Would download {len(todo_all)} file(s) ({ui.human_size(total_bytes(todo_all))}), "
                      f"delete {len(extras)} local ROM(s) and {stale_count} media file(s); {len(missing)} listed ROM(s) not in storage"))
        return 0

    move_failed = 0
    for path, new in renames:
        try:
            downloads.rename_on_card(path, new)
        except OSError as e:
            move_failed += 1
            ui.failure(ui.red(f"  ❌ {path}: {e}"))
    for path, job in card_moves:
        try:
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            os.replace(path, job[1])
        except OSError as e:  # downloaded instead
            ui.failure(ui.red(f"  ❌ {path}: {e}"))
            (bios_todo if job in bios_moves else rom_todo).append(job)
            todo_all.append(job)
    if clean_card and (renames or card_moves):
        clean._clean_root = base

    if extras:  # cleared first so the free space shown below is what the downloads really get
        delete_extras(extras)
    cardfs.clear()

    if todo_all:
        short = space(free_space(base))
        if short:
            if ui.ASSUME_YES or not ui.has_terminal():  # nobody to answer "Try anyway?"
                ui.fail(short, 1)
            ui.failure(ui.red(f"❌ {short}"))
            if not ui.confirm("Try anyway?", default=False):
                print(ui.yellow("👋 Cancelled."))
                return 0
        if not ui.confirm(f"⬇️  Download {len(todo_all)} file(s) ({ui.human_size(total_bytes(todo_all))})?"):
            print(ui.yellow("👋 Cancelled."))
            return 0

    if clean_card and todo_all:  # nothing downloaded means nothing to finalize
        clean._clean_root = base
    started = time.monotonic()
    failures = []
    disc_dirs = {os.path.normpath(dest_of(s)): disc_dir for s in chosen if available(s)} if disc_dir else None
    failed = move_failed + downloads.run_downloads(rom_todo, "ROMs", "💿", roms_dir, failures, disc_dirs) + downloads.run_downloads(bios_todo, "BIOS", "🧠", bios_dir, failures)
    if apk_jobs:
        failed += downloads.run_downloads(apk_todo, "Android", "🤖", apk_dir, failures)
    if driver_entries:
        failed += downloads.run_downloads(driver_todo, "Drivers", "🎮", drivers_dir, failures)
    # also when the card gets no drivers now (another device or layout): the ones sync copied before go
    prune_drivers(False)
    pico8_wrote = []
    failed += install_apps(False, pico8_wrote)
    if theme_todo:
        failed += downloads.run_downloads(theme_todo, "Themes", "🎨", os.path.join(base, themes_dir), failures)
    prefixed = 0
    for s in chosen:
        if disc_dir and available(s):
            prefixed += m3u.prefix_playlists(dest_of(s), disc_dir, [p for _, p, _ in rom_todo if p.lower().endswith(".m3u")])
    cardfs.clear()

    psvita_wrote = []
    if layout_name in frontend.ESDE_LAYOUTS:  # ES-DE launches an installed Vita game through its .psvita file
        for path, error in vita.add_psvita_files({dest_of(s) for s in chosen if s["bucket"] == "psvita"}, psvita_wrote):
            failed += 1
            failures.append((os.path.relpath(path, roms_dir), error))
            ui.failure(ui.red(f"  ❌ {os.path.relpath(path, roms_dir)}: {error}"))
        cardfs.clear()
    if clean_card and (pico8_wrote or prefixed or psvita_wrote):
        clean._clean_root = base

    stale = []
    if scrapes:
        plan = build_plan(cardfs.exists, {path for _, path, _ in planned["jobs"]})  # media found current then still are
        scrape_todo = plan["jobs"]
        scrape_failed, wrote = scrape_plan.apply_scrape_plan(plan, base, failures)
        failed += scrape_failed
        if clean_card and wrote:
            clean._clean_root = base
        cardfs.clear()
        stale = scrape_plan.stale_media(layout_name, manifest["systems"], roms_dir, stale_es_dir, base)
    if args.no_delete:
        list_kept(stale, "media file(s) for ROMs that aren't on this card")
    else:
        remove_stale_media(stale)
    cardfs.clear()
    for folder in [] if args.no_delete else scrape_plan.prune_empty_systems(layout_name, manifest["systems"], roms_dir):
        print(ui.green(f"🧹 Removed empty system folder {os.path.relpath(folder, base)}"))
    cardfs.clear()
    frontend_step(False)
    spruce_emu_step(False)
    if spruce_fixes.run(layout_name, base, False) and clean_card:
        clean._clean_root = base
    if onion_surprise.write_list(card, layout_name, base, roms_dir, systems, False) and clean_card:
        clean._clean_root = base
    try:
        cardfs.flush()  # the frontend settings, before the card is reported done
    except OSError as e:
        failed += 1
        failures.append(("frontend settings", str(e)))
    failed += stage_spruce(False)  # last: the 7z is large, and the card's other writes come first
    if failures:
        report_failures(failures)
    if not failed and not args.no_eject and usersettings.load_settings().get("eject", True) is not False:
        clean._eject_root = base  # after the card tidy, which still needs it mounted
    failed_keys = {k for k, _ in failures}
    got = [j for j in rom_todo + bios_todo + apk_todo + driver_todo + theme_todo + scrape_todo if j[0] not in failed_keys]
    done = (f"downloaded {len(got)} file(s) ({ui.human_size(total_bytes(got))}) in {ui.eta(time.monotonic() - started)}"
            + (f"; {len(missing)} listed ROM(s) not in storage" if missing else ""))
    if failed:
        ui.failure(ui.red(f"\n⚠️  Done with {failed} failure(s): {done}"))
    else:
        print(ui.green(f"\n🎉 Done: {done}"))
    return 1 if failed else 0


free_space = downloads.free_space
