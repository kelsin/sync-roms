import os
import sys
import unittest
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import tempfile  # noqa: E402
from sync_roms import spruce_theme_fix  # noqa: E402

NES = b"nes-logo"


class FixTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())
        with open(spruce_theme_fix.IMAGE, "rb") as f:
            self.image = f.read()

    def path(self, theme, name):
        return os.path.join(self.base, "Themes", theme, "icons", "overlay", name)

    def put(self, theme, fc, fds):
        for name, data in (("fc.png", fc), ("fds.png", fds)):
            os.makedirs(os.path.dirname(self.path(theme, name)), exist_ok=True)
            with open(self.path(theme, name), "wb") as f:
                f.write(data)

    def read(self, theme, name="fds.png"):
        with open(self.path(theme, name), "rb") as f:
            return f.read()

    def test_buggy_card_is_fixed(self):
        for theme in spruce_theme_fix.THEMES:
            self.put(theme, NES, NES)
        self.assertEqual(len(spruce_theme_fix.install("spruce", self.base, False)), 3)
        for theme in spruce_theme_fix.THEMES:
            self.assertEqual(self.read(theme), self.image)
            self.assertEqual(self.read(theme, "fc.png"), NES)

    def test_different_fds_untouched(self):
        self.put("ART_BOOK_NEXT", NES, b"fixed upstream")
        self.assertEqual(spruce_theme_fix.install("spruce", self.base, False), [])
        self.assertEqual(self.read("ART_BOOK_NEXT"), b"fixed upstream")

    def test_absent_theme_or_files(self):
        self.assertEqual(spruce_theme_fix.install("spruce", self.base, False), [])
        os.makedirs(os.path.dirname(self.path("ART_BOOK_NOIR", "fc.png")))
        with open(self.path("ART_BOOK_NOIR", "fc.png"), "wb") as f:
            f.write(NES)
        self.assertEqual(spruce_theme_fix.install("spruce", self.base, False), [])

    def test_idempotent(self):
        self.put("ART_BOOK_NOIR", NES, NES)
        self.assertEqual(len(spruce_theme_fix.install("spruce", self.base, False)), 1)
        self.assertEqual(spruce_theme_fix.install("spruce", self.base, False), [])
        self.assertEqual(self.read("ART_BOOK_NOIR"), self.image)

    def test_dry_run_writes_nothing(self):
        self.put("ART_BOOK_OUTLINE", NES, NES)
        with mock.patch("sys.stdout", new=StringIO()) as out:
            self.assertEqual(len(spruce_theme_fix.install("spruce", self.base, True)), 1)
        self.assertIn("would replace", out.getvalue())
        self.assertEqual(self.read("ART_BOOK_OUTLINE"), NES)

    def test_other_layouts_skipped(self):
        self.put("ART_BOOK_NEXT", NES, NES)
        self.assertEqual(spruce_theme_fix.install("onion", self.base, False), [])
        self.assertEqual(self.read("ART_BOOK_NEXT"), NES)


if __name__ == "__main__":
    unittest.main()
