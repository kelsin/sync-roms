import contextlib
import io
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir  # noqa: E402
from PIL import Image  # noqa: E402
from sync_roms import s3, scrape_art, scrape_plan, store, upload  # noqa: E402

GBA = {"name": "Game Boy Advance", "bucket": "gba", "screenscraper": 12, "full_system": True, "folders": {}}
NES = {"name": "NES", "bucket": "nes", "screenscraper": 3, "full_system": True, "folders": {}}
PICO8 = {"name": "PICO-8", "bucket": "pico8", "screenscraper": 234, "full_system": True, "folders": {}}


def image_bytes(size=(600, 400)):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 10, 10)).save(out, "PNG")
    return out.getvalue()


def keys(*names):
    return {f"scrapes/gba/{n}": 10 for n in names}


class PlanTest(unittest.TestCase):
    def test_candidates_need_a_cover_or_miximage(self):
        plan = scrape_art.plan_art(keys("covers/a.png", "miximages/b.png", "screenshots/c.png"), {"onion", "spruce"}, False)
        self.assertEqual(sorted(s for s, _ in plan.make["onion"]), ["a", "b"])
        self.assertEqual(plan.no_source, 1)

    def test_cover_is_the_source_over_a_miximage(self):
        plan = scrape_art.plan_art(keys("covers/a.png", "miximages/a.png"), {"onion"}, False)
        self.assertEqual(plan.make["onion"], [("a", "scrapes/gba/covers/a.png")])

    def test_existing_files_are_skipped_without_replace(self):
        listing = keys("covers/a.png", "covers/b.png", "onion/a.png", "spruce/b.qoi")
        plan = scrape_art.plan_art(listing, {"onion", "spruce"}, False)
        self.assertEqual([s for s, _ in plan.make["onion"]], ["b"])
        self.assertEqual([s for s, _ in plan.make["spruce"]], ["a"])
        self.assertEqual((plan.have["onion"], plan.have["spruce"]), (1, 1))

    def test_replace_remakes_existing_files(self):
        plan = scrape_art.plan_art(keys("covers/a.png", "onion/a.png", "spruce/a.qoi"), {"onion", "spruce"}, True)
        self.assertEqual([s for s, _ in plan.make["onion"]], ["a"])
        self.assertEqual([s for s, _ in plan.make["spruce"]], ["a"])

    def test_subfolder_roms_are_ignored(self):
        plan = scrape_art.plan_art(keys("covers/Disc/a.png", "covers/b.png"), {"onion"}, False)
        self.assertEqual([s for s, _ in plan.make["onion"]], ["b"])

    def test_for_onion_only_plans_no_spruce(self):
        plan = scrape_art.plan_art(keys("covers/a.png"), {"onion"}, False)
        self.assertNotIn("spruce", plan.make)

    def test_estimates_per_rom(self):
        plan = scrape_art.plan_art(keys("covers/a.png", "covers/b.png"), {"onion", "spruce"}, False)
        self.assertEqual(plan.estimate_bytes["spruce"], 2 * scrape_art.EST_SPRUCE_BYTES)
        self.assertEqual(plan.estimate_bytes["onion"], 2 * scrape_art.EST_ONION_BYTES)

    def test_pico8_cart_is_a_candidate_with_the_cart_as_source(self):
        plan = scrape_art.plan_art({}, {"onion"}, False, carts=["pico8/x.p8.png", "pico8/note.txt"])
        self.assertEqual(plan.make["onion"], [("x.p8", "pico8/x.p8.png")])

    def test_pico8_cart_with_a_cover_uses_the_cover(self):
        listing = {"scrapes/pico8/covers/x.p8.png": 10}
        plan = scrape_art.plan_art(listing, {"onion"}, False, carts=["pico8/x.p8.png"])
        self.assertEqual(plan.make["onion"], [("x.p8", "scrapes/pico8/covers/x.p8.png")])


