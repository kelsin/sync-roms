import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import scrape_plan, store  # noqa: E402

FAMILY = {"parents": {"1942": "1942 (Revision B)", "puckman": "Puck Man (Japan, set 1)"},
          "clones": {"1942a": ["1942", "1942 (Revision A)"], "pacman": ["puckman", "Pac-Man (Midway)"]}}


class VariantTags(unittest.TestCase):
    def test_clone_and_parent_esde(self):
        self.assertEqual(scrape_plan.variant_tags("esde", FAMILY, "1942a"),
                         {"name": "1942 (Revision A)", "sortname": "1942 - 1942 (Revision A)"})
        self.assertEqual(scrape_plan.variant_tags("esde", FAMILY, "1942"),
                         {"name": "1942 (Revision B)", "sortname": "1942"})
        self.assertEqual(scrape_plan.variant_tags("esde", FAMILY, "pacman")["sortname"], "Puck Man - Pac-Man (Midway)")

    def test_knulli_and_onion_get_name_only(self):
        self.assertEqual(scrape_plan.variant_tags("knulli", FAMILY, "1942a"), {"name": "1942 (Revision A)"})
        self.assertEqual(scrape_plan.variant_tags("onion", FAMILY, "1942a"), {"name": "1942 (Revision A)"})

    def test_other_layouts_and_unknown_roms(self):
        self.assertEqual(scrape_plan.variant_tags("muos", FAMILY, "1942a"), {})
        self.assertEqual(scrape_plan.variant_tags("esde", FAMILY, "other"), {})

    def test_plan_overrides_scraped_name_and_creates_entry(self):
        meta = {"1942a.zip": {"name": "1942", "desc": "d"}}
        _, entries, _ = scrape_plan.plan_scrapes("esde", ["1942a.zip", "x.zip"], {}, meta, "/m", "/r",
                                                 lambda rom: True, FAMILY)
        self.assertEqual(entries, {"1942a.zip": {"name": "1942 (Revision A)", "desc": "d",
                                                 "sortname": "1942 - 1942 (Revision A)"}})

    def test_onion_writes_name_without_scrape_metadata(self):
        _, entries, _ = scrape_plan.plan_scrapes("onion", ["1942a.zip", "x.zip"], {}, {}, "/m", "/r",
                                                 lambda rom: True, FAMILY)
        self.assertEqual(entries, {"1942a.zip": {"name": "1942 (Revision A)"}})

    def test_shipped_data(self):
        data = store.repo_json("clones")
        for system in ("mame", "fbneo"):
            d = data[system]
            self.assertTrue(d["clones"])
            self.assertTrue(all(p in d["parents"] for p, _ in d["clones"].values()))
        self.assertEqual(data["fbneo"]["clones"]["1942a"][0], "1942")


if __name__ == "__main__":
    unittest.main()
