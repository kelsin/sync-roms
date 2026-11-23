# Pixel-art frames: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redraw the base theme's frame, bar, panel, key and small-glyph images in pixel art, in each palette's colors and at each screen size's native dimensions, with tested margin and balance rules.

**Architecture:** A frames kit (`pixel/frames.py`: shades, cell size, footprint, a cell-grid canvas that enforces margin rules, and a registry) plus three group modules registering frame drawers; `build_theme` runs the frames step last over every `skin*` folder. Tests enforce margins, symmetry, footprint and determinism on a synthetic base; a developer script renders contact sheets for visual review.

**Tech Stack:** Python 3.12+, Pillow, unittest, `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-23-pixel-frames-design.md` (the "Rulings" section at its end binds this plan; the file table lists the frames and base sizes).

## Global Constraints

- Always `uv run python ...`; tests `uv run python -m unittest discover -s tests`; Python 3.12 compatible; pristine test output (new tests once with `-W error`); never commit theme data (the real base lives at `/private/tmp/claude-501/-Users-kelsin-src-sync-roms--claude-worktrees-retro-console-pixel-art-c83a54/4153eb75-3ceb-4963-a2af-2a80e67443f5/scratchpad/spruce/Themes/SPRUCE/`, read only, for visual review and size lookup; tests use synthetic bases).
- Conventional Commits; each commit ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- The five margin rules and the cell-size rule from the spec are binding and tested: same footprint (base alpha >= 128 bounding box; image size unchanged), cell grid with leftover split evenly (extra pixel right/bottom when odd), even insets and equal inner padding, exact left-right mirroring where declared symmetric, regular 1:1 steps only.
- Palette fields: `name, text, list, selected, accent, dim, bar`; shades `hi = mix(bar, white, .35)`, `sh = mix(bar, black, .4)`, `mid = mix(bar, black, .45)`, `dark = mix(bar, black, .7)`; ink `(27, 21, 48)`.
- Order in `build_theme`: palette recolor and blacken first, frames last on every `skin*` folder holding a registered file (including `skin_640_480/`); `resize_variants` must not resize frame files; files missing from a base are skipped; `skin/background.png` stays black.
- Style: chunky panels (1-cell ink outline, stepped 1:1 corners, light top edge, dark bottom edge, palette fill), dotted rules, segmented progress, bevelled key tiles; no text or logos except tiny pixel glyph letters where the base shows letters (A, B, X, Y, MENU, SELECT, START: reuse the font helpers of `pixel/ui_status.py` if suitable).
- No changes to icons, palettes data, config layout or text positions.

## Review Focus

- A frame drawn for a base with an odd leftover (footprint not a multiple of the cell) must stay balanced: artwork offset by at most 1 px and opposite insets equal in cells.
- A copy folder with non-uniform scaling (`skin_1280x720/bg-list-l` 1280x135 vs 640x90) uses the min-ratio cell and still fills its own footprint exactly.
- A base theme lacking some registered files, or holding a frame with soft alpha edges, builds without error and without touching unregistered files.
- Building the same theme twice gives byte-identical frames; building two palettes gives the same geometry (alpha masks identical) with different colors.
- Contact sheets rendered for review show no clipped content, uneven margins, or one-sided leftovers in any of the reviewed palettes.

## File Structure

- Create `src/sync_roms/custom_themes/pixel/frames.py` (kit and registry), `frames_select.py` (selection bars and tiles), `frames_panels.py` (bars, screens, panels, loading, dividers), `frames_keys.py` (keys, counters, glyphs, nav, hints, spinner/charging).
- Modify `pixel/build.py` (frames step, `resize_variants` exclusion), `custom_themes/pixel/recolor.py` only if needed.
- Create `tools/frames_sheet.py` (developer contact-sheet script: builds a throwaway synthetic or real-base theme and renders every registered frame in chosen palettes onto one sheet; not shipped).
- Tests: `tests/test_frames.py`.

---

### Task 1: The kit, build integration, and selection frames

**Files:**
- Create: `pixel/frames.py`, `pixel/frames_select.py`, `tools/frames_sheet.py`
- Modify: `pixel/build.py`
- Test: `tests/test_frames.py`

