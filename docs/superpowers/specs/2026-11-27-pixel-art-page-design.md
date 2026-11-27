# Pixel art page on the public site

## Intent

Share every piece of pixel art sync-roms makes on the public GitHub Pages site (`https://sync-roms.games/`), as a page next to the collections pages. Anyone browsing can see all of it; hovering a picture (tapping on a phone) shows it large with a pixel grid, so the individual pixels can be studied.

It is also a reference for artists making new themes: it shows everything a pixel theme needs drawn, with the file each picture goes in and that file's size.

## Goals

- One page, `https://sync-roms.games/pixel-art/`, linked from the site's root page, rebuilt by every `collections publish` (and so by `collections update`).
- Every pixel picture we make is on it. Nothing we draw is left off:
  - **Systems**: every system icon of both pixel themes (`build.systems("CONSOLES")` and `build.systems("CONTROLLERS")`). Icons drawn the same in both (the batches' `SHARED`) appear once, in a shared group; the rest show per theme.
  - **Regional versions**: every region of every `variants.VARIANTS` entry, console and pad, labeled by region, including the regions the themes don't use (marked as unused).
  - **Main menu**: `menu.SPRITES` plus the two themes' Games icons (`menu.handheld`, `menu.controller`).
  - **UI**: `app_icons.ICONS`, `ui_settings.ICONS`, `ui_status.ICONS`.
  - **Frames**: every frame in `frames.FRAMES` that draws something, in one palette (see below). That is the frames `frames.apply` writes for the real `SPRUCE` base, plus the hint pills (`context-a`, `-b`, `-x`, `-y`, `-menu`, `-select`, `-start`), which the code draws but the base has no file for: they are drawn at the sizes the frame tests use (26x26 for a letter, 66x26 for a word, the whole file as footprint), kept in one table in the page code, and marked "not in the SPRUCE base". Frames the base keeps fully transparent (`bg-grid-s`, `div-line-v-02`, `navbg`, `num-bg`, `preview-bg`, `statbg`, `thumb-default`) are left off, as `apply` leaves them blank in every theme.
  - **Box art**: every collection box in `data/themes/art-book-next/art-box/` (the sprite-on-box pictures Spruce shows for collections).
- Every icon is shown in both states the themes use: selected (`"sel"`) and unselected (`"n"`, dimmed).
- Each picture has a readable label (the system's name from `ids.IDS` where it has one, else its id or file name) and, for artists, the path(s) it is written to in a theme (`icons/gb.png` and `icons/sel/gb.png`, `skin/ic-favorite-n.png` and `-f.png`, `skin/bg-list-l.png`, ...) with that file's size in the 640x480 theme, and for a frame its cell size. Box art shows its paths on the card (`Collections/Imgs/<name>.png`, `Imgs_med/`, `Imgs_small/`) and their sizes.

## Non-goals

- No palette switcher. Frames are shown in one palette only.
- Frames at other screen sizes (`skin_<W>x<H>/`): the same art redrawn larger, so only the 640x480 `skin/` versions are shown.
- The palette preview mock-ups (`preview.png`, `themes palettes`): drawn screens with text, not pixel art.
- The ToTK theme art and the ES-DE outline art (`art/`): not pixel art.
- No change to the collections pages themselves.

## Anti-goals

- Blurry or resampled pixels anywhere, in the grid view or in the gallery.
- A grid that doesn't line up with the art's own pixels (or a frame's cells).
- A second copy of the drawing rules (outline, bevel, dimming) in JavaScript: the images come from the same Python that builds the themes.
- A page that needs anything outside the site: no external scripts, fonts or images, like the collections page.

## Constraints

- Frames are drawn to the base theme's own `skin/` files (their sizes and footprints), so building the page needs the base theme `SPRUCE` from storage, through `custom_themes.fetch_base`. `collections publish` already needs storage and fails without it; the pixel page fails the same way (nothing published) rather than publishing a page without frames.
- `tools/` isn't part of the package, so the box art comes from the committed `art-box/` PNGs, not `tools/gen_box_art.py`.
- Must run on Python 3.12. Tests import `isolate` first and never touch real storage (fake the base theme with a small `skin/` folder, as `tests/test_frames.py` does).
- The repo never holds the built page; it is written into the Pages clone by `pages_site.build`.

## Approaches

1. **Static images at one art pixel per image pixel (chosen).** Publish writes each picture as a small PNG at its native resolution: sprites rendered at scale 1, frames reduced to one pixel per cell, box art at its 84x120 base size. The browser scales them up with `image-rendering: pixelated`; the large view draws the grid on a canvas, one line per image pixel. Least code, images come straight from the theme code, and it matches how the collections page writes its art as separate files.
2. **Pixel data in JSON, drawn in the browser.** One data file with palette slots, instant palette switching. Rejected: it either duplicates the renderer in JS or needs a slot export the frames don't have, and the palette switcher it's best at isn't wanted.
3. **Images for sprites, data for frames.** Rejected: the cost of 2 for the part that doesn't need it.

The user chose approach 1 with frames in one palette.

## Design

### Output

`pages_site.build` also writes `<site>/pixel-art/` (emptied first): `index.html`, its CSS and JS (from a new template folder `src/sync_roms/data/pixel-art-page/`, in the collections page's colours, light and dark), and `img/<group>/<name>.png`. The site root's `index.html` gets a link to `pixel-art/` besides the list of users.

The page's data (groups, each a list of `{label, src, w, h, cell?}` and, for icons, the unselected image) is put in the page as an inline JSON block, like the collections page's `page-data`.

### Images

- **Sprites** (systems, regional versions, menu, UI): `sprite.render(draw(), scale=1, state=...)` for `"sel"` and `"n"`. That keeps the 1px outline and the bevel exactly as in the themes.
- **Frames**: build the theme for real (`build.build_theme`, CONSOLES, the chosen palette) into a temporary folder, since some frames' heights come from the built `config.json`'s rounded font sizes (`frames_select.row_height`); the frames don't depend on which theme is built (builder's call, after the builder check). For each frame `frames.apply` wrote in `skin/`, crop the cell grid (the Canvas's `ox`, `oy`, `cols * cell`, `rows * cell`) and reduce it by `cell` so one cell is one pixel. The reduction must be exact (every cell one flat colour); a test checks it. A frame's background fill outside the cell grid isn't shown.
- **Box art**: each `art-box/Imgs/<id>.png` (336x480) reduced 4x to 84x120 with nearest-neighbour; a test checks the reduction is exact.

### Palette

Frames are drawn in `Gruvbox`, the first of `palettes.py`, fixed in the code (not the user's saved `custom_theme_palettes`, so the public page doesn't change with a personal setting).

### Page

- Sections in this order: Main menu, Systems (Shared, Consoles, Controllers), Regional versions, Apps, Settings, Status and buttons, Frames, Box art. Each section has a heading and a count; a small jump list at the top.
- The gallery shows each picture at an integer scale (2x or 3x, fitted per section so small icons and large frames both read) on a dark tile, with its label underneath. Icons show the selected image; the unselected one is shown next to it in the large view.
- **Large view**: hovering a tile (pointer devices) or tapping it (touch) opens a panel with the picture drawn on a canvas at the largest integer scale that fits the viewport, a 1px grid line between every pixel (subtle, visible on dark and light pixels), the label, its native size in pixels, and for icons both states side by side. It closes on pointer leave, Escape or a tap outside. It must not run off the screen on a phone (16px gutter, no horizontal scroll).
- Self-contained: no external URLs. The ScreenScraper credit isn't needed (no scraped data on this page).

### Tests

- Every picture source above appears on the page: the count of images per group equals the count of draw functions, regions and art-box files, and the frames equal `frames.FRAMES` minus exactly the transparent-in-base list (so new art can't be missed, and a frame that goes blank is noticed).
- Frame and box-art reductions are exact.
- `pages_site.build` writes `pixel-art/index.html` and the root links to it; publish fails without the base theme.
- The page HTML has no external URLs.

### Docs

`docs/github-pages.md` mentions the pixel art page and that publishing needs the base theme in storage. CLAUDE.md's `pages-site/` line names the new template folder and the `pixel-art/` output.

## Left to the builder

- The module layout (a new `pixel_art_page.py` next to `collections_page.py` is the obvious home) and how `pages_site.build` calls it.
- How the Canvas's cell grid is recovered for a frame (recompute it from the base file's footprint and `cell_for`, or have `frames.apply` return it).
- Exact gallery scales, tile sizes, grid line colour and the page's styling, within the anti-goals.
- File naming inside `img/`.
