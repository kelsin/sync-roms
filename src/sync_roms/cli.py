"""Download ROMs and BIOS files from your ROM storage."""
import ast
import contextlib
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from . import __version__, bezels, budget, cardedit, cardfs, clean, commands, downloads, drivers, frontend, inventory, m3u, mirroring, picker, runtime, s3, scrape_plan, store
from . import knulli_conf, muos_collections, nextui_folders, onion_surprise, pico8, portmaster, raofflineproxy, rocknix_collections, saves, spruce_collections, spruce_bootlogo, spruce_emu, spruce_os, spruce_fixes, spruce_hotkeys, spruce_retroarch, spruce_settings, spruce_splore, spruce_syncthing, spruce_themes, spruce_wifi, splore, surprise, themeart, ui, usersettings, vita
from . import collections as colls
from . import guest as guests


ALIASES = {"card": "cards", "game": "games", "set": "sets", "collection": "collections", "theme": "themes", "save": "saves",  # alias -> main name
           "device": "devices", "layout": "layouts", "playlists": "playlist", "scrapes": "scrape", "downloads": "download", "port": "ports",
           "umount": "unmount"}


def canonical(word):
    """A command's main name: the word itself unless it's an alias."""
    return ALIASES.get(word, word)

SUBCOMMANDS = {  # name -> (usage, one-line summary)
    "sync": ("[CARD]", "download the ROMs, BIOS and scraped data for a card (this is what plain `sync-roms CARD` does)"),
    "edit": ("", "interactive editor: cards, sets, collections, device systems"),
    "games": ("list|add|remove|full|sets|export|import", "edit a card's games, interactively or from scripts"),
    "sets": ("edit", "edit the game sets in storage by hand and save the changes there"),
    "collections": ("edit", "edit your collections of favourite games (saved in ~/.sync-roms/collections/)"),
    "themes": ("update|pick|build|publish|palettes", "copy the latest Art Book Next for ES-DE and the PyUI themes for spruce from GitHub into storage; build and publish custom spruce themes"),
    "download": ("pico8", "add the PICO-8 BBS Featured carts storage doesn't have, and newer revisions of those it has"),
    "ports": ("search|download", "put PortMaster ports and the runtimes they need in storage, from PortMaster's catalogue"),
    "flash": ("", "write a Knulli, BaseOS, muOS, ROCKNIX or OakMoss image from storage's os/ to an SD card"),
    "format": ("", "erase an SD card as exFAT or FAT32 with a picked label"),
    "unmount": ("", "clean the macOS junk off an SD card and unmount it"),
    "mount": ("", "mount again an SD card that was unmounted but not pulled out"),
    "cards": ("[list|new|set|rename|layout|install|clean|delete|copy|export|import]", "list and manage the cards you've synced"),
    "saves": ("stash|apply [CARD] [--retroarch DIR], manage", "copy RetroArch saves and states off a card, or onto one (Android: over adb), or tidy the stashes"),
    "devices": ("[ID]", "list the supported devices, or one device's systems"),
    "layouts": ("[ID]", "list the firmware card layouts, or one layout's folders and devices"),
    "upload": ("[DIR]", "upload ROMs to the storage folder of a system you pick"),
    "diff": ("[DIR]", "list the ROMs in only DIR or only storage, ignoring renames"),
    "scrape": ("[SYSTEM | match SYSTEM ROM GAME | review [SYSTEM] | missing [SYSTEM] | art [SYSTEM] | clean]", "scrape the ROMs that have no metadata from ScreenScraper into storage's scrapes/ folder"),
    "refresh": ("", "after changing storage: update the cache, scrape every missing ROM, clean the scrapes, make the box art"),
    "playlist": ("[DIR]", "create or fix the .m3u playlist of every multi-disc game"),
    "prepare": ("[DIR]", "unzip archives and convert disc images to verified .chd"),
    "install": ("", "brew install the 7z, unar and chdman that `prepare` needs"),
    "mirror": ("[DIR] | use DIR | clear", "make or refresh a local copy of everything your lists reference"),
    "cache": ("[update [--full]]", "show the storage cache every command reads file lists and sizes from, or update it"),
    "config": ("show|path|set NAME VALUE|unset NAME|import [CARD]|apply [CARD]", "show the effective settings and where each comes from, or change one"),
    "guide": ("", "open the device setup guide (steps to finish a device by hand) in a browser"),
    "doctor": ("", "check the AWS profile, storage access, tools and your data files"),
    "check": ("", "validate cards.json, surprises.json, the device overlay, the sets and your collections"),
    "completion": ("bash|zsh|fish", "print a shell completion script"),
}

