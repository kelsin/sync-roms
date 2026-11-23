# Pixel Theme Previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One 640x480 mock of the Pixel theme's main screen in a palette's colors, used as the built theme's `preview.png`, in the palette picker and in the `themes palettes` sheet.

**Architecture:** A new module `src/sync_roms/custom_themes/pixel/preview.py` draws the image from sprite code (`sprite.render`) and the `Palette`, with no built theme needed. `build.preview` saves it; `palette_sheet.render_panel` becomes a half-size, captioned copy of it, which the picker and sheet already call.

**Tech Stack:** Python 3.12+, Pillow, unittest (`uv run python -m unittest discover -s tests`).

**Spec:** `docs/superpowers/specs/2026-11-23-pixel-theme-previews-design.md`

## Global Constraints

- Code must run on Python 3.12. Always run through `uv run`.
- Test modules that import `sync_roms` import `isolate`/`helpers` first (existing test files already do).
- Image is 640x480, background black `(0, 0, 0)`.
- Font: the given `.ttf` path, else `ImageFont.load_default(size)` (reuse `palette_sheet._font`).
- Palette roles: `selected` for the selected label/row text, `bar` for the selected row/box, `dim` for unselected menu labels, `list` for unselected list rows, swatch strip order text, list, selected, accent, dim, bar.
- Conventional Commits; commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Missing font (no base theme in cache, e.g. on a fresh machine running the picker): the image still renders with Pillow's default font — Task 1 `test_renders_without_font`.
- Both styles: `CONTROLLERS` must render as well as `CONSOLES` (different `game` sprite and system set) — Task 1 `test_both_kinds`.
- Determinism: building the same theme twice must give byte-identical `preview.png` (`test_build_is_deterministic` in `tests/test_custom_themes.py` already covers this; it must keep passing).
- Light palettes (`Pocket`, `Monochrome`: `selected` `#FFFFFF`): the selected label must still be on `bar`, not on black, so it reads — covered by the bar-pixel assertion in Task 1.
- Picker speed: rendering one preview must stay fast enough for scrolling (draw only the few sprites used, never all of `systems(kind)`'s renders) — reviewer check.

---

### Task 1: The preview renderer and the built theme's preview.png

**Files:**
- Create: `src/sync_roms/custom_themes/pixel/preview.py`
- Modify: `src/sync_roms/custom_themes/pixel/build.py:153` and `:159-171` (`preview`)
- Test: `tests/test_pixel_preview.py` (new)

**Interfaces:**
- Consumes: `build.systems(kind) -> {id: draw fn}`, `build.SPECS[kind]["game"]`, `menu.SPRITES`, `ui_status.ICONS` (keys like `"skin/icon-wifi-signal-04.png"`, `"skin/power-80%-icon.png"`), `sprite.render(sprite, scale, state)` (`state` `"sel"` or `"n"`), `palette_sheet._font(path, size)`.
- Produces:
  - `preview.SIZE = (640, 480)`
  - `preview.LAYOUT`: a dict of the fixed points the tests read — `"menu_bar"` (an (x, y) inside the selected menu item's `bar` box but off its sprite and label), `"row_bar"` (an (x, y) inside the selected list row's `bar` fill, off its text), `"swatches"` (list of six (x, y) points, one inside each swatch).
  - `preview.preview_image(kind: str, palette: Palette, font_path: str | None = None) -> PIL.Image.Image` (mode `"RGB"`, size `SIZE`).
  - `build.preview(dest, spec, kind)` saves `preview_image(kind, palette, <dest>/nunwen.ttf if it exists else None)` as `<dest>/preview.png`. Change its call in `build_theme` to pass `kind` and `palette` (signature becomes `preview(dest, kind, palette)`; `spec` is no longer needed there).

- [ ] **Step 1: Write the failing tests** in `tests/test_pixel_preview.py` (import `helpers` first, like `tests/test_theme_palettes.py`):

```python
def hexrgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

class PixelPreview(unittest.TestCase):
    def test_size_mode_background(self):
        img = preview.preview_image("CONSOLES", palettes.get("Gruvbox"))
        self.assertEqual((img.size, img.mode), ((640, 480), "RGB"))
        self.assertEqual(img.getpixel((0, 479)), (0, 0, 0))

    def test_palette_colors_at_layout_points(self):
        for name in ("Gruvbox", "Pocket", "Game Boy"):
            p = palettes.get(name)
            img = preview.preview_image("CONSOLES", p)
            self.assertEqual(img.getpixel(preview.LAYOUT["menu_bar"]), hexrgb(p.bar))
            self.assertEqual(img.getpixel(preview.LAYOUT["row_bar"]), hexrgb(p.bar))
            self.assertEqual([img.getpixel(pt) for pt in preview.LAYOUT["swatches"]],
                             [hexrgb(c) for c in (p.text, p.list, p.selected, p.accent, p.dim, p.bar)])

    def test_selected_and_list_text_colors_present(self):
        p = palettes.get("Dracula")
        colors = {c for _, c in preview.preview_image("CONSOLES", p).getcolors(640 * 480)}
        for c in (p.selected, p.list, p.dim):
            self.assertIn(hexrgb(c), colors)

    def test_both_kinds(self):
        p = palettes.get("Gruvbox")
        a = preview.preview_image("CONSOLES", p)
        b = preview.preview_image("CONTROLLERS", p)
        self.assertEqual(a.size, b.size)
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_renders_without_font(self):
        img = preview.preview_image("CONSOLES", palettes.get("Gruvbox"), font_path=None)
        self.assertEqual(img.size, (640, 480))
```

Note on `test_selected_and_list_text_colors_present`: anti-aliased text may not hit the exact color; draw text with `ImageDraw` on an RGB image with `fontmode = "1"` (no anti-aliasing) so exact palette colors appear. Pick this in Step 3.

- [ ] **Step 2: Run and see them fail**

Run: `uv run python -m unittest tests.test_pixel_preview -v`
Expected: FAIL / ImportError (`preview` module missing).

- [ ] **Step 3: Implement `preview.py`** following the approved throwaway mock, `/private/tmp/claude-501/-Users-kelsin-src-sync-roms--claude-worktrees-android-adb-wireless-debug-ce8335/5742787c-0689-402c-b29c-d5223f83a829/scratchpad/mock.py` (its coordinates are the approved layout: clock "12:34" top left in `text`, menu items 160 px apart with Favorites on a rounded `bar` box, a `dim` divider line, the list, three system icons with "Game Boy" under them in `accent`, swatches at the bottom; drop its stray "2/" text). In short:
  - top right: wifi (`skin/icon-wifi-signal-04.png` draw fn) and battery (`skin/power-80%-icon.png`), rendered `"sel"` at scale 2;
  - menu row across the upper half: Favorites (`menu.SPRITES["favorite"]`), Games (`build.SPECS[kind]["game"]`), Apps (`"app"`), Settings (`"setting"`); sprites rendered with `sprite.render(..., 4, state)` (`"sel"` for Favorites, `"n"` for the rest), labels under them; Favorites sits in a `bar` rectangle with its label in `selected`, others' labels in `dim`;
  - lower half left: three list rows, e.g. "Super Metroid", "Chrono Trigger", "F-Zero"; the middle on a full-width-of-column `bar` fill in `selected`, others in `list`; lower half right: three system icons from `build.systems(kind)` (e.g. `gb`, `snes`, `n64` when present, else the first three ids), the first `"sel"`, the others `"n"`, at a size that fits;
  - bottom: six swatches in a row.
  - Draw text with `fontmode = "1"`. Import `build` lazily inside `preview_image` if a top-level import would be circular (`build` will import `preview`).
  - Set `LAYOUT` from the same constants the drawing uses, so tests and drawing can't drift.

- [ ] **Step 4: Run the new tests**

Run: `uv run python -m unittest tests.test_pixel_preview -v`
Expected: all PASS.

- [ ] **Step 5: Switch `build.preview` to the renderer** (signature `preview(dest, kind, palette)`, font `<dest>/nunwen.ttf` when present), update the call in `build_theme`. Add to `tests/test_pixel_preview.py`:

```python
    def test_build_preview_writes_png(self):
        with tempfile.TemporaryDirectory() as d:
            build.preview(d, "CONSOLES", palettes.get("Gruvbox"))
            with Image.open(os.path.join(d, "preview.png")) as im:
                self.assertEqual(im.size, (640, 480))
```

- [ ] **Step 6: Run the full suite**

Run: `uv run python -m unittest discover -s tests`
Expected: OK (including `test_build_is_deterministic`, `test_build_overlays_base`, `test_frames`).

- [ ] **Step 7: Look at the result.** Render Gruvbox, Pocket and Synthwave for both kinds into the session scratchpad (font: `~/.sync-roms/cache/themes/base/SPRUCE/nunwen.ttf` if present) and read the PNGs. Fix overlaps or clipped labels before committing.

- [ ] **Step 8: Commit**

```bash
git add src/sync_roms/custom_themes/pixel/preview.py src/sync_roms/custom_themes/pixel/build.py tests/test_pixel_preview.py
git commit -m "feat(themes): preview pixel themes as their main screen in the palette"
```

### Task 2: Palette picker and palettes sheet use the preview

**Files:**
- Modify: `src/sync_roms/custom_themes/palette_sheet.py` (`PANEL`, `render_panel`; `render_sheet` keeps its shape)
- Modify: `CLAUDE.md` only if it describes the panel (it says "the picker's previews are the same panels" — keep true)
- Test: `tests/test_theme_palettes.py:323-340` (`test_render_panel_size_and_colors`, `test_render_sheet_size`)

**Interfaces:**
- Consumes: `preview.preview_image(kind, palette, font_path)`, `preview.SIZE`, `preview.LAYOUT` from Task 1.
- Produces: `palette_sheet.PANEL = (320, 240)`; `palette_sheet.render_panel(palette, font_path=None, caption=None) -> Image` (RGB, `PANEL` size): `preview_image("CONSOLES", palette, font_path)` resized to half with `Image.NEAREST`, the caption (default `palette.name`) in `CAPTION` color at top left. `palette_picker._preview` is unchanged (it already calls `render_panel`) and now shows the new image.

- [ ] **Step 1: Update the tests**

```python
    def test_render_panel_size_and_colors(self):
        p = palettes.get("Gruvbox")
        img = palette_sheet.render_panel(p)
        self.assertEqual((img.size, img.mode), ((320, 240), "RGB"))
        half = lambda pt: (pt[0] // 2, pt[1] // 2)
        self.assertEqual(img.getpixel(half(preview.LAYOUT["row_bar"])), hexrgb(p.bar))
        self.assertEqual([img.getpixel(half(pt)) for pt in preview.LAYOUT["swatches"]],
                         [hexrgb(c) for c in (p.text, p.list, p.selected, p.accent, p.dim, p.bar)])

    def test_render_sheet_size(self):
        img = palette_sheet.render_sheet(palettes.PALETTES.values())
        self.assertEqual(img.size, (5 * 320 + 6 * 8, 6 * 240 + 7 * 8))
        self.assertEqual(img.getpixel((0, 0)), (28, 28, 28))
```

(Swatches and the row bar must be at least 2 px from their edges so the half-size pixel lands inside; Task 1's `LAYOUT` points already are inside.)

- [ ] **Step 2: Run and see them fail**

Run: `uv run python -m unittest tests.test_theme_palettes -v`
Expected: the two tests FAIL on size.

- [ ] **Step 3: Rewrite `render_panel`** as in Interfaces; drop the old list-mock drawing and any constants only it used. Keep `_font`, `font_path`, `save_image`, `write_sheet`.

- [ ] **Step 4: Run the full suite**

Run: `uv run python -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 5: Look at the sheet.** Write it with `palette_sheet.write_sheet(<scratchpad>/palettes.png)` and read it; captions must not hide the status icons badly.

- [ ] **Step 6: Commit**

```bash
git add src/sync_roms/custom_themes/palette_sheet.py tests/test_theme_palettes.py
git commit -m "feat(themes): show the pixel preview in the palette picker and sheet"
```
