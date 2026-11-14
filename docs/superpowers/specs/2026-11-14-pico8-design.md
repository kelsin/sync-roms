# PICO-8: official binary on cards, and Featured carts from the BBS

## Why

PICO-8 carts run best on the official, paid PICO-8 binary, and Splore (PICO-8's built-in BBS browser) only exists
there. The user keeps the official Raspberry Pi zip in storage and wants every card set up to use it, even a card
with no PICO-8 games, so Splore is always there. The user also wants a quick way to fill storage with highly rated
carts from the Lexaloffle BBS, shown under their real titles in the editors and on the frontends.

## Goals

- Every card on `esde` (Android), `knulli`, `muos`, `onion` and `allium` gets what that frontend needs to run the
  official binary, whether or not the card syncs any `pico8` games.
- Storage's newest Raspberry Pi zip is used, with no version number in the code; a newer zip in storage reaches the
  cards on their next sync.
- `sync-roms download pico8` adds every Featured BBS cart that storage doesn't have yet to storage's `pico8/`
  folder, under their BBS file names, with their titles stored so the editors and frontends show them, and upgrades
  carts storage has when the BBS has a newer revision.

## Non-goals

- Running the frontends' installers, or choosing PICO-8 as the emulator in a frontend's settings: the user does that
  once per device.
- Desktop targets (ES-DE on a PC, EmuDeck): the binary is installed on the machine there, not the card.
- muOS game names (sync writes none for any system today) and EmuDeck gamelists (they live off the card).
- ScreenScraper art for downloaded carts: titles only (the user's choice). `sync-roms scrape` keeps skipping
  carts that have a metadata entry; the cart image is its own label.
- The pico8-android APK: storage's `os/android/APKs/` already holds `pico8-frontend.apk`, and sync already copies
  that folder to Android cards.

## Anti-goals

- Copying a zip back onto a card after the frontend's installer used it up (Knulli deletes it), which would make the
  installer prompt again every sync.
- Hardcoding a PICO-8 version or file name.
- Putting the binary, or anything from the zip, in the repo.

## Approaches

1. **Frontend installers (chosen).** Sync copies the zip to where Knulli's and muOS's own installers and the Android
   app look for it, and the user runs them once. Chosen by the user so sync keeps working when the installers change
   what they install where.
2. Sync extracts and installs the files itself for every frontend (including Knulli's extra system file and emulator
   setting). Rejected: duplicates the installers and breaks when they change.

Onion and Allium have no installer for the binary, so sync copies the two files they need out of the zip. The user
asked for this, and for it to happen on every card of those layouts.

## Design

### Storage

- `os/pico8/` holds the user's untouched official zips. The zip sync uses is the newest file matching
  `pico-8_*_raspi.zip`: highest by natural sort of the file name (runs of digits compared as numbers), so
  `0.2.10` beats `0.2.7`. A new constant beside the other `os/` prefixes in `runtime.py`; listed through `inventory`
  like the others (and added to the mirror's prefixes in `mirroring.py` if the mirror needs it to copy).
- No zip in `os/pico8/`: sync does nothing PICO-8 related and says nothing (or one dim line).

### What sync puts on a card

| Layout | Card path | From the zip |
|---|---|---|
| `esde` (Android) | `PICO-8/<zip name>` | the zip as is, for pico8-android's zip picker |
| `knulli` | `roms/pico8/<zip name>` | the zip as is, for Device Settings → Install Pico-8 |
| `muos` | `ARCHIVE/<zip name without .zip>.muxzip` | the zip as is, renamed, for Archive Manager |
| `onion` | `RApp/PICO-8/bin/pico8_dyn`, `RApp/PICO-8/bin/pico8.dat` | `pico-8/pico8_dyn`, `pico-8/pico8.dat` |
| `allium` | `Apps/pico.pak/bin/pico8_dyn`, `Apps/pico.pak/bin/pico8.dat` | the same two files |

Paths come from each project's source (Onion's RApp package `launch.sh`, Allium's `static/Apps/pico.pak/launch.sh`,
Knulli's `knulli-install-pico8`, muOS's `ext-pico8.sh` and Archive Manager); the Android app needs the zip's name
to contain `pico-8` and `raspi.zip`, which storage's names already do. `pico8_dyn` is written executable. Other
layouts (`slot`, `emudeck`) get nothing. It happens for every card of those layouts, regardless of its `games`.

`esde` cards are not told apart by device: every `esde` card gets the zip, as every `esde` card gets the APKs today
(a desktop `esde` card just carries a stray zip). *Builder's call, made in review.*

### Card cleanup

Sync's extras check (`downloads.find_extras`, run on every system folder) must not offer to delete what the PICO-8
setup puts or leaves in a ROM folder. In the pico8 ROM folder of every layout, keep (pass as `keep`) the recorded zip
name and any file whose name starts with `Splore` or contains `with Splore` (Knulli's installer writes
`roms/pico8/Splore.png`; Onion's package adds `~Run PICO-8 with Splore.png`; muOS and Knulli open Splore from a cart
named `Splore*`). The builder confirms these names from the installers' source. *Builder's call, made in review.*

### Doing it once per zip

The card's entry in `cards.json` gets `"pico8": "<zip name>"`, the zip sync last put on that card (like `drivers`).

- Recorded name equals storage's newest: nothing to do, even if the installer deleted the zip.
- Otherwise: copy (or extract) the newest; for the zip layouts delete the file sync put there for the old recorded
  name if it is still on the card; then record the new name.
- Onion/Allium: also redo the extraction when either of the two files is missing on the card (the user may have
  reinstalled the Onion package). The zip layouts never re-copy on a missing file, by design.
- `--dry-run` reports what would be copied or deleted and records nothing.
- `games export`/`import` carry it like `@drivers` (`@pico8 NAME`), so a card's state round-trips.

### `sync-roms download pico8`

`sync-roms download pico8 [--count N] [--dry-run] [--yes]`, needs storage write access. By default it reads every
page of the Featured listing (about 19 today) and takes every cart; `--count N` stops after N new or upgraded carts.

1. Read the BBS Featured listing (`https://www.lexaloffle.com/bbs/?cat=7&sub=2&orderby=featured`, then its later
   pages), parsing the `pdat=[...]` rows embedded in each page: post id, cart id, title, author, tags, and the cart
   file name. The builder reads a live page to map row positions to fields and to find the cart download URL.
2. Walk the rows in Featured order. A cart's identity is its file name with the revision suffix dropped
   (`molemole-1.p8.png` and `molemole-2.p8.png` are one cart, revision 1 and 2; a name with no `-<digits>` suffix is
   revision 0). Compare with the keys in `pico8/` (from `inventory`):
   - no key for that cart: **new**;
   - a key with a lower revision: **upgrade**;
   - the same or a higher revision, or the cart is in `ignored.json`: skip.
3. Download each new cart's `.p8.png` to a temp file (in its own folder, never executed), check it is a PNG, and
   upload it as `pico8/<BBS file name>` through `s3.put_file`.
4. Merge into storage's `scrapes/pico8/metadata.json` (read, `merge_metadata` with the new entries, `put_text`):
   per cart file `{"name": title, "developer": author}`. Existing entries for other carts are left as they are.
5. An upgrade replaces the old revision, since the file name changes:
   - delete the old key from storage (through the existing `s3.delete_keys`, which patches the cache);
   - move its metadata entry to the new file name (BBS title and author win), and move any `scrapes/pico8/` media
     named after the old stem to the new stem (`s3.move_keys`);
   - rewrite references to the old key in personal files: each card's `games` and `surprises` in `cards.json`,
     `surprises.json`, and `collections/*.json`;
   - repo sets can't be changed from here: list any set that names the old key, as a warning, for the user to update.
   Cards drop the old file on their next sync through the normal extras check, and get the new one.
6. Before writing, print the new carts and the upgrades (old → new) and ask once to go ahead (`--yes` skips the ask);
   `--dry-run` prints the same and writes nothing. Then print what was added and upgraded.

Polite to the BBS: one request at a time, a plain generic User-Agent, stop at the first HTTP error with a warning and
keep what was already added.

### Titles

- Editors: add `"pico8"` to `names.SYSTEMS`. `names.title` then reads `scrapes/pico8/metadata.json`; pico8 has no
  `clones.json` family, so the lookup falls straight to the scraped name, then the file name.
- Frontends: sync already writes the stored `name` into ES-DE's and Knulli's `gamelist.xml`, Onion's
  `miyoogamelist.xml` and Allium's `gamelist.xml`, so new carts get titles with no sync change.
- Fallback for a cart with no stored name: `store.key_title` strips one extension, leaving `molemole-1.p8`. Strip a
  trailing `.p8` from the file-name fallback for pico8 so it shows `molemole-1`.

## Left to the builder

- The exact BBS row fields, paging parameter and cart download URL (read from the live page).
- Where in `cli.py`'s sync the PICO-8 jobs go (beside APKs, drivers and themes) and how they feed
  `downloads.plan_downloads` and the size budget; extraction may need its own small step since the other jobs are
  plain copies.
- CLI help text and README updates for the new command and the new card field.
- Tests in `tests/` for: newest-zip choice, the once-per-zip rule, the new/upgrade/skip rule, the metadata merge,
  rewriting references on upgrade, and the `.p8` fallback.