TOPICS = {
    "sync": """
  sync-roms [sync] [CARD] [--dry-run] [--ask] [--yes] [--device ID|full] [--layout NAME]
      [--no-delete] [--no-clean] [--no-eject]

  CARD is the card or folder root (default: the current directory); the chosen firmware decides the
  folders inside it (ES-DE ROMs/ BIOS/, Knulli roms/ bios/, Onion Roms/ BIOS/). Missing folders are
  created after you confirm.

  FLOW
   1. Pick a device (its recommended systems come from device-systems.json plus your overlay) or
      Full, then its firmware. Remembered per card folder name and used without asking next time;
      --ask confirms it first. --device/--layout set it without the picker (and save it).
   2. Interactively, you pick which of the card's surprises to keep, then the card editor opens,
      showing the card's size and how much isn't on it yet as you add games and collections;
      otherwise every surprise is replaced. Then, with Surprise on, the empty slots are filled.
   3. Every system with games picked on the card is synced. The totals to download are shown: ROMs,
      BIOS, scraped data and, where the card gets them, Android APKs, bezels, GPU drivers and Onion
      themes.
   4. Card files spelled differently from storage are renamed, and unwanted ones that match a
      missing file are moved to its place. Local ROMs no longer in a system's list, in a system with
      no games listed, or in a system the card's device no longer lists, are listed and, after you
      confirm (default no), deleted first so the free space shown is accurate. Then free space is
      shown and you confirm the download.
   5. ROMs download, then BIOS: BIOS for every system with ROMs on the card is installed, games
      picked or not. Then what the card's layout gets: Android APKs, bezels, GPU drivers (old ones
      are removed), PICO-8, the Onion Surprise app, RAOfflineProxy and Onion themes.
   6. Scraped data for the card's games is installed from storage's scrapes/ folder, then media on
      the card for ROMs it doesn't have is removed, in every system's folder, synced or not.
   7. Onion, Allium and Spruce system folders left with no ROMs and nothing else are removed, synced
      or not. The card's collections and their art are written, a Spruce card gets the newest
      spruceOS 7z, and last the card is ejected.

  --dry-run   show what would be downloaded and deleted, change nothing
  --yes       answer every prompt with its default (a default-no prompt, like deleting files, stays
              no)
  --no-delete never delete anything from the card: ROMs no longer in the lists, their media, old
              drivers, retired collections and their art, and empty system folders are listed as
              kept and the delete prompt is skipped (for adding games to a card someone set up by
              hand)
  --guest     make CARD a guest card (saved; F in the card editor turns it off): its picks are
              seeded from the storage ROMs on it, only ROMs, BIOS and scrapes are copied, no file on
              it is overwritten, and only the seeded ROMs you deselect are deleted, with their media
  --no-clean  skip the end-of-run card tidy (.metadata_never_index, .fseventsd, ._ files)
  --no-eject  leave the card mounted (by default a Mac unmounts all of its volumes after a run with
              no failures; "eject": false in settings.json turns that off for every run)

  A run that wrote to the card (not --dry-run) creates .metadata_never_index in CARD, empties its
  .fseventsd, and on a Mac deletes its ._ files (and offers sudo mdutil to turn Spotlight off, which
  asks for your password).
""",
    "games": """
  sync-roms games list --card NAME [--json]
  sync-roms games add SYSTEM KEY... --card NAME [-n]
      KEY: file name, SYSTEM/file key, or a glob like 'Mario*'
  sync-roms games remove SYSTEM KEY... --card NAME [-n]
  sync-roms games full SYSTEM on|off --card NAME [-n]
  sync-roms games sets list | add ID | remove ID --card NAME [-n]
  sync-roms games export --card NAME        one SYSTEM/file per line (full systems as 'SYSTEM/*'),
                                            then '@collections ID', '@frontend_collections NAME',
                                            '@drivers NAME', '@pico8 ZIP', '@surprise true|false'
                                            (only when it differs from the layout's default: on for
                                            esde/knulli/rocknix/emudeck/muos/nextui/onion/spruce,
                                            off for allium) and '@surprises SYSTEM/file' lines
  sync-roms games import FILE --card NAME [-n]
      add the games in such a file (- reads it from standard input); '@' lines replace the card's
      collections / frontend_collections / drivers / surprises and set pico8, and set Surprise on or
      off

  --card NAME is required: a card's games are saved in ~/.sync-roms/cards.json with the previous
  version kept as .bak. Removing only drops a game from the list. In the editor: / filters, Space
  toggles a row, a all/none shown, u reverts the list, o cycles all/on/changed, f toggles a full
  system, S opens the settings menu (Surprise, theme, collections, RAOfflineProxy); in a system's
  games, s lists its sets and Space there picks (or unpicks) a set's games. ? in any list shows all
  its keys.
""",
    "sets": """
  sync-roms sets edit                         edit the sets in storage (games, categories, new and
                                              deleted sets), then save them

  The sets are shared by everyone using this storage: each set is storage's sets/<id>.json. Saving
  writes the new and changed sets there and deletes the deleted ones; nothing else in storage or
  ~/.sync-roms changes. Pick a set to switch games off, add games from a system or from another set
  across its systems (you're asked for a category), change a game's category or rename it. ➕ New set
  creates one; d deletes the highlighted one. Esc reviews the changes before they're saved.
""",
    "collections": """
  sync-roms collections edit                  edit your collections of favourite games

  Your own lists of games (like a set, but personal), saved to ~/.sync-roms/collections/<id>.json
  after Done or Esc shows the changes; Quit discards. No git or gh needed, and nothing goes to
  storage or the repo. Same keys as the set editor. Deleting a collection that cards use asks first,
  then removes it from them (the file is kept as <id>.json.bak). In a card's system list, l adds a
  collection to that card. Theme art picks the picture (Action, RPG, ...) the collection gets on
  ES-DE, Knulli and ROCKNIX cards that use Art Book Next.
""",
    "themes": """
  sync-roms themes update [--dry-run]         put the latest Art Book Next for ES-DE and the PyUI
                                              themes in storage

  Downloads the GitHub archive of the theme's latest commit (about 200 MB) and replaces
  os/esde/themes/ in storage (write profile). Syncs copy it from there onto ES-DE cards that use Art
  Book Next, so the Surprise collection has its art; a card's copy is replaced when storage has a
  newer commit. Does nothing when storage already has the latest. It also refreshes the PyUI themes
  for spruce in os/spruceos/themes/ (the spruceUI/PyUI-Themes release, unpacked with 7z; folders you
  add there yourself are left alone).

  sync-roms themes pick                       choose the PyUI themes every spruce card gets by
                                              default (saved as spruce_themes)

  sync-roms themes build [STYLE...] [--palette NAME (repeatable) | --all-palettes] [--out DIR]
      build custom spruce themes

  Builds each named custom theme style (Pixel Consoles, Pixel Controllers, ToTK - James; all of them
  without names). Pixel Consoles and Pixel Controllers are built in each chosen palette: --palette
  NAME, repeatable, or --all-palettes for all 28 (Gruvbox, Arcade, Candy, ..., Monochrome). Without
  either, a terminal shows the palette picker (each palette's six colors as a bar, and a preview
  where the terminal draws images), starting from the saved selection; Enter saves the palettes on
  as custom_theme_palettes and builds them, Esc builds nothing. With --yes or no terminal the saved
  palettes are built (none saved: exit 2). The flags never change the saved palettes. Each theme is
  named "<style> - <palette>", e.g. "Pixel Consoles - Gruvbox", and goes into the cache's
  themes/build/ folder, or into DIR/<theme> with --out (replaced); the folders are printed. The base
  theme is read from os/spruceos/themes/SPRUCE/ in storage, so run `sync-roms themes update` first
  (ToTK - James has no palette: it is built once, as "ToTK - James", from os/spruceos/themes/ToTK/,
  and asks for none when it is the only style named). Nothing is written to storage.

  sync-roms themes palettes                   write the overview image of all the palettes and open
                                              it

  Draws one small list screen per palette, numbered, from the palette data, into the cache's
  themes/palettes.png (the path is printed) and opens it in the default viewer. The picker of themes
  build/publish shows the same panels as its previews.

  sync-roms themes publish [STYLE...] [--palette NAME (repeatable) | --all-palettes] [--dry-run]
          [--yes]
      put them in storage

  Builds as above (the palettes chosen the same way; a choice made in the picker is saved even with
  --dry-run), then makes each theme's os/spruceos/themes/<theme>/ match the build (write profile):
  uploads the files whose content changed and deletes the files the build no longer makes, after one
  confirmation. Only the themes built this run are touched: other palettes' folders stay as they
  are, and so do the folders of the earlier single-palette themes (Pixel Consoles, Pixel
  Controllers), which are never adopted. Each file's hash is kept in os/spruceos/custom-themes.json,
  so an unchanged rebuild uploads nothing and a failed upload is retried next time. A custom theme's
  name is reserved: an existing folder of that name is adopted (every file uploaded, the others
  deleted), except a theme `themes update` downloaded, which is left alone (exit code 1).
  `themes pick` and sync then treat it like any other theme. Other machines see custom themes a
  publish added or removed after `sync-roms cache update`.
""",
    "download": """
  sync-roms download pico8 [--count N] [--dry-run] [--yes]
      add the BBS Featured carts to storage's pico8/

  Reads every page of the Lexaloffle BBS Featured PICO-8 listing (--count N: stops after N carts to
  add or upgrade), lists the carts storage doesn't have and those the BBS has a newer revision of,
  and asks once (write profile; without a terminal it needs --yes). Each cart goes to
  pico8/<BBS file name> with its title and author in scrapes/pico8/metadata.json. An upgrade
  removes the old revision, moves its metadata and scraped media to the new name and points your
  cards, Surprise history and collections at it; sets that name the old file are listed to change
  with sets edit. Carts in ignored.json are skipped.
  Requests go one at a time; the first HTTP error stops it, keeping what was added.
""",
    "ports": """
  sync-roms ports search [TEXT...] [--needs-data | --ready] [--refresh] [-n] [-y]
      find ports in PortMaster's catalogue and pick ones to download
  sync-roms ports download [ZIP...] [--update] [--refresh] [--dry-run]
      put PortMaster ports in storage's ports/

  search lists the aarch64 ports whose title, zip name, genres or description hold every word of
  TEXT, one row each (title, zip, genres, size; "needs game data" for a port you must add files
  to, "in storage" for one storage has). --needs-data keeps only the ports that need game data,
  --ready only the ready-to-run ones. With a terminal (and without --yes) you pick ports with the
  space bar and the ones storage lacks are downloaded as `ports download` does; otherwise the rows
  are only printed. Both end by listing ports in storage that have a newer version.

  Each ZIP is a port's zip name in PortMaster's catalogue (celeste.zip, or just celeste; only ports
  that run on aarch64). Its zip goes to ports/<zip>, each runtime it needs that storage lacks to
  os/portmaster/runtimes/, and its title and facts to scrapes/ports/metadata.json, all checked
  against the catalogue's md5 (write profile). A zip storage has is skipped; --update replaces it
  when the catalogue has a newer version, and --update with no ZIP updates every such port. An
  unknown name, a failed download or an md5 mismatch is warned about and the rest go on (exit 1).
  The catalogue is cached for a day; --refresh fetches it again.
""",
    "flash": """
  sync-roms flash [--dry-run]                 write a Knulli, BaseOS, muOS, ROCKNIX or OakMoss image
                                              to an SD card (macOS only)

  Pick a firmware (only when storage's os/ has images of more than one: Knulli or BaseOS, muOS,
  ROCKNIX, OakMoss), then a device, then an image from storage's os/knulli/knulli-*.img.gz or
  os/baseos/baseos-*.img.zip (the ones matching the device first, newest first),
  os/muos/muos-*.img.gz (muOS image names aren't documented, so they are never matched) or
  os/rocknix/ROCKNIX-*.img.gz (not the update .tar files; matched by the device's SoC image, H700
  devices matching both DDR3 and DDR4: pick the one for your device's RAM) or
  os/oakmoss/oakmoss-*.img.xz (not the .omupd files; matched by the device name in the file), then
  an external SD card (shown with its volume names); the boot disk and the disks holding the temp
  folder or storage are never offered, and flash stops if it can't tell which disks those are. Type
  the disk id (disk4) to confirm: --yes never skips that. --dry-run stops there. The image is copied
  to a local temp folder (free space is checked first); right before writing, the card must still be
  the same disk (id, size and name). Then `sudo dd` writes it, decompressed (gz, xz or zip) on the
  fly, with 4 MiB blocks (sudo may ask for your password before downloading and writing). Last, the
  temp folder is removed and the card is ejected; after a failure it is unmounted instead, so you
  can retry.
""",
    "format": """
  sync-roms format [--dry-run]                erase an SD card as exFAT or FAT32 (macOS only)

  Pick an external SD card (shown with its volume names; the boot disk and the disk holding storage
  are never offered), a filesystem (exFAT or FAT32), then a label: your card names, then the layout
  names uppercased, or type your own. FAT32 labels are uppercase, at most 11 characters; exFAT at
  most 15; longer ones are left out of the list, and a typed one with characters the filesystem
  doesn't allow is asked again. Type the disk id (disk4) to confirm: --yes never skips that.
  --dry-run stops there and shows the command. Right before erasing, the card must still be the
  same disk (id, size and name). Then `sudo diskutil eraseDisk <FS> <LABEL> MBR <disk>` erases it
  (sudo may ask for your password). The card is left mounted.
""",
    "unmount": """
  sync-roms unmount [--dry-run]                clean the macOS junk off an SD card and unmount it
                                               (macOS only)

  Lists the mounted external SD cards (disk id, size, name and volume names; never the disk holding
  storage), then runs the end-of-sync tidy on each volume of the one you pick:
  .metadata_never_index, .fseventsd/no_log and the ._ files macOS leaves, plus the sudo mdutil offer
  when Spotlight is on. Ctrl-C skips the rest of that volume's tidy. Last, `diskutil unmountDisk`
  unmounts the card.
""",
    "mount": """
  sync-roms mount [--dry-run]                 mount again an SD card that was unmounted but not
                                              pulled out (macOS only)

  Lists the external SD cards with no volume mounted (never the disk holding storage), then runs
  `diskutil mountDisk` on the one you pick, so you don't have to pull it out and put it back after
  unmount or a sync. An ejected card (as flash leaves it) is gone from the list: that one has to be
  put back in.
""",
    "edit": """
  sync-roms edit                              main menu: Cards, Sets (saved to storage),
                                              Collections, Device systems

  ? in any list shows all its keys. In a card's system list: Enter opens a system's games, f makes
  it a full system, l picks collections, S opens the settings menu (Surprise, theme, collections,
  RAOfflineProxy), D clears the card. After / in any list, Enter keeps the filter and goes back to
  moving; Esc clears it. Ctrl-C while an editor is busy between two lists ("Working...") stops it
  when that step ends, as Ctrl-C in a list does; another Ctrl-C a second or more later, with the
  step still running, quits at once, and unsaved changes in the open editor are lost.
""",
    "cards": """
  sync-roms cards [list] [--all] [--json]     list is the default; guest cards are hidden unless
                                              --all
  sync-roms cards new NAME --device ID|full --layout NAME [--size 512GB]
  sync-roms cards set NAME [--device ID|full] [--layout NAME] [--size 512GB]
  sync-roms cards rename OLD NEW
  sync-roms cards layout [CARD] --layout NAME [--dry-run] [--yes]
      move the card's ROMs, BIOS and saves to another layout's folders
  sync-roms cards install [CARD] [--dry-run] [--yes]
      put storage's newest spruceOS on a spruce card: a clean install: deletes all but Roms, then
      unpacks it
  sync-roms cards clean [CARD] [--dry-run] [--yes]
      delete the media other layouts' scrapes left in the card's ROM folders
  sync-roms cards delete NAME [--yes]
  sync-roms cards copy SRC DST                merge SRC's games, sets, excluded and collections into
                                              DST (not surprises); skips systems DST can't play
  sync-roms cards export FILE [--yes]         surprises and collections go into the file as plain
                                              games; asks before overwriting FILE (--yes overwrites;
                                              without a terminal it needs --yes)
  sync-roms cards import FILE                 keeps size, device, layout, games and excluded;
                                              Surprise off; r renames, p prefixes all

  CARD (layout, install, clean) is a saved card's name or its mounted folder (default: the
  current directory).

  A card is a folder name (the card root's basename) with a remembered device, firmware and games.
  new, set, rename, delete, copy, export and import take --dry-run (-n): they say what they would do
  and save nothing.
""",
    "saves": """
  sync-roms saves stash [CARD] [--retroarch DIR] [--dry-run]
      copy picked saves and states off the card
  sync-roms saves apply [CARD] [--retroarch DIR] [--dry-run]
      copy picked stashed ones onto the card
  sync-roms saves manage [--dry-run] [--yes]
      inspect, label, move, prune and delete stashes

  CARD is the card's mounted folder (default: the current directory); it needs a layout
  (`sync-roms cards set NAME --layout`). An Android card (esde, not windows-pc) is reached
  over wireless adb instead: CARD is its name, or with no CARD (and the current folder isn't a card)
  a device is picked from those adb sees, the last row walking through pairing a new one (Wireless
  debugging). It needs adb (brew install android-platform-tools). The card's SD card is remembered
  (android_volume) so it's found in any device. RetroArch must be closed on the device (it asks you
  to, then checks again); its save and state folders are read from its retroarch.cfg. apply copies
  onto a temp copy, then pushes the files it wrote; --dry-run never writes to the device. A name of
  another layout's card fails: pass its mounted folder. stash lists the card's games that have
  RetroArch saves (.srm and .rtc) or states (.state, .stateN, .state.auto and their .png), then
  their files, and copies them to ~/.sync-roms/saves/<system>/<game>/<time>-<card>/ (with
  stash.json). On layouts sorted by core and flat folders a save whose game isn't on the card is
  skipped; on Knulli and ROCKNIX the folder gives the system (on ROCKNIX, where saves sit beside the
  ROMs, a save or state whose game isn't in the system's ROM folder is skipped too). apply lists the
  stashes of systems the card syncs (one per game, with each one's label from `saves manage`) and
  copies them into the card's RetroArch folders. A different file already there is only overwritten
  after you confirm (default yes); identical ones are skipped. A stash without a core going to a
  layout sorted by core asks which core folder to use (skipped with --yes). manage lists every stash
  (unreadable ones too, which can only be inspected and deleted). Space picks; m and d act on the
  picked stashes, else the highlighted one. Enter lists a stash's files, w labels it, m moves it to
  another system (its game never changes), p picks all but the newest N of each game, d deletes
  after you confirm (default no; it can't be undone; --yes skips the question). --dry-run changes
  nothing and says what it would do.

  Layout    RetroArch folder             saves            states
  esde      RetroArch                    saves/<core>     states/<core>
  knulli    saves                        <system folder>  <system folder>
  rocknix   roms (beside the ROMs)       <system folder>  savestates/<system folder>
  onion     Saves/CurrentProfile         saves/<core>     states/<core>
  allium    Saves/CurrentProfile         saves/<core>     states/<core>
  spruce    Saves                        saves/<core>     states/<core>
  muos      MUOS/pickles                 sram/<core>      state/<core>
                                                          (Pickles, not RetroArch)
  emudeck   Emulation/saves/retroarch    saves            states
  nextui    (card root)                  Saves/<TAG>      .userdata/shared/<TAG>-<core>
                                                          (MinUI .sav naming)

  --retroarch DIR   read or write that folder instead of a mounted card's RetroArch folder (not over
                    adb): the real folder EmuDeck's symlinks point to, or a copy of an Android
                    device's RetroArch folder.

  nextui: apply renames saves to MinUI's Game.gba.sav (from the card's ROM; PlayStation and saves
  with no ROM there keep their name), stash turns .sav back into .srm. States are stashed and
  applied as they are, so NextUI's own state names aren't converted.

  muos: the saves and states are Pickles' own, copied as they are; --retroarch is ignored (with a
  warning), and a Pickles stash is only applied to a muOS card, which takes no other stash.

  States only load in the core they were made with; .srm (and .rtc) saves usually work in any core
  of the system.
""",
    "devices": """
  sync-roms devices [ID] [--json]

  Without an ID: every device with its chip and system count. With one: its firmwares, note and
  systems.
""",
    "layouts": """
  sync-roms layouts [ID] [--json]

  Without an ID: every firmware layout with its ROMs and BIOS folders and how many devices run it.
  With one: its folders, note and the devices that run it (marked where it's their default
  firmware).
""",
    "upload": """
  sync-roms upload [DIR] [--replace] [--dry-run]    upload the ROMs in DIR (default: current
                                                    directory) to storage folder of a system you
                                                    pick

  It first runs `prepare` on DIR (so archives are unzipped and disc images converted to .chd before
  they go up; it prints nothing when no folder there converts).
  The system is guessed from the folder name; same-size files are skipped, a different size
  overwrites after you confirm.
  --replace makes the storage folder match DIR: renamed files are moved by content (big bucket files
  without an MD5 are compared on samples, and those renames are marked), and left-over storage files
  are listed so you tick which to delete (none are ticked at first). Uploads use the write profile
  (ROMS_WRITE_PROFILE, default 'roms').
  After files were uploaded it runs `scrape SYSTEM --all` and `scrape art SYSTEM --for both` for the
  system (a failure there only warns), so a following `refresh` has nothing to do.
""",
    "diff": """
  sync-roms diff [DIR] [--system ID] [--json]

  Lists the ROMs in only one of DIR and storage folder of a system you pick. Same path and size is
  the same file; the rest are matched by content (the CRCs inside zips, the bytes of other files, as
  upload --replace does). It only reads, so --dry-run is refused.
  --system ID   compare with that storage folder instead of picking one
  --json        print the result as one JSON document (needs --system unless DIR is named after a
                system)
""",
    "scrape": """
  sync-roms scrape [SYSTEM | --system ID] [--all] [--retry] [--fill-media] [--skip-media TYPES]
      [--dry-run]
  sync-roms scrape match SYSTEM ROM GAME_ID_OR_NAME [--skip-media TYPES] [--translated] [--dry-run]
  sync-roms scrape review [SYSTEM]
  sync-roms scrape missing [SYSTEM | --system ID] [--all]
  sync-roms scrape art [SYSTEM | --system ID] [--for onion|spruce|both] [--dry-run] [--replace]
      [--workers N]
  sync-roms scrape clean [--dry-run]
  sync-roms scrape --set-credentials

  Looks up every available ROM with no entry in scrapes/<system>/metadata.json on ScreenScraper and
  writes its metadata and media (and the Onion images) to storage; pico8 carts with an entry but no
  scraped picture are taken too (their BBS title and author are kept). The ROMs and how each will be
  looked up are listed first, then the most requests the run can make against what is left of
  today's quota. ROMs ScreenScraper doesn't know are remembered and skipped until --retry. Each
  batch of ROMs shows today's requests and the time elapsed and left; each ROM gets a line as it
  ends (the game it matched, how, and its media count).
  SYSTEM             only that storage folder (e.g. gba); --system ID is the same
  --retry            also look up the ROMs ScreenScraper didn't know before (ROMs whose lookup
                     failed are always tried again; non-games never are: see review) and, with
                     --fill-media, the media it didn't offer
  --all              every ROM in the storage, not just those your cards list (games, sets, full
                     systems)
  --fill-media       also scrape ROMs that have metadata but lack some media type in storage; their
                     existing metadata is kept. Types ScreenScraper didn't offer for a ROM are
                     remembered and not asked for again until --retry
  --skip-media TYPES comma-separated media folders not to download (covers, 3dboxes, backcovers,
                     fanart, manuals, marquees, ...); other values are refused with the list
  --dry-run          list the ROMs and the metadata and media folders that would be written; no
                     ScreenScraper credentials or requests (scrape match --dry-run needs credentials
                     and searches when given a name; a game id is not checked)
  match              say which ScreenScraper game a ROM is (a game id, or a name to search and pick
                     from), then scrape it; for a ROM that already has metadata it asks before
                     replacing the entry and deleting its old media. --translated: the ROM is a fan
                     translation: title '<name> - Translated'; an ignored ROM is taken off
                     ignored.json first. Without a terminal it needs --yes
  review             go through the ROMs ScreenScraper calls non-games or doesn't know, each with
                     its position (3 of 120): i ignore, s search under another name and scrape the
                     game picked, t search like s and scrape the pick as a fan translation, k keep
                     for later (listed after the others next time), b take back the last ignore, q
                     quit, I ignore all the rest
  missing            list every ROM with no metadata and why (non-game, not on ScreenScraper,
                     matched but not scraped, not looked up yet); nothing is looked up. --all: every
                     ROM in the storage
  art                make the Onion (PNG) and Spruce (QOI, up to three sizes) box art for the ROMs
                     that have a cover or miximage in storage (a PICO-8 cart is its own picture),
                     from the cover, else the miximage; files that exist are kept. --for picks
                     Onion, Spruce or both (default). --dry-run lists what would be made with an
                     estimated size and reads no image; --replace remakes existing files; --workers
                     N bounds the parallel downloads (default: your CPU count). Spruce art needs
                     Pillow
  clean              remove scrapes/ media and metadata for ROMs that aren't in storage at all (asks
                     first; --yes deletes without asking)
  --set-credentials  ask for your ScreenScraper username and password (saved in settings.json,
                     readable only by you; blank keeps the current value), then check them with one
                     request and show today's quota and threads, or the error (exit 1 when
                     ScreenScraper refuses them)
  A rate-limited request, a server error (HTTP 5xx) or a network failure is tried 3 more times,
  waiting 10, 20 and 40 seconds. The run stops cleanly, keeping what it finished, when
  ScreenScraper's daily quota runs out (run it again tomorrow), when ScreenScraper refuses the
  login, is closed or no longer accepts this version (the message says what to do), or when 3 ROMs
  in a row can't reach it. Ctrl-C stops it too: the ROMs that finished are uploaded and saved, it
  says how many were saved and how many are left, and it exits 130 (a second Ctrl-C aborts at once).
  Writes use the write profile.
""",
    "playlist": """
  sync-roms playlist [DIR] [--dry-run]

  Creates or fixes the .m3u of every multi-disc game ("Name (Disc 1).chd", "Name (Disc 2).chd") in
  DIR and its subfolders. Playlists whose files are all missing are deleted (asks first). Local
  only.
""",
    "prepare": """
  sync-roms prepare [DIR] [--dry-run] [--yes]

  Unzips (7z, or unar for .rar) every .zip/.7z/.rar, and the archives inside them, and converts each
  disc image (.cue, .gdi, .toc, .iso) to a verified .chd (Xbox .iso to xiso, Xbox 360 .iso to .zar),
  per the `chd` key in systems.json of the system whose folder it is in. Archives and images are
  removed once their chd verifies, then the .m3u playlists are fixed. It unpacks archives
  in the system temp folder when it is on another drive with room, else beside themselves; as many
  files convert at once as there are CPU cores and free space for, biggest first. The progress bar
  goes by size, with the rate and time left, and each file's result shows as it finishes. Before it
  starts it asks to convert N files and remove the originals (default yes; --yes goes ahead, no
  terminal exits 2). Inside a saved card's folder it first warns that the next sync downloads the
  archives again and asks (default no, so --yes or no terminal stops it). Inside the storage folder,
  once a file converts, it ends by saying to run `sync-roms cache update`. Needs 7z, chdman and, for
  Xbox, extract-xiso and, for Xbox 360, iso2zar (see `install`).
""",
    "install": """
  sync-roms install

  brew install the 7z (sevenzip), unar and chdman (rom-tools) that `prepare` needs, and say how to
  build extract-xiso and iso2zar. `doctor --fix` runs it when one of those three is missing.
""",
    "mirror": """
  sync-roms mirror [DIR] [--dry-run]     make or refresh a local copy of everything the lists
                                         reference (no DIR: the saved mirror)
  sync-roms mirror use DIR               refresh DIR, then save it so every sync refreshes it first
                                         and copies from it
  sync-roms mirror clear                 forget the saved mirror (its files stay)

  Files no longer referenced are deleted (after confirming when it is a lot).
""",
    "config": """
  sync-roms config show                 the effective bucket, endpoint, profiles and mirror, and
                                        where each came from; other saved settings follow (accounts
                                        and passwords as `(set, not shown)`)
  sync-roms config path                 the data folder
  sync-roms config set NAME VALUE       save one setting in settings.json
  sync-roms config unset NAME           remove it (back to its default)
  sync-roms config import [CARD]        save a card's own settings (spruceOS or Knulli
                                        preferences) in settings.json
  sync-roms config apply [CARD] [--dry-run] [--yes]   apply the saved settings to a spruce or Knulli
                                                      card or an Android device

  NAME is bucket, root, endpoint, profile, write_profile, mirror, screenscraper_user or
  screenscraper_password (text), eject, storage_cache_declined or syncthing (true or false),
  surprise_ttl_days (a positive number of days) or surprise_excluded_systems (comma-separated system
  ids, e.g. gba,snes). root and mirror must be absolute paths (~ is expanded). The password is saved
  but never printed; `scrape --set-credentials` asks for it without echoing it.

  ra_mode (Manual, Disabled, Casual, Softcore or Hardcore), ra_username, ra_password and ra_api_key
  (text, the last two never printed), ra_offline_proxy and ra_proxy_stats (true or false): the
  RetroAchievements settings written into a spruce card or an Android device's
  Saves/spruce/spruce-config.json. Set them with `config set`; `config import` doesn't read them
  from the card.

  config import takes CARD (a card name from cards.json, found at /Volumes/<name>, or the card's
  folder; default the current folder) and picks what to import from the card's saved layout (spruce
  or Knulli). For a spruce card it copies the current values of the spruceOS settings that are
  your preferences (emulator, in-game menu, button, boot and network options; not hardware, LED,
  battery, audio or proxy ones) from Saves/spruce/spruce-config.json into settings.json's
  spruce_settings, merged with what is there. It lists the settings identical to the saved ones and
  those that differ or are new, then asks Yes (all of them), No or Pick (one by one); no answer is
  assumed, and with no terminal input nothing is saved. Every sync of a spruce card then sets those
  that the card's file already has. spruce_settings isn't a `config set` name: import it, or edit
  settings.json by hand ({"section": {"key": value}}, values as the card holds them).

  For a Knulli card it copies the allowlisted preferences (shaders, scaling, rewind, autosave, quick
  resume, the RetroAchievements display options, language and timezone) from system/knulli.conf into
  settings.json's knulli_settings. knulli_settings isn't a config set name: import it, or edit
  settings.json by hand ({"key": "value"}).

  config apply sets the saved settings without a sync. A mounted spruce card (CARD as for import)
  gets the spruceOS settings, WiFi networks and Syncthing settings a sync writes. A mounted Knulli
  card gets the RetroAchievements login, WiFi networks, hotkey scheme and knulli_settings in
  system/knulli.conf. An Android device
  over adb (CARD naming an Android card, or none to pick the device) gets RetroArch's and ES-DE's
  settings (RetroArch Cloud Sync turned off, its overlay folder pointed at the card's
  Bezels/retroarch when storage has bezels for the device) and its APKs installed or upgraded,
  except those that don't fit the device.
  --dry-run lists every setting, changed or not; --yes skips the questions.
""",
    "cache": """
  sync-roms cache [update [--full]]

  Every command reads what storage holds (file names, sizes and, for a bucket, ETags) from a cache
  in ~/.sync-roms/cache/storage-cache.json; only the files themselves are downloaded from storage.
  Nothing refreshes it on its own: sync-roms's own uploads, moves and deletes keep it up to date,
  and after changing storage any other way run `sync-roms cache update`.

  cache          where the cache was read from, when it was last updated, and its files and size per
                 folder
  cache update   read storage again: one listing of a bucket, or a walk of a folder that lists only
                 subfolders whose modification time changed and stats only files the cache doesn't
                 have; the rest keep their cached files and sizes. This relies on storage changing a
                 folder's modification time when a file is added, removed or renamed in it; a change
                 made in the last few minutes is picked up on the following update
  --full         in a folder, list every subfolder and stat every file: covers files replaced under
                 the same name and anything a folder's modification time didn't show (a bucket
                 listing is the same either way)

  With no cache for the storage in use, the first command that reads storage offers to build it.
  Saying no is remembered (storage_cache_declined in settings.json), and commands then list storage
  each run.
""",
    "refresh": """
  sync-roms refresh

  Runs, in order, stopping at the first that fails:
    sync-roms cache update
    sync-roms scrape --all --yes
    sync-roms scrape clean --yes
    sync-roms scrape art --for both
""",
    "doctor": """
  sync-roms doctor

  Checks the AWS profile and storage access, the tools `prepare` needs, and that your data files
  parse.
""",
    "guide": """
  sync-roms guide

  Opens the device setup guide in your browser: the apps to install and the frontend, RetroArch and
  emulator settings to change after a card is synced. Pick a device and layout at the top of the
  page.
""",
    "check": """
  sync-roms check [--bucket-keys]

  Validates cards.json, surprises.json, device-systems.json, the sets in storage and your
  collections: bad JSON, unknown systems, devices, sets and art. Exits 1 if anything is wrong. Sets
  with no art of their own, or sharing art, are noted without failing.
  --bucket-keys also reports every game or set file storage doesn't have (read-only profile). It
                goes by the storage cache: run `sync-roms cache update` first, since a stale cache
                reports files that are there.
""",
    "completion": """
  sync-roms completion bash|zsh|fish
  sync-roms completion list cards|systems|devices|layouts

  Prints a completion script, e.g.  sync-roms completion zsh > ~/.zfunc/_sync-roms
  list prints those names one per line (the scripts call it; handy for --card, --system, --device
  and --layout).
""",
}


