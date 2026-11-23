import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402
from test_custom_themes import make_base as make_theme_base  # noqa: E402

from sync_roms.custom_themes import palettes  # noqa: E402
from sync_roms.custom_themes.pixel import build as pixel_build  # noqa: E402
from sync_roms.custom_themes.pixel import frames, frames_keys, frames_panels  # noqa: E402

GRUVBOX = palettes.get("Gruvbox")
ARCADE = palettes.get("Arcade")

# file: (size, opaque box or None for a fully opaque image), in the base theme's plain skin/ (640x480)
BASE = {
    "bg-list-l.png": ((640, 90), None),
    "bg-list-s.png": ((640, 60), None),
    "bg-list-s2.png": ((320, 60), None),
    "list-item-select-bg-short.png": ((320, 60), None),
    "menu-sub-title-bg.png": ((320, 36), None),
    "grid-game-selected.png": ((140, 140), None),
    "bg-game-item-f.png": ((154, 170), (6, 0, 144, 153)),
    "bg-grid-s.png": ((156, 176), (7, 3, 150, 166)),
    # bars, screens, panels, loading and dividers (the real base has some fully transparent: opaque here to draw them)
    "bg-title.png": ((640, 60), None),
    "tips-bar-bg.png": ((640, 60), None),
    "navbg.png": ((640, 60), None),
    "statbg.png": ((640, 62), None),
    "bg-gamelist.png": ((640, 360), None),
    "menu-5line-bg.png": ((640, 480), None),
    "menu-6line-bg.png": ((640, 480), None),
    "app_loading_bg.png": ((640, 480), None),
    "bg-pop-menu-4.png": ((320, 250), (0, 0, 320, 240)),
    "menu-sub-bg.png": ((320, 300), None),
    "loading-bg.png": ((508, 68), None),
    "loading-progress-left.png": ((4, 50), None),
    "loading-progress-mid.png": ((4, 50), None),
    "loading-progress-right.png": ((4, 50), None),
    "preview-bg.png": ((254, 360), None),
    "preview-nameFrame.png": ((174, 70), None),
    "thumb-default.png": ((250, 360), None),
    "div-line-v-02.png": ((4, 420), None),
    # keys, counters, glyphs, hints, spinner and charging (glyph footprints as in the real base: soft edges trimmed)
    "bg-btn-01-f.png": ((50, 50), None),
    "bg-btn-01-n.png": ((50, 50), None),
    "bg-btn-02-f.png": ((111, 50), None),
    "bg-btn-02-n.png": ((111, 50), None),
    "bg-btn-nor.png": ((48, 48), None),
    "bg-btn-sel.png": ((50, 50), None),
    "bg-btn-shift-active.png": ((48, 48), None),
    "value-frame-f.png": ((61, 24), None),
    "value-frame-n.png": ((61, 24), None),
    "num-bg.png": ((44, 24), None),
    "btn-delete.png": ((30, 30), (1, 5, 29, 25)),
    "btn-empty.png": ((30, 30), (1, 3, 29, 28)),
    "btn-shift.png": ((30, 30), (2, 7, 28, 23)),
    "btn-space.png": ((30, 30), (4, 4, 26, 26)),
    "nav-favorite-f.png": ((40, 40), (2, 3, 38, 37)),
    "nav-favorite-n.png": ((40, 40), (2, 3, 38, 37)),
    "nav-file-f.png": ((40, 40), (3, 5, 37, 33)),
    "nav-file-n.png": ((40, 40), (3, 5, 37, 33)),
    "progress-dot.png": ((12, 12), (1, 1, 11, 11)),
    "context-a.png": ((26, 26), None),
    "context-b.png": ((26, 26), None),
    "context-x.png": ((26, 26), None),
    "context-y.png": ((26, 26), None),
    "context-menu.png": ((66, 26), None),
    "context-select.png": ((66, 26), None),
    "context-start.png": ((66, 26), None),
}
for _i in range(1, 6):
    BASE[f"app_loading_0{_i}.png"] = ((100, 480), (27, 198, 75, 282))
    BASE[f"charging-0{_i}.png"] = ((100, 480), (27, 198, 75, 282))
KEYS = {"bg-btn-01-f", "bg-btn-01-n", "bg-btn-02-f", "bg-btn-02-n", "bg-btn-nor", "bg-btn-sel", "bg-btn-shift-active",
        "value-frame-f", "value-frame-n", "num-bg", "btn-delete", "btn-empty", "btn-shift", "btn-space",
        "nav-favorite-f", "nav-favorite-n", "nav-file-f", "nav-file-n", "progress-dot", "context-a", "context-b",
        "context-x", "context-y", "context-menu", "context-select", "context-start"} | {
    f"{kind}{i}" for kind in ("app_loading_0", "charging-0") for i in range(1, 6)}
# the spec's file list (2026-11-23-pixel-frames-design.md, "The files"), and the ones it keeps as they are
SPEC_FILES = {
    "bg-list-l", "bg-list-s", "bg-list-s2", "list-item-select-bg-short", "menu-sub-title-bg", "grid-game-selected",
    "bg-game-item-f", "bg-game-item-n", "bg-grid-s", "bg-title", "tips-bar-bg", "navbg", "statbg", "bg-gamelist",
    "menu-5line-bg", "menu-6line-bg", "app_loading_bg", "bg-pop-menu-4", "menu-sub-bg", "loading-bg",
    "loading-progress-left", "loading-progress-mid", "loading-progress-right", "preview-bg", "preview-nameFrame",
    "thumb-default", "missing_image", "div-line-v-02", "div-line-h", "div-line-v-01", "background"} | KEYS
