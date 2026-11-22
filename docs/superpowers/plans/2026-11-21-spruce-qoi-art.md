# Spruce QOI Box Art Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Spruce cards get QOI box art in the layout spruceOS's PyUI reads (no on-device conversion), make Onion and Spruce art from covers then miximages, and add `sync-roms scrape art` to make that art for everything already in storage, with a dry run.

**Architecture:** A pure-Python QOI encoder plus a single `make_art(src, dst, box)` entry point that writes a PNG (Onion) or QOI (Spruce) by the destination extension. `scrape_files.derived_art` returns the Onion file and the three Spruce files for a ROM; new scrapes and the new `scrape art` command both upload them through the existing `upload.run_uploads` shrink path. Sync installs the Spruce QOI files instead of the Onion PNG on `spruce` cards.

**Tech Stack:** Python 3.12+, Pillow (becomes a runtime dependency), `unittest`, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-21-spruce-qoi-art-design.md`

## Global Constraints

- Run everything with `uv run` (`uv run python -m unittest discover -s tests`); never bare `python`/`pip`. Add the dependency with `uv add`.
- Conventional Commits, lowercase, imperative (`feat(spruce): ...`). Commit after each task.
- Spruce art sizes: `spruce` fit in 640x480, `spruce_med` 400x300, `spruce_small` 200x200; Onion PNG stays 250x360. Shrink to fit, aspect ratio kept, never enlarged. QOI is RGBA (4 channels, sRGB, header `qoif`).
- Storage keys: `scrapes/<system>/spruce/<stem>.qoi`, `.../spruce_med/<stem>.qoi`, `.../spruce_small/<stem>.qoi`; Onion keeps `scrapes/<system>/onion/<stem>.png`. ROMs in subfolders (a `/` in the stem) get no art.
- Source order for both targets: `covers`, then `miximages`; for PICO-8 (`pico8/`) then the cart's own picture, the `.p8.png` in storage (pseudo source type `cart`). A cart's stem is its ROM name without the final extension (`foo.p8`), so its art keys are `scrapes/pico8/onion/foo.p8.png` and `scrapes/pico8/spruce/foo.p8.qoi`, and its card files `Imgs/foo.p8.png` / `Imgs/foo.p8.qoi`. The 160x205 cart picture is never enlarged, so a cart only gets the `spruce` tier.
- Card layout for Spruce: `Imgs/<ROM>.qoi`, `Imgs_med/<ROM>.qoi`, `Imgs_small/<ROM>.qoi`; no PNG or JPG may be left in a Spruce card's `Imgs/` (it makes PyUI prompt to convert).
- A `spruce_med` file is made only if the source's fit in 400x300 differs from its fit in 640x480; a `spruce_small` file only if its fit in 200x200 differs from its fit in 400x300. Missing tiers are fine: PyUI falls back small, then med, then large.
- Storage is read through `inventory.py`, never `s3.list_*`. Nothing personal goes to storage. Do not run anything that writes to the real storage (`scrape art` without `--dry-run`, `upload`): tests use the mocks in the existing scrape tests only.
- Repo files must not contain notes about the bucket's contents. Be concise in docs and messages.

## Review Focus

- A cover that is not a readable image (one 3dbox PNG in storage already is not): the run reports it, skips that ROM, and carries on; the failure count is non-zero.
- Source image modes other than RGB: palette PNG with transparency, grayscale, 16-bit, CMYK JPEG. The QOI must still come out as correct RGBA.
- A tiny source (smaller than 200x200): only `spruce` is made, no med/small copies, nothing enlarged.
- Re-running `scrape art` after an interruption: existing keys are skipped, nothing is remade without `--replace`.
- A Spruce card synced before this change (PNGs in `Imgs/`): the PNGs are removed and replaced by QOI, none left behind.
- PICO-8 carts: with no scraped cover or miximage, a cart's own picture becomes the Onion PNG and the Spruce QOI, in a normal scrape and in `scrape art`; on a Spruce card no PNG copy of a cart's picture goes into `Imgs/`.
- `--dry-run` reads no image and changes nothing; `--for` accepts only `onion`, `spruce`, `both`.

---

### Task 1: QOI encoder and the Pillow dependency

**Files:**
- Create: `src/sync_roms/qoi.py`
- Modify: `pyproject.toml` (Pillow into `dependencies`), `uv.lock`
- Test: `tests/test_qoi.py`

**Interfaces:**
- Produces: `qoi.encode(image) -> bytes` where `image` is a `PIL.Image.Image` of any mode; it converts to RGBA and returns a complete QOI file (14-byte header, chunks, 8-byte end marker). Raises `ValueError` for a zero-size image.

- [ ] **Step 1: Write the failing tests** in `tests/test_qoi.py`. The test module contains its own small reference decoder `decode(data) -> (width, height, rgba bytes)` written straight from the QOI spec (ops: INDEX, DIFF, LUMA, RUN, RGB, RGBA), because Pillow cannot read QOI. Tests, each building an image with Pillow, encoding, decoding and comparing pixels: `test_flat_color_round_trip` (RGBA 8x8 solid), `test_gradient_round_trip` (RGB 64x48 gradient, exercises DIFF/LUMA/RGB), `test_alpha_round_trip` (RGBA with varying alpha, exercises the RGBA op), `test_palette_with_transparency_round_trip` (mode `P` with a transparent index), `test_grayscale_and_16bit_become_rgba` (modes `L` and `I;16`), `test_header` (magic `qoif`, big-endian width and height, channels 4, colorspace 0, ends with `\x00\x00\x00\x00\x00\x00\x00\x01`), `test_long_run_is_split_at_62` (200 identical pixels decode right).
- [ ] **Step 2: Run to verify it fails.** Run: `uv run python -m unittest tests.test_qoi -v`. Expected: FAIL, `No module named 'sync_roms.qoi'`.
- [ ] **Step 3: Implement `qoi.encode`** in `src/sync_roms/qoi.py`, following the QOI spec. Hash is `(r*3 + g*5 + b*7 + a*11) % 64`. Read pixels once with `image.convert("RGBA").tobytes()` and loop over them; keep it a plain loop (about 0.1 s for 640x480).
- [ ] **Step 4: Run to verify it passes.** Same command. Expected: all PASS.
- [ ] **Step 5: Add Pillow as a runtime dependency.** Run `uv add Pillow`; keep the existing `images` extra and `dev` group as they are. Run the full suite: `uv run python -m unittest discover -s tests`. Expected: PASS.
- [ ] **Step 6: Commit.** `git add src/sync_roms/qoi.py tests/test_qoi.py pyproject.toml uv.lock` then `git commit -m "feat(spruce): add a QOI encoder and make Pillow a dependency"`.

---

### Task 2: Art model, `make_art` and the new source order

**Files:**
- Modify: `src/sync_roms/scrape_plan.py` (constants near lines 20-25, `can_shrink`/`shrink_png` near 232-265), `src/sync_roms/scrape_files.py` (`derived_art`, line 32), `src/sync_roms/upload.py` (`shrink_and_send`, line 188)
- Test: `tests/test_firmware_scrapes.py` (`DerivedArtTest`, line 369), `tests/test_scrape_art_model.py` (new), `tests/test_upload.py` (line 865 stub)

**Interfaces:**
- Produces in `scrape_plan`:
  - `ONION_ART = ("covers", "miximages")`
  - `SPRUCE_TIERS = (("spruce", (640, 480)), ("spruce_med", (400, 300)), ("spruce_small", (200, 200)))`
  - `SPRUCE_TYPES = tuple(t for t, _ in SPRUCE_TIERS)`
  - `BUCKET_MEDIA = MEDIA_TYPES | {ONION_TYPE, *SPRUCE_TYPES}`
  - `fit(size, box) -> (int, int)`: the size an image of `size` becomes when shrunk to fit `box`, never enlarged, each side at least 1.
  - `spruce_tiers(size) -> list[str]`: the tier type names wanted for a source of `size`, per the med/small rule above (always includes `"spruce"`).
  - `can_make_qoi() -> bool`: true when Pillow imports.
  - `make_art(src, dst, box) -> None`: writes `src` shrunk to fit `box` to `dst`; `.qoi` destination encodes QOI through `qoi.encode`, any other destination does what `shrink_png` does today (keep `shrink_png` as is and call it).
- Produces in `scrape_files`: `derived_art(system, stem, found, size=None) -> [(key, src, box)]`. `found` is `{media type: local path or None}`; `size` is the source's `(w, h)` or None. Returns the Onion file (`scrapes/<system>/onion/<stem>.png`, box `ONION_MAX`) plus, when `can_make_qoi()` and `size` is None or `spruce_tiers(size)` lists the tier, each Spruce file (`scrapes/<system>/<tier type>/<stem>.qoi`, tier box). `src` is the first of `ONION_ART` present in `found`, and for `system == "pico8"` the first of `ONION_ART + ("cart",)`; the caller puts the local cart file in `found` under `"cart"`. No entries for a stem containing `/`.
- Consumes: `qoi.encode` from Task 1.

- [ ] **Step 1: Write failing tests** in `tests/test_scrape_art_model.py`: `test_fit_never_enlarges` (`fit((100, 50), (640, 480)) == (100, 50)`), `test_fit_keeps_aspect` (`fit((1280, 960), (640, 480)) == (640, 480)`, `fit((700, 1000), (640, 480)) == (336, 480)`), `test_tiers_for_a_large_source` (`spruce_tiers((1280, 960)) == ["spruce", "spruce_med", "spruce_small"]`), `test_tiers_for_a_small_source` (`spruce_tiers((150, 100)) == ["spruce"]`), `test_tiers_for_a_mid_source` (`spruce_tiers((500, 400)) == ["spruce", "spruce_med", "spruce_small"]` and `spruce_tiers((300, 250)) == ["spruce", "spruce_small"]`, since 300x250 fits 400x300 unchanged), `test_make_art_writes_qoi_for_a_qoi_destination` (write a 300x200 PNG, `make_art(src, "x.qoi", (200, 200))`, bytes start with `qoif` and the header size is 200x133), `test_make_art_writes_png_otherwise`. In `tests/test_firmware_scrapes.py` replace `DerivedArtTest` cases: `test_art_makes_onion_and_spruce_art` (keys for onion, spruce, spruce_med, spruce_small and their boxes), `test_miximage_is_used_when_there_is_no_cover`, `test_cover_is_preferred_over_a_miximage`, `test_pico8_falls_back_to_the_cart_picture` (`derived_art("pico8", "foo.p8", {"cart": "c.p8.png"})` has src `c.p8.png`; a cover wins over it; other systems ignore a `cart` entry), `test_three_dboxes_and_screenshots_are_no_longer_used` (`{"3dboxes": "d.png", "screenshots": "s.png"}` gives `[]`), `test_a_rom_in_a_subfolder_gets_no_art`, `test_small_source_gets_only_the_large_spruce_tier` (pass `size=(150, 100)`), `test_no_spruce_art_without_pillow` (patch `can_make_qoi` to False: only the Onion entry).
- [ ] **Step 2: Run to verify they fail.** `uv run python -m unittest tests.test_scrape_art_model tests.test_firmware_scrapes -v`. Expected: FAIL (missing names).
- [ ] **Step 3: Implement** the constants and functions above in `scrape_plan.py`, and `derived_art` in `scrape_files.py`. Pillow's `Image.thumbnail` with `Image.LANCZOS` does the resize in `make_art` for QOI.
- [ ] **Step 4: Make the upload shrink path format-aware.** In `upload.py` `shrink_and_send`, name the temp file with the extension of `job[0]` (the key) instead of `.png`, and run `scrape_plan.make_art(job[1], art, job[3])` in a `concurrent.futures.ProcessPoolExecutor(os.cpu_count() or 4)` (created next to the `shrinkers` pool, only when a job has a shrink box) instead of calling `shrink_png` in the thread: the shrinker thread does `procs.submit(scrape_plan.make_art, ...).result()`. The QOI encoder is a pure-Python loop that holds the GIL, so threads alone would use one core; `make_art` is a top-level function so it can be pickled for the spawned processes. Shut the process pool down with the others on Ctrl-C and on exit. Update the stub in `tests/test_upload.py` (line 865) to the `make_art` name and add `test_qoi_jobs_are_uploaded_as_qoi` (a job whose key ends `.qoi` reaches the stub with a `.qoi` destination).
- [ ] **Step 4b: Test the parallelism.** `test_qoi_conversion_uses_worker_processes` in `tests/test_upload.py`: with two QOI shrink jobs, the stub or a recorded `os.getpid()` inside `make_art` shows it ran in a process other than the test's own. Keep the test fast (tiny images).
- [ ] **Step 5: Run the affected tests and the full suite.** `uv run python -m unittest discover -s tests`. Expected: PASS except tests for behavior Task 3 changes; fix any failures that are only the old source order (`3dboxes`, `screenshots`) by updating the test to covers/miximages.
- [ ] **Step 6: Commit.** `feat(spruce): make Onion and Spruce art from covers then miximages`.

---

### Task 3: New scrapes make the art; clean and listings know the new types

**Files:**
- Modify: `src/sync_roms/scrape_online.py` (line 24 `PICO8_PICTURES`, line 218 `SCRAPER_TYPES`, lines 650-660 and 875-877)
- Modify: `src/sync_roms/scrape_files.py` (`plan_clean`, line 54, if it special-cases `onion`; check it handles any type in `BUCKET_MEDIA`)
- Test: `tests/test_scrape_run.py` (lines 583-620, 1175-1185 and the test near 1165 that expects `onion/`), `tests/test_scrape_art_model.py`

**Interfaces:**
- Consumes: `scrape_files.derived_art`, `scrape_plan.can_shrink`, `scrape_plan.can_make_qoi`, `SPRUCE_TYPES`.
- Produces: a normal `scrape` uploads the Spruce QOI files together with the Onion PNG for each new ROM; `scrape_online.SCRAPER_TYPES` includes the three Spruce types; the kept-file rule still holds (a type already in storage counts as found).

- [ ] **Step 1: Write failing tests** in `tests/test_scrape_run.py`: `test_scrape_makes_spruce_art_with_the_onion_art` (after a scrape of one ROM, `scrapes/gba/spruce/a.qoi`, `spruce_med/a.qoi`, `spruce_small/a.qoi` and `onion/a.png` are stored; the stored `spruce` file starts with `qoif`), `test_scrape_skips_spruce_art_without_pillow` (patch `can_make_qoi` False: warns with a Pillow message, makes the Onion PNG only), `test_existing_spruce_art_is_kept` (a stored `spruce/a.qoi` is not rewritten), `test_pico8_cart_without_scraped_art_gets_art_from_the_cart` (a `pico8/foo.p8.png` cart ScreenScraper has no pictures for ends up with `scrapes/pico8/onion/foo.p8.png` and `scrapes/pico8/spruce/foo.p8.qoi`, no `spruce_med`/`spruce_small`), `test_clean_scrapes_removes_spruce_art_of_a_gone_rom` (use the `plan_clean` helpers the existing clean tests use: the three Spruce keys of a ROM that is not in storage are deleted). Adjust the existing derived-art tests there that name `3dboxes`/`screenshots` sources.
- [ ] **Step 2: Run to verify they fail.** `uv run python -m unittest tests.test_scrape_run tests.test_firmware_scrapes -v`.
- [ ] **Step 3: Implement.** For a PICO-8 `.p8.png` ROM with no cover or miximage found, download the cart from storage (`s3.download((f"pico8/{rom}", local path, size))`) into the scrape's temp folder and pass it as `found["cart"]`. Add `*scrape_plan.SPRUCE_TYPES` to `SCRAPER_TYPES`; in `scrape_system` pass the source image size (`PIL.Image.open(src).size`, wrapped so an unreadable image gives `size=None`) to `derived_art`; when `not scrape_plan.can_make_qoi()` print a yellow warning naming Pillow once, next to the existing `NO_SHRINK` warning. Make `plan_clean` treat the new types like `onion` if it needs anything.
- [ ] **Step 4: Run to verify they pass, then the full suite.**
- [ ] **Step 5: Commit.** `feat(spruce): scrapes make Spruce QOI art as they go`.

---

### Task 4: `sync-roms scrape art`

**Files:**
- Create: `src/sync_roms/scrape_art.py`
- Modify: `src/sync_roms/cli.py` (the `LEGACY` table near line 512, `SUBCOMMANDS` text line 32, `PLAIN_FLAGS`/`VALUE_FLAGS`, `build_parser`, `check_modes`, the dispatch near line 780, help `TOPICS["scrape"]` near line 225), and completion data (`tests/test_completion.py` shows what it reads)
- Test: `tests/test_scrape_art_cmd.py` (new), `tests/test_scrape_cli.py`, `tests/test_completion.py`

**Interfaces:**
- Produces: `scrape_art.plan_art(listing, targets, replace) -> ArtPlan` where `listing` is `{key: size}` for `scrapes/<system>/`, `targets` is a subset of `{"onion", "spruce"}`; `ArtPlan` has per target: `make` (list of `(stem, source key)` needing files), `have` (count of ROMs that already have the target's files), and `estimate_bytes` (`len(make)` times the constants `EST_SPRUCE_BYTES = 540_000` or `EST_ONION_BYTES = 150_000`, per ROM). It also has `no_source`: the count of listed top-level stems that have neither a cover nor a miximage (they only have other media). Rule: a ROM stem (no `/`) is a candidate when the listing holds a `covers` or `miximages` key for it; the source is the cover, else the miximage. For system `pico8` a `.p8.png` cart in the system's storage listing (`pico8/<rom>`, listed through `inventory.files("pico8/")`) is also a candidate, its source being the cart itself; the run downloads it like any source. With `replace` false a target is skipped for a ROM when its keys already exist (Spruce: the `spruce` key exists).
- Produces: `scrape_art.art_command(args) -> int` for `sync-roms scrape art [SYSTEM | --system ID] [--for onion|spruce|both] [--dry-run] [--replace] [--workers N]`.
  - `--dry-run`: lists the storage folders through `inventory.files`, prints per system and target the ROMs with a source, files it would make (for Spruce "up to 3 per ROM"), how many already exist, ROMs with no source, and a total with an estimated size labeled as an estimate; reads no image, writes nothing, exits 0.
  - Real run: for each system, downloads each source (`s3.download((key, path, size))` into a temp dir), reads its size, builds jobs through `scrape_files.derived_art(system, stem, found, size)`, filters out keys already present unless `--replace`, uploads through `upload.run_uploads(jobs, quiet=True)` (which converts in parallel in one worker process per core), prints a final line with made, skipped and failed counts, returns 1 if any failed. `--workers N` bounds the number of parallel source downloads (default CPU count). Unreadable sources are counted as failed and skipped. Ctrl-C keeps what finished and exits 130.
  - Refuses (exit 2, clear message) when Pillow is missing and Spruce is a target, and when `--for` is not `onion|spruce|both`.
- Consumes: `scrape_plan.SPRUCE_TIERS`, `scrape_files.derived_art`, `upload.run_uploads`, `scrape_online._pick_systems` (system choice by bucket name, as `scrape missing` does).

- [ ] **Step 1: Write failing tests** in `tests/test_scrape_art_cmd.py` (follow the fixtures in `tests/test_scrape_run.py` for a fake storage; for pure planning tests use plain dicts). `plan_art` tests: `test_candidates_need_a_cover_or_miximage`, `test_cover_is_the_source_over_a_miximage`, `test_existing_files_are_skipped_without_replace`, `test_replace_remakes_existing_files`, `test_subfolder_roms_are_ignored`, `test_for_onion_only_plans_no_spruce`, `test_pico8_cart_is_a_candidate_with_the_cart_as_source`, `test_pico8_cart_with_a_cover_uses_the_cover`. Command tests: `test_dry_run_reports_counts_and_writes_nothing` (output contains per-target counts and the word "estimate"; storage unchanged; no image opened: patch `PIL.Image.open` to raise), `test_run_makes_all_four_files_for_a_rom` (stored `onion/a.png`, `spruce/a.qoi`, `spruce_med/a.qoi`, `spruce_small/a.qoi`), `test_rerun_makes_nothing_new`, `test_replace_remakes_onion_art_with_the_new_source_order`, `test_unreadable_cover_is_reported_and_the_rest_continue` (exit 1, other ROM made), `test_for_spruce_only`, `test_bad_for_value_is_refused`, `test_spruce_without_pillow_is_refused`, `test_one_system_by_name`. In `tests/test_scrape_cli.py` add parsing tests: `scrape art`, `scrape art gba --for spruce --dry-run`, `scrape art --replace --workers 4`, and that `--for` and `--workers` are refused outside `scrape art`. Update `tests/test_completion.py` for the new subcommand and flags.
- [ ] **Step 2: Run to verify they fail.** `uv run python -m unittest tests.test_scrape_art_cmd tests.test_scrape_cli tests.test_completion -v`.
- [ ] **Step 3: Implement `plan_art` and `art_command`** in `scrape_art.py`.
- [ ] **Step 4: Wire the CLI.** Add `("scrape", "art"): ["--scrape-art"]` to `LEGACY` before `("scrape",)`; `--scrape-art` (`nargs="?"`, like `--scrape-missing`); `--for` and `--workers` as value flags (add to `VALUE_FLAGS` and the parser); `check_modes` entries (the mode name, `--dry-run` and `--replace` allowed for it, the system-argument shuffle `scrape art SYSTEM`, the "only applies to" errors, and the `--system` message listing `scrape art`); dispatch to `scrape_art.art_command(args)`; add the line to the `scrape` help and the topic text. Keep `--replace` valid for `scrape art` (today it errors unless the mode is `--upload`).
- [ ] **Step 5: Run to verify they pass, then the full suite.**
- [ ] **Step 6: Commit.** `feat(scrape): add scrape art to make Onion and Spruce art for what's in storage`.