HELP_WIDTH = 100


def _fill(text, indent):
    """text broken into lines that fit HELP_WIDTH once indented by indent (a `backticked` span stays whole)."""
    lines, cur = [], ""
    for word in re.findall(r"(?:`[^`]*`|\S)+", text):
        if cur and indent + len(cur) + 1 + len(word) > HELP_WIDTH:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + [cur]


def _row(name, usage, summary):
    """A command's two help rows (its name and usage, then its summary), wrapped under the usage and at 6."""
    pad = 20 + len(ui.green(""))
    usage_lines = [ui.cyan(line) for line in _fill(usage, 23)] if usage else [""]
    lines = [f"  {ui.green(name):<{pad}} {usage_lines[0]}", *(" " * 23 + line for line in usage_lines[1:])]
    return "\n".join(lines + [" " * 6 + line for line in _fill(summary, 6)])


def help_text(topic=None):
    if topic in TOPICS:
        name = f"🎮 sync-roms {topic}"
        head = _fill(f"{name} — {SUBCOMMANDS[topic][1]}", 3)
        head = "\n   ".join([head[0].replace(name, ui.bold(name), 1), *head[1:]])
        return f"\n{head}\n{TOPICS[topic]}"
    rows = "\n".join(_row(name, usage, summary) for name, (usage, summary) in SUBCOMMANDS.items())
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
  {ui.yellow('-y, --yes')}       answer prompts with their default (deleting stays "no"). In these commands
                  --yes is the confirmation, so they go ahead: `upload` (overwrites), `prepare`
                  (removes the originals), `scrape clean`, `cards clean`, `cards layout` (the old
                  layout's media), `cards install` (the card's other files), `cards delete`,
                  `cards export` (overwrites FILE), `saves manage` (deletes the picked stashes),
                  `themes publish` (stale theme files), `download pico8` (old cart revisions) and
                  `scrape match`. Without a terminal, `upload`, `prepare`, `scrape clean`,
                  `cards install`, `cards export` (over FILE), `themes publish`, `download pico8`
                  and `scrape match` exit 2 unless --yes is given
  {ui.yellow('--quiet')}         print only errors, warnings and --json data (prompts go to stderr)
  {ui.yellow('--verbose')}       also print the effective settings
  {ui.yellow('--json')}          machine-readable output for devices, layouts, diff, games list, cards list and
                  `sync --dry-run` (use --device/--layout to skip the pickers)
  {ui.yellow('--profile P')} {ui.yellow('--write-profile P')} {ui.yellow('--bucket B')} {ui.yellow('--root DIR')} {ui.yellow('--endpoint URL')}
                  override those settings for this run
  {ui.yellow('-a, --ask')}       sync: confirm the saved device/firmware instead of using it silently
  {ui.yellow('--version')}       print the version      {ui.yellow('-h, --help')}   this screen

