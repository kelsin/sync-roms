import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from sync_roms import scrape_plan, store  # noqa: E402


class VariantTags(unittest.TestCase):
    def test_allium_writes_a_gamelist_xml_with_names_and_metadata(self):
        meta = {"a.zip": {"name": "A", "developer": "Dev", "rating": 0.8, "desc": "d"}}
        listing = {"scrapes/gba/onion/a.png": 5}
        jobs, entries, _ = scrape_plan.plan_scrapes("allium", ["a.zip", "b.zip", "sub/c.zip"], listing, meta, "/m", "/r",
                                                    lambda rom: True)
        self.assertEqual(entries, {"a.zip": {"name": "A", "developer": "Dev", "rating": "0.8", "image": "./Imgs/a.png"},
                                   "b.zip": {"name": "b"}})
        self.assertEqual(scrape_plan.GAMELIST_FILES["allium"], "gamelist.xml")

    def test_shipped_data(self):
        data = store.repo_json("clones")
        for system in ("mame", "fbneo"):
            d = data[system]
            self.assertTrue(d["clones"])
            self.assertTrue(all(p in d["parents"] for p, _ in d["clones"].values()))
        self.assertEqual(data["fbneo"]["clones"]["1942a"][0], "1942")


if __name__ == "__main__":
    unittest.main()
