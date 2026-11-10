---
name: build-card
description: Use when the user wants a local card (an entry in ~/.sync-roms/cards.json) built for a device that fits a given SD card size, e.g. "make me a card for the RG35XX H that fits 256 GB". Takes a device, a card name and a card size (asks if the size is missing); sizes the core list, fills spare room from online rankings, and verifies scrapes fit.
---

# build-card

Input: a **device** (id or name from `src/sync_roms/data/devices.json`), a **card name** (the card's folder name; it is the key in `~/.sync-roms/cards.json`) and a **card size**. The card size is required: if it wasn't given, ask for it (e.g. 64, 128, 256, 512 GB or 1 TB) before doing anything else, and don't assume a default. Confirm the unit (GB, not MB). Optional: what to prioritise.

Never put a real game list in the repo. The card lives only in `~/.sync-roms/cards.json`. Read-only bucket access: always `--profile roms-readonly`; never write to the bucket.

## 1. Resolve the device
- Find the device in `devices.json`; layout = its first firmware unless told otherwise.
- Systems = `store.device_defaults()[device]["systems"]` (resolved from the tiers in `src/sync_roms/data/device-systems.json`) (plus the optional `~/.sync-roms/device-systems.json` overlay). Read its `note` for systems that are unstable on the SoC and leave those out of any additions.
- If the device or name is ambiguous (e.g. RG Cube vs CubeXX), ask.

## 2. Baseline size of the core
Dry-run into a scratch dir (use the scratchpad):
```bash
mkdir -p $SCRATCH/<card> && sync-roms sync $SCRATCH/<card> --device <id> --layout <layout> --systems all --yes --dry-run --json
```
Sum `downloads[].size` per system (`key.split('/')[0]`). Also run it without `--json` and read `Scraped data: N file(s) (X GB)` for scrapes. The tool prints **GiB**; JSON sizes are bytes.

## 3. Budget
Usable = capacity_GB × 1e9 / 2^30 GiB (256 GB = 238.4 GiB). Reserve scrapes (re-measure after every change, they grow with games), ~2 GiB filesystem slack for tens of thousands of small files, and ~5-8% headroom. Report totals **including scrapes**.

If the core alone is over budget, stop and ask the user how to cut it (trim the biggest system to ranked picks, drop a system, or trim evenly). Trim with the card's `excluded` map (`{"ps2": ["ps2/File.chd", ...]}`), never by editing `games.json`.

## 4. Fill spare room, cheapest games per GiB first
1. Whole small cartridge systems: `{"full_system": true}` for systems whose whole bucket folder is small (list with `aws s3 ls s3://<bucket>/<sys>/ --recursive --summarize --profile roms-readonly`; GBA, SNES, Genesis, NES, GB, GBC, Game Gear, Master System, PC Engine are all a few GB or less).
2. Large systems (PS1, Sega CD, GC, PS2, Dreamcast, arcade): ranked picks only, within the budget. Full FBNeo (~46 GB) only if room remains.
3. Anything else the user asks for.

## 5. Picking from rankings (online only)
- Use WebSearch/WebFetch for published rankings; combine several per system (Metacritic all-time browse pages work: `https://www.metacritic.com/browse/game/<platform>/all/all-time/metascore/`; Wikipedia best-seller lists; genre/"best of" lists; fan votes for Dreamcast). Many sites 403 or truncate; use `offset` to read further. Don't use a list from a spam/auto-generated page.
- Score = sum over lists of (N - rank + 1) / N. Exclude yearly sports titles, peripherals (Guitar Hero, EyeToy) and movie tie-ins unless asked.
- Match titles to the bucket listing (`aws s3 ls ... --recursive`, saved locally as `size<TAB>key`). Only `(USA`/`(World` files; group a game's discs and `.m3u` together (keep all of them); skip beta/demo/proto. **Check every fuzzy match by eye**: sequels, "X-2" vs "X", collections and renamed US titles (e.g. Thunderhawk = AH3 Thunderstrike) match wrongly. Games already in the core are skipped when adding.
- Fill in score order until each system's size cap is reached. State the caps.

## 6. Write the card
Entry in `~/.sync-roms/cards.json`:
```json
"<card>": {"device": "<id>", "layout": "<layout>", "systems": [...device systems...],
           "games": {"<system>": [{"bucket": "sys/File.chd"}] | {"full_system": true}},
           "excluded": {"<system>": ["sys/File.chd"]}}
```
- Load the file, set the key, write with `sort_keys=True`; keep any other cards. Save a copy of the whole file to the scratchpad first and after.
- Check `sync-roms --version` and that the repo is on current main (older code's tests overwrote the real `cards.json`). If the card disappears, restore it from the backup copy.

## 7. Verify and report
Dry-run again with a scratch dir named exactly `<card>` (the card key is the folder name) and read ROM total + `Scraped data`. Report a table: ROMs+BIOS, scrapes, total, free on the card; list what was added per system, what was excluded, which rankings were used, and what was left out (and why). If under ~5% free, offer trims.
