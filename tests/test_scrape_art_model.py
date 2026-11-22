import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from PIL import Image  # noqa: E402
from sync_roms import scrape_plan  # noqa: E402


class FitTest(unittest.TestCase):
    def test_fit_never_enlarges(self):
        self.assertEqual(scrape_plan.fit((100, 50), (640, 480)), (100, 50))

    def test_fit_keeps_aspect(self):
        self.assertEqual(scrape_plan.fit((1280, 960), (640, 480)), (640, 480))
        self.assertEqual(scrape_plan.fit((700, 1000), (640, 480)), (336, 480))


class TiersTest(unittest.TestCase):
    def test_tiers_for_a_large_source(self):
        self.assertEqual(scrape_plan.spruce_tiers((1280, 960)), ["spruce", "spruce_med", "spruce_small"])

    def test_tiers_for_a_small_source(self):
        self.assertEqual(scrape_plan.spruce_tiers((150, 100)), ["spruce"])

    def test_tiers_for_a_mid_source(self):
        self.assertEqual(scrape_plan.spruce_tiers((500, 400)), ["spruce", "spruce_med", "spruce_small"])
        self.assertEqual(scrape_plan.spruce_tiers((300, 250)), ["spruce", "spruce_small"])


class MakeArtTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.src = os.path.join(tmp.name, "s.png")
        Image.new("RGB", (300, 200), (200, 10, 10)).save(self.src)

    def test_make_art_writes_qoi_for_a_qoi_destination(self):
        dst = os.path.join(self.dir, "x.qoi")
        scrape_plan.make_art(self.src, dst, (200, 200))
        with open(dst, "rb") as f:
            data = f.read()
        self.assertEqual(data[:4], b"qoif")
        self.assertEqual((int.from_bytes(data[4:8], "big"), int.from_bytes(data[8:12], "big")), (200, 133))

    def test_make_art_writes_png_otherwise(self):
        dst = os.path.join(self.dir, "x.png")
        scrape_plan.make_art(self.src, dst, (200, 200))
        with Image.open(dst) as im:
            self.assertEqual((im.format, im.size), ("PNG", (200, 133)))


if __name__ == "__main__":
    unittest.main()
