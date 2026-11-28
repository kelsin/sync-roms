import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

from sync_roms.custom_themes import palettes, templates  # noqa: E402
from sync_roms.custom_themes.pixel import frames, recolor  # noqa: E402
from sync_roms.custom_themes.pixel.recipe import ROLES, Recipe  # noqa: E402
from sync_roms.custom_themes.pixel.sprite import _rgb  # noqa: E402

WHITE, BLACK = (255, 255, 255), (0, 0, 0)


def colors(p):
    return {r: getattr(p, r) for r in ROLES}


class TemplateTests(unittest.TestCase):
    def test_round_trip_fixed(self):
        px = [(i * 15 % 256, i * 7 % 256, i * 3 % 256, 255 if i % 3 else 0) for i in range(16)]
        w, h, out = templates.render(templates.encode(4, 4, px), {})
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(out, bytes(c for p in px for c in p))

    def test_role_and_mix_entries(self):
        p = palettes.PALETTES["Nord"]
        bar = _rgb(p.bar)
        data = templates.encode(2, 1, [(Recipe("bar"), 255), (Recipe("bar", WHITE, .35), 255)])
        _, _, out = templates.render(data, colors(p))
        self.assertEqual(tuple(out[:3]), bar)
        self.assertEqual(tuple(out[4:7]), frames._mix(bar, WHITE, .35))

    def test_nested_recipe_is_kind2(self):
        r = Recipe(Recipe("bar", BLACK, .7), BLACK, .5)
        data = templates.encode(1, 1, [(r, 200)])
        _, _, entries, _ = templates.decode(data)
        kinds = [e[1] for e in entries]
        self.assertIn(2, kinds)
        for i, e in enumerate(entries):
            if e[1] == 2:
                self.assertLess(e[2], i)
        p = palettes.PALETTES["Nord"]
        _, _, out = templates.render(data, colors(p))
        from sync_roms.custom_themes.pixel import recipe
        self.assertEqual(tuple(out[:3]), recipe.resolve(r, p))
        self.assertEqual(out[3], 200)

    def test_two_byte_indexes(self):
        px = [(i % 256, i // 256, 0, 255) for i in range(300)]
        data = templates.encode(20, 15, px)
        self.assertEqual(templates.decode(data)[2].__len__(), 300)
        self.assertEqual(int.from_bytes(data[10:12], "little") & 1, 1)
        self.assertEqual(templates.render(data, {})[2], bytes(c for p in px for c in p))

    def test_role_ids_match_recipe(self):
        self.assertEqual(templates.ROLE_IDS, ROLES)

    def test_bad_magic(self):
        with self.assertRaises(ValueError):
            templates.decode(b"NUTP" + b"\0" * 20)

    def test_from_canvas_matches_image(self):
        cv = frames.Canvas((23, 17), 3, (1, 1, 22, 16), background=(10, 20, 30))
        cv.rect(1, 1, 2, 2, (200, 100, 50))
        cv.px(0, 0, (1, 2, 3))
        w, h, out = templates.render(templates.from_canvas(cv), {})
        self.assertEqual((w, h), (23, 17))
        self.assertEqual(out, cv.image().tobytes())

    def test_from_canvas_recipes(self):
        cv = frames.Canvas((6, 6), 2, (0, 0, 6, 6))
        cv.px(0, 0, Recipe("bar"))
        p = palettes.PALETTES["Nord"]
        _, _, out = templates.render(templates.from_canvas(cv), colors(p))
        self.assertEqual(tuple(out[:4]), _rgb(p.bar) + (255,))
        self.assertEqual(tuple(out[8:12]), (0, 0, 0, 0))

    def test_from_bar_image(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.png")
            img = Image.new("RGBA", (2, 1), recolor.BAR_GRAY + (128,))
            img.putpixel((1, 0), (9, 8, 7, 255))
            img.save(path)
            data = templates.from_bar_image(path)
            p = palettes.PALETTES["Nord"]
            _, _, out = templates.render(data, colors(p))
            self.assertEqual(tuple(out[:4]), _rgb(p.bar) + (128,))
            self.assertEqual(tuple(out[4:]), (9, 8, 7, 255))
            Image.new("RGBA", (1, 1), (1, 2, 3, 255)).save(path)
            self.assertIsNone(templates.from_bar_image(path))

    def test_render_uses_no_pillow(self):
        data = templates.encode(2, 1, [(Recipe("bar", WHITE, .35), 255), (1, 2, 3, 4)])
        code = ("import sys\n"
                "from sync_roms.custom_themes import templates\n"
                "sys.modules['PIL'] = None  # the package imports Pillow; render itself must not\n"
                f"w, h, out = templates.render({data!r}, {{'bar': '#434C5E'}})\n"
                "print(w, h, out.hex())")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split()[:2], ["2", "1"])


if __name__ == "__main__":
    unittest.main()
