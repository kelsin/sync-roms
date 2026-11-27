# Pixel Art Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `collections publish` also writes `https://sync-roms.games/pixel-art/`: every pixel picture sync-roms draws, at one art pixel per image pixel, with a hover/tap large view on a pixel grid and, for artists, each picture's theme file paths and sizes.

**Architecture:** A new `pixel_art_page.py` renders every sprite (`sprite.render(..., scale=1)`), every frame (from a real `build_theme` of `Pixel Consoles - Gruvbox` into a temp folder, read back one pixel per cell from the frames' `Canvas` objects) and every box art (`art-box/Imgs/*.png` reduced 4x) as PNGs under `pixel-art/img/`, and fills a static template (`data/pixel-art-page/`) with a JSON data block. `pages_site.build` calls it and links it from the root page.

**Tech Stack:** Python 3.12+, Pillow, unittest, plain HTML/CSS/JS (no external URLs).

**Spec:** `docs/superpowers/specs/2026-11-27-pixel-art-page-design.md`

## Global Constraints

- Runs on Python 3.12; always `uv run`. Tests: `uv run python tools/run_tests.py` (or `uv run python -m unittest tests.<module>`), stdin closed (`< /dev/null`).
- Every test module imports `helpers` (which imports `isolate`) before `sync_roms`. No test touches real storage: base themes are faked (`tests/test_frames.make_base` on top of `tests/test_custom_themes.make_base`).
- The page has no external URLs (no scripts, fonts, images or stylesheets from elsewhere). Colours as in `data/pages-site/index.html` (`--bg`, `--surface`, `--text`, `--muted`, `--border`, `--accent`), light and dark.
- Frames palette: `palettes.get("Gruvbox")`, fixed in code. Base theme: `pixel_consoles.BASE` (`"SPRUCE"`) through `custom_themes.fetch_base`.
- Never resample with anything but `Image.NEAREST`; the browser scales with `image-rendering: pixelated` at integer scales only.
- Conventional Commits; never edit `__version__`, `CHANGELOG.md`, `.release-please-manifest.json`.
- Phone width: 16px side gutter, no horizontal page scroll.

## Review Focus

1. A picture source that gains a new entry later (a new system, app icon, frame or box): the page must show it with no code change — counts are derived from the sources, and tests compare against them.
2. A frame file whose footprint isn't a whole number of cells (odd leftovers): the 1-cell image must still equal the frame's cells exactly (Task 1 test on a 752x70-style leftover).
3. Large view on a phone or near the screen edge: it must stay fully on screen (16px gutter) and close on Escape / tap outside (manual check in Task 4).
4. `collections publish` with the base theme missing from storage or failing to download: nothing is committed or pushed, and the user gets the "Storage isn't reachable" style message (Task 4 test).
5. A label or path containing `<` or `&` in the data block: escaped like `collections_page.fill` (`<` → `<`), and the JS inserts text with `textContent`, never `innerHTML` (Task 4 test on the filled HTML).

---

## File Structure

- Modify `src/sync_roms/custom_themes/pixel/frames.py`: `Canvas.cell_image()`; `apply(..., canvases=None)` records each drawn canvas.
- Modify `src/sync_roms/custom_themes/pixel/build.py`: `build_theme(..., canvases=None)` passes it to `frames.apply`.
- Create `src/sync_roms/pixel_art_page.py`: collects every picture, writes images and the page.
- Create `src/sync_roms/data/pixel-art-page/page.html`, `page.css`, `page.js`.
- Modify `src/sync_roms/pages_site.py`, `src/sync_roms/data/pages-site/index.html`.
- Modify `docs/github-pages.md`, `CLAUDE.md` (the `pages-site/` line and a `pixel-art-page/` line under Repo data), `src/sync_roms/cli.py` help for `collections publish` (one clause: "and the pixel art page").
- Tests: `tests/test_frames.py` (Task 1), new `tests/test_pixel_art_page.py` (Tasks 2–4), `tests/test_pages_site.py` (Task 4).

---

### Task 1: Frames expose their cell grid

**Files:**
- Modify: `src/sync_roms/custom_themes/pixel/frames.py` (`Canvas`, `apply`)
- Modify: `src/sync_roms/custom_themes/pixel/build.py` (`build_theme`)
- Test: `tests/test_frames.py`

**Interfaces:**
- Produces: `Canvas.cell_image() -> PIL.Image` (RGBA, `cols x rows`; each cell's colour at its position, the `background` colour (alpha 255) under empty cells when set, else transparent). `frames.apply(theme_dir, palette, canvases=None)`: when `canvases` is a dict, sets `canvases[f"{folder}/{file}"] = canvas` for every frame drawn. `build_theme(base_dir, out_dir, name, kind, palette, canvases=None)` passes it through. Return values unchanged.

- [ ] **Step 1: Write the failing tests** in `tests/test_frames.py`:
  - `test_cell_image_matches_drawn_frame`: build a theme from `make_base` (as the existing build tests do) with `canvases={}`; for every `skin/...` entry, `canvas.cell_image().resize((cols*cell, rows*cell), Image.NEAREST)` equals the built file cropped to `(ox, oy, ox+cols*cell, oy+rows*cell)` (compare with `ImageChops.difference(...).getbbox() is None`). Include the `skin_752x560` copies (odd leftovers) via `COPIES`.
  - `test_apply_without_canvases_unchanged`: `apply` with no `canvases` returns the same written list as with one, and `set(canvases) == set(written)`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_frames < /dev/null` — expected: the two new tests FAIL (`cell_image` / `canvases` unknown).
- [ ] **Step 3: Implement** `Canvas.cell_image`, the `canvases` parameter of `apply` and of `build_theme`.
- [ ] **Step 4: Run** `uv run python -m unittest tests.test_frames tests.test_custom_themes < /dev/null` — expected: all PASS.
- [ ] **Step 5: Commit** `git commit -m "refactor(themes): let frames report their cell grids"`

---

### Task 2: Sprite sections (no storage)

**Files:**
- Create: `src/sync_roms/pixel_art_page.py`
- Test: `tests/test_pixel_art_page.py`

**Interfaces:**
- Produces:
  - `PALETTE = "Gruvbox"`
  - `Item` = dict `{"label": str, "img": str, "w": int, "h": int, "dim"?: str, "files": [{"path": str, "size": [w, h] | None}], "cell"?: int, "note"?: str}`; `img`/`dim` are paths relative to the page (`img/<section>/<name>.png`, `<name>-n.png` for the unselected state). `size` is the file's size in the built 640x480 theme, `None` when unknown.
  - `Section` = dict `{"id": str, "title": str, "items": [Item]}`.
  - `sprite_sections(img_dir: str, theme_dir: str | None = None) -> list[Section]`: writes the PNGs under `img_dir` and returns, in this order, sections `menu`, `systems-shared`, `systems-consoles`, `systems-controllers`, `regions`, `apps`, `settings`, `status`. `theme_dir` (a built theme) supplies file sizes; `None` leaves sizes `None` except the fixed ones (`build.ICON_SIZE` for system icons, `build.MENU_SIZE` for menu icons).

Rules the code must follow:
- Every sprite: `img` = `render(draw(), 1, "sel")`, `dim` = `render(draw(), 1, "n")`.
- `menu`: each `menu.SPRITES` key, plus `game-consoles` (`menu.handheld`) and `game-controllers` (`menu.controller`), files `skin/ic-<key>-n.png` and `skin/ic-<key>-f.png` (both games icons are `ic-game-*`, labelled with their theme).
- Systems: ids where `build.systems("CONSOLES")[id] is build.systems("CONTROLLERS")[id]` go to `systems-shared`, the rest to both theme sections. Label `ids.IDS.get(id, id)`; files `icons/<id>.png`, `icons/sel/<id>.png`.
- `regions`: every `(icon, region, part)` of `variants.VARIANTS`; label `"<IDS name> — <region upper> <console|pad>"`; `note` `"used by the themes"` when `region == variants.REGION[icon]`, else `"not used by the themes"`; no `files` for unused ones.
- `apps`, `settings`, `status`: one item per `app_icons.ICONS`, `ui_settings.ICONS`, `ui_status.ICONS` key; files `[key]`; label the key's file name without `.png`; when `theme_dir` has no such file, `note` `"not in the SPRUCE base"` (apps excepted: build always draws `icons/app/`, size `app_icons.APP_SIZE`). Selected state only for these three (build draws them `"sel"`): no `dim`.

- [ ] **Step 1: Write failing tests** in `tests/test_pixel_art_page.py` (imports `helpers` first), with `img_dir` a temp folder and `theme_dir=None`:
  - `test_every_sprite_is_on_the_page`: per section, item count equals: `len(menu.SPRITES) + 2`; shared/consoles/controllers counts derived from the two `build.systems` dicts as above; `sum(len(regions) * 2 for regions in variants.VARIANTS.values())` (two parts each); `len(app_icons.ICONS)`, `len(ui_settings.ICONS)`, `len(ui_status.ICONS)`.
  - `test_images_are_one_pixel_per_art_pixel`: for `systems-consoles` item `gb`, the PNG at `img` equals `render(build.systems("CONSOLES")["gb"](), 1, "sel")` byte for byte as RGBA, `w/h` equal its size, and `dim` equals the `"n"` render.
  - `test_files_and_notes`: the `gb` item's files are `icons/gb.png` and `icons/sel/gb.png` with size `[120, 130]`; an unused region item has `note == "not used by the themes"` and no files; a status item with `theme_dir=None` has `note == "not in the SPRUCE base"`.
  - `test_image_paths_unique`: no two items share an `img` or `dim`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_pixel_art_page < /dev/null` — expected FAIL (module missing).
- [ ] **Step 3: Implement** `PALETTE` and `sprite_sections` in `src/sync_roms/pixel_art_page.py`. Image names: the id or file stem, made filesystem-safe (`re.sub(r"[^A-Za-z0-9_.-]", "_", name)`), unique within a section.
- [ ] **Step 4: Run** the same command — expected PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(collections): render every pixel sprite for a pixel art page"`

---

### Task 3: Frame and box-art sections

**Files:**
- Modify: `src/sync_roms/pixel_art_page.py`
- Test: `tests/test_pixel_art_page.py`

**Interfaces:**
- Consumes: Task 1's `build_theme(..., canvases=)`, `Canvas.cell_image()`; Task 2's `Item`/`Section`.
- Produces:
  - `HINT_SIZES = {"context-a.png": (26, 26), "context-b.png": (26, 26), "context-x.png": (26, 26), "context-y.png": (26, 26), "context-menu.png": (66, 26), "context-select.png": (66, 26), "context-start.png": (66, 26)}`
  - `build_frames_theme(base_dir: str, out_dir: str) -> tuple[str, dict]`: `build.build_theme(base_dir, out_dir, theme_name("Pixel Consoles", PALETTE), "CONSOLES", palettes.get(PALETTE), canvases=c)`; returns `(theme_dir, {"skin/<file>": Canvas})` keeping only `skin/` keys.
  - `frame_section(img_dir: str, canvases: dict) -> Section` (`id` `frames`): one item per canvas, sorted by file, `img` = `cell_image()`, `cell` = `canvas.cell`, files `[{"path": key, "size": list(canvas.size)}]`; plus every `HINT_SIZES` file not in `canvases` whose frame is in `frames.FRAMES`, drawn on `frames.Canvas(size, frames.cell_for(size, None, spec.small), (0, 0) + size, spec.background)` with `spec.draw(canvas, frames.shades(palette))`, `note` `"not in the SPRUCE base"`.
  - `box_section(img_dir: str) -> Section` (`id` `boxes`): one item per `data/themes/art-book-next/art-box/Imgs/*.png`, `img` the 336x480 file reduced to 84x120 with NEAREST; label the id; files `Collections/Imgs/<id>.png` [336, 480], `Collections/Imgs_med/<id>.png` [210, 300], `Collections/Imgs_small/<id>.png` [140, 200].

- [ ] **Step 1: Write failing tests**:
  - `test_frames_section_covers_what_themes_draw`: fake base = `test_custom_themes.make_base` + `test_frames.make_base(path, files=F, copies={})` where `F` is `test_frames.BASE` minus the seven `context-*` files and with the seven transparent-in-real-base files (`bg-grid-s`, `div-line-v-02`, `navbg`, `num-bg`, `preview-bg`, `statbg`, `thumb-default`) written fully transparent. Then the section's file paths == `{f"skin/{n}" for n in frames.FRAMES keys' file names} - those seven transparent ones`, and the seven hint items have `note == "not in the SPRUCE base"` and `w, h` == `HINT_SIZES[...]` divided by their `cell`.
  - `test_frame_image_is_cells`: for `skin/bg-title.png`, the item's PNG resized by `cell` with NEAREST equals the built file's cell-grid crop.
  - `test_box_reduction_exact`: for each box item, its PNG resized 4x with NEAREST equals the source `Imgs/<id>.png` (as RGB); count equals the folder's PNG count.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_pixel_art_page < /dev/null` — expected the new tests FAIL.
- [ ] **Step 3: Implement** `HINT_SIZES`, `build_frames_theme`, `frame_section`, `box_section`.
- [ ] **Step 4: Run** the same — expected PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(collections): add frames and box art to the pixel art page"`

---

### Task 4: The page, publishing and docs

**Files:**
- Create: `src/sync_roms/data/pixel-art-page/page.html`, `page.css`, `page.js`
- Modify: `src/sync_roms/pixel_art_page.py`, `src/sync_roms/pages_site.py`, `src/sync_roms/data/pages-site/index.html`, `src/sync_roms/cli.py` (publish help), `docs/github-pages.md`, `CLAUDE.md`
- Test: `tests/test_pixel_art_page.py`, `tests/test_pages_site.py`

**Interfaces:**
- Consumes: Tasks 2–3.
- Produces:
  - `pixel_art_page.write(out_dir: str, base_dir: str | None = None) -> None`: empties `out_dir`; `base_dir` defaults to `custom_themes.fetch_base(pixel_consoles.BASE)` (raises `BaseMissing`/`DownloadFailed`); builds the frames theme in a `tempfile.TemporaryDirectory`; writes `img/`, `page.css`, `page.js` and `index.html` = `page.html` with `{"palette": PALETTE, "home": "/", "sections": [...]}` in its `<script type="application/json" id="page-data">{}</script>` block (same escaping as `collections_page.fill`). Section order: menu, systems-shared, systems-consoles, systems-controllers, regions, apps, settings, status, frames, boxes. `sprite_sections` gets the built theme's dir for sizes.
  - `pages_site.build` calls `pixel_art_page.write(os.path.join(site_dir, "pixel-art"))` after the user's page. `pages_site.publish` also catches `custom_themes.BaseMissing` and `custom_themes.DownloadFailed` with the existing failure message, so nothing is committed.
  - The root `index.html` template has a link `<a href="pixel-art/">Pixel art</a>` (styled like the user links) with a one-line intro, above the credit.

Page behaviour (`page.js`, reading the data block; text always via `textContent`):
- Title "Pixel art", a line saying frames are shown in the palette name, a jump list of sections with counts, a "← All users" link to `home`.
- Each section: heading + count, a grid of tiles (dark tile background), each the `img` at an integer CSS scale (`image-rendering: pixelated`): 3x for sprites, 2x for frames and boxes, reduced to the largest integer that fits the tile width; label under it; `note` as a small muted line.
- Large view: `pointerenter` on a tile (when `matchMedia("(hover: hover)")`) or `click` (touch) opens a fixed panel; it draws `img` (and `dim` beside it, labelled "selected"/"unselected") on a `<canvas>` at the largest integer scale ≥ 4 that fits within the viewport minus 32px, with `imageSmoothingEnabled = false`, then a 1px grid line between every pixel in a colour that shows on light and dark pixels (e.g. `rgba(128,128,128,.55)`). Under it: label, native `w×h`, `cell` when present ("1 pixel = N screen pixels"), each file path with its size. Closes on `pointerleave` (hover mode), Escape, or a click outside. Positioned to stay inside the viewport.

- [ ] **Step 1: Write failing tests**:
  - `tests/test_pixel_art_page.py::test_write_page`: `write(out, base_dir=fake)` (fake base from Task 3) writes `index.html`, `page.css`, `page.js`; the data block parses as JSON with the ten section ids in order and every `img`/`dim` exists under `out`; `re.search(r'(src|href)=["\']?(https?:)?//', html_css_js)` finds nothing.
  - `test_data_escaped`: with `sprite_sections` patched to return one item labelled `"</script><b>&"`, the filled `index.html` contains no `</script><b>` and the JSON round-trips the label.
  - `tests/test_pages_site.py`: in `Site.setUp`, patch `pixel_art_page.write` with a stub that writes `index.html` in its folder (existing tests stay storage-free). `test_build_layout` adds: `pixel-art/index.html` exists and the root has `href="pixel-art/"`. New `test_publish_fails_without_base`: un-stub, patch `custom_themes.fetch_base` to raise `custom_themes.BaseMissing("SPRUCE")`; `pages_site.publish("kelsin")` raises `SystemExit` with code 1 and `git_ls_tree(self.bare, "main") == []`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_pixel_art_page tests.test_pages_site < /dev/null` — expected the new tests FAIL.
- [ ] **Step 3: Implement** the template files, `write`, the `pages_site` changes and the root link.
- [ ] **Step 4: Run** the same — expected PASS; then the full suite `uv run python tools/run_tests.py < /dev/null` — expected PASS (including `test_readme`).
- [ ] **Step 5: Manual check in the browser**: `uv run python -I -c "from sync_roms import pixel_art_page; pixel_art_page.write('<scratchpad>/pixel-art')"` (real base from the cache/storage), serve it with `python -m http.server` from the scratchpad and open it in the built-in browser. Check: all ten sections show; pixels are crisp; hovering opens the grid view with lines between pixels, a selected/unselected pair for icons, and paths and sizes; on the mobile preset (375 wide) a tap opens it inside the screen, Escape and tap outside close it; no horizontal scroll; dark and light schemes both readable.
- [ ] **Step 6: Docs**: `docs/github-pages.md` (section 8 "Check" adds `https://sync-roms.games/pixel-art/`; the intro says publish also builds the pixel art page and needs the `SPRUCE` base theme in storage); `CLAUDE.md` (the `pages-site/` bullet names the root's pixel-art link; a new Repo data bullet for `pixel-art-page/` saying what `pixel_art_page.write` puts in `pixel-art/`: every pixel picture at one art pixel per image pixel, frames in Gruvbox from a real build of the SPRUCE base, hint pills drawn at `HINT_SIZES`, transparent-in-base frames left off); `cli.py` publish help mentions the pixel art page.
- [ ] **Step 7: Commit** `git commit -m "feat(collections): publish a pixel art page to sync-roms.games"`