**Interfaces:**
- Produces:
  - `frames.Shades` (frozen dataclass: `text, list, selected, accent, dim, bar, hi, sh, mid, dark, ink`, RGB tuples) and `frames.shades(palette) -> Shades`.
  - `frames.cell_for(size, base_size) -> int` (rulings formula; `base_size=None` => cell 4 when width >= 64 else 2) and `frames.footprint(img) -> tuple[int, int, int, int]` (x0, y0, x1, y1 of alpha >= 128; whole image when none transparent).
  - `frames.Canvas(size, cell, box)`: cell-grid canvas over footprint `box`; attributes `cols`, `rows`, `ox`, `oy` (pixel origin after splitting leftover evenly, extra pixel right/bottom); methods `px(cx, cy, rgb)`, `rect(cx, cy, cw, ch, rgb)`, `panel(cx, cy, cw, ch, fill, hi, sh, outline, cut=2)` (stepped-corner bevelled panel on the cell grid), `hline_dots(cx, cy, cw, rgb, on=2, off=1)`, `vline_dots(...)`, `mirror()` (copy left half onto the right half in cells), `image() -> PIL RGBA` of `size`.
  - `frames.FrameSpec` (dataclass: `draw: callable(canvas, shades)`, `symmetric: bool = False`, `flush: tuple = ()`), `frames.FRAMES: dict[str, FrameSpec]` keyed `"skin/<file>.png"` (plain-skin name; applied to the same file in every `skin*` folder), `frames.register(name, draw, symmetric=False, flush=())`.
  - `frames.apply(theme_dir, palette)`: for every `skin*` folder and registered file present, read the base image (size, footprint), choose the cell from the same file in plain `skin/` (or the no-base rule), run the drawer on a Canvas, save PNG (deterministic), skipping missing files; returns the list of written relative paths so `build_theme` excludes them from `resize_variants`.
  - `frames_select.py` registers: `bg-list-l`, `bg-list-s`, `bg-list-s2`, `list-item-select-bg-short` (dark box with accent border), `menu-sub-title-bg`, `grid-game-selected`, `bg-game-item-f`, `bg-grid-s`. (`bg-game-item-n` is 1x1: untouched.)
- `build_theme` calls `frames.apply(dest, palette)` after the recolor/blacken steps and passes the written paths to `resize_variants` so those files are not resized.

- [ ] **Step 1: Failing tests** (`tests/test_frames.py`; helper `make_base(dir, files)` creating synthetic PNGs at the spec's base sizes with a base-like alpha footprint; one copy folder `skin_1280x720` with the 1280x135 bg-list-l and `skin_720x480` with 720x90):
  - `test_shades`: values for Gruvbox bar `(80,73,69)`: `hi == (round(80+(255-80)*.35), ...)` etc., `dark` darker than `sh`.
  - `test_cell_for`: (640x90 vs 640x90) 4; (1280x135 vs 640x90) 6; (720x90 vs 640x90) 4; (100x20 vs no base) 2; small files per the rule.
  - `test_footprint`: opaque image => whole; image with a transparent margin => the inner box; alpha 100 pixels ignored.
  - `test_canvas_leftover_split`: footprint 650 px wide with cell 4 => 162 cols and a 1 px right offset (extra pixel right when odd): `ox == (650 - 648) // 2` and the artwork within the footprint; even leftover split exactly.
  - `test_panel_symmetric_corners`: a `panel` on a canvas has identical corner stepping on all four corners (compare each corner mask mirrored) and equal outline insets.
  - `test_every_registered_frame` over `frames.FRAMES` (parametrized by `subTest`): applying to a synthetic base keeps the image size, all opaque pixels lie in the footprint, symmetric specs are mirror-identical in the cell grid (allowing the 1 px leftover offset), flush sides touch the footprint edge and non-flush sides have equal opposite insets, the output is deterministic (two runs identical bytes), and two palettes give the same alpha mask with different RGB.
  - `test_apply_skips_missing_files_and_other_folders`: a base lacking registered files builds without error; a PNG under `icons/` is untouched; `skin/background.png` stays black.
  - `test_build_theme_draws_frames_natively`: a full `build_theme` on the mini base: `skin_720x480/bg-list-l.png` has size (720, 90) and is not a resized copy of the 640 one (cell-4 geometry check), and `resize_variants` leaves it.
- [ ] **Step 2: Run to verify failure.** `uv run python -m unittest tests.test_frames -v` Expected: ImportError/FAIL.
- [ ] **Step 3: Implement** the kit and `frames_select.py` and the build integration. Study the base images first (`scratchpad` base theme, read only; view them enlarged) so footprints and inner content areas match; design each selection frame in the reviewed style with even insets and equal inner padding; the list bars are flush left/right (full-width) with a 1-cell vertical inset top and bottom equal. Write `tools/frames_sheet.py` (args: `--base DIR`, `--palette NAME` repeatable, `--out FILE`; builds into a temp folder with the real `build_theme` and tiles every registered frame with its name over black, enlarged) and use it to verify visually (view the sheet, zoom crops, check margins by eye and with the tests) in at least Gruvbox, Arcade, Virtual Boy and Mint.
- [ ] **Step 4: Run** `uv run python -W error -m unittest tests.test_frames tests.test_theme_palettes tests.test_custom_themes -v` Expected: PASS; then the full suite once.
- [ ] **Step 5: Commit** `feat(themes): draw the selection frames in pixel art`

---

### Task 2: Bars, screens, panels, loading and dividers

**Files:**
- Create: `pixel/frames_panels.py` (imported by `pixel/frames.py`'s registry load point or by `build.py`, following Task 1's pattern)
- Test: `tests/test_frames.py`

**Interfaces:**
- Consumes: Task 1's kit and registry. Produces registrations for: `bg-title` (a small pixel-art version of the base's logo kept at the left, dotted bottom rule), `tips-bar-bg`, `navbg`, `statbg`, `bg-gamelist`, `menu-5line-bg`, `menu-6line-bg`, `app_loading_bg` (opaque black areas with palette-colored dotted rules/borders at the edges where the base has a bar or frame), `bg-pop-menu-4`, `menu-sub-bg`, `loading-bg`, `loading-progress-left`, `loading-progress-mid`, `loading-progress-right` (segmented fill pieces that tile seamlessly: the mid piece tiles horizontally with itself and with left/right ends), `preview-bg`, `preview-nameFrame`, `thumb-default` (a neutral pixel-art placeholder panel), `div-line-v-02` (dotted vertical divider). `missing_image` is not touched.

