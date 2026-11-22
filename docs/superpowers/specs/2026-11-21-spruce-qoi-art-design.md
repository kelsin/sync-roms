# Spruce QOI box art, and covers-first art for Onion and Spruce

## Intent

A Spruce card should need no on-device image conversion. Today sync copies a 250x360 PNG to `Imgs/<ROM>.png`. spruceOS's PyUI then prompts on first browse ("Originals will be converted"), deletes the PNGs and rewrites them as QOI at 640x480, 400x300 and 200x200 (`App/PyUI/main-ui/games/utils/box_art_resizer.py`), and the 250x360 source is soft at 640x480. The goal is the best quality Spruce can show, delivered in the form PyUI reads directly, with no prompt and no deleted files.

Onion and Spruce also change which art they use: **covers first, then miximages** (today: covers, 3dboxes, screenshots).

## Goals

- Spruce cards get `Imgs/<ROM>.qoi` (fit in 640x480), `Imgs_med/<ROM>.qoi` (400x300) and `Imgs_small/<ROM>.qoi` (200x200), the layout PyUI reads. Images are shrunk to fit, aspect ratio kept, never enlarged.
- Onion keeps its 250x360 PNG, now made from covers, then miximages.
- One command makes the art for Spruce, Onion or both, for every ROM already in storage, and reports (dry run) how many files it would make and roughly how much space they take.
- New scrapes make the same art as they go, so the command is only for what is already in storage.

## Non-goals

- No per-device tiers: spruceOS's own resizer writes the same three sizes on every device (the Mini family only declares 400x300 as its large size, which its views use to pick a tier), so every Spruce card gets all three.
- No other art types for Spruce (it shows one image per game), no savestate screenshots, no collection art changes (`Collections/Imgs` PNGs are read directly and are already right).
- No change for Allium or NextUI beyond the new source order, since they share the `onion` PNG.

## Anti-goals

- QOI files must never be left half-written or mixed with PNGs in a card's `Imgs/`: any PNG/JPG there makes PyUI prompt again.
- Nothing is made from an image that is not a ROM's own cover or mix image.

## Constraints

- Pillow reads and writes no QOI (checked with Pillow 13: `QOI` is in neither `Image.OPEN` nor `Image.SAVE`), and there is no ffmpeg here. We need our own QOI encoder (RGBA, 4 channels, as PyUI's ffmpeg path writes).
- Pillow is only a `dev` dependency today. QOI needs it, so it becomes a runtime dependency (`uv add`). The macOS `sips` fallback stays for Onion's PNG only.
- Storage, cache and personal-data rules in `CLAUDE.md` apply: shared files are read through `inventory.py` (never `s3.list_*`), derived art lives in storage under `scrapes/<system>/`, nothing personal goes to storage.
- Measured (14 random samples per type, QOI is lossless): 3 tiers cost about 540 KB per ROM from covers and 560 KB from miximages, about 150 KB per ROM for the Onion PNG; about 33.7k ROMs in storage have art, so Spruce art would be roughly 18-19 GB, Onion's regenerated art about 5 GB. Encoding takes 0.15 s per ROM (0.04 load, 0.10 encode) in pure Python.

## Approaches

1. **QOI made at sync time from raw ScreenScraper art, cached locally.** No new storage type. Needs raw covers (about 550 KB each) downloaded and converted on each machine. Viable, rejected in favor of 2.
2. **QOI made at upload time and stored in storage (chosen).** One conversion per ROM, shared by every machine and card; sync is a copy. Storage grows by about 18-19 GB. Tiers are the same for every device.
3. **A new high-quality PNG made at upload, QOI made at sync.** Smaller storage, but each card repeats the encoding. Rejected.

You picked 2, with covers then miximages for Onion and Spruce.

## Design

**Storage.** New media types alongside `onion`: `spruce` (key `scrapes/<system>/spruce/<stem>.qoi`, fit in 640x480), `spruce_med` (`.../spruce_med/<stem>.qoi`, 400x300), `spruce_small` (`.../spruce_small/<stem>.qoi`, 200x200). `onion` keeps its key (`.../onion/<stem>.png`, 250x360). Art is made only for ROMs at the top of a system folder (the layouts' `Imgs` folders are flat), as for Onion today.

**Sources.** Both targets take the first of `covers`, `miximages` found for the ROM (`ONION_ART` changes to `("covers", "miximages")`; Spruce uses the same list).

**PICO-8.** A cart with no cover or miximage uses its own picture (the `.p8.png` in storage) as the source for the Onion PNG and the Spruce QOI, in a normal scrape and in `scrape art`. The cart is never enlarged, so it gets only the `spruce` tier. On a Spruce card sync copies no PNG of a cart's picture into `Imgs/`.

**Encoder.** A small pure-Python QOI encoder (RGBA) in its own module. Tests check it against a reference decoder written in the test, since Pillow cannot read QOI. Resizing is Pillow's LANCZOS thumbnail. A `spruce_med` or `spruce_small` file is skipped when the image it would be made from is already no larger than that tier's box (PyUI falls back small, then med, then large).

**Sync.** On a `spruce` card sync installs `Imgs/<ROM>.qoi`, `Imgs_med/<ROM>.qoi` and `Imgs_small/<ROM>.qoi` from storage instead of the `onion` PNG, and removes the `Imgs/<ROM>.png` it wrote there before so no PNG is left to trigger the prompt. A ROM with no `spruce` key in storage gets no image (never the Onion PNG, which would bring back the prompt), and sync hints to run the art command. The builder checks how `miyoogamelist.xml`'s `image` tag should read for QOI (omit it, or point at `./Imgs/<ROM>.qoi`) from PyUI's `rom_utils.py` and `rom_select_options_builder.py`. Pillow missing means no Spruce art and a warning, like `NO_SHRINK` now.

**The art command.** `sync-roms scrape art [SYSTEM ...]`:
- `--for onion|spruce|both` (default `both`).
- `--dry-run`: reads only storage listings, no image is read or written. Per system and target it prints ROMs with a cover or mix image, files it would make, files already there, ROMs with no source, and an estimated size (the measured averages above, labeled an estimate). It exits 0 and changes nothing.
- `--replace` remakes files that exist (use it once to redo Onion's art with the new source order); without it existing keys are skipped, so a rerun resumes after an interruption.
- `--workers N` (default: CPU count) runs the conversions in parallel; uploads use the existing `upload.run_uploads`; Ctrl-C lets files in flight finish and keeps what is done.
- It prints progress, and a final count of made, skipped and failed files. A storage image that cannot be read is reported and skipped (one 3dbox PNG in storage is already unreadable).
- Estimated time for everything: about 85 minutes on one core, about 10 minutes of CPU on 10 cores, plus writing about 24 GB (Spruce plus the redone Onion art) to storage.

**New scrapes.** `scrape_files.derived_art` returns the Onion and Spruce files for a ROM from the media it just downloaded, so a normal `scrape` makes them with no extra command. `scrape_plan` and `clean scrapes` know the new types; `sync-roms check` and the storage cache handle them like `onion`.

## Left to the builder

- Module and function names, the progress display, and the exact column layout of the dry-run report.
- Whether the `spruce_*` keys are one type with a size suffix or three types in `BUCKET_MEDIA` (they must be listed there and in `SCRAPER_TYPES`).
- The gamelist `image` tag for QOI, from the PyUI source.
- Tests: encoder round trip, tier sizes and skip rule, the planner (Spruce card installs QOI and removes old PNGs, a missing key installs nothing), dry-run counts, `derived_art` for the new order, `--for` selection.
- Documenting the new storage prefixes and the command in `CLAUDE.md`.