---

### Task 5: Spruce cards install QOI and drop the PNGs

**Files:**
- Modify: `src/sync_roms/scrape_plan.py` (`ONION_LAYOUTS` branches in `plan_scrapes` ~line 199, `build_scrape_plan` pico8 branch ~line 366, `stale_media` ~line 498, `prune_empty_systems` ~line 516, `card_stems`/`scrape_cost` callers), `src/sync_roms/cli.py` line 941 if it assumes `Imgs/` only
- Test: `tests/test_firmware_scrapes.py`, `tests/test_scrape_run.py` where Spruce card scrapes are tested

**Interfaces:**
- Consumes: `SPRUCE_TIERS`, `BUCKET_MEDIA` types in the scrape index (`found` has keys `spruce`, `spruce_med`, `spruce_small`).
- Produces: for `layout_name == "spruce"` (and only it): `plan_scrapes` adds jobs `Imgs/<base>.qoi` from `found["spruce"]`, `Imgs_med/<base>.qoi` from `found["spruce_med"]`, `Imgs_small/<base>.qoi` from `found["spruce_small"]`, each only when that key exists; it never adds an `onion` PNG and writes no `image` tag in the `miyoogamelist.xml` entry (name only) unless Step 1's source check below says the gamelist needs it; `Imgs/`, `Imgs_med/` and `Imgs_small/` of a Spruce card hold nothing but `.qoi` files for ROMs on the card, so `stale_media` also lists every non-`.qoi` file in `Imgs/` (and the three folders' `.qoi` files whose ROM is gone); a PICO-8 cart gets no `Imgs/` copy of its own picture on Spruce (its art is the QOI from storage, made from the cart when nothing was scraped). Onion and Allium keep the existing copy as a fallback for carts with no art in storage yet. Onion, Allium and NextUI behavior is unchanged.

