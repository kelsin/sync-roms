import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402
from test_frames import make_base  # noqa: E402

from sync_roms.custom_themes import palettes  # noqa: E402
from sync_roms.custom_themes.pixel import frames, recipe  # noqa: E402
from sync_roms.custom_themes.pixel.recipe import Recipe  # noqa: E402
from sync_roms.custom_themes.pixel.sprite import _rgb  # noqa: E402

BLACK = (0, 0, 0)


class RecipeTests(unittest.TestCase):
    def test_resolve_matches_shades(self):
        rs = recipe.shades()
        for p in palettes.PALETTES.values():
            want = frames.shades(p)
            for f in want.__dataclass_fields__:
                self.assertEqual(getattr(want, f), recipe.resolve(getattr(rs, f), p), (p.name, f))

    def test_mix_composes(self):
        for p in palettes.PALETTES.values():
            bar = _rgb(p.bar)
            got = frames._mix(Recipe("bar", BLACK, .7), BLACK, .5)
            self.assertIsInstance(got, Recipe)
            self.assertEqual(recipe.resolve(got, p), frames._mix(frames._mix(bar, BLACK, .7), BLACK, .5))

    def test_recorded_frames_resolve_to_drawn(self):
        for name in ("Gruvbox", "Arcade", "Dracula"):
            p = palettes.get(name)
            with tempfile.TemporaryDirectory() as d:
                make_base(d)
                recorded = {}
                written = frames.apply(d, p, recipes=recorded)
                self.assertTrue(written)
                self.assertEqual(sorted(recorded), sorted(written))
                for rel in written:
                    canvas = recorded[rel]
                    canvas.cells = {k: recipe.resolve(v, p) for k, v in canvas.cells.items()}
                    with Image.open(os.path.join(d, rel)) as im:
                        self.assertEqual(canvas.image().tobytes(), im.convert("RGBA").tobytes(), (name, rel))


if __name__ == "__main__":
    unittest.main()
