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

    def test_make_art_writes_qoi_for_a_part_file_of_a_qoi(self):
        dst = os.path.join(self.dir, "x.qoi.part")
        scrape_plan.make_art(self.src, dst, (200, 200))
        with open(dst, "rb") as f:
            self.assertEqual(f.read(4), b"qoif")

    def test_make_art_writes_png_otherwise(self):
        dst = os.path.join(self.dir, "x.png")
        scrape_plan.make_art(self.src, dst, (200, 200))
        with Image.open(dst) as im:
            self.assertEqual((im.format, im.size), ("PNG", (200, 133)))

    def checkerboard(self):
        im = Image.new("P", (200, 200))
        im.putpalette([0, 0, 0, 255, 255, 255])
        im.putdata([(x // 2 + y // 2) % 2 for y in range(200) for x in range(200)])
        return im

    def test_shrinking_a_palette_image_smooths_it(self):
        src, dst = os.path.join(self.dir, "p.png"), os.path.join(self.dir, "p-out.png")
        self.checkerboard().save(src)
        scrape_plan.shrink_png(src, dst, (50, 50))
        with Image.open(dst) as im:
            self.assertIn(len({v for v in im.convert("L").get_flattened_data() if 0 < v < 255}), range(1, 300))

    def test_make_art_smooths_a_palette_image(self):
        src, dst = os.path.join(self.dir, "p.png"), os.path.join(self.dir, "p.qoi")
        self.checkerboard().save(src)
        scrape_plan.make_art(src, dst, (50, 50))  # raises if the resize left the palette mode the encoder can't take
        with open(dst, "rb") as f:
            self.assertEqual(f.read(4), b"qoif")

    def test_cmyk_jpeg_becomes_png_art(self):
        src, dst = os.path.join(self.dir, "c.jpg"), os.path.join(self.dir, "c.png")
        Image.new("CMYK", (300, 200), (10, 20, 30, 40)).save(src, "JPEG")
        scrape_plan.shrink_png(src, dst, (100, 100))
        with Image.open(dst) as im:
            self.assertEqual((im.format, im.mode, im.size), ("PNG", "RGB", (100, 67)))


if __name__ == "__main__":
    unittest.main()
