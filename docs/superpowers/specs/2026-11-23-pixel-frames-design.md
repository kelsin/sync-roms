# Pixel-art frames for the custom spruce themes

Builds on `2026-11-23-custom-spruce-themes-design.md` and `2026-11-23-theme-palettes-design.md` (palettes, `pixel/build.py`).

## Intent

Today the custom themes keep the base SPRUCE theme's frames: flat gray selection bars, plain panels, text-like glyphs. The user wants them redrawn as pixel art in the same chunky style as the icons, in the colors of whichever palette is built, and asked above all for **careful margins and balance**.

## Goals

- Every frame, bar, panel, key and small glyph image of the base theme's `skin/` that is not already redrawn (about 60 files, listed below) is redrawn in pixel art, per palette, at each screen size's native pixel dimensions.
- Style (reviewed prototype): chunky panel = 1-cell dark outline, stepped (diagonal 1:1) corners, light top edge, dark bottom edge, fill from the palette; dotted dividers and rules; segmented progress bars; keys as small bevelled tiles; glyphs in the icon style.
- Palette colors: `bar` is the selected fill; derived shades computed from it: `hi = mix(bar, white, .35)`, `sh = mix(bar, black, .4)`, `mid = mix(bar, black, .45)`, `dark = mix(bar, black, .7)`; text/accent/dim/list/selected come from the palette as in the config recolor; outline is the icon outline ink `(27, 21, 48)`.
- Margins and balance (binding rules, tested):
  1. **Same footprint.** A redrawn frame keeps the base image's pixel size, and its opaque artwork occupies the same bounding box as the base image's non-transparent pixels, so PyUI's text and image placement is unaffected. Full-screen backgrounds stay full-screen and opaque.
  2. **Cell grid.** Artwork is drawn on a grid of square cells (the cell size per screen size below); when the footprint is not a whole number of cells, the leftover pixels are split evenly between opposite sides (extra pixel to the right/bottom when odd), never added to one side.
  3. **Even insets.** A panel's outline is inset from its footprint equally on all sides (same number of cells left/right and top/bottom, unless the base image is deliberately flush on a side, like a full-width bar), and its inner padding (outline to content area) is equal on opposite sides.
  4. **Symmetry.** Frames that are symmetric left-right are exactly mirrored (draw half, mirror); stepped corners are identical on all four corners of a panel.
  5. **Regular steps.** Straight and 1:1 diagonal edges only; no jogs or stray pixels.
- Cell size: `cell = max(2, round(4 * file_width / base_file_width))` where `base_file_width` is the width of the same file in the 640x480 `skin/` folder, so a 640-wide bar uses 4-pixel cells and a 1280-wide-theme copy uses 8; small files (under 64 px wide in the base) use `cell = max(1, round(2 * ratio))` so their pixels don't swamp them.
- The pre-scaled `skin_<size>/` copies are drawn natively (not resized), by the same code, from each copy's own file size.
- Tests enforce the margin rules per frame (alpha bounding box vs base, even insets, left-right symmetry where declared, determinism) on a synthetic base, and a contact-sheet script (developer tool, not shipped) renders every frame in several palettes for review.

## The files (base theme sizes at 640x480)

- **Selection and tiles:** `bg-list-l` (640x90), `bg-list-s` (640x60), `bg-list-s2` (320x60), `list-item-select-bg-short` (320x60, orange outlined box), `menu-sub-title-bg` (320x36), `grid-game-selected` (140x140), `bg-game-item-f` (154x170), `bg-game-item-n` (1x1, stays transparent), `bg-grid-s` (156x176).
- **Bars and screens:** `bg-title` (640x60, with a small logo at the left), `tips-bar-bg` (640x60), `navbg` (640x60), `statbg` (640x62), `bg-gamelist` (640x360), `menu-5line-bg`, `menu-6line-bg`, `app_loading_bg` (640x480): dark opaque areas; they become black with palette-colored dotted rules/borders where a bar or frame edge exists.
- **Panels:** `bg-pop-menu-4` (320x250), `menu-sub-bg` (320x300), `loading-bg` (508x68), `loading-progress-left/mid/right` (4x50 each: the segmented bar pieces), `preview-bg` (254x360), `preview-nameFrame` (174x70), `thumb-default` (250x360), `missing_image` (240x240, already drawn: leave).
- **Keys and counters:** `bg-btn-01-f/n` (50x50), `bg-btn-02-f/n` (111x50), `bg-btn-nor`, `bg-btn-sel`, `bg-btn-shift-active` (48-50 px), `value-frame-f/n` (61x24), `num-bg` (44x24), `btn-delete`, `btn-empty`, `btn-shift`, `btn-space` (30x30 glyphs: back-arrow, trash, shift arrow, space bracket).
- **Glyphs:** `nav-favorite-f/n`, `nav-file-f/n` (40x40), `progress-dot` (12x12), `context-a/b/x/y` (26x26), `context-menu/select/start` (66x26), `div-line-v-02` (4x420), `div-line-h`/`div-line-v-01` (1x1: stay as they are), and the animated frames `app_loading_01..05` (100x480) and `charging-01..05` (100x480).
- Anything already redrawn (icons, status, `Empty`, `missing_image`, `ic-*`) is untouched. Files absent from a base theme are skipped (as the icon modules do).