- [ ] **Step 1: Failing tests** extending `test_every_registered_frame` coverage (the parametrized test covers the new registrations automatically): plus `test_progress_pieces_tile` (left+mid+mid+right laid side by side has no gap or color seam at the joins: compare the columns at each join), `test_full_screen_backgrounds_stay_opaque_black_inside` (the interior of the full-screen entries is exactly black; only the declared edge rules carry color), `test_registry_has_all_panel_files`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** Study the base images (sizes in the spec table and the real base copy) so interiors, insets and footprints match; panels get equal insets and padding on opposite sides (popup/menu panels symmetric); the 4-px-wide progress pieces need cell size 1-2: draw by the small-file rule and make the pieces tile exactly; use `tools/frames_sheet.py` to review in Gruvbox, Arcade, Virtual Boy and Mint, with crops enlarged for the joins and margins.
- [ ] **Step 4: Run** `uv run python -W error -m unittest tests.test_frames -v` Expected: PASS; then the full suite once.
- [ ] **Step 5: Commit** `feat(themes): draw bars, panels and the loading bar in pixel art`

---

### Task 3: Keys, counters, glyphs, hints, spinner and charging

**Files:**
- Create: `pixel/frames_keys.py`
- Test: `tests/test_frames.py`

**Interfaces:**
- Consumes: Task 1's kit and registry. Produces registrations for: `bg-btn-01-f/n`, `bg-btn-02-f/n`, `bg-btn-nor`, `bg-btn-sel`, `bg-btn-shift-active`, `value-frame-f/n`, `num-bg`, `btn-delete`, `btn-empty`, `btn-shift`, `btn-space` (glyph keys: back-arrow, trash, shift arrow, space bracket), `nav-favorite-f/n` (star), `nav-file-f/n` (folder), `progress-dot`, `context-a/b/x/y` (round letter buttons), `context-menu/select/start` (pills with letters), `app_loading_01..05` and `charging-01..05` (redraw the glyph inside each frame's own footprint; keep count and positions; inspect the base frames first: they are 100x480 strips).

- [ ] **Step 1: Failing tests**: the parametrized every-registered-frame test covers the margin rules; plus `test_selected_and_unselected_share_geometry` (`-f` vs `-n` pairs have identical alpha masks outside their fill/colors where the spec says only color differs, or documented differences), `test_animation_frames_keep_positions` (the five frames' glyph bounding boxes differ only as designed and each lies within its footprint), `test_registry_has_all_key_files`, and a spec-coverage test: the union of all registered names equals the spec's file list minus the documented exclusions (`bg-game-item-n`, `div-line-h`, `div-line-v-01`, `missing_image`, `background`).
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** Glyph letters/arrows use tiny pixel fonts or primitives with clean 1:1 steps; every glyph is centered in its footprint with equal margins (the kit's inset checks apply); star and folder symmetric; use the contact-sheet tool to review in the four palettes plus two more (Candy, Game Boy) with enlarged crops.
- [ ] **Step 4: Run** `uv run python -W error -m unittest tests.test_frames -v`, then the full suite once.
- [ ] **Step 5: Commit** `feat(themes): draw keys, hints and small glyphs in pixel art`
