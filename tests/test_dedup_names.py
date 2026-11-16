import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir  # noqa: E402

from sync_roms import scrape_online, scrape_plan, usersettings  # noqa: E402

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "dedup-names", "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


find_duplicates = load("find_duplicates")
apply_names = load("apply_names")

CLONES = {"mame": {"parents": {"sf2": "Street Fighter II (World)"}, "clones": {"sf2j": ["sf2", "Japan"]}}}


def find(metadata, stored):
    return find_duplicates.find(metadata, set(stored), CLONES)


class FindDuplicates(unittest.TestCase):
    def test_groups_same_name_case_and_space_insensitive(self):
        out = find({"gba": {"A.zip": {"name": "Starfy", "developer": "TOSE", "releasedate": "2002"},
                            "B.zip": {"name": "starfy ", "qualifier": "x", "translated": True},
                            "C.zip": {"name": "Other"}}},
                   ["gba/A.zip", "gba/B.zip", "gba/C.zip"])
        self.assertEqual(out["groups"], [{"system": "gba", "name": "Starfy", "roms": [
            {"rom": "A.zip", "name": "Starfy", "developer": "TOSE", "releasedate": "2002"},
            {"rom": "B.zip", "name": "starfy ", "qualifier": "x", "translated": True, "developer": None,
             "releasedate": None}]}])

    def test_systems_kept_apart(self):
        out = find({"gba": {"A.zip": {"name": "X"}}, "nes": {"A.zip": {"name": "X"}}}, ["gba/A.zip", "nes/A.zip"])
        self.assertEqual(out["groups"], [])

    def test_not_stored_left_out(self):
        out = find({"gba": {"A.zip": {"name": "X"}, "B.zip": {"name": "X"}}}, ["gba/A.zip"])
        self.assertEqual(out["groups"], [])
        self.assertEqual(out["skipped"]["not_stored"], 1)

    def test_discs_left_out(self):
        stored = ["psx/G.m3u", "psx/G (Disc 1).chd", "psx/G (Disc 2).chd"]
        meta = {"psx": {"G.m3u": {"name": "G"}, "G (Disc 1).chd": {"name": "G"}, "G (Disc 2).chd": {"name": "G"}}}
        out = find(meta, stored)
        self.assertEqual(out["groups"], [])
        self.assertEqual(out["skipped"]["discs"], 2)

    def test_set_folder_files_left_out(self):
        stored = ["mame/area51.zip", "mame/area51/area51.chd"]
        out = find({"mame": {"area51.zip": {"name": "Area 51"}, "area51/area51.chd": {"name": "Area 51"}}}, stored)
        self.assertEqual(out["groups"], [])
        self.assertEqual(out["skipped"]["set_folders"], 1)

    def test_folder_without_sibling_set_counts(self):
        stored = ["dos/Game/game.zip", "dos/game.zip"]
        out = find({"dos": {"Game/game.zip": {"name": "G"}, "game.zip": {"name": "G"}}}, stored)
        self.assertEqual(len(out["groups"]), 1)

    def test_vita_extras_left_out(self):
        with mock.patch.object(find_duplicates.vita, "is_extra", side_effect=lambda k: k.endswith("DLC.zip")):
            out = find({"psvita": {"A.zip": {"name": "X"}, "A DLC.zip": {"name": "X"}}}, ["psvita/A.zip", "psvita/A DLC.zip"])
        self.assertEqual(out["groups"], [])
        self.assertEqual(out["skipped"]["vita_extras"], 1)

    def test_clone_families_skipped(self):
        stored = ["mame/sf2.zip", "mame/sf2j.zip", "mame/other.zip", "mame/other2.zip"]
        meta = {"mame": {"sf2.zip": {"name": "SF2"}, "sf2j.zip": {"name": "SF2"},
                         "other.zip": {"name": "Other"}, "other2.zip": {"name": "Other"}}}
        out = find(meta, stored)
        self.assertEqual([[r["rom"] for r in g["roms"]] for g in out["groups"]], [["other.zip", "other2.zip"]])
        self.assertEqual(out["skipped"]["clones"], 2)

    def test_entry_without_name_ignored(self):
        out = find({"gba": {"A.zip": {"desc": "x"}, "B.zip": {"desc": "y"}}}, ["gba/A.zip", "gba/B.zip"])
        self.assertEqual(out["groups"], [])