{ui.bold('ENVIRONMENT')}
  {ui.yellow('ROMS_BUCKET')}  {ui.yellow('ROMS_ROOT')}  {ui.yellow('ROMS_ENDPOINT')}  {ui.yellow('ROMS_PROFILE')} (default roms-readonly)
  {ui.yellow('ROMS_WRITE_PROFILE')} (default roms)
  override settings.json "bucket", "root" (a folder, e.g. a mounted network share, used as storage
  instead of a bucket), "endpoint", "profile", "write_profile"; the flags above override these.
  {ui.yellow('NO_COLOR')} / {ui.yellow('FORCE_COLOR')} control colors.

{ui.bold('EXIT CODES')}
  0 done (or nothing to do, or you declined)   1 some files failed   2 bad usage
  3 setup problem (credentials, bucket, tools, bad data file)   130 interrupted

{ui.bold('EXAMPLES')}
  sync-roms /Volumes/SD                          sync the card
  sync-roms sync /Volumes/SD --device anbernic-rg-35xxsp --layout knulli --yes --dry-run
  sync-roms games add gba 'Metroid*' --card SD   add games to a card
  sync-roms upload ~/roms/gba                    upload ROMs to storage

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


LEAD_FLAGS = {"-n", "--dry-run", "-y", "--yes", "-a", "--ask", "--json"}  # flags that may come before the command


