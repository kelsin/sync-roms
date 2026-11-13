import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import budget, inventory  # noqa: E402

GBA = {"bucket": "gba", "name": "GBA"}
SIZES = {"gba/A.zip": 100, "gba/B.zip": 200, "gba/C.zip": 400}
SCRAPES = {"scrapes/gba/screenshots/A.png": 10, "scrapes/gba/onion/A.png": 3, "scrapes/gba/slot/A.png": 5,
           "scrapes/gba/screenshots/B.png": 20}
VITA = {"bucket": "psvita", "name": "Vita"}
G = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"
DLC = "psvita/D [PCSE00349] [USA] [DLC-X].zip"
UPD = "psvita/G [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip"
SET = {"id": "s", "name": "S", "games": [{"system": "gba", "bucket": "gba/A.zip"}, {"system": "gba", "bucket": "gba/B.zip"}]}


def g(key):
    return {"title": key, "bucket": key}


class Budget(DataDir):
    def setUp(self):
        super().setUp()
        self.cache = {"gba/": SIZES, "scrapes/gba/": SCRAPES}
        for target, new in (("cached", lambda p: self.cache.get(p)), ):
            p = mock.patch.object(inventory, target, new)
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

    def test_collection_games_count_like_picks_and_ignore_exclusions(self):
        fav = {"id": "fav", "name": "Fav", "games": [{"system": "gba", "bucket": "gba/C.zip"}, {"system": "gba", "bucket": "gba/A.zip"}]}
        with mock.patch("sync_roms.collections.load_collections", lambda: [fav]):
            u = self.usage({"games": {"gba": [g("gba/A.zip")]}, "collections": ["fav"],
                            "excluded": {"gba": ["gba/C.zip"]}}, "other")
        self.assertEqual((u.bytes, u.count), (500, 2))

    def test_direct_and_set_count_once(self):
        u = self.usage({"games": {"gba": [g("gba/A.zip")], "sets": ["s"]}}, "other")
        self.assertEqual((u.bytes, u.count), (300, 2))

    def test_full_system(self):
        u = self.usage({"games": {"gba": {"full_system": True}}}, "other")
        self.assertEqual((u.bytes, u.count), (700, 3))

    def test_vita_game_costs_include_its_extras_and_count_once(self):
        self.cache["psvita/"] = {G: 1000, DLC: 20, UPD: 300}
        self.assertEqual(budget.game_costs({"layout": "other"}, VITA, [G]), ({G: 1320}, False))
        u = budget.system_usage({"layout": "other", "games": {"psvita": [g(G)]}}, VITA)
        self.assertEqual((u.bytes, u.count), (1320, 1))

    def test_vita_fetch_counts_extras(self):
        self.cache["psvita/"] = {G: 1000, DLC: 20, UPD: 300}
        asked = []
        self.assertEqual(budget.fetch_bytes(VITA, [G], lambda s, keys: asked.extend(keys) or set(keys)), 1320)
        self.assertEqual(sorted(asked), sorted([G, DLC, UPD]))

    def test_fetch_with_no_keys_is_zero(self):
        self.assertEqual(budget.fetch_bytes(VITA, None, lambda s, keys: set(keys)), 0)

    def test_excluded(self):
        u = self.usage({"games": {"sets": ["s"]}, "excluded": {"gba": ["gba/A.zip"]}}, "other")
        self.assertEqual((u.bytes, u.count), (200, 1))

    def test_full_system_ignores_exclusions_like_sync(self):
        u = self.usage({"games": {"gba": {"full_system": True}}, "excluded": {"gba": ["gba/A.zip"]}}, "other")
        self.assertEqual((u.bytes, u.count), (700, 3))

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
        self.assertEqual(tuple(u), (100, 1, False))  # ps2 has nothing picked, so its missing cache doesn't matter
        u = budget.card_usage({"layout": "other", "games": {"gba": [g("gba/A.zip")], "ps2": [g("ps2/X.iso")]}},
                              [GBA, {"bucket": "ps2"}])
        self.assertEqual(tuple(u), (100, 2, True))  # ps2 has no cache

    def test_card_usage_adds_bios_of_picked_systems_once(self):
        self.cache["BIOS/"] = {"BIOS/gba_bios.bin": 16, "BIOS/gb_bios.bin": 1, "BIOS/scph1001.bin": 512}
        gba = {**GBA, "bios": {"files": ["gba_bios.bin", "gb_bios.bin", "missing.bin"]}}
        gb = {"bucket": "gb", "bios": {"files": ["gb_bios.bin"]}}
        ps1 = {"bucket": "psx", "bios": {"files": ["scph1001.bin"]}}
        self.cache["gb/"] = {"gb/T.gb": 7}
        card = {"layout": "other", "games": {"gba": [g("gba/A.zip")], "gb": [g("gb/T.gb")]}}
        self.assertEqual(tuple(budget.card_usage(card, [gba, gb, ps1])), (100 + 7 + 17, 2, False))  # psx unpicked

    def test_bios_usage_counts_rom_folder_bios(self):
        self.cache["BIOS/"] = {"BIOS/gamate.zip": 5, "BIOS/a.bin": 2}
        gamate = {"bucket": "gamate", "bios": {"files": ["a.bin"], "rom_files": ["gamate.zip"]}}
        self.assertEqual(tuple(budget.bios_usage([gamate])), (7, 2, False))

    def test_bios_uncached_is_partial(self):
        gba = {**GBA, "bios": {"files": ["gba_bios.bin"]}}
        u = budget.card_usage({"layout": "other", "games": {"gba": [g("gba/A.zip")]}}, [gba])
        self.assertEqual(tuple(u), (100, 1, True))
        self.assertEqual(tuple(budget.bios_usage([GBA])), (0, 0, False))  # no BIOS needed: nothing to size

    def test_picked_game_not_in_storage_costs_nothing_and_is_not_partial(self):
        u = self.usage({"games": {"gba": [g("gba/A.zip"), g("gba/Gone.zip")]}}, "other")
        self.assertEqual(tuple(u), (100, 2, False))
        u = self.usage({"games": {"gba": [g("gba/A.zip"), g("gba/Gone.zip")]}}, "slot")
        self.assertEqual(tuple(u), (105, 2, False))

    def test_nothing_picked_is_not_partial(self):
        self.cache.clear()
        self.assertEqual(tuple(self.usage({})), (0, 0, False))

    def test_game_costs(self):
        costs, missing = budget.game_costs({"layout": "slot"}, GBA, ["gba/A.zip", "gba/B.zip", "gba/Z.zip"])
        self.assertEqual((costs, missing), ({"gba/A.zip": 105, "gba/B.zip": 200}, False))
        self.cache.pop("scrapes/gba/")
        self.assertEqual(budget.game_costs({"layout": "esde"}, GBA, ["gba/A.zip"]), ({"gba/A.zip": 100}, True))

    def test_capacity(self):
        self.assertEqual(budget.card_capacity({"size": "512 GB"}), 512 * 10 ** 9)
        self.assertEqual(budget.card_capacity({"size": "1 TB"}), 10 ** 12)
        for bad in ({}, {"size": ""}, {"size": "lots"}, {"size": 5}, {"size": None}):
            self.assertIsNone(budget.card_capacity(bad))


if __name__ == "__main__":
    unittest.main()
