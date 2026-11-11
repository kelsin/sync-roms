import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import budget, sizecache  # noqa: E402

GBA = {"bucket": "gba", "name": "GBA"}
SIZES = {"gba/A.zip": 100, "gba/B.zip": 200, "gba/C.zip": 400}
SCRAPES = {"scrapes/gba/screenshots/A.png": 10, "scrapes/gba/onion/A.png": 3, "scrapes/gba/slot/A.png": 5,
           "scrapes/gba/screenshots/B.png": 20}
SET = {"id": "s", "name": "S", "games": [{"system": "gba", "bucket": "gba/A.zip"}, {"system": "gba", "bucket": "gba/B.zip"}]}


def g(key):
    return {"title": key, "bucket": key}


class Budget(DataDir):
    def setUp(self):
        super().setUp()
        self.cache = {"gba/": SIZES, "scrapes/gba/": SCRAPES}
        for target, new in (("cached", lambda p: self.cache.get(p)), ):
            p = mock.patch.object(sizecache, target, new)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("sync_roms.store.load_sets", lambda: [SET])
        p.start()
        self.addCleanup(p.stop)

    def usage(self, card, layout="slot"):
        return budget.system_usage({"layout": layout, **card}, GBA)

    def test_rom_plus_layout_scrapes(self):
        self.assertEqual(tuple(self.usage({"games": {"gba": [g("gba/A.zip")]}}, "slot")), (105, 1, False))
        self.assertEqual(self.usage({"games": {"gba": [g("gba/A.zip")]}}, "esde").bytes, 110)
        self.assertEqual(self.usage({"games": {"gba": [g("gba/A.zip")]}}, "onion").bytes, 103)

    def test_layout_without_scrapes(self):
        self.assertEqual(self.usage({"games": {"gba": [g("gba/A.zip")]}}, "other").bytes, 100)

    def test_direct_and_set_count_once(self):
        u = self.usage({"games": {"gba": [g("gba/A.zip")], "sets": ["s"]}}, "other")
        self.assertEqual((u.bytes, u.count), (300, 2))

    def test_full_system(self):
        u = self.usage({"games": {"gba": {"full_system": True}}}, "other")
        self.assertEqual((u.bytes, u.count), (700, 3))

    def test_excluded(self):
        u = self.usage({"games": {"sets": ["s"]}, "excluded": {"gba": ["gba/A.zip"]}}, "other")
        self.assertEqual((u.bytes, u.count), (200, 1))

    def test_uncached_is_partial(self):
        self.cache.pop("gba/")
        u = self.usage({"games": {"gba": [g("gba/A.zip")]}}, "other")
        self.assertEqual(tuple(u), (0, 1, True))
        self.cache["gba/"] = SIZES
        self.cache.pop("scrapes/gba/")
        u = self.usage({"games": {"gba": [g("gba/A.zip")]}}, "esde")
        self.assertEqual(tuple(u), (100, 1, True))

    def test_card_usage_sums(self):
        u = budget.card_usage({"layout": "other", "games": {"gba": [g("gba/A.zip")]}}, [GBA, {"bucket": "ps2"}])
        self.assertEqual(tuple(u), (100, 1, True))  # ps2 has no cache

    def test_capacity(self):
        self.assertEqual(budget.card_capacity({"size": "512 GB"}), 512 * 10 ** 9)
        self.assertEqual(budget.card_capacity({"size": "1 TB"}), 10 ** 12)
        for bad in ({}, {"size": ""}, {"size": "lots"}, {"size": 5}, {"size": None}):
            self.assertIsNone(budget.card_capacity(bad))


if __name__ == "__main__":
    unittest.main()