## Non-goals and anti-goals

- No changes to image sizes, file names, config layout or text positions.
- No new palettes or palette data (derived shades are computed).
- No animation changes (the spinner/charging frames keep their count and timing; only art).
- No attempt to fix PyUI's own scaling; the per-size drawing is native.

## Constraints from the codebase

- The frame code lives in `src/sync_roms/custom_themes/pixel/` (`frames.py` kit and per-group modules); it runs inside `pixel/build.py::build_theme` after the base copy and the palette recolor, replacing the bar-gray recolor for the files it draws (that recolor stays for any frame file not redrawn).
- Determinism, Pillow-only, Python 3.12, pristine test output; icons code untouched.
- Build time must stay reasonable (the earlier build is 4-5 s per theme; frames add at most a few seconds).

## Approaches

1. **Procedural frames from a small kit, drawn per palette and per size (chosen).** One kit (panel, bar, dots, key, segmented progress, glyph helpers) and a registry `{file: draw function(w, h, cell, palette)}`; the same code serves every screen size and palette. Matches how icons are built; margin rules are enforced in the kit.
2. Hand-drawn frame PNGs per palette. Rejected: hundreds of files, not rebuildable.
3. Recolor-only (keep the base shapes, recolor to the palette). Rejected: it is what the palettes already do, and the user wants the shapes redrawn.

## Left to the builder

The exact art of each frame within the style and margin rules, the kit's function names, the contact-sheet script, how the build handles animation frame files, and whether the base's logo in `bg-title` is kept as a small pixel-art version.

## Rulings (from the builder check; these bind the plan)

- **Cell size.** Per file, compare with the same file in plain `skin/` (the base): `ratio = min(width / base_width, height / base_height)`; `cell = max(2, round(4 * ratio))` for files at least 64 px wide in the base, else `cell = max(1, round(2 * ratio))`. Files that exist only in a copy (not in plain `skin/`, e.g. in `skin_640_480/`) use cell 4 (large) or the small rule by their own size. (Copies don't scale uniformly: `skin_1280x720/bg-list-l` is 1280x135 against 640x90, so min ratio 1.5 gives cell 6; `skin_720x480` bars at ratio 1.0 use cell 4.)
- **Order and folders.** The frames step runs last in `build_theme` among the skin steps (after `recolor_bar` and `blacken`), on every `skin*` folder (including `skin_640_480/`, the in-game menu) that holds a registered file, overwriting it; `resize_variants` leaves frame files alone (they are drawn natively); the blacken/bar recolor stay for any frame file not redrawn. `skin/background.png` stays plain black.
- **Footprint.** The footprint is the bounding box of pixels with alpha >= 128 in the base PNG that is in the built theme folder when the frames step runs (read at build time, so it follows whatever base theme is used); a fully opaque image's footprint is the whole image. Soft edges are ignored. Tests use a synthetic base made from the sizes/shapes in the table above. `list-item-select-bg-short` (orange-outlined dark box) becomes a dark box with an `accent` border (same meaning, palette color).
- **Palette fields and shades.** `Palette` fields are `name, text, list, selected, accent, dim, bar` (`palettes.py`). The derived shades (`hi`, `sh`, `mid`, `dark`) and `ink` live in `pixel/frames.py` as `shades(palette)`; `dark` fills panels, pure black is only for full-screen backgrounds.
- **Symmetry and flush.** Each registry entry declares `symmetric: bool` and `flush: tuple` of sides (`"left"`, `"right"`, `"top"`, `"bottom"`) where the artwork touches the footprint edge. The symmetry test compares the cell-grid artwork (exact mirror in cells); the leftover-pixel rule (extra pixel to the right/bottom when odd) may offset the artwork by at most 1 px, which the test tolerates.
- **Animation frames.** The builder inspects the base `app_loading_01..05` and `charging-01..05` and redraws the glyph inside each frame's own footprint (the same footprint rule), keeping the frame count and positions.

## Accepted exceptions (decided during the build)

- `context-menu/select/start` (66 px) and `bg-btn-02-f/n` use the small-file cell rule (`small=True`) instead of the width formula, so their letters fit and the wide keys match the narrow ones.
- `nav-file-f/n` is not mirror-symmetric (the folder tab sits at the left; its body mirrors exactly).
- `btn-shift` draws a solid arrow only, without the base glyph's own outline box (only 4 rows are free inside it); it stays inside the base footprint and is centered with equal margins; the key tile behind it draws the key.
- Files fully transparent in the real base (`navbg`, `statbg`, `preview-bg`, `thumb-default`, `div-line-v-02`, `bg-grid-s`, `num-bg`) are left transparent: an empty footprint has nothing to draw.
- PyUI does not load `loading-bg`, `loading-progress-*`, `progress-dot`, `app_loading_*`, `charging-0*`, `nav-*`, the keyboard `btn-*` glyphs or `navbg`/`statbg`/`preview-bg`/`thumb-default` (older spruce UIs do); they are still redrawn.