- [ ] **Step 1: Check the gamelist question against the PyUI source** (`github.com/spruceUI/spruceOS`, `App/PyUI/main-ui/games/utils/rom_utils.py` and `menus/games/utils/rom_select_options_builder.py`): does PyUI show a QOI in `Imgs/` for a ROM with no `<image>` tag in `miyoogamelist.xml`? The builder code looks up `Imgs/<ROM name>.qoi` by name first, so the expected answer is yes and the tag is omitted. If the source shows the tag is required, write `./Imgs/<base>.qoi` instead and use that in the tests below.
- [ ] **Step 2: Write failing tests:** `test_spruce_installs_qoi_in_three_folders` (jobs for `Imgs/a.qoi`, `Imgs_med/a.qoi`, `Imgs_small/a.qoi`, none for the onion PNG), `test_spruce_rom_with_only_an_onion_png_gets_no_image` (installs nothing for art, entry has the name only), `test_spruce_gamelist_has_no_png_image_tag`, `test_onion_still_installs_the_png` and `test_allium_and_nextui_unchanged` (regression guards), `test_stale_spruce_pngs_are_removed` (a card with `Imgs/a.png` for a present ROM lists it as stale), `test_stale_spruce_qoi_of_a_gone_rom`, `test_spruce_pico8_cart_picture_is_not_copied_to_imgs`, `test_spruce_pico8_cart_art_from_storage_is_installed_as_qoi`, `test_onion_pico8_cart_without_art_still_copies_its_picture`, `test_empty_spruce_system_removes_all_three_art_folders` (extend `prune_empty_systems` for `Imgs_med`/`Imgs_small`).
- [ ] **Step 3: Run to verify they fail.**
- [ ] **Step 4: Implement** in `scrape_plan.py` with a `layout_name == "spruce"` branch placed before the shared `ONION_LAYOUTS` branch. Keep `ONION_LAYOUTS` as it is for everything else.
- [ ] **Step 5: Run to verify they pass, then the full suite.**
- [ ] **Step 6: Commit.** `feat(spruce): install QOI art on Spruce cards and remove old PNGs`.

