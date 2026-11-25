# Splore carts into storage (spruce)

## Why

Splore on a spruce card is a way to find new PICO-8 carts. Every cart it downloads should join the collection in storage
and be on the card as a normal synced cart, and a newer revision found there should replace the one storage holds.

## Goals

- Every cart in a `spruce` card's Splore cache that storage's `pico8/` lacks is uploaded and added to the card's games.
- A cached cart that is a newer revision (`<base>-<rev>.p8.png`, `bbs.identity`) of one in storage replaces it, exactly as
  `download pico8` upgrades: metadata entry moved, media and scrape state moved, every personal reference retargeted
  (`bbs.retarget`), old key deleted last, sets still naming it warned about.
- Title-named copies that "Import carts from Splore" put in `Roms/PICO8` stop showing up as extras each sync.

## Non-goals

- Other layouts (only spruce's cache path is known: `Emu/PICO8/.lexaloffle/pico-8/`).
- Guest cards (a friend's card): skipped.
- Changing the cache on the card, or taking favourites as a filter.
- Uploading loose carts in `Roms/PICO8` that match no cached cart.

## Approaches

1. **Harvest the Splore cache in sync (picked).** Reads canonical BBS file names, so `bbs.classify` and the upgrade path
   of `download pico8` apply unchanged.
2. Harvest the imported copies in `Roms/PICO8`: their names are titles, so revisions can't be told apart; rejected.
3. A separate `download splore` command: an extra step to remember for something sync can see; rejected.

## Design

- Source: `Emu/PICO8/.lexaloffle/pico-8/bbs/carts/*.p8.png` and `bbs/*/*.p8.png` (PICO-8 shards numeric ids into
  `bbs/<n>/`), skipping `temp-*` (partial downloads), non-PNG files and names that aren't plain (`bbs._FILE`). Per base,
  the highest revision on the card.
- Classify against `inventory.files("pico8/")` and the ignore list with `bbs.classify`. A card revision lower than or
  equal to storage's does nothing.
- Titles and authors: from `favourites.txt` (`|name-rev |slug |id |author |... |title`, fields trimmed; field 2's path
  and extension dropped) where it has the cart; otherwise no metadata entry is written (names fall back to the file name
  until the scrape below fills it). An upgrade keeps the old entry's fields, as `download pico8` does.
- When: early in a non-guest spruce sync, before the card editor, so new carts show in it. Listed as a block
  (`new: …`, `upgrade: old → new`); one `ui.confirm` ("Add these to <storage>?", default yes; `--yes` accepts; without a
  terminal and without `--yes`, skipped with a hint). A dry run lists only. No write access: warned and skipped.
- Scrape: right after the uploads, the new carts (not upgrades, which keep the old revision's media and metadata) are
  scraped with `scrape_online.run_scrape(client, {"pico8": system}, {"pico8": [(cart, size, etag)]}, skip=set(),
  ask=False)`, covered by the same confirm. The scrape only adds to metadata, so `favourites.txt` titles stay, and it
  makes the `onion`/`spruce` box art as it goes, so the carts get art on this sync. No ScreenScraper credentials: skipped
  with a hint to run `sync-roms scrape pico8`. A scrape failure (quota, API, storage) is a warning and the sync goes
  on: its `ui.fail` exits must not end the sync. A dry run lists the carts it would scrape.
- Card: new carts are appended to the card's `games["pico8"]` as `{"title", "system", "bucket"}` (title via
  `names.title` after the metadata write), unless pico8 is a full system on the card. Upgrades need no add: `retarget`
  moves the card's reference.
- Import copies: a file in `Roms/PICO8` with the same bytes as a harvested (or already stored) cached cart but another
  name is renamed on the card to the cart's storage name, so sync finds it present.
- The shared helpers of `download pico8` (metadata write, `_media_moves`, `_move_state`, `retarget`, delete) are reused,
  factored out of `download_pico8` only as far as needed to call them from here.

## Left to the builder

- Exact hook point in `cli.py` and how the storage cache and local mirror see the uploads within the same run.
- Test layout (fixtures for a card's cache and `favourites.txt`).
- README / CLAUDE.md notes for the new behaviour.