class CommandBase(StorageDir):
    systems = [GBA]

    def setUp(self):
        super().setUp()
        self.out = io.StringIO()
        for p in (mock.patch.object(store, "load_manifest", side_effect=lambda *a: {"systems": self.systems}),
                  mock.patch.object(upload, "ProcessPoolExecutor", ThreadPoolExecutor)):
            p.start()
            self.addCleanup(p.stop)

    def art(self, rom="a", kind="covers", size=(600, 400)):
        self.put(f"scrapes/gba/{kind}/{rom}.png", image_bytes(size))

    def run_art(self, **kw):
        args = SimpleNamespace(**{"system": None, "target": "both", "dry_run": False, "replace": False, "workers": 2, **kw})
        with contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.out):
            return scrape_art.art_command(args)

    def stored(self):
        return {k for k in s3.list_sizes("scrapes/")}

    def size_of(self, key):
        with Image.open(os.path.join(self.root, key)) as im:
            return im.size

    def read(self, key):
        with open(os.path.join(self.root, key), "rb") as f:
            return f.read()


class CommandTest(CommandBase):
    def test_dry_run_reports_counts_and_writes_nothing(self):
        self.art("a")
        self.art("b")
        self.put("scrapes/gba/spruce/b.qoi", b"old")
        self.put("scrapes/gba/screenshots/c.png")
        before = self.stored()
        with mock.patch("PIL.Image.open", side_effect=AssertionError("read an image")):
            self.assertEqual(self.run_art(dry_run=True), 0)
        text = self.out.getvalue()
        self.assertIn("estimate", text)
        self.assertIn("up to 3", text)
        self.assertEqual(self.stored(), before)

    def test_run_makes_all_four_files_for_a_rom(self):
        self.art("a")
        self.assertEqual(self.run_art(), 0)
        have = self.stored()
        for key in ("onion/a.png", "spruce/a.qoi", "spruce_med/a.qoi", "spruce_small/a.qoi"):
            self.assertIn(f"scrapes/gba/{key}", have)
        self.assertEqual(self.read("scrapes/gba/spruce/a.qoi")[:4], b"qoif")

    def test_rerun_makes_nothing_new(self):
        self.art("a")
        self.run_art()
        before = self.stored()
        with mock.patch.object(upload, "run_uploads") as run:
            self.assertEqual(self.run_art(), 0)
        run.assert_not_called()
        self.assertEqual(self.stored(), before)

    def test_replace_remakes_onion_art_with_the_new_source_order(self):
        self.art("a", "miximages", (100, 100))
        self.run_art(target="onion")
        self.assertEqual(self.size_of("scrapes/gba/onion/a.png"), (100, 100))
        self.art("a", "covers", (50, 80))
        self.run_art(target="onion", replace=True)
        self.assertEqual(self.size_of("scrapes/gba/onion/a.png"), (50, 80))

    def test_unreadable_cover_is_reported_and_the_rest_continue(self):
        self.put("scrapes/gba/covers/a.png", b"not an image")
        self.art("b")
        self.assertEqual(self.run_art(), 1)
        have = self.stored()
        self.assertIn("scrapes/gba/onion/b.png", have)
        self.assertNotIn("scrapes/gba/onion/a.png", have)
        self.assertIn("failed", self.out.getvalue())

    def test_for_spruce_only(self):
        self.art("a")
        self.assertEqual(self.run_art(target="spruce"), 0)
        have = self.stored()
        self.assertIn("scrapes/gba/spruce/a.qoi", have)
        self.assertNotIn("scrapes/gba/onion/a.png", have)

    def test_bad_for_value_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            self.run_art(target="bogus")
        self.assertEqual(e.exception.code, 2)

    def test_spruce_without_pillow_is_refused(self):
        self.art("a")
        with mock.patch.object(scrape_plan, "can_make_qoi", return_value=False), self.assertRaises(SystemExit) as e:
            self.run_art()
        self.assertEqual(e.exception.code, 2)

    def test_one_system_by_name(self):
        self.systems = [GBA, NES]
        self.art("a")
        self.put("scrapes/nes/covers/n.png", image_bytes())
        self.assertEqual(self.run_art(system="nes"), 0)
        have = self.stored()
        self.assertIn("scrapes/nes/onion/n.png", have)
        self.assertNotIn("scrapes/gba/onion/a.png", have)

    def test_pico8_cart_is_its_own_art(self):
        self.systems = [PICO8]
        self.put("pico8/x.p8.png", image_bytes((160, 205)))
        self.assertEqual(self.run_art(system="pico8"), 0)
        self.assertIn("scrapes/pico8/onion/x.p8.png", self.stored())
        self.assertIn("scrapes/pico8/spruce/x.p8.qoi", self.stored())


if __name__ == "__main__":
    unittest.main()