NOT_DRAWN = {"bg-game-item-n", "div-line-h", "div-line-v-01", "missing_image", "background"}
PAIRS = ("bg-btn-01", "bg-btn-02", "value-frame", "nav-favorite", "nav-file")
PANELS = {"bg-title", "tips-bar-bg", "navbg", "statbg", "bg-gamelist", "menu-5line-bg", "menu-6line-bg", "app_loading_bg",
          "bg-pop-menu-4", "menu-sub-bg", "loading-bg", "loading-progress-left", "loading-progress-mid",
          "loading-progress-right", "preview-bg", "preview-nameFrame", "thumb-default", "div-line-v-02"}
FULL_SCREEN = ("bg-title", "tips-bar-bg", "navbg", "statbg", "bg-gamelist", "menu-5line-bg", "menu-6line-bg",
               "app_loading_bg")
PROGRESS = ("loading-progress-left", "loading-progress-mid", "loading-progress-right")
# copies drawn natively at their own size
COPIES = {
    "skin_1280x720": {"bg-list-l.png": ((1280, 135), None), "bg-game-item-f.png": ((231, 255), (9, 0, 216, 230)),
                      "bg-title.png": ((1280, 90), None), "app_loading_bg.png": ((960, 720), None),
                      "bg-pop-menu-4.png": ((480, 375), (0, 0, 480, 360)), "loading-progress-left.png": ((6, 75), None),
                      "loading-progress-mid.png": ((6, 75), None), "loading-progress-right.png": ((6, 75), None)},
    "skin_720x480": {"bg-list-l.png": ((720, 90), None), "list-item-select-bg-short.png": ((320, 60), None)},
    "skin_640_480": {"menu-sub-title-bg.png": ((320, 36), None), "menu-5line-bg.png": ((640, 480), None)},
    # odd leftovers: 752x70 and 746x559 at cell 5, 373x349 and 201x81 at cell 5
    "skin_752x560": {"bg-title.png": ((752, 70), None), "app_loading_bg.png": ((746, 559), None),
                     "menu-sub-bg.png": ((373, 349), None), "preview-nameFrame.png": ((201, 81), None),
                     "thumb-default.png": ((291, 419), None)},
    # even grids at cell 2 (a 14-cell button, 36x14 pills) and cell 3 copies
    "skin_720x540": {"context-a.png": ((29, 29), None), "context-start.png": ((73, 29), None),
                     "context-select.png": ((73, 29), None), "context-menu.png": ((73, 29), None),
                     "btn-delete.png": ((33, 33), (1, 5, 32, 28)), "btn-empty.png": ((33, 33), (1, 3, 32, 30)),
                     "btn-shift.png": ((33, 33), (2, 8, 31, 25)), "btn-space.png": ((33, 33), (4, 4, 29, 29)),
                     "nav-favorite-f.png": ((45, 45), (2, 3, 43, 42)), "nav-file-n.png": ((45, 45), (4, 6, 41, 37)),
                     "progress-dot.png": ((13, 13), (1, 1, 12, 12)), "bg-btn-02-f.png": ((123, 55), None),
                     "app_loading_03.png": ((112, 540), (30, 223, 84, 317))},
    "skin_1024x768": {"context-b.png": ((41, 41), None), "context-menu.png": ((104, 41), None),
                      "btn-empty.png": ((48, 48), (2, 4, 46, 44)), "nav-file-f.png": ((64, 64), (5, 8, 59, 53)),
                      "nav-favorite-n.png": ((64, 64), (3, 4, 61, 60)), "bg-btn-01-f.png": ((80, 80), None),
                      "value-frame-n.png": ((96, 38), None), "charging-02.png": ((160, 768), (43, 317, 120, 451))},
}


def synthetic(path, size, box):
    """A base-like PNG: the bar gray over `box` (the whole image when None), soft alpha-100 pixels around it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box or (0, 0) + size
    img.paste((80, 73, 69, 255), (x0, y0, x1, y1))
    if box:
        for x in range(x0, x1):
            if y1 < size[1]:
                img.putpixel((x, y1), (80, 73, 69, 100))
    img.save(path)


def make_base(path, files=None, copies=None):
    for name, (size, box) in (BASE if files is None else files).items():
        synthetic(os.path.join(path, "skin", name), size, box)
    for folder, entries in (COPIES if copies is None else copies).items():
        for name, (size, box) in entries.items():
            synthetic(os.path.join(path, folder, name), size, box)


def load(path):
    with Image.open(path) as im:
        return im.convert("RGBA")


def grid(img, canvas):
    """The cell grid of a drawn frame: {(cx, cy): RGBA} sampled at each cell's top-left pixel."""
    px = img.load()
    return {(cx, cy): px[canvas.ox + cx * canvas.cell, canvas.oy + cy * canvas.cell]
            for cy in range(canvas.rows) for cx in range(canvas.cols)}