GBA = {"name": "Game Boy Advance", "bucket": "gba", "screenscraper": 12, "folders": {}}
KEY = "scrapes/gba/metadata.json"


class ApplyNames(StorageDir):
    def setUp(self):
        super().setUp()
        self.put(KEY, scrape_plan.dump_json({"A.zip": {"name": "A"}, "B (T).zip": {"name": "A - Translated",
                                                                                     "translated": True}}).encode())
        p = mock.patch.object(usersettings, "apply_settings")
        p.start()
        self.addCleanup(p.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def run_main(self, decisions, *flags):
        path = os.path.join(self.dir.name, "decisions.json")
        with open(path, "w") as f:
            json.dump(decisions, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = apply_names.main([path, *flags])
        return code, out.getvalue()

    def metadata(self):
        with open(os.path.join(self.root, KEY)) as f:
            return json.load(f)

    def test_qualifies(self):
        code, out = self.run_main({"qualify": [{"system": "gba", "rom": "B (T).zip", "qualifier": "Aeon"}]})
        self.assertEqual(code, 0)
        self.assertEqual(self.metadata()["B (T).zip"], {"name": "A (Aeon) - Translated", "translated": True, "qualifier": "Aeon"})
        self.assertIn("gba/B (T).zip: A - Translated → A (Aeon) - Translated", out)

    def test_dry_run_writes_nothing(self):
        before = self.metadata()
        with mock.patch.object(scrape_online, "match_command") as match:
            code, out = self.run_main({"qualify": [{"system": "gba", "rom": "A.zip", "qualifier": "Japan"}],
                                       "rescrape": [{"system": "gba", "rom": "A.zip", "game": 5}]}, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.metadata(), before)
        match.assert_not_called()
        self.assertIn("A → A (Japan)", out)

    def test_missing_entry_writes_nothing(self):
        before = self.metadata()
        with self.assertRaises(SystemExit):
            self.run_main({"qualify": [{"system": "gba", "rom": "A.zip", "qualifier": "Japan"},
                                       {"system": "gba", "rom": "Z.zip", "qualifier": "x"}]})
        self.assertEqual(self.metadata(), before)

    def test_rescrape_calls_match_then_qualifies(self):
        def match(args):
            self.assertEqual(args, argparse.Namespace(system="gba", rom="B (T).zip", game="5", skip_media=None,
                                                      translated=True, dry_run=False, confirmed=True))
            self.put(KEY, scrape_plan.dump_json({**self.metadata(), "B (T).zip": {"name": "New - Translated",
                                                                                   "translated": True}}).encode())
            return 0
        with mock.patch.object(scrape_online, "match_command", side_effect=match) as m:
            code, _ = self.run_main({"rescrape": [{"system": "gba", "rom": "B (T).zip", "game": 5, "qualifier": "Aeon"}]})
        self.assertEqual(code, 0)
        m.assert_called_once()
        self.assertEqual(self.metadata()["B (T).zip"]["name"], "New (Aeon) - Translated")

    def test_rescrape_translated_from_entry(self):
        self.put(KEY, scrape_plan.dump_json({"C.zip": {"name": "C - Translated", "translated": True},
                                             "D.zip": {"name": "D"}}).encode())
        seen = []
        with mock.patch.object(scrape_online, "match_command", side_effect=lambda a: seen.append(a.translated) or 0):
            self.run_main({"rescrape": [{"system": "gba", "rom": "C.zip", "game": 1}, {"system": "gba", "rom": "D.zip", "game": 2}]})
        self.assertEqual(seen, [True, False])

    def test_failed_rescrape_reported(self):
        with mock.patch.object(scrape_online, "match_command", return_value=1):
            code, out = self.run_main({"rescrape": [{"system": "gba", "rom": "A.zip", "game": 5, "qualifier": "x"}]})
        self.assertEqual(code, 1)
        self.assertEqual(self.metadata()["A.zip"], {"name": "A"})


if __name__ == "__main__":
    unittest.main()