GLOBAL_VALUE_FLAGS = {"--profile": "profile", "--write-profile": "write_profile", "--bucket": "bucket", "--root": "root", "--endpoint": "endpoint"}
DATA_COMMANDS = {("devices",), ("layouts",), ("completion",), ("games", "list"), ("games", "export"), ("cards", "list"), ("config", "path"),
                 ("config", "show"), ("doctor",), ("games", "sets", "list")}


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
    words = tuple(canonical(w) for w in words[:1]) + words[1:]
    if words[:2] == ("games", "set"):
        words = ("games", "sets", *words[2:])
    return words in (("cards",), ("cache",)) or any(words[:len(d)] == d for d in DATA_COMMANDS)


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
    while lead < len(argv) and argv[lead] in LEAD_FLAGS:
        lead += 1
    word = argv[lead] if lead < len(argv) else None
    if word == "--version":
        print(f"sync-roms {__version__}")
        return 0
    if word in ("-h", "--help"):
        topic = canonical(argv[lead + 1]) if lead + 1 < len(argv) else None
        print(help_text(topic if topic in SUBCOMMANDS else None))
        return 0
    if word is not None:
        word = canonical(word)
        argv = argv[:lead] + [word, *argv[lead + 1:]]
    if word not in commands.COMMANDS | {"help"}:  # a card, or nothing: sync it
        if word is not None and not word.startswith("-"):
            commands.check_card(word)
        argv = argv[:lead] + ["sync"] + argv[lead:]
        word = "sync"
    if word in commands.COMMANDS:
        cmd = argv[lead:] + argv[:lead]  # leading global flags go after the command, where its parser reads them
        if "-h" in cmd or "--help" in cmd:
            print(help_text(cmd[0]))
            return 0
        return commands.run(cmd)
    name = argv[lead + 1] if lead + 1 < len(argv) else None  # `help [COMMAND]`
    if name is not None:
        name = canonical(name)
    if name is not None and name not in SUBCOMMANDS:
        ui.fail(f"No help for {name!r}: it isn't a command. See `sync-roms help` for the commands.", 2)
    print(help_text(name))
    return 0


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


def remove_samples(paths):
    """Delete spruceOS's sample files from the card, and a folder that held only them."""
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            ui.failure(ui.red(f"  ❌ {path}: {e}"))
        try:
            if os.path.basename(os.path.dirname(path)) == "licenses":
                os.rmdir(os.path.dirname(path))
        except OSError:  # not empty
            pass
    if paths:
        print(ui.dim(f"  🧹 Removed {len(paths)} spruceOS sample file(s)"))


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
    damaged = [reason for _, reason in failures if reason.endswith(downloads.DAMAGED_HINT)]
    if damaged:
        ui.failure(ui.dim(f"   {damaged_advice(damaged[0])}"))
    if all(reason.endswith(downloads.STALE_HINT) for _, reason in failures):
        ui.failure(ui.dim(f"   These are gone from storage since the cache was built: run {inventory.UPDATE_HINT}, then sync again."))
    elif len(damaged) < len(failures):
        ui.failure(ui.dim("   Files already downloaded are skipped, so run the same command again to retry just these."))