---

### Task 6: Documentation and final checks

**Files:**
- Modify: `CLAUDE.md` (the Data files section: the `onion` source order, the `spruce*` storage prefixes and card layout, `scrape art`), `README.md` if it lists scrape subcommands, `src/sync_roms/data/layouts.json` Spruce `note` (art now QOI in `Imgs/`, `Imgs_med/`, `Imgs_small/`), `tools/`-level docs if any mention the Onion art source order
- Test: `tests/test_readme.py`, `tests/test_setup_guide.py` (run only)

**Interfaces:** none.

- [ ] **Step 1: Update the docs** in the files above, in the same terse style: covers then miximages for `scrapes/<system>/onion/`; the three `spruce*` prefixes (`.qoi`, 640x480, 400x300, 200x200, shrink to fit); Spruce cards get `Imgs/`, `Imgs_med/` and `Imgs_small/` QOI files and no PNGs, so PyUI does not prompt; `sync-roms scrape art` with `--for`, `--dry-run`, `--replace`, `--workers`.
- [ ] **Step 2: Run the full suite and check the help.** `uv run python -m unittest discover -s tests`, then `uv run sync-roms scrape --help` and `uv run sync-roms --help`. Expected: tests PASS, and the help output lists `scrape art`. Do not run `scrape art` itself.
- [ ] **Step 3: Commit.** `docs(spruce): document QOI art and scrape art`.

---

**Not part of this plan (done by the owner afterwards):** `sync-roms scrape art --dry-run` to see the counts, then `sync-roms scrape art --replace --for onion` and `sync-roms scrape art --for spruce` against real storage, then a Spruce card sync.
