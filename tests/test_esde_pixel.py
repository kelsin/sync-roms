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


if __name__ == "__main__":
    unittest.main()
