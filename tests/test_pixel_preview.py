import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

from sync_roms.custom_themes import palettes  # noqa: E402
from sync_roms.custom_themes.pixel import build, preview  # noqa: E402


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


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

    def test_build_preview_writes_png(self):
        with tempfile.TemporaryDirectory() as d:
            build.preview(d, "CONSOLES", palettes.get("Gruvbox"))
            with Image.open(os.path.join(d, "preview.png")) as im:
                self.assertEqual(im.size, (640, 480))


if __name__ == "__main__":
    unittest.main()
