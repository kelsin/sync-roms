# PortMaster ports on spruce cards

## Intent

The user wants to find PortMaster ports, keep them in storage, and add them to spruce cards with the card editor, the
same way they add games. Many ports are commercial games that need the user's own game files ("game data"). Getting
that data onto every card that has the port should be easy: sync says which installed ports still need data, quotes
the port's own instructions and names the storage folder to put it in; once it is there, every later sync copies it to
each card that has the port, with nothing to pick.

## Goals

- `sync-roms ports search [TEXT]`: search PortMaster's catalogue and download picked ports to storage.
- `sync-roms ports download ZIP...`: the same download without searching.
- Ports picked on a spruce card get installed by PortMaster on the device, runtimes included, with no WiFi needed.
- Every spruce sync lists the installed ports that need game data storage doesn't have yet, with instructions and the
  exact storage folder.
- Every spruce sync copies game data from storage to installed ports that haven't had it, once per card and port.
- `sync-roms ports done CARD PORT`: mark a port's data as already on a card (for data added by hand before this).

## Non-goals

- Layouts other than `spruce` (ROCKNIX, Knulli, muOS come later; nothing in this design should assume spruce where a
  layout table would do, but only spruce is built).
- Removing or updating ports on cards. sync-roms never deletes or upgrades an installed port, its folder, its saves or a
  runtime; PortMaster on the device updates ports.
- A report file in the card or storage: the needed list is personal, in the data folder.

## Anti-goals

- Overwriting or deleting anything in an installed port's folder. Ports patch their game data on first run (Undertale
  zips `assets/` into `undertale.port` and deletes `assets/`; Celeste repacks `gamedata/`) and keep saves in their
  folder (`celeste/savedata`, `undertale/save`).
- Re-copying game data every sync. It is copied once per card and port.
- Game data, port zips or runtimes in the repo. Repo files never name storage contents.

## What spruce does (read from an RG35XXH card running spruceOS, PortMaster 2026.11.17-0700)

- PortMaster lives in `Persistent/portmaster/` (unpacked on first boot from `App/PortMaster/portmaster.7z`). Its
  control folder is `Persistent/portmaster/PortMaster/`.
- The only autoinstall folder is `Persistent/portmaster/PortMaster/autoinstall/` (spruce's `App/PortMaster/PortMaster.txt`
  sets both autoinstall dirs to it; `Roms/PORTS/autoinstall/` exists but is never read).
- Opening the PortMaster app installs, in order, `PortMaster.zip`, `runtimes*.zip`, `*.squashfs`, then port zips from
  that folder, deleting each once installed. After the app exits, `App/PortMaster/update_images.sh` makes
  `Roms/PORTS/Imgs/<script name>.png` from each port's cover.
- An installed port is `Roms/PORTS/<Title>.sh` plus `Roms/PORTS/<port folder>/` holding `port.json` (the zip's metadata
  plus a `status` block PortMaster adds). spruce's harbourmaster platform (`PlatformSpruce`) does nothing per port.
- Runtimes are `*.squashfs` in `Persistent/portmaster/PortMaster/libs/`.
- The ROM folder is `Roms/PORTS` (the `ports` system's spruce folder). The card is exFAT (case-insensitive; the folder
  shows as `ports` in some listings).

## PortMaster's catalogue

