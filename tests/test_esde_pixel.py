import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)

from sync_roms.custom_themes.esde import systems as esde_systems  # noqa: E402
from sync_roms.custom_themes.pixel import build as pixel_build  # noqa: E402
from sync_roms.custom_themes.pixel.sprite import Sprite  # noqa: E402


class SystemsMap(unittest.TestCase):
    def test_every_esde_system_is_mapped_or_pending(self):
        names = set(esde_systems.esde_names())
        mapped = set(esde_systems.ICONS) | set(esde_systems.EXTRA)
        self.assertEqual(names - mapped, esde_systems.PENDING)

    def test_pending_and_mapped_are_disjoint(self):
        self.assertFalse(esde_systems.PENDING & (set(esde_systems.ICONS) | set(esde_systems.EXTRA)))

    def test_icons_point_at_drawn_sprites(self):
        for kind in ("CONSOLES", "CONTROLLERS"):
            drawn = pixel_build.systems(kind)
            for name, icon in esde_systems.ICONS.items():
                self.assertIn(icon, drawn, (kind, name))

    def test_sprites_render(self):
        for kind in ("CONSOLES", "CONTROLLERS"):
            for name, draw in esde_systems.sprites(kind).items():
                self.assertIsInstance(draw(), Sprite, (kind, name))

    def test_reuse(self):
        self.assertEqual(esde_systems.ICONS["mame-advmame"], esde_systems.ICONS["mame"])
        self.assertEqual(esde_systems.ICONS["naomi2"], "naomi")
        self.assertEqual(esde_systems.ICONS["naomigd"], "naomi")
        self.assertEqual(esde_systems.ICONS["msx2"], "msx")
        self.assertEqual(esde_systems.ICONS["fbneo"], "arcade")
        self.assertIn("mark3", esde_systems.EXTRA)


def existing_range():
    """The smallest and largest width or height of the Spruce set's sprites, both kinds."""
    sizes = []
    for kind in ("CONSOLES", "CONTROLLERS"):
        for draw in pixel_build.systems(kind).values():
            x0, y0, x1, y1 = draw().bounds()
            sizes += [x1 - x0, y1 - y0]
    return min(sizes), max(sizes)


class Batches(unittest.TestCase):
    def assert_drawn(self, names):
        low, high = existing_range()
        for name in names:
            self.assertIn(name, esde_systems.EXTRA, name)
            self.assertNotIn(name, esde_systems.PENDING, name)
            for kind in ("CONSOLES", "CONTROLLERS"):
                sprite = esde_systems.EXTRA[name][kind]()
                self.assertIsInstance(sprite, Sprite, (name, kind))
                x0, y0, x1, y1 = sprite.bounds()
                for size in (x1 - x0, y1 - y0):
                    self.assertGreaterEqual(size, low, (name, kind))
                    self.assertLessEqual(size, high, (name, kind))

    def test_batch_3_drawn(self):
        self.assert_drawn(["gc", "wii", "wiiu", "switch", "n64dd"])

    def test_batch_4_drawn(self):
        self.assert_drawn(["ps2", "ps3", "ps4", "psvita", "xbox", "xbox360", "xboxone"])

    def test_batch_5_drawn(self):
        self.assert_drawn(["3do", "cdimono1", "pcfx", "atarijaguarcd", "arcadia", "gamecom", "uzebox"])


def load_tool(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SpriteSheet(unittest.TestCase):
    def test_sheet_has_a_row_per_name_and_the_reference_row(self):
        tool = load_tool("esde_sprite_sheet")
        img = tool.sheet(["gb", "nes"])
        self.assertEqual(img.height, 3 * tool.ROW)
        self.assertGreaterEqual(img.width, 4 * tool.CELL)


if __name__ == "__main__":
    unittest.main()
