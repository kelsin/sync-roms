import os
import sys
import tempfile
import unittest
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import io  # noqa: E402
import re  # noqa: E402
from PIL import Image  # noqa: E402
from sync_roms import cardfs, spruce_fixes, store  # noqa: E402
from sync_roms.spruce_fixes import fds, pokemini  # noqa: E402

NES = b"nes-logo"


class Base(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())

    def put(self, rel, data=b"x"):
        path = os.path.join(self.base, "Themes", *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def get(self, rel):
        with open(os.path.join(self.base, "Themes", *rel.split("/")), "rb") as f:
            return f.read()

    def run_fixes(self, dry_run=False, layout="spruce"):
        with mock.patch("sys.stdout", new=StringIO()) as out:
            count = spruce_fixes.run(layout, self.base, dry_run)
        cardfs.flush()
        return count, out.getvalue()

    def line(self, out, fix):
        line = [x for x in out.splitlines() if store.repo_json("spruce-fixes")[fix.ID]["title"] in x][0]
        self.assertIn(store.repo_json("spruce-fixes")[fix.ID]["upstream"], line)
        return line


class PokeminiTests(Base):
    def test_copies_missing_poke(self):
        self.put("ART_BOOK_OUTLINE/bg/pokemini.png", b"bg")
        self.put("ART_BOOK_OUTLINE/icons/overlay/pokemini.png", b"logo")
        self.put("ART_BOOK_OUTLINE/icons/pokemini.png", b"icon")
        self.put("ART_BOOK_OUTLINE/icons/poke.png", b"icon")
        writes, _ = pokemini.plan(self.base)
        self.assertEqual(len(writes), 2)
        count, out = self.run_fixes()
        self.assertEqual(count, 2 + 0)
        self.assertIn("applied to 2 file(s)", self.line(out, pokemini))
        self.assertEqual(self.get("ART_BOOK_OUTLINE/icons/overlay/poke.png"), b"logo")
        count, out = self.run_fixes()
        self.assertIn("already has poke.png", self.line(out, pokemini))

    def test_skipped_when_fixed_or_absent(self):
        self.assertEqual(pokemini.plan(self.base), ([], spruce_fixes.ABSENT))
        self.put("ART_BOOK_NEXT/icons/overlay/pokemini.png")
        self.put("ART_BOOK_NEXT/icons/overlay/poke.png")
        writes, skip = pokemini.plan(self.base)
        self.assertEqual(writes, [])
        self.assertIn("already has poke.png", skip)

    def test_resized_copies(self):
        self.put("ART_BOOK_NEXT/icons_720x480/overlay/pokemini.png", b"scaled")
        self.put("ART_BOOK_NEXT/icons_old/overlay/pokemini.png", b"old")
        count, out = self.run_fixes()
        self.assertEqual(count, 1)
        self.assertIn("Fixing 720x480 theme variation", out)
        self.assertEqual(self.get("ART_BOOK_NEXT/icons_720x480/overlay/poke.png"), b"scaled")
        self.assertFalse(os.path.exists(os.path.join(self.base, "Themes", "ART_BOOK_NEXT", "icons_old", "overlay",
                                                     "poke.png")))

    def test_other_themes_untouched(self):
        self.put("SPRUCE/icons/pokemini.png")
        self.assertEqual(pokemini.plan(self.base), ([], spruce_fixes.ABSENT))


class FdsTests(Base):
    def setUp(self):
        super().setUp()
        with open(fds.IMAGE, "rb") as f:
            self.image = f.read()

    def put_pair(self, theme, fc, fds_data):
        self.put(f"{theme}/icons/overlay/fc.png", fc)
        self.put(f"{theme}/icons/overlay/fds.png", fds_data)

    def read(self, theme, name="fds.png"):
        return self.get(f"{theme}/icons/overlay/{name}")

    def test_fds_keeps_only_fixed_file(self):
        fixed = self.put("ART_BOOK_NEXT/icons/overlay/fds.png", self.image)
        other = self.put("ART_BOOK_NEXT/icons/overlay/fc.png", self.image)
        buggy = self.put("ART_BOOK_NOIR/icons/overlay/fds.png", NES)
        outside = self.put("OTHER/icons/overlay/fds.png", self.image)
        self.assertTrue(fds.keeps(fixed))
        self.assertTrue(spruce_fixes.keeps(fixed))
        for path in (other, buggy, outside, os.path.join(self.base, "Themes", "ART_BOOK_NEXT", "icons", "overlay", "none.png")):
            self.assertFalse(fds.keeps(path))
            self.assertFalse(spruce_fixes.keeps(path))

    def test_buggy_card_is_fixed(self):
        for theme in fds.THEMES:
            self.put_pair(theme, NES, NES)
        count, out = self.run_fixes()
        self.assertEqual(count, 3)
        self.assertIn("applied to 3 file(s)", self.line(out, fds))
        self.assertNotIn("theme variation", out)
        for theme in fds.THEMES:
            self.assertEqual(self.read(theme), self.image)
            self.assertEqual(self.read(theme, "fc.png"), NES)

    def test_upstream_fixed_untouched(self):
        self.put_pair("ART_BOOK_NEXT", NES, b"fixed upstream")
        count, out = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("upstream fixed it", self.line(out, fds))
        self.assertEqual(self.read("ART_BOOK_NEXT"), b"fixed upstream")

    def test_earlier_sync_is_not_called_upstream(self):
        self.put_pair("ART_BOOK_NOIR", NES, NES)
        self.run_fixes()
        count, out = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("an earlier sync applied it", self.line(out, fds))
        self.assertNotIn("upstream fixed", self.line(out, fds))
        self.assertEqual(self.read("ART_BOOK_NOIR"), self.image)

    def background(self, theme, size):
        out = io.BytesIO()
        Image.new("RGB", size).save(out, "PNG")
        self.put(f"{theme}/skin/background.png", out.getvalue())

    def test_resized_copy_at_scale_one(self):
        self.background("ART_BOOK_NEXT", (640, 480))
        self.put("ART_BOOK_NEXT/icons_720x480/overlay/fc.png", NES)
        self.put("ART_BOOK_NEXT/icons_720x480/overlay/fds.png", NES)
        self.put("ART_BOOK_NEXT/icons_old/overlay/fc.png", NES)
        self.put("ART_BOOK_NEXT/icons_old/overlay/fds.png", NES)
        count, out = self.run_fixes()
        self.assertEqual(count, 1)
        self.assertIn("Fixing 720x480 theme variation", out)
        self.assertEqual(self.get("ART_BOOK_NEXT/icons_720x480/overlay/fds.png"), self.image)
        self.assertEqual(self.get("ART_BOOK_NEXT/icons_old/overlay/fds.png"), NES)
        count, out = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("an earlier sync applied it", self.line(out, fds))

    def test_resized_copy_is_scaled(self):
        self.background("ART_BOOK_NOIR", (640, 480))
        self.put_pair("ART_BOOK_NOIR", NES, NES)
        self.put("ART_BOOK_NOIR/icons_1280x960/overlay/fc.png", NES)
        self.put("ART_BOOK_NOIR/icons_1280x960/overlay/fds.png", NES)
        count, _ = self.run_fixes()
        self.assertEqual(count, 2)
        self.assertEqual(self.read("ART_BOOK_NOIR"), self.image)
        scaled = Image.open(io.BytesIO(self.get("ART_BOOK_NOIR/icons_1280x960/overlay/fds.png")))
        self.assertEqual(scaled.size, (800, 144))
        count, out = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("an earlier sync applied it", self.line(out, fds))
        self.assertNotIn("upstream fixed", self.line(out, fds))

    def test_absent_theme_or_files(self):
        self.assertEqual(fds.plan(self.base), ([], spruce_fixes.ABSENT))
        self.put("ART_BOOK_NOIR/icons/overlay/fc.png", NES)
        self.assertEqual(fds.plan(self.base), ([], spruce_fixes.ABSENT))


class DataTests(unittest.TestCase):
    def test_every_fix_has_a_pull_request_url(self):
        info = store.repo_json("spruce-fixes")
        self.assertEqual(sorted(info), sorted(f.ID for f in spruce_fixes.FIXES))
        for entry in info.values():
            self.assertTrue(entry["title"])
            self.assertRegex(entry["upstream"], r"^https://github\.com/[^/]+/[^/]+/pull/\d+$")


class RunTests(Base):
    def test_dry_run_writes_nothing(self):
        self.put("ART_BOOK_OUTLINE/icons/overlay/pokemini.png", b"logo")
        self.put("ART_BOOK_OUTLINE/icons/overlay/fc.png", NES)
        self.put("ART_BOOK_OUTLINE/icons/overlay/fds.png", NES)
        count, out = self.run_fixes(dry_run=True)
        self.assertEqual(count, 2)
        self.assertIn("would apply to 1 file(s)", self.line(out, fds))
        self.assertIn("would apply to 1 file(s)", self.line(out, pokemini))
        self.assertEqual(self.get("ART_BOOK_OUTLINE/icons/overlay/fds.png"), NES)
        self.assertFalse(os.path.exists(os.path.join(self.base, "Themes", "ART_BOOK_OUTLINE", "icons", "overlay", "poke.png")))

    def test_absent_line(self):
        count, out = self.run_fixes()
        self.assertEqual(count, 0)
        self.assertIn("Spruce fixes", out)
        for fix in spruce_fixes.FIXES:
            self.assertIn(getattr(fix, "MISSING", "the theme isn't on the card"), self.line(out, fix))

    def test_other_layouts_print_nothing(self):
        self.put("ART_BOOK_NEXT/icons/overlay/fc.png", NES)
        self.put("ART_BOOK_NEXT/icons/overlay/fds.png", NES)
        count, out = self.run_fixes(layout="onion")
        self.assertEqual((count, out), (0, ""))
        self.assertEqual(self.get("ART_BOOK_NEXT/icons/overlay/fds.png"), NES)


if __name__ == "__main__":
    unittest.main()