`https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json` (about 2.6 MB): `{"ports": {zip
name: entry}, "utils": {file name: {name, md5, size, url}}}`. A port entry has `name` (the zip name, e.g.
`celeste.zip`), `items` (top-level entries the zip installs: the `.sh` and the port folder, folders with or without a
trailing `/`), `attr` (`title`, `desc`, `inst` (plain-text instructions), `genres`, `rtr` (ready to run: false means it
needs the user's game files), `runtime` (list of `.squashfs` names, may be absent or null), `arch`, `porter`) and
`source` (`url`, `md5`, `size`, `date_updated`). Runtimes are in `utils` by file name with their `url` and `md5`.
Of 1518 ports, 787 have `rtr: false`.

## Approaches

1. **Autoinstall (picked).** Sync puts picked port zips and their runtimes where PortMaster installs from; the user
   opens PortMaster once. PortMaster does the install exactly as it would itself (status in `port.json`, cover images).
   Game data for a newly picked port goes in on the first sync after the install.
2. **Sync unpacks ports itself.** Works with no visit to the app and data goes in the same sync, but PortMaster doesn't
   record the port as installed (may list it as unknown or offer to reinstall) and sync would reimplement the installer.
3. **Copy installed ports from storage.** Firmware-specific copies and still needs runtimes; rejected.

The user asked for 1 implicitly by accepting the autoinstall design; it keeps sync-roms out of PortMaster's job.

## Design

### Storage

| Path | Holds | Written by |
|---|---|---|
| `ports/<zip>` | PortMaster port zips, under PortMaster's zip name (`celeste.zip`). The `ports` system's storage folder, so the card editor lists them like games. | `ports search`, `ports download` |
| `os/portmaster/runtimes/<name>.squashfs` | Runtimes the stored ports need, under PortMaster's name. | `ports search`, `ports download` |
| `os/portmaster/gamedata/<port folder>/...` | The user's game data, laid out like the port's folder on the card (`undertale/assets/data.win`, `celeste/gamedata/...`, `slaythespire/desktop-1.0.jar`). | the user, by hand |
| `scrapes/ports/metadata.json` | `{zip: {"name": title, ...}}` so the editors show "Celeste", not `celeste.zip`. Only adds entries, never changes an existing field (like `download pico8`). | `ports search`, `ports download` |

`ports` joins `names.SYSTEMS` so `names.title` uses the scraped name.

### Catalogue cache

`cache/portmaster/ports.json`, refreshed when older than a day (or with `--refresh`), through an ETag/If-Modified-Since
request where GitHub supports it, else a plain download. A failed refresh with a cached copy uses the copy and warns.
Only entries whose `attr.arch` includes `aarch64` (or has no `arch`) are offered, and only `aarch64` (or arch-less)
runtimes are downloaded.

### Devices

64-bit devices only for now. `devices.json` gets `"portmaster": true` on the spruce devices with a 64-bit SoC (the
Anbernic H700 devices, `miyoo-flip`, the TrimUI A133P/A523 devices, `magicx-zero40`); `miyoo-a30` (32-bit) and the
Miyoo Minis get none. A spruce card whose device lacks it skips every PortMaster step and the editor hides `ports`
there. The setup guide's embedded device copy doesn't need the field.

### `sync-roms ports search [TEXT] [--refresh] [--needs-data | --ready]`

Matches TEXT (case-insensitive, all words) against title, zip name, genres and description. Prints one row per match:
title, zip, genres, size, `needs game data` when `rtr` is false, `in storage` when `ports/<zip>` is there. With a
terminal and without `--yes`, a multi-select picker over the matches (the existing `ui` picker style); Enter downloads
the picks as `ports download` does. Without a terminal it only prints.

### `sync-roms ports download [ZIP...] [--update] [--refresh]`

For each zip (names as in the catalogue; a bare name without `.zip` is accepted): download `source.url`, check `md5`,
upload to `ports/<zip>` (skipped when storage has it at the catalogue's size), then each `attr.runtime` from `utils` to
`os/portmaster/runtimes/` (skipped when present), then add the title to `scrapes/ports/metadata.json` through
`shared.py`. An unknown name, a failed download or an md5 mismatch is reported and the rest go on; exit code 1 if any
failed. Writes go through `s3.py` so the storage cache is patched.

A zip storage already has is skipped unless `--update`, which replaces it when the catalogue's `source.md5` differs
from storage's copy (md5 of the stored file, computed from the mirror or storage and kept in
`cache/portmaster/md5.json` by storage tag so it is computed once per file version).

### Outdated ports

- `ports search` and `ports download` without `--update` end with `N ports in storage have newer versions: <titles>.
  Run sync-roms ports download --update` when any stored zip's md5 differs from the catalogue.
  `ports download --update` with no zip names updates all of them.
- Updating installed ports on a card is done on the device: PortMaster marks a port "update available" when the
  catalogue's md5 differs from the `status.md5` in the installed `port.json`, and installs it over WiFi. Sync never
  restages an installed port. With a cached catalogue (never fetched during sync), sync prints
  `🧩 Updates available in PortMaster on the device: <titles>` for installed ports whose `status.md5` differs.

### `sync-roms ports done CARD PORT...`

Marks each PORT (the port folder name, or its zip name, matched against the card's installed ports when the card is
mounted, else taken as given) as having its data on CARD: adds it to the card's `portmaster_data`. `--undo` removes it.

### Sync, `spruce` cards

New module `portmaster.py`, called from cli.py's spruce steps (dry-run and real paths), skipped for guest cards and for
devices without `portmaster`.

On every other layout `ports` is hidden in the editors and skipped by sync until that layout is built, so stored zips
are never copied as ROMs. On spruce, `ports` is left out of Surprise, collections (`custom_collections` included),
scraping, the gamelist, the `scrape art` hint and the editor's size, to-fetch and on-card counts: a port zip is never a
file in `Roms/PORTS`.

Picks unpicked before PortMaster runs: sync records the zips and runtimes it staged in `autoinstall/` in the card
field `portmaster_staged` and removes a staged zip no longer picked that is still waiting there (kept with
`--no-delete`). Entries PortMaster installed (gone from `autoinstall/`) drop out of the field.

1. **Installed ports.** Read `Roms/PORTS/*/port.json` (any one-level subfolder with a `port.json`): its `name` (zip),
   `items`, `attr.title`, `attr.rtr`, `attr.inst`, `attr.runtime`. Unreadable files are skipped with a warning.
2. **Picked ports.** The card's picked `ports` games (zips). A zip is installed when an installed `port.json` has the
   same `name`, or when every entry of its `items` exists in `Roms/PORTS/` (case-insensitive). The `ports` system's
   normal ROM copy is skipped for spruce cards: port zips never go into `Roms/PORTS/`, and the existing extras sweep
   must not offer to delete the `.sh` files, port folders, `Imgs/` or `autoinstall/` there.
3. **Autoinstall.** Each picked, not installed zip is copied to `Persistent/portmaster/PortMaster/autoinstall/<zip>`
   when not already there at storage's size. Each runtime its `port.json` (read from the zip in storage, or the local
   mirror) names that isn't in `libs/` or `autoinstall/` is copied from `os/portmaster/runtimes/` to `autoinstall/`
   (PortMaster installs `*.squashfs` from there before ports). A runtime storage lacks is warned about (`ports download
   <zip>` fetches it). When `Persistent/portmaster/PortMaster/` doesn't exist (spruceOS never booted), skip with a note
   to boot the device once. Prints `🧩 Open PortMaster on the device to install: Celeste, Undertale` when anything was
   staged.
4. **Game data.** For each installed port with `rtr: false`, the port folder (from `items`, the entry that is a folder):
   - In `portmaster_data`: nothing.
   - Storage has files under `os/portmaster/gamedata/<folder>/`: copy each file whose card path doesn't exist yet into
     `Roms/PORTS/<folder>/` at the same relative path (never overwrite), then add the folder to `portmaster_data`. A
     copy failure leaves it out of `portmaster_data` so the next sync retries.
   - Else: list it in the summary.
   Picked ports not installed yet that need data are listed too, as "after PortMaster installs it".
5. **Needed list.** Each port listed in step 4 is saved to the personal file `ports-needed.json` (below), with this
   card added to its cards; each port whose data storage now has is removed from the file.
6. **Summary.** A block `Ports waiting for game data` after the sync's other output: per port its title, its `inst`
   text indented, and `Put the files in <storage path>/os/portmaster/gamedata/<folder>/`; when `inst` mentions a path
   inside the port folder (`ports/undertale/assets`, `"celeste/gamedata"`, `assets folder`), the suggested folder is
   that subfolder. Ends with `Already on the card? sync-roms ports done <CARD> <folder>` and `All of them: sync-roms
   ports needed`. The storage path shown is the real one for a folder root, or `s3://<bucket>/...` for a bucket.

### Needed list, `~/.sync-roms/ports-needed.json`

Personal (data folder), written with `store.write_json`. `{port folder: {"title", "zip", "inst", "folder" (the
suggested storage folder, relative to storage's root, e.g. `os/portmaster/gamedata/undertale/assets/`), "cards":
[card names, sorted]}}`.

- Sync adds or refreshes an entry (title, zip, inst, folder from the card's `port.json`) and adds the card, for every
  installed port of a spruce card that needs data storage doesn't have and isn't in the card's `portmaster_data`.
  A picked port not installed yet is added too, from the zip's `port.json`.
- An entry is removed when storage has files under `os/portmaster/gamedata/<folder>/`: checked on every sync for all
  entries (not just the card's ports), from the storage listing (`inventory.py`).
- `ports done CARD PORT` takes CARD out of the entry's cards; the entry goes when no cards are left.
- A dry run reads the file but never writes it.

### `sync-roms ports needed`

Prints every entry of `ports-needed.json`, in title order, the same block as the sync summary plus the cards that
have the port. First drops entries whose data storage now has (and says so). Prints `No ports are waiting for game
data` when empty.

Dry runs print what would be staged and copied, and the summary, writing nothing.

### Card field

| Field | Written by | Meaning |
|---|---|---|
| `portmaster_data` | sync, `ports done` | `spruce` cards: sorted port folder names whose game data is on the card (copied by sync or marked done); never copied again. Absent when empty. |
| `portmaster_staged` | sync | `spruce` cards: sorted file names sync put in PortMaster's `autoinstall/` that were still there at the end of the sync. Absent when empty. |
| `portmaster_ports` | sync | `spruce` cards: sorted port folders installed on the card that need game data, so `mirror` (no card mounted) keeps their data. Absent when empty. |

Add it to `cards.schema.json` and the CLAUDE.md card fields table.

### Local mirror

The `mirror` command keeps the cards' picked port zips (they are ROMs of `ports`), the runtimes they name and the game
data folders of each card's `portmaster_ports` (and its picked ports that need data), so a sync from the mirror works
offline.

### CLI wiring

`ports` in `commands.COMMANDS` and `build_parser` with second words `search`, `download`, `done`, `needed`; help in `cli.TOPICS`,
place in `cli.SUBCOMMANDS`, README Commands table (checked by `tests/test_readme.py`).

## Left to the builder

- Exact output wording and emoji, matching nearby steps.
- How the instruction-path guess is written (a small regex over `inst` for `<folder>/<sub>` and "the <sub> folder").
- Whether reading runtimes for a picked zip opens the zip from storage or the mirror (through `s3.py`), as long as it
  works for a bucket and a folder.
- Tests: catalogue parsing and search, download skipping and md5 failure (network mocked), installed-port detection
  from fixture `port.json` files, autoinstall staging, data copy never overwriting, `portmaster_data`, the summary, the
  sweep leaving `Roms/PORTS` alone.