def damaged_advice(reason):
    """What to do about a damaged card file system, from a DAMAGED_HINT failure reason (str of the OSError, so the
    damaged path is its quoted filename)."""
    m = re.search(r"Invalid argument: ('.*'|\".*\")" + re.escape(downloads.DAMAGED_HINT) + "$", reason)
    path = ast.literal_eval(m.group(1)) if m else None
    device = path and clean.volume_device(path)
    if not device:
        return "The card's file system is damaged: check it (First Aid, chkdsk or fsck), then sync again."
    return (f"The card's file system is damaged: close anything using the card, run diskutil repairVolume {device} (it "
            f"unmounts the card while it works), then sync again. If that doesn't fix it, delete {path} and sync again.")


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
    print("📄 Reading the card's games list...")
    card = os.path.basename(base) or base
    mirrored_theme = spruce_themes.current(card)  # the card's theme when the mirror was refreshed
    manifest = store.load_manifest([card])
    systems, layouts = manifest["systems"], manifest["layouts"]
    if not any(s["games"] or s.get("full_system") for s in systems):
        print(ui.dim(f"  {card} has no games picked: add some with `sync-roms edit`"))
    old_list = os.path.join(store.data_dir(), "games.json")  # the core list from before cards had their own games
    if os.path.exists(old_list) and store.personal_json("games.json"):
        ui.warn(f"{old_list} is no longer read; pick its games for {card} in 'sync-roms edit'.")
    cards = store.load_cards()
    saved = store.saved_card(card, cards)
    chosen_setup = choose_card_setup(args, base, card, manifest, cards.get(card))
    if chosen_setup is None:
        return 0
    device, layout_name, dirs = chosen_setup
    if args.guest and not args.dry_run:
        store.update_card(card, guest=True)
    # a friend's card: only ROMs, BIOS and scrapes are copied, and only the ROMs deselected this session are deleted.
    # Stays a guest sync for this run even when the card editor turns the flag off
    guest = args.guest or guests.is_guest(store.saved_card(card))
    layout = layouts[layout_name]
    disc_dir = layout.get("disc_dir")  # multi-disc games' discs go in this hidden folder, their playlist beside it (Onion)
    disc_folders = layout.get("disc_folders")  # each disc game goes in a folder of its own (NextUI)
    onion = layout_name in scrape_plan.ONION_LAYOUTS
    roms_dir, bios_dir = dirs
    if layout_name == "nextui" and not guest:  # folders an earlier sync named differently from NextUI move rather than download again
        for old, new in nextui_folders.migrate(roms_dir, args.dry_run):
            print(ui.dim(f"  📦 {'would rename' if args.dry_run else 'Renamed'} {old} → {new}"))
            if args.dry_run:  # plan the card as the real run will find it, with the folder already renamed
                cardfs.alias(os.path.join(roms_dir, new), os.path.join(roms_dir, old))
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
    if guest:  # nothing on a friend's card is unwanted for being in a system the device doesn't list
        dropped = []
    systems = synced(systems)
    if layout_name == "spruce" and not guest:  # the folders an earlier sync used for a system that now uses another: all of it is unwanted
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
    def reload_changes(stale=()):
        """Pick up the card's games as saved now: refresh the mirror and the listings for the systems that changed.
        stale: system ids whose storage folder changed this run, refreshed too."""
        nonlocal systems, saved

        def picks(s):
            return s.get("full_system"), store.listed(s)
        before = {s["bucket"]: picks(s) for s in systems}
        systems = synced(store.load_manifest([card])["systems"])  # with the card's games as they are saved now
        changed = [s["bucket"] for s in systems if picks(s) != before.get(s["bucket"]) or s["bucket"] in stale]
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

    seed = {}  # guest syncs: {system id: {storage key: card path}}, the storage ROMs on the card when seeded

    def reseed(reload=True):
        """Make the storage ROMs on the card (a matching name and storage's size) the card's picks, replacing the ones
        saved before: in cards.json, or in memory on a dry run. reload=False (from the card editor): only saved, so
        nothing prints or downloads under the editor; the sync reloads after it."""
        seed.clear()
        for s in systems:
            dest = os.path.join(roms_dir, s["folders"][layout_name])
            found = {}
            if cardfs.is_dir(dest):
                keys = sorted(k for k in inventory.files(s["bucket"] + "/", sizes=False) if not k.endswith("/"))
                folders = m3u.game_folders(keys) if disc_folders else None
                named = guests.named(dest, keys, disc_dir, folders)  # sizes only for these: a share is slow to stat
                if named:
                    with mirroring.storage_reads():  # storage's sizes, not the mirror's
                        sizes = inventory.stat(sorted(named))
                    found = guests.recognized(dest, keys, sizes, disc_dir, folders)
            seed[s["bucket"]] = found
        if args.dry_run:
            guests.apply_seed(systems, seed)
            listings.clear()
            relist()
        else:
            guests.save_seed(card, seed)
            if reload:
                reload_changes()

    splore_failed = 0
    pico8_system = next((s for s in systems if s["bucket"] == "pico8"), None)
    if layout_name == "spruce" and not guest and pico8_system and (pico8_system.get("full_system") or store.listed(pico8_system)):
        # the carts Splore cached on the card go to storage (and the new ones into the card's games) before the editor
        full = pico8_system.get("full_system") and not args.dry_run

        def held():
            """Storage's pico8/ names (None when it can't be listed): a full system's picks don't change when carts are
            added, so this tells whether its listing and the mirror need refreshing."""
            try:
                return set(inventory.files("pico8/", sizes=False))
            except s3.ERRORS:
                return None
        with mirroring.storage_reads():  # storage's pico8/ itself: the mirror holds only the carts the cards pick
            before = held() if full else None
            splore_failed = splore.run(card, base, os.path.join(roms_dir, pico8_system["folders"][layout_name]),
                                       pico8_system, args.dry_run)
            stale = ["pico8"] if full and (before is None or held() != before) else []
        if not args.dry_run:
            reload_changes(stale)

    if guest:  # no Surprise: the card editor opens on the picks seeded from the card
        reseed()
        if interactive and not args.dry_run:
            cardedit.edit_card(card, (device, layout_name), to_fetch, card_match)
            reload_changes()
    else:
        def on_guest():
            """F in the card editor turned the card into a guest card: this sync is a guest sync from here."""
            nonlocal guest
            guest = True
            reseed(reload=False)  # run_surprise only returns after the editor, then the picks are reloaded

        # surprises come in two steps: which ones to replace first (then the card editor, which shows the ones kept), and
        # the empty slots last, right before the sync, from every system the card's device supports, games picked or not
        surprise.run_surprise(card, (device, layout_name), systems, interactive, args.dry_run, to_fetch=to_fetch,
                              card_match=card_match, on_guest=on_guest)
        if not args.dry_run:  # the step (and the card editor it opens) may have changed the card's games
            reload_changes()
        if not guest:
            surprise.fill_surprises(card, (device, layout_name), systems, args.dry_run)
        if not args.dry_run:
            reload_changes()

    def install_apps(dry_run, wrote=None):
        """Put PICO-8 (wrote, a list, gets what it put), the Surprise app and RAOfflineProxy on the card. The failure count."""
        return (pico8.run(card, layout_name, base, dry_run, wrote) + onion_surprise.install(card, layout_name, base, dry_run, keep=args.no_delete)
                + raofflineproxy.install(card, layout_name, base, dry_run))

    spruce_staged = []  # the spruceOS 7z staged this sync, for the reminder at the end

    def stage_spruce(dry_run):
        """Stage boot logos, the newest spruceOS, the saved settings and WiFi networks on a spruce card, and the knulli.conf settings on a Knulli card. The failure count."""
        wrote = []
        failed = spruce_bootlogo.install(card, layout_name, device, base, dry_run, wrote, keep=args.no_delete)
        failed += spruce_os.install(card, layout_name, base, dry_run, spruce_staged, keep=args.no_delete)
        wrote += spruce_staged
        failed += spruce_settings.install(card, layout_name, base, dry_run)
        failed += spruce_wifi.install(card, layout_name, base, dry_run)
        failed += spruce_syncthing.run(card, layout_name, base, dry_run)
        failed += spruce_hotkeys.install(card, layout_name, base, dry_run)
        failed += spruce_retroarch.install(card, layout_name, base, dry_run)
        failed += knulli_conf.install(card, layout_name, base, dry_run)
        failed += spruce_splore.install(card, layout_name, base, dry_run)
        failed += portmaster.stage(card, device, layout_name, base, port_picks, dry_run, args.no_delete)[0]
        if clean_card and wrote:
            clean._clean_root = base
        return failed

    chosen = [s for s in systems if available(s)]
    port_picks = []  # the picked port zips: PortMaster installs them from its autoinstall folder, never Roms/PORTS
    if portmaster.enabled(device, layout_name):
        port_picks = sorted(os.path.basename(k) for s in chosen if s["bucket"] == portmaster.PORTS for k in available(s))
        chosen = [s for s in chosen if s["bucket"] != portmaster.PORTS]
    deselected = []  # guest syncs: the seeded ROMs the card editor deselected, the only ROMs a guest sync deletes
    if guest:
        picked = {s["bucket"]: set(available(s)) for s in systems}
        # x (systems_off) skips a system this sync, and a system no longer synced is never touched
        deselected = guests.deletions(seed, picked, store.systems_off(store.saved_card(card)) | (set(seed) - set(picked)))
    if not chosen and not deselected:
        failed = splore_failed
        pico8_wrote = []
        if not guest:
            failed += install_apps(args.dry_run, pico8_wrote)
            if onion_surprise.write_list(card, layout_name, base, roms_dir, systems, args.dry_run) and clean_card:
                clean._clean_root = base
            failed += stage_spruce(args.dry_run)
        print(ui.yellow(f"👋 {card} has nothing to sync. Add games with `sync-roms edit`."))
        spruce_os.remind(spruce_staged)
        pico8.remind(layout_name, pico8_wrote)
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
        if disc_keys and not guest:  # discs a past sync left loose go where they belong rather than being downloaded again
            moved.update(downloads.hide_discs(dest, disc_dir, disc_keys, args.dry_run))
        for key in wanted:
            if key in have and key in seed.get(s["bucket"], {}):  # guest: where the card has it, as the card spells it
                rom_jobs.append((key, seed[s["bucket"]][key], have[key]))
            elif key in have:
                downloads.add_job(rom_jobs, key, dest, downloads.rom_rel(key, disc_dir, disc_keys, folders_of(s)), have[key])
            else:
                missing.append(key)
    ui.report_missing(missing, "ROM(s)")
    # systems can share a folder (Onion: WS, NGP), so a folder's expected files are the union over all of them
    # a system with nothing to sync is always scanned, selected or not: whatever it has on the card is unwanted
    chosen_ids = {s["bucket"] for s in chosen}
    dropped_dests = {os.path.join(roms_dir, s["folders"][layout_name]) for s in dropped
                     if s["folders"].get(layout_name) and not portmaster.owns_folder(s)}
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
    if guest:  # no sweep of a friend's card: only what the card editor deselected
        extras = list(deselected)
    for dest in [] if guest else sorted({dest_of(s) for s in systems if (s["bucket"] in chosen_ids or not available(s)) and not portmaster.owns_folder(s)} | dropped_dests):
        extras += downloads.find_extras(dest, dest_keys[dest], onion, disc_dir, dest_discs[dest], dest_bios[dest] | own_files[dest] | (pico8.keep_in(dest, card, layout_name) if dest in pico8_dests else set()), renames=renames, folders=dest_folders[dest], skip_saves=saves.beside_roms(layout))

    # BIOS for every system with ROMs already on the card too, even when this sync doesn't touch that system
    off = store.systems_off(store.saved_card(card)) if guest else set()  # x skips a system of a guest card, BIOS too
    bios_systems = chosen + [s for s in systems if s["bucket"] not in chosen_ids and s["bucket"] not in off
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
                                             or not raofflineproxy.APK_NAME.fullmatch(os.path.basename(k)))] if layout_name == "esde" and not guest else [])
    apk_jobs = downloads.with_sizes(apk_jobs)
    # and the device's bezels (os/android/bezels/<device id>/) in a Bezels/ folder
    bezel_dir = os.path.join(base, "Bezels")
    bezel_jobs = (downloads.with_sizes(bezels.jobs((device or {}).get("id"), base))
                  if layout_name == "esde" and not guest else [])
    # and the suggested GPU drivers for the device's Adreno GPU, kept up to date in storage first, in a Drivers/ folder
    driver_entries = [] if guest else drivers.for_device(device, layout_name)
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
    if themes_dir and not guest:
        for k, size in sorted(inventory.files(runtime.THEMES_PREFIX, sizes=False).items()):
            rel = k[len(runtime.THEMES_PREFIX):]
            if k.endswith("/") or os.path.basename(rel) == ".DS_Store":
                continue
            downloads.add_job(theme_jobs, k, os.path.join(base, themes_dir), rel, size)

    theme_jobs = downloads.with_sizes(theme_jobs)
    # spruce cards get the PyUI themes of the default list and the card's current theme in Themes/
    theme_plan = None
    if layout_name == "spruce" and not guest:
        theme_names = spruce_themes.default_list()
        if store.saved_card(card).get("one_theme") is True:  # only the card's own theme, not the default list
            theme_names = []
            if not spruce_themes.current(card) and interactive and not args.dry_run:
                with mirroring.storage_reads():
                    cardedit.pick_spruce_theme(card, None)
            if not spruce_themes.current(card):
                print(ui.dim("🎨 One theme only is on and the card has no theme: pick one in the card editor's S menu"))
        with mirroring.storage_reads() if spruce_themes.current(card) != mirrored_theme else contextlib.nullcontext():
            theme_plan = spruce_themes.plan(card, base, theme_names, args.no_delete)
            theme_jobs = downloads.with_sizes(theme_plan["jobs"])

    rom_todo, bios_todo = downloads.plan_downloads(rom_jobs, disc_dir), downloads.plan_downloads(bios_jobs)
    apk_todo = downloads.plan_downloads(apk_jobs)
    bezel_todo = downloads.plan_downloads(bezel_jobs)
    driver_todo = downloads.plan_downloads(driver_jobs)
    theme_todo = spruce_themes.todo(theme_jobs) if theme_plan else downloads.plan_downloads(theme_jobs)
    if guest:  # never overwrite a file on a friend's card
        rom_todo, bios_todo = guests.new_files(rom_todo), guests.new_files(bios_todo)
    if args.dry_run:  # the real run moves these first, so they are already there and not extras
        rom_todo = [j for j in rom_todo if j[1] not in moved]
        extras = [p for p in extras if not moved or os.path.join(os.path.dirname(p), disc_dir, os.path.basename(p)) not in moved]
    elif moved:
        print(ui.dim(f"  📦 Moved {len(moved)} loose disc file(s) into {disc_dir}/"))
    # card files spelled differently from storage are renamed, and unwanted ones that match a missing file are moved
    # there, before the downloads: neither is downloaded or deleted
    rom_todo, bios_todo = downloads.after_renames(rom_todo, renames, disc_dir), downloads.after_renames(bios_todo, renames)
    card_moves = [] if guest else downloads.plan_moves(rom_todo + bios_todo, {p: cardfs.size(p) for p in extras})
    moved_jobs, moved_from = {j for _, j in card_moves}, {p for p, _ in card_moves}
    bios_moves = moved_jobs.intersection(bios_todo)
    extras = [p for p in extras if p not in moved_from]
    samples = [p for p in extras if layout_name == "spruce" and downloads.spruce_sample(roms_dir, p)]  # deleted without asking
    extras = [p for p in extras if p not in samples]
    if args.no_delete:
        samples = []
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
            # a guest card's own ROMs (the seed) get no scrapes: only the games added this sync do
            scraped["rels"] = {s["bucket"]: [k.split("/", 1)[1] for k in available(s)
                                             if k in listings[s["bucket"]] and k not in seed.get(s["bucket"], {})]
                               for s in chosen}
        if disc_folders:  # scrapes name a ROM by its storage path; a disc game is in its own folder on the card
            moved_to = {os.path.join(dest_of(s), k.split("/", 1)[1]): os.path.join(dest_of(s), downloads.rom_rel(k, folders=folders_of(s)))
                        for s in chosen for k in folders_of(s)}
            found = present

            def present(path):
                return found(moved_to.get(path, path))
        hidden = {}
        if layout_name in frontend.ESDE_LAYOUTS:  # ES-DE lists every disc beside its playlist, so hide the discs of games that have one
            for s in chosen:
                disc_set = {k for g in m3u.file_groups(available(s)).values() if g[0].lower().endswith(".m3u") for k in g[1:]}
                if discs := [r for r in scraped["rels"][s["bucket"]] if f"{s['bucket']}/{r}" in disc_set]:
                    hidden[s["bucket"]] = discs
        plan = scrape_plan.build_scrape_plan(layout_name, chosen, scraped["data"], scraped["rels"], dest_of, es_dir, present, base,
                                             recheck=recheck, **({"hidden": hidden} if hidden else {}))
        if esde_problem and plan["gamelists"]:
            skipped()
            plan["gamelists"] = {}
        if guest:  # never overwrite a file on a friend's card, nor a gamelist entry
            plan["jobs"] = guests.new_files(plan["jobs"])
            plan["writes"] = [w for w in plan["writes"] if cardfs.size(w[0]) is None]
            plan["gamelists"] = guests.new_gamelist_entries(plan["gamelists"])
        return plan

    def deleted_media(paths):
        """Guest syncs: the media on the card of the seeded ROMs at paths, where this layout names them."""
        gone = defaultdict(list)
        for bucket, found in seed.items():
            gone[bucket] += [k.split("/", 1)[1] for k, path in found.items() if path in paths]
        those = [s for s in systems if gone.get(s["bucket"])]
        if not (scrapes and those):
            return []
        plan = scrape_plan.build_scrape_plan(layout_name, those, scrape_plan.load_scrape_data(those), gone, dest_of, es_dir,
                                             lambda path: True, base, all_media=True)
        return sorted({p for p in [j[1] for j in plan["jobs"]] + [w[0] for w in plan["writes"]] if cardfs.size(p) is not None})

    def deleted_gamelists(paths):
        """Guest syncs: {gamelist file: [(rom rel, card path)]} for the seeded ROMs at paths, where this layout lists them."""
        out = defaultdict(list)
        if esde_problem:
            return out
        for s in systems:
            gl = scrape_plan.gamelist_path(layout_name, s, es_dir, dest_of(s))
            if gl:
                out[gl] += [(k.split("/", 1)[1], p) for k, p in seed.get(s["bucket"], {}).items() if p in paths]
        return {gl: roms for gl, roms in out.items() if roms}

    # computed before the ROMs go; removed after, only those no ROM left on the card still names
    gamelists_gone = deleted_gamelists(set(extras)) if guest else {}
    media_gone = deleted_media(set(extras) | set(kept_extras)) if guest else []

    # the media of every ROM that will be on the card, so the totals and the space check count it
    planned = build_plan(lambda path: True) if scrapes else None
    scrape_todo = planned["jobs"] if planned else []
    summary = [f"{icon} {label}: {ui.bold(str(len(todo)))} to download ({ui.human_size(total_bytes(todo))}), "
               f"{len(jobs) - len(todo)} already present"
               for icon, label, todo, jobs, always in (("💿", "ROMs", rom_todo, rom_jobs, True), ("🧠", "BIOS", bios_todo, bios_jobs, True),
                                                       ("🤖", "Android", apk_todo, apk_jobs, False), ("🖼️", "Bezels", bezel_todo, bezel_jobs, False), ("🎮", "Drivers", driver_todo, driver_jobs, False),
                                                       ("🎨", "Themes", theme_todo, theme_jobs, False))
               if always or jobs]
    print("\n" + "\n".join(summary))
    if planned:
        scrape_plan.describe_scrape_plan(planned)
    if extras:
        print(f"🗑️  Local ROMs no longer in the selection: {ui.bold(str(len(extras)))}")
    if theme_plan and theme_plan["remove"]:
        print(f"🗑️  Themes to remove: {ui.bold(str(len(theme_plan['remove'])))}")
    list_kept(kept_extras, "local ROM(s) no longer in the selection")
    if renames or card_moves:
        print(f"📦 Card files to rename or move instead of downloading: {ui.bold(str(len(renames) + len(card_moves)))}")
    todo_all = rom_todo + bios_todo + apk_todo + bezel_todo + driver_todo + theme_todo + scrape_todo
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
        only_surprises = {g.get("bucket") for s in chosen for g in s["games"] if g.get("from") == surprise.LABEL}
        synced_keys = {k for s in chosen for k in available(s)} - only_surprises  # a surprise alone matches no collection
        listed_ids = names("collections")
        card_colls = ([by_id[i] for i in listed_ids if i in by_id]
                      + [c for c in by_id.values() if c["id"] not in listed_ids
                         and any(g.get("bucket") in synced_keys for g in c["games"])]) if collections_on else []
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
            plan = muos_collections.plan(base, muos_collections.wanted(card_colls, systems, on_card, mount), owned, args.no_delete)
        elif layout_name == "spruce":
            plan = spruce_collections.plan(base, spruce_collections.wanted(card_colls, systems, on_card), owned, args.no_delete)
        else:
            wanted = frontend.wanted_collections(layout_name, card_colls, systems, on_card,
                                                 {k: d for s in systems for k, d in folders_of(s).items()})
            plan = frontend.plan_collections(layout_name, base, wanted, owned, args.no_delete)
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
                if not plan["unreadable"]:
                    themeart.describe(layout_name, base, arts, {*owned, *plan["owned"]}, entry.get("spruce_theme"),
                                      keep=args.no_delete)
            elif arts or store.card_flag(entry, "theme"):  # with no art to add it still names the art that would go
                themeart.describe(layout_name, base, arts, keep=args.no_delete)
            list_kept(plan.get("kept", []), "retired collection(s) and their art")
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
            art = not plan["unreadable"] and themeart.install(layout_name, base, arts, {*owned, *plan["owned"]},
                                                              entry.get("spruce_theme"), keep=args.no_delete)
        else:  # with no art to add it still removes the art sync-roms wrote before
            art = (bool(arts) or store.card_flag(entry, "theme")) and themeart.install(layout_name, base, arts, keep=args.no_delete)
        list_kept(plan.get("kept", []), "retired collection(s) and their art")
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

    capacity = budget.card_capacity(saved) if surprise.enabled(saved) and not guest else None
    if capacity:
        used = budget.card_usage(cardedit.card_entry(card, (device, layout_name)), systems).bytes
        if used > capacity:
            ui.warn(f"{card}'s picks take {cardedit.size_text(used)} of its {saved['size']}: "
                    f"{cardedit.size_text(used - capacity)} over")

    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing downloaded or deleted"))
        free = free_space(base) + sum(cardfs.size(p) or 0 for p in extras + samples)  # the real run deletes these first
        if theme_plan:
            free += spruce_themes.freed(base, theme_plan["remove"])
        plan_json = {
            "downloads": [{"kind": kind, "key": key, "path": path, "size": size or 0}
                          for kind, todo in (("rom", rom_todo), ("bios", bios_todo), ("android", apk_todo), ("bezel", bezel_todo), ("driver", driver_todo),
                                          ("theme", theme_todo), ("scrape", scrape_todo))
                          for key, path, size in todo],
            "delete": list(extras) + samples, "kept": kept_extras, "theme_remove": theme_plan["remove"] if theme_plan else [], "rename": [{"from": a, "to": b} for a, b in renames + [(p, j[1]) for p, j in card_moves]],
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
        for path in extras + samples:
            print(f"  {ui.red('would delete')} {path}")
        if theme_plan:
            spruce_themes.remove(base, theme_plan["remove"], True)
            spruce_themes.clear_copies(base, spruce_themes.stale_copies(base, theme_todo), True)
            spruce_themes.select(card, base, True)
        if not guest:
            prune_drivers(True)
            install_apps(True)
            stage_spruce(True)
        stale_count = 0
        if scrapes:
            stale_files = media_gone if guest else scrape_plan.stale_media(layout_name, manifest['systems'], roms_dir, stale_es_dir, base)
            if args.no_delete:
                list_kept(stale_files, "media file(s) for ROMs that aren't on this card")
            else:
                stale_count = len(stale_files)
                print(f"🧹 Media on the card for ROMs it doesn't have: {stale_count} file(s) to remove")
        if not guest:
            frontend_step(True)
        spruce_emu_step(True)
        if not guest:
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

    remove_samples(samples)
    if extras:  # cleared first so the free space shown below is what the downloads really get
        delete_extras(extras)
    cardfs.clear()
    for gl, roms in gamelists_gone.items():  # the entries of the ROMs that really went
        guests.remove_gamelist_entries(gl, [r for r, p in roms if not os.path.exists(p)])

    # on spruce cards t picks this sync's themes; the removals wait for the answer, so a kept theme isn't copied again
    pick_themes = theme_plan is not None and not ui.ASSUME_YES and ui.has_terminal()
    # a list picked with t, or a card theme picked since the mirror was refreshed: the mirror keeps only the default
    # list's themes and the cards' then-current ones, so storage is read
    themes_picked = spruce_themes.current(card) != mirrored_theme
    while todo_all or pick_themes:
        if todo_all:
            short = space(free_space(base) + (spruce_themes.freed(base, theme_plan["remove"]) if theme_plan else 0))
            if short:
                if ui.ASSUME_YES or not ui.has_terminal():  # nobody to answer "Try anyway?"
                    ui.fail(short, 1)
                ui.failure(ui.red(f"❌ {short}"))
                if not ui.confirm("Try anyway?", default=False):
                    print(ui.yellow("👋 Cancelled."))
                    return 0
        question = (f"⬇️  Download {len(todo_all)} file(s) ({ui.human_size(total_bytes(todo_all))})?" if todo_all
                    else "Nothing to download. Continue?")
        answer = ui.choose(question, "ynt", "y", "t: themes for this sync") if pick_themes else "y" if ui.confirm(question) else "n"
        if answer == "n":
            print(ui.yellow("👋 Cancelled."))
            return 0
        if answer == "y":
            break
        with mirroring.storage_reads():
            picked = spruce_themes.pick("🎨 Themes for this sync only", theme_names, locked=store.saved_card(card).get("spruce_theme"))
            if picked is not None:
                theme_names, themes_picked = picked, True
                theme_plan = spruce_themes.plan(card, base, theme_names, args.no_delete)
                theme_jobs = downloads.with_sizes(theme_plan["jobs"])
                theme_todo = spruce_themes.todo(theme_jobs)
        if picked is not None:
            todo_all = rom_todo + bios_todo + apk_todo + bezel_todo + driver_todo + theme_todo + scrape_todo
            print(f"🎨 Themes: {ui.bold(str(len(theme_todo)))} to download ({ui.human_size(total_bytes(theme_todo))}), "
                  f"{len(theme_jobs) - len(theme_todo)} already present"
                  + (f"; {len(theme_plan['remove'])} to remove" if theme_plan["remove"] else ""))
    present = [n for n in theme_plan["remove"] if os.path.isdir(os.path.join(base, "Themes", n))] if theme_plan else []
    removal_failed = spruce_themes.remove(base, theme_plan["remove"], False) if theme_plan else 0
    if theme_plan:
        removal_failed += spruce_themes.clear_copies(base, spruce_themes.stale_copies(base, theme_todo), False)
    themes_removed = any(not os.path.isdir(os.path.join(base, "Themes", n)) for n in present)
    if removal_failed:  # a folder that couldn't be removed stays recorded, so the next sync tries again
        theme_plan["installed"] = spruce_themes.sorted_names(
            [*theme_plan["installed"], *(n for n in theme_plan["remove"] if os.path.isdir(os.path.join(base, "Themes", n)))])
    cardfs.clear()

    if clean_card and todo_all:  # nothing downloaded means nothing to finalize
        clean._clean_root = base
    started = time.monotonic()
    failures = []
    disc_dirs = {os.path.normpath(dest_of(s)): disc_dir for s in chosen if available(s)} if disc_dir else None
    failed = splore_failed + move_failed + removal_failed + downloads.run_downloads(rom_todo, "ROMs", "💿", roms_dir, failures, disc_dirs) + downloads.run_downloads(bios_todo, "BIOS", "🧠", bios_dir, failures)
    if apk_jobs:
        failed += downloads.run_downloads(apk_todo, "Android", "🤖", apk_dir, failures)
    if bezel_jobs:
        failed += downloads.run_downloads(bezel_todo, "Bezels", "🖼️", bezel_dir, failures)
    if driver_entries:
        failed += downloads.run_downloads(driver_todo, "Drivers", "🎮", drivers_dir, failures)
    # also when the card gets no drivers now (another device or layout): the ones sync copied before go
    if not guest:
        prune_drivers(False)
    pico8_wrote = []
    if not guest:
        failed += install_apps(False, pico8_wrote)
    if theme_todo:
        with mirroring.storage_reads() if themes_picked else contextlib.nullcontext():
            failed += downloads.run_downloads(theme_todo, "Themes", "🎨", base if theme_plan else os.path.join(base, themes_dir), failures)
    if theme_plan:
        if theme_plan["installed"] != (store.saved_card(card).get("spruce_themes_installed") or []):
            store.update_card(card, spruce_themes_installed=theme_plan["installed"])
        if (spruce_themes.select(card, base, False) or themes_removed) and clean_card:
            clean._clean_root = base
    prefixed = 0
    for s in chosen:
        if disc_dir and available(s):
            prefixed += m3u.prefix_playlists(dest_of(s), disc_dir, [p for _, p, _ in rom_todo if p.lower().endswith(".m3u")])
    cardfs.clear()

    psvita_wrote = []
    if layout_name in frontend.ESDE_LAYOUTS and not guest:  # ES-DE launches an installed Vita game through its .psvita file
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
        if not guest:
            stale = scrape_plan.stale_media(layout_name, manifest["systems"], roms_dir, stale_es_dir, base)
        elif media_gone and not args.no_delete:  # a picture another ROM on the card still names stays (a ROM kept at the prompt too)
            swept = set(scrape_plan.stale_media(layout_name, systems, roms_dir, stale_es_dir, base))
            stale = [p for p in media_gone if p in swept]
        else:
            stale = media_gone
    if args.no_delete:
        list_kept(stale, "media file(s) for ROMs that aren't on this card")
    else:
        remove_stale_media(stale)
    cardfs.clear()
    for folder in [] if args.no_delete or guest else scrape_plan.prune_empty_systems(layout_name, manifest["systems"], roms_dir):
        print(ui.green(f"🧹 Removed empty system folder {os.path.relpath(folder, base)}"))
    cardfs.clear()
    if not guest:
        frontend_step(False)
    spruce_emu_step(False)
    if not guest and spruce_fixes.run(layout_name, base, False) and clean_card:
        clean._clean_root = base
    if not guest and onion_surprise.write_list(card, layout_name, base, roms_dir, systems, False) and clean_card:
        clean._clean_root = base
    try:
        cardfs.flush()  # the frontend settings, before the card is reported done
    except OSError as e:
        failed += 1
        failures.append(("frontend settings", str(e)))
    if not guest:
        failed += stage_spruce(False)  # last: the 7z is large, and the card's other writes come first
    if failures:
        report_failures(failures)
    if not failed and not args.no_eject and usersettings.load_settings().get("eject", True) is not False:
        clean._eject_root = base  # after the card tidy, which still needs it mounted
    failed_keys = {k for k, _ in failures}
    got = [j for j in rom_todo + bios_todo + apk_todo + bezel_todo + driver_todo + theme_todo + scrape_todo if j[0] not in failed_keys]
    done = (f"downloaded {len(got)} file(s) ({ui.human_size(total_bytes(got))}) in {ui.eta(time.monotonic() - started)}"
            + (f"; {len(missing)} listed ROM(s) not in storage" if missing else ""))
    if failed:
        ui.failure(ui.red(f"\n⚠️  Done with {failed} failure(s): {done}"))
    else:
        print(ui.green(f"\n🎉 Done: {done}"))
    spruce_os.remind(spruce_staged)
    pico8.remind(layout_name, pico8_wrote)
    return 1 if failed else 0


free_space = downloads.free_space