class Kit(unittest.TestCase):
    def test_shades(self):
        s = frames.shades(GRUVBOX)
        bar = (80, 73, 69)
        self.assertEqual(s.bar, bar)
        self.assertEqual(s.hi, tuple(round(v + (255 - v) * .35) for v in bar))
        self.assertEqual(s.sh, tuple(round(v * .6) for v in bar))
        self.assertEqual(s.mid, tuple(round(v * .55) for v in bar))
        self.assertEqual(s.dark, tuple(round(v * .3) for v in bar))
        self.assertLess(sum(s.dark), sum(s.sh))
        self.assertEqual(s.ink, (27, 21, 48))
        self.assertEqual(s.accent, (0xD6, 0x5D, 0x0E))
        self.assertEqual((s.text, s.list, s.selected, s.dim),
                         ((0xEB, 0xDB, 0xB2), (0xFB, 0xF1, 0xC7), (0xFB, 0xF1, 0xC7), (0x7C, 0x6F, 0x64)))

    def test_cell_for(self):
        self.assertEqual(frames.cell_for((66, 26), (66, 26), small=True), 2)  # a wide glyph drawn as a small file
        self.assertEqual(frames.cell_for((104, 41), (66, 26), small=True), 3)
        self.assertEqual(frames.cell_for((66, 26), (66, 26)), 4)
        self.assertEqual(frames.cell_for((100, 20), None, small=True), 2)
        self.assertEqual(frames.cell_for((640, 90), (640, 90)), 4)
        self.assertEqual(frames.cell_for((1280, 135), (640, 90)), 6)
        self.assertEqual(frames.cell_for((720, 90), (640, 90)), 4)
        self.assertEqual(frames.cell_for((1280, 720), (640, 480)), 6)
        self.assertEqual(frames.cell_for((100, 20), None), 4)
        self.assertEqual(frames.cell_for((40, 20), None), 2)
        # small files (under 64 px wide in the base)
        self.assertEqual(frames.cell_for((50, 50), (50, 50)), 2)
        self.assertEqual(frames.cell_for((100, 100), (50, 50)), 4)
        self.assertEqual(frames.cell_for((30, 30), (50, 50)), 1)
        self.assertEqual(frames.cell_for((10, 10), (100, 100)), 2)

    def test_footprint(self):
        self.assertEqual(frames.footprint(Image.new("RGBA", (30, 20), (1, 2, 3, 255))), (0, 0, 30, 20))
        img = Image.new("RGBA", (30, 20), (0, 0, 0, 0))
        img.paste((1, 2, 3, 255), (4, 2, 26, 15))
        img.paste((1, 2, 3, 100), (0, 0, 30, 1))  # a soft edge, ignored
        self.assertEqual(frames.footprint(img), (4, 2, 26, 15))
        self.assertEqual(frames.footprint(Image.new("RGB", (5, 6))), (0, 0, 5, 6))
        self.assertIsNone(frames.footprint(Image.new("RGBA", (5, 6), (0, 0, 0, 0))))

    def test_canvas_leftover_split(self):
        c = frames.Canvas((700, 100), 4, (20, 10, 670, 90))  # 650 x 80
        self.assertEqual((c.cols, c.rows), (162, 20))
        self.assertEqual(c.ox, 20 + (650 - 648) // 2)
        self.assertEqual(c.oy, 10)
        c = frames.Canvas((700, 100), 4, (0, 0, 651, 83))  # odd leftovers: extra pixel right/bottom
        self.assertEqual((c.cols, c.rows, c.ox, c.oy), (162, 20, 1, 1))
        c.rect(0, 0, c.cols, c.rows, (9, 9, 9))
        self.assertEqual(c.image().getchannel("A").getbbox(), (1, 1, 649, 81))
        self.assertEqual(c.image().size, (700, 100))

    def test_rect_and_px_clip(self):
        c = frames.Canvas((16, 16), 4, (0, 0, 16, 16))
        c.rect(-2, -2, 10, 3, (1, 1, 1))
        c.px(9, 9, (1, 1, 1))
        self.assertEqual(c.image().getchannel("A").getbbox(), (0, 0, 16, 4))

    def test_panel_symmetric_corners(self):
        c = frames.Canvas((120, 80), 4, (0, 0, 120, 80))
        s = frames.shades(GRUVBOX)
        c.panel(1, 1, 28, 18, s.bar, s.hi, s.sh, s.ink, cut=3)
        alpha = c.image().getchannel("A")
        self.assertEqual(alpha.getbbox(), (4, 4, 116, 76))
        self.assertEqual(alpha, alpha.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
        self.assertEqual(alpha, alpha.transpose(Image.Transpose.FLIP_TOP_BOTTOM))
        px = c.image().load()
        self.assertEqual(px[4, 40][:3], s.ink)  # outline at the left edge
        self.assertEqual(px[4, 4][3], 0)  # corner cut
        self.assertEqual(px[16, 4][:3], s.ink)  # top edge starts after the 3-cell cut
        self.assertEqual(px[16, 8][:3], s.hi)
        self.assertEqual(px[16, 68][:3], s.sh)
        self.assertEqual(px[60, 40][:3], s.bar)
        self.assertEqual(px[12, 12][:3], s.bar)  # the bevel stays on the straight rows: no stray cell in the corner
        self.assertEqual(px[12, 64][:3], s.bar)
        # stepped 1:1: the outline's first cell on each row of the corner moves one cell per row
        firsts = [min(x for x in range(120) if px[x, y][3]) for y in (4, 8, 12, 16)]
        self.assertEqual(firsts, [16, 12, 8, 4])

    def test_dots_and_mirror(self):
        c = frames.Canvas((40, 8), 4, (0, 0, 40, 8))
        c.hline_dots(0, 0, 10, (5, 5, 5))
        c.vline_dots(0, 0, 2, (6, 6, 6), on=1, off=1)
        row = [c.image().load()[x * 4, 0][3] > 0 for x in range(10)]
        self.assertEqual(row, [True, True, False, True, True, False, True, True, False, True])
        self.assertEqual(c.image().load()[0, 4][3], 0)
        m = frames.Canvas((40, 4), 4, (0, 0, 40, 4))
        m.px(1, 0, (7, 7, 7))
        m.mirror()
        self.assertEqual(m.image().load()[8 * 4, 0][:3], (7, 7, 7))


class Frames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def build(self, palette, name="theme"):
        theme = os.path.join(self.tmp.name, name)
        make_base(theme)
        return theme, frames.apply(theme, palette)

    def check_margins(self, img, box, cell, spec):
        canvas = frames.Canvas(img.size, cell, box)
        alpha = img.getchannel("A")
        bbox = alpha.getbbox()
        self.assertIsNotNone(bbox)
        x0, y0, x1, y1 = box
        self.assertTrue(x0 <= bbox[0] and y0 <= bbox[1] and bbox[2] <= x1 and bbox[3] <= y1, (bbox, box))
        # regular steps: every pixel is its cell's color, nothing outside the grid
        cells = grid(img, canvas)
        expect = Image.new("RGBA", img.size, (0, 0, 0, 0))
        if spec.background is not None:
            expect.paste(tuple(spec.background) + (255,), box)
        for (cx, cy), rgba in cells.items():
            x, y = canvas.ox + cx * cell, canvas.oy + cy * cell
            expect.paste(rgba, (x, y, x + cell, y + cell))
        self.assertEqual(list(img.get_flattened_data()), list(expect.get_flattened_data()))
        # insets in cells: flush sides reach the grid edge, opposite non-flush insets are equal
        blank = (0, 0, 0, 0) if spec.background is None else tuple(spec.background) + (255,)
        on = [(cx, cy) for (cx, cy), rgba in cells.items() if rgba != blank]  # the artwork, not the background
        inset = {"left": min(x for x, _ in on), "right": canvas.cols - 1 - max(x for x, _ in on),
                 "top": min(y for _, y in on), "bottom": canvas.rows - 1 - max(y for _, y in on)}
        for side in spec.flush:
            self.assertEqual(inset[side], 0, side)
        for a, b in (("left", "right"), ("top", "bottom")):
            if a not in spec.flush and b not in spec.flush:
                self.assertEqual(inset[a], inset[b], (a, b, inset))
        # leftover pixels split evenly: at most one more on the right/bottom
        for lead, total, n in ((canvas.ox - x0, x1 - x0, canvas.cols), (canvas.oy - y0, y1 - y0, canvas.rows)):
            trail = total - n * cell - lead
            self.assertIn(trail - lead, (0, 1))
        if spec.symmetric:
            for (cx, cy), rgba in cells.items():
                self.assertEqual(rgba, cells[(canvas.cols - 1 - cx, cy)], (cx, cy))

    def test_every_registered_frame(self):
        names = {key.split("/", 1)[1] for key in frames.FRAMES}
        self.assertEqual(names, set(BASE))
        theme, written = self.build(GRUVBOX, "a")
        other, _ = self.build(GRUVBOX, "b")
        arcade, _ = self.build(ARCADE, "c")
        expected = {f"skin/{n}" for n in BASE} | {f"{folder}/{n}" for folder, entries in COPIES.items() for n in entries}
        self.assertEqual(sorted(written), sorted(expected))
        sizes = dict({f"skin/{n}": v for n, v in BASE.items()},
                     **{f"{folder}/{n}": v for folder, entries in COPIES.items() for n, v in entries.items()})
        for rel in sorted(written):
            with self.subTest(rel):
                spec = frames.FRAMES["skin/" + rel.split("/", 1)[1]]
                (size, box), base_size = sizes[rel], BASE[rel.split("/", 1)[1]][0]
                img = load(os.path.join(theme, rel))
                self.assertEqual(img.size, size)
                self.check_margins(img, box or (0, 0) + size, frames.cell_for(size, base_size, spec.small), spec)
                with open(os.path.join(theme, rel), "rb") as f, open(os.path.join(other, rel), "rb") as g:
                    self.assertEqual(f.read(), g.read())
                second = load(os.path.join(arcade, rel))
                self.assertEqual(img.getchannel("A"), second.getchannel("A"))
                self.assertNotEqual(img.convert("RGB"), second.convert("RGB"))

    def test_registry_has_all_key_files(self):
        names = {key.split("/", 1)[1][:-len(".png")] for key in frames.FRAMES}
        self.assertLessEqual(KEYS, names)
        for name in KEYS:
            self.assertIsNone(frames.FRAMES[f"skin/{name}.png"].background, name)  # glyphs keep a transparent surround

    def test_registry_covers_the_spec(self):
        names = {key.split("/", 1)[1][:-len(".png")] for key in frames.FRAMES}
        self.assertEqual(names, SPEC_FILES - NOT_DRAWN)

    def test_selected_and_unselected_share_geometry(self):
        theme, written = self.build(GRUVBOX)
        folders = sorted({rel.split("/", 1)[0] for rel in written})
        checked = 0
        for folder in folders:
            for pair in PAIRS:
                f, n = (os.path.join(theme, folder, f"{pair}-{state}.png") for state in "fn")
                if not (os.path.exists(f) and os.path.exists(n)):
                    continue
                with self.subTest(folder=folder, pair=pair):
                    img_f, img_n = load(f), load(n)
                    self.assertEqual(img_f.getchannel("A"), img_n.getchannel("A"))
                    self.assertNotEqual(img_f.convert("RGB"), img_n.convert("RGB"))
                    checked += 1
        self.assertGreaterEqual(checked, len(PAIRS))

    def test_hint_letters_centered(self):
        """The letter or word of a button hint is centered in its button: equal ink margins left/right and top/bottom,
        on odd (13-cell) and even (14-cell) grids alike."""
        theme, written = self.build(GRUVBOX)
        ink = frames.shades(GRUVBOX).ink
        hints = [rel for rel in written if rel.split("/", 1)[1].startswith("context-")]
        self.assertGreaterEqual(len(hints), 7 + 5)
        for rel in hints:
            with self.subTest(rel):
                img = load(os.path.join(theme, rel))
                name = rel.split("/", 1)[1]
                canvas = frames.Canvas(img.size, frames.cell_for(img.size, BASE[name][0], small=True), (0, 0) + img.size)
                cells = grid(img, canvas)
                # the letters: ink cells inside the button (not its outline ring)
                body = {xy for xy, rgba in cells.items() if rgba[3] and rgba[:3] != ink}
                letters = [(x, y) for (x, y), rgba in cells.items() if rgba[:3] == ink and
                           all((x + dx, y + dy) in body or cells.get((x + dx, y + dy), (0,) * 4)[:3] == ink
                               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
                self.assertTrue(letters)
                left, right = min(x for x, _ in letters), max(x for x, _ in letters)
                top, bottom = min(y for _, y in letters), max(y for _, y in letters)
                self.assertEqual(left, canvas.cols - 1 - right)
                self.assertEqual(top, canvas.rows - 1 - bottom)

    def test_animation_frames_keep_positions(self):
        theme, written = self.build(GRUVBOX)
        s = frames.shades(GRUVBOX)
        for kind in ("app_loading_0", "charging-0"):
            for folder in sorted({rel.split("/", 1)[0] for rel in written}):
                paths = [os.path.join(theme, folder, f"{kind}{i}.png") for i in range(1, 6)]
                if not all(os.path.exists(p) for p in paths):
                    continue
                with self.subTest(kind=kind, folder=folder):
                    imgs = [load(p) for p in paths]
                    masks = [img.getchannel("A") for img in imgs]
                    for mask in masks[1:]:
                        self.assertEqual(mask, masks[0])  # the same glyph in every frame: only its colors change
                    lit = [sum(px[:3] == s.accent and px[3] > 0 for px in img.get_flattened_data()) for img in imgs]
                    self.assertEqual(lit[0], 0)
                    self.assertEqual(lit, sorted(set(lit)))  # each frame lights more than the one before
                    self.assertEqual(lit[-1], sum(1 for v in masks[0].get_flattened_data() if v))

    def test_animation_frames_share_a_grid_inside_each_footprint(self):
        """A frame whose footprint is a pixel taller (a soft pixel over the threshold) still draws on the frames'
        common grid, so nothing jumps between frames, and each frame stays inside its own footprint."""
        theme = os.path.join(self.tmp.name, "theme")
        boxes = {i: (27, 198, 75, 282) for i in range(1, 6)}
        boxes[5] = (27, 197, 75, 282)
        make_base(theme, {f"charging-0{i}.png": ((100, 480), box) for i, box in boxes.items()}, {})
        frames.apply(theme, GRUVBOX)
        imgs = {i: load(os.path.join(theme, "skin", f"charging-0{i}.png")) for i in boxes}
        for i, img in imgs.items():
            bbox = img.getchannel("A").getbbox()
            x0, y0, x1, y1 = boxes[i]
            self.assertTrue(x0 <= bbox[0] and y0 <= bbox[1] and bbox[2] <= x1 and bbox[3] <= y1, (i, bbox))
            self.assertEqual(img.getchannel("A"), imgs[1].getchannel("A"), i)

    def test_trash_lines_evenly_spaced_both_ways(self):
        """The trash can's lines are as far from the lid and the bottom as from each other and the body's sides, at
        the base's grid, the 1280 copy's, odd and even widths."""
        s = frames.shades(GRUVBOX)
        for size, cell in (((28, 25), 2), ((41, 37), 3), ((30, 27), 2), ((31, 23), 2), ((44, 40), 3)):
            canvas = frames.Canvas(size, cell, (0, 0) + size)
            with self.subTest(grid=(canvas.cols, canvas.rows)):
                frames_keys.trash(canvas, s)
                overhang, lines, gap = frames_keys._trash_body(canvas.cols)
                self.assertGreater(lines, 0)
                left, right = overhang, canvas.cols - 1 - overhang
                xs = [left + 1 + gap + i * (gap + 1) for i in range(lines)]
                for x in xs:
                    column = [y for y in range(3, canvas.rows - 1) if (x, y) in canvas.cells]
                    top, bottom = column[0] - 3, canvas.rows - 2 - column[-1]  # rows clear under the lid, over the base
                    self.assertEqual(top, bottom, x)
                    self.assertEqual(top, gap)
                    self.assertEqual(column, list(range(column[0], column[-1] + 1)))
                self.assertEqual(xs[0] - left - 1, right - 1 - xs[-1])

    def test_small_grids_fall_back(self):
        """A grid too small for the usual trash spacing or tree still draws (fewer or no lines, a narrower tree or
        none), mirrored and centered, without raising."""
        s = frames.shades(GRUVBOX)
        for cols in (8, 10, 6, 5):
            canvas = frames.Canvas((cols * 2, 24), 2, (0, 0, cols * 2, 24))
            with self.subTest(trash=cols):
                frames_keys.trash(canvas, s)
                self.assertTrue(canvas.cells)
                for (x, y), rgb in canvas.cells.items():
                    self.assertEqual(canvas.cells.get((cols - 1 - x, y)), rgb, (x, y))
        for cols, rows in ((12, 8), (6, 12), (4, 4), (12, 14)):
            canvas = frames.Canvas((cols * 4, rows * 4), 4, (0, 0, cols * 4, rows * 4))
            with self.subTest(tree=(cols, rows)):
                frames_keys.tree(4)(canvas, s)
                if canvas.cells:
                    xs = [x for x, _ in canvas.cells]
                    ys = [y for _, y in canvas.cells]
                    self.assertEqual(min(xs), cols - 1 - max(xs))
                    self.assertEqual(min(ys), rows - 1 - max(ys))
        self.assertTrue(frames_keys.tree_rows(6, 12))  # narrower than the grid, but a tree

    def test_shift_arrow_fills_its_key(self):
        """The shift arrow is as big in its key as the backspace arrow: one cell of padding above and below it, and
        at least as many cells as the backspace head's span."""
        s = frames.shades(GRUVBOX)
        for size, cell in (((26, 16), 2), ((29, 17), 2), ((39, 25), 3)):
            canvas = frames.Canvas(size, cell, (0, 0) + size)
            with self.subTest(grid=(canvas.cols, canvas.rows)):
                frames_keys.shift(canvas, s)
                arrow = [(x, y) for x, y in canvas.cells if 1 < x < canvas.cols - 2 and 1 < y < canvas.rows - 2]
                ys = [y for _, y in arrow]
                xs = [x for x, _ in arrow]
                self.assertEqual((min(ys), max(ys)), (2, canvas.rows - 3))
                self.assertEqual(min(xs) - 1, canvas.cols - 2 - max(xs))
                self.assertGreaterEqual(max(xs) - min(xs) + 1, canvas.rows - 3)
                self.assertGreaterEqual(len(arrow), 10)

    def test_star_is_a_classic_star(self):
        """The star: a narrow peak, arms tapering to 1-cell points, legs tapering to 1-cell feet straight under the
        waist round a V notch whose top is the peak's width and whose depth is about a third of the star's height;
        exactly mirrored, centered with equal margins."""
        for cols, rows in ((18, 17), (19, 18), (20, 19), (21, 20)):
            cells, width, height = frames_keys.star_mask(cols, rows)
            with self.subTest(grid=(cols, rows)):
                peak = 2 - cols % 2
                self.assertEqual((cols - width) % 2, 0)
                self.assertEqual((rows - height) % 2, 0)
                self.assertLessEqual((width, height), (cols, rows))
                for (x, y) in cells:
                    self.assertIn((width - 1 - x, y), cells)

                def runs(y):
                    out, x = [], 0
                    while x < width:
                        if (x, y) in cells:
                            start = x
                            while (x, y) in cells:
                                x += 1
                            out.append((start, x - start))
                        x += 1
                    return out

                self.assertEqual(runs(0), [((width - peak) // 2, peak)])
                arm = max(range(height), key=lambda y: sum(n for _, n in runs(y)))
                self.assertEqual(runs(arm), [(0, width)])
                self.assertEqual(runs(arm + 1), [(1, width - 2)])  # the arm tips are single-cell points
                notch = [y for y in range(height) if len(runs(y)) == 2]
                self.assertEqual(notch, list(range(notch[0], height)))
                self.assertEqual(runs(notch[0])[1][0] - sum(runs(notch[0])[0]), peak)
                self.assertTrue(.25 <= len(notch) / height <= .4, (len(notch), height))
                legs = [runs(y)[0] for y in notch]
                self.assertEqual({start for start, _ in legs}, {legs[0][0]})  # a straight outer edge
                self.assertEqual([n for _, n in legs], list(range(legs[0][1], 0, -1)))  # 1:1 to a pointed foot

    def test_shift_arrow_is_solid(self):
        """The shift arrow is a solid head (a filled 1:1 triangle of three rows) over a stem as wide as its tip."""
        s = frames.shades(GRUVBOX)
        for size, cell in (((26, 16), 2), ((29, 17), 2), ((39, 25), 3)):
            canvas = frames.Canvas(size, cell, (0, 0) + size)
            with self.subTest(grid=(canvas.cols, canvas.rows)):
                frames_keys.shift(canvas, s)
                widths = [sum(1 for x in range(2, canvas.cols - 2) if (x, y) in canvas.cells)
                          for y in range(2, canvas.rows - 2)]
                tip = 2 - canvas.cols % 2
                self.assertEqual(widths, [tip, tip + 2, tip + 4] + [tip] * (len(widths) - 3))

    def test_registry_has_all_panel_files(self):
        names = {key.split("/", 1)[1][:-len(".png")] for key in frames.FRAMES}
        self.assertLessEqual(PANELS, names)
        self.assertNotIn("missing_image", names)
        for name in FULL_SCREEN:
            self.assertEqual(frames.FRAMES[f"skin/{name}.png"].background, (0, 0, 0), name)

    def test_progress_pieces_tile(self):
        theme, _ = self.build(GRUVBOX)
        for folder, cell in (("skin", 2), ("skin_1280x720", 3)):
            with self.subTest(folder):
                left, mid, right = (load(os.path.join(theme, folder, f"{n}.png")) for n in PROGRESS)
                pieces = [left, mid, mid, mid, right]
                strip = Image.new("RGBA", (sum(p.width for p in pieces), left.height), (0, 0, 0, 0))
                x = 0
                for p in pieces:
                    self.assertEqual((p.size, p.width), (left.size, 2 * cell))
                    strip.paste(p, (x, 0))
                    x += p.width
                px = strip.load()
                n, rows = strip.width // cell, strip.height // cell
                self.assertEqual(rows * cell, strip.height)
                cols = [tuple(px[c * cell, r * cell] for r in range(rows)) for c in range(n)]
                # no gap anywhere between the end caps' rows: every pixel inside is opaque
                for y in range(cell, strip.height - cell):
                    for x in range(strip.width):
                        self.assertEqual(px[x, y][3], 255, (x, y))
                # the outline rows run unbroken across every join, end cap to end cap
                for r in (0, rows - 1):
                    self.assertEqual({cols[c][r] for c in range(1, n - 1)}, {cols[1][r]})
                    self.assertEqual(cols[0][r][3], 0)  # the caps' stepped corners
                    self.assertEqual(cols[n - 1][r][3], 0)
                # the segments alternate evenly across the left and mid joins up to the leading edge
                for c in range(1, n - 3):
                    self.assertNotEqual(cols[c], cols[c + 1], c)
                    if c + 2 <= n - 3:
                        self.assertEqual(cols[c], cols[c + 2], c)
                # every piece is whole cells: each pixel is its cell's color
                for y in range(strip.height):
                    for x in range(strip.width):
                        self.assertEqual(px[x, y], px[x - x % cell, y - y % cell], (x, y))

    def test_full_screen_backgrounds_stay_opaque_black_inside(self):
        theme, written = self.build(GRUVBOX)
        files = [rel for rel in written if rel.split("/", 1)[1][:-len(".png")] in FULL_SCREEN]
        self.assertGreaterEqual(len(files), len(FULL_SCREEN) + 4)
        for rel in files:
            with self.subTest(rel):
                img = load(os.path.join(theme, rel))
                spec = frames.FRAMES["skin/" + rel.split("/", 1)[1]]
                base_size = BASE[rel.split("/", 1)[1]][0]
                canvas = frames.Canvas(img.size, frames.cell_for(img.size, base_size), (0, 0) + img.size)
                logo = rel.endswith("bg-title.png")
                colored = 0
                px = img.load()
                for y in range(img.height):
                    for x in range(img.width):
                        rgba = px[x, y]
                        self.assertEqual(rgba[3], 255, (x, y))
                        cx, cy = (x - canvas.ox) // canvas.cell, (y - canvas.oy) // canvas.cell
                        on_grid = 0 <= cx < canvas.cols and 0 <= cy < canvas.rows
                        edge = on_grid and min(cx, canvas.cols - 1 - cx, cy, canvas.rows - 1 - cy) < 2
                        slot = logo and on_grid and cx < canvas.rows  # bg-title's logo, at the left
                        if not (edge or slot):
                            self.assertEqual(rgba, (0, 0, 0, 255), (x, y))
                        colored += rgba != (0, 0, 0, 255)
                self.assertGreater(colored, 0)
                self.assertEqual(spec.background, (0, 0, 0))

    def test_border_brackets_have_equal_arms(self):
        s = frames.shades(GRUVBOX)
        accent = s.accent
        # every full-screen size of the real base's skin folders (and odd grids), at its own cell
        sizes = [(640, 480), (720, 480), (720, 540), (720, 720), (746, 559), (960, 720), (1024, 768), (1280, 720),
                 (852, 640), (644, 484), (650, 490)]
        for size in sizes:
            canvas = frames.Canvas(size, frames.cell_for(size, (640, 480)), (0, 0) + size)
            with self.subTest(size=size, grid=(canvas.cols, canvas.rows)):
                frames_panels.border(canvas, s)
                cells = canvas.cells
                x0, y0, x1, y1 = 1, 1, canvas.cols - 2, canvas.rows - 2
                arms = set()
                for x, dx in ((x0, 1), (x1, -1)):
                    for y, dy in ((y0, 1), (y1, -1)):
                        across = next(i for i in range(canvas.cols) if cells.get((x + dx * i, y)) != accent)
                        down = next(i for i in range(canvas.rows) if cells.get((x, y + dy * i)) != accent)
                        self.assertEqual(across, down, (x, y))
                        arms.add(across)
                        # a 1-2 cell gap, then a whole dash
                        gap_x = next(i for i in range(across, canvas.cols) if (x + dx * i, y) in cells) - across
                        gap_y = next(i for i in range(down, canvas.rows) if (x, y + dy * i) in cells) - down
                        self.assertIn(gap_x, (1, 2))
                        self.assertIn(gap_y, (1, 2))
                        self.assertIn((x + dx * (across + gap_x + 1), y), cells)
                        self.assertIn((x, y + dy * (down + gap_y + 1)), cells)
                self.assertEqual(len(arms), 1)
                self.assertIn(arms.pop(), (3, 4, 5))

    def test_title_tree_is_centered_in_its_slot(self):
        theme, written = self.build(GRUVBOX)
        accent, trunk = frames.shades(GRUVBOX).accent, frames.shades(GRUVBOX).hi
        for rel in sorted(r for r in written if r.endswith("bg-title.png")):
            with self.subTest(rel):
                img = load(os.path.join(theme, rel))
                canvas = frames.Canvas(img.size, frames.cell_for(img.size, BASE["bg-title.png"][0]), (0, 0) + img.size)
                cells = grid(img, canvas)
                tree = [(cx, cy) for (cx, cy), rgba in cells.items()
                        if cy < canvas.rows - 1 and rgba[:3] in (accent, trunk)]
                slot = (img.height - canvas.ox) // canvas.cell  # the title text starts at the bar's height
                left, right = min(x for x, _ in tree), max(x for x, _ in tree)
                top, bottom = min(y for _, y in tree), max(y for _, y in tree)
                self.assertEqual(left, slot - 1 - right)
                self.assertEqual(top, canvas.rows - 2 - bottom)
                self.assertGreaterEqual(top, 1)
                # three tiers of three rows each, every row centered on the tree's axis
                for y in range(top, bottom + 1):
                    xs = [x for x, yy in tree if yy == y]
                    self.assertEqual(min(xs) - left, right - max(xs), y)

    def test_non_uniform_copy_uses_min_ratio_cell(self):
        theme, _ = self.build(GRUVBOX)
        img = load(os.path.join(theme, "skin_1280x720", "bg-list-l.png"))
        canvas = frames.Canvas((1280, 135), 6, (0, 0, 1280, 135))
        self.assertEqual((canvas.cols, canvas.rows, canvas.ox, canvas.oy), (213, 22, 1, 1))
        alpha = img.getchannel("A")
        # the bar's first opaque row is one cell (6 px) below the grid top
        self.assertEqual(alpha.getbbox()[1], 1 + 6)
        self.assertEqual(alpha.getbbox()[3], 135 - 2 - 6)

    def test_apply_skips_missing_files_and_other_folders(self):
        theme = os.path.join(self.tmp.name, "theme")
        make_base(theme, {"bg-list-s.png": ((640, 60), None)}, {})
        synthetic(os.path.join(theme, "icons", "bg-list-l.png"), (640, 90), None)
        synthetic(os.path.join(theme, "skin_720x480", "bg-grid-s.png"), (156, 176), (2, 2, 150, 170))  # not in skin/
        Image.new("RGBA", (640, 480), (0, 0, 0, 255)).save(os.path.join(theme, "skin", "background.png"))
        with open(os.path.join(theme, "icons", "bg-list-l.png"), "rb") as f:
            icon = f.read()
        written = frames.apply(theme, GRUVBOX)
        self.assertEqual(sorted(written), ["skin/bg-list-s.png", "skin_720x480/bg-grid-s.png"])
        with open(os.path.join(theme, "icons", "bg-list-l.png"), "rb") as f:
            self.assertEqual(f.read(), icon)
        self.assertEqual(set(load(os.path.join(theme, "skin", "background.png")).get_flattened_data()), {(0, 0, 0, 255)})
        self.assertFalse(os.path.exists(os.path.join(theme, "skin", "bg-list-l.png")))

    def test_fully_transparent_base_stays_transparent(self):
        theme = os.path.join(self.tmp.name, "theme")
        os.makedirs(os.path.join(theme, "skin"))
        path = os.path.join(theme, "skin", "bg-grid-s.png")
        Image.new("RGBA", (156, 176), (0, 0, 0, 0)).save(path)
        with open(path, "rb") as f:
            before = f.read()
        self.assertEqual(frames.apply(theme, GRUVBOX), [])
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_build_theme_draws_frames_natively(self):
        base = os.path.join(self.tmp.name, "base")
        make_theme_base(base)
        make_base(base)
        dest = pixel_build.build_theme(base, os.path.join(self.tmp.name, "out"), "T", "CONSOLES", GRUVBOX)
        img = load(os.path.join(dest, "skin_720x480", "bg-list-l.png"))
        self.assertEqual(img.size, (720, 90))
        canvas = frames.Canvas((720, 90), 4, (0, 0, 720, 90))
        cells = grid(img, canvas)
        self.check_margins(img, (0, 0, 720, 90), 4, frames.FRAMES["skin/bg-list-l.png"])
        # drawn on its own 180-cell grid, not the 640 bar stretched: the outline row's corner cut is whole cells
        row = [cx for cx in range(canvas.cols) if cells[(cx, 1)][3]]
        self.assertEqual((row[0], row[-1]), (2, canvas.cols - 3))
        self.assertEqual(img.load()[7, 5][3], 0)
        self.assertEqual(img.load()[8, 5][:3], frames.shades(GRUVBOX).ink)
        self.assertEqual(load(os.path.join(dest, "skin", "bg-list-l.png")).size, (640, 90))

    def test_resize_variants_leaves_native_files(self):
        theme = os.path.join(self.tmp.name, "theme")
        make_base(theme, {"bg-list-l.png": ((640, 90), None)}, {"skin_720x480": {"bg-list-l.png": ((720, 90), None)}})
        Image.new("RGBA", (720, 60), (40, 40, 40, 255)).save(os.path.join(theme, "skin_720x480", "bg-title.png"))
        before = {}
        for file in ("bg-list-l.png", "bg-title.png"):
            with open(os.path.join(theme, "skin_720x480", file), "rb") as f:
                before[file] = f.read()
        native = {"skin_720x480/bg-list-l.png", "skin_720x480/bg-title.png"}
        pixel_build.resize_variants(theme, {"skin/bg-list-l.png"}, native)
        for file, data in before.items():
            with open(os.path.join(theme, "skin_720x480", file), "rb") as f:
                self.assertEqual(f.read(), data, file)
        pixel_build.resize_variants(theme, {"skin/bg-list-l.png"})
        self.assertEqual(load(os.path.join(theme, "skin_720x480", "bg-title.png")).getpixel((0, 0)), (0, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
