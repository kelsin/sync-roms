import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardfs, spruce_theme_fix  # noqa: E402


class ThemeFixTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())

    def put(self, rel, data=b"x"):
        path = os.path.join(self.base, "Themes", *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_copies_missing_poke(self):
        self.put("ART_BOOK_OUTLINE/bg/pokemini.png", b"bg")
        self.put("ART_BOOK_OUTLINE/icons/overlay/pokemini.png", b"logo")
        self.put("ART_BOOK_OUTLINE/icons/pokemini.png", b"icon")
        self.put("ART_BOOK_OUTLINE/icons/poke.png", b"icon")
        copies = spruce_theme_fix.plan(self.base)
        self.assertEqual(spruce_theme_fix.apply(copies), 2)
        cardfs.flush()
        with open(os.path.join(self.base, "Themes", "ART_BOOK_OUTLINE", "icons", "overlay", "poke.png"), "rb") as f:
            self.assertEqual(f.read(), b"logo")
        self.assertEqual(spruce_theme_fix.plan(self.base), [])

    def test_nothing_when_fixed_or_absent(self):
        self.assertEqual(spruce_theme_fix.plan(self.base), [])
        self.put("ART_BOOK_NEXT/icons/overlay/pokemini.png")
        self.put("ART_BOOK_NEXT/icons/overlay/poke.png")
        self.assertEqual(spruce_theme_fix.plan(self.base), [])

    def test_other_themes_untouched(self):
        self.put("SPRUCE/icons/pokemini.png")
        self.assertEqual(spruce_theme_fix.plan(self.base), [])


if __name__ == "__main__":
    unittest.main()
