import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import StorageDir  # noqa: E402  (imports isolate first)
from sync_roms import portmaster_needed as needed, runtime  # noqa: E402


class SubfolderTest(unittest.TestCase):
    def test_subfolder_cases(self):
        cases = [
            ("undertale", "Copy the contents of your Steam or GOG installation to ports/undertale/assets.", "assets"),
            ("celeste", 'Copy the game\'s data into "celeste/gamedata".', "gamedata"),
            ("tmntsr", "Copy the game files to ports/tmntsr/gamedata/.", "gamedata"),
            ("zeroranger", "Copy the data.win into the assets folder.", "assets"),
            ("slaythespire", "copy the desktop-1.0.jar to the slaythespire folder!", ""),
            ("cave", "Buy the game and copy its files.", ""),
        ]
        for folder, inst, sub in cases:
            with self.subTest(folder=folder):
                self.assertEqual(needed.subfolder(folder, inst), sub)


class NeededTest(StorageDir):
    def test_add_and_remove_card_drops_empty_entry(self):
        entries = {}
        needed.add(entries, "undertale", "Undertale", "undertale.zip", "Copy it to ports/undertale/assets.", "b")
        needed.add(entries, "undertale", "UNDERTALE", "undertale.zip", "Copy it to ports/undertale/assets.", "a")
        needed.add(entries, "undertale", "UNDERTALE", "undertale.zip", "Copy it to ports/undertale/assets.", "a")
        self.assertEqual(entries, {"undertale": {"title": "UNDERTALE", "zip": "undertale.zip",
                                                 "inst": "Copy it to ports/undertale/assets.",
                                                 "folder": "os/portmaster/gamedata/undertale/assets/", "cards": ["a", "b"]}})
        needed.remove_card(entries, "undertale", "a")
        self.assertEqual(entries["undertale"]["cards"], ["b"])
        needed.remove_card(entries, "undertale", "b")
        needed.remove_card(entries, "nope", "b")
        self.assertEqual(entries, {})

    def test_save_and_load(self):
        self.assertEqual(needed.load(), {})
        entries = {}
        needed.add(entries, "celeste", "Celeste", "celeste.zip", "", "c")
        needed.save(entries)
        self.assertEqual(needed.path(), os.path.join(self.data, "ports-needed.json"))
        with open(needed.path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), entries)
        self.assertEqual(needed.load(), entries)

    def test_prune_drops_entries_with_storage_data(self):
        entries = {}
        for folder in ("celeste", "undertale"):
            needed.add(entries, folder, folder.title(), folder + ".zip", "", "c")
        self.put("os/portmaster/gamedata/undertale/assets/data.win")
        self.put("os/portmaster/gamedata/celestial/x")  # another port's folder
        self.assertEqual(needed.prune(entries), ["Undertale"])
        self.assertEqual(list(entries), ["celeste"])

    def test_prune_keeps_everything_when_storage_is_missing(self):
        entries = {}
        needed.add(entries, "celeste", "Celeste", "celeste.zip", "", "c")
        with mock.patch.object(runtime, "ROOT", os.path.join(self.root, "gone")), mock.patch("sys.stderr"):
            self.assertEqual(needed.prune(entries), [])
        self.assertEqual(list(entries), ["celeste"])

    def test_block(self):
        entries = {}
        needed.add(entries, "undertale", "Undertale", "undertale.zip", "Line one\nCopy it to ports/undertale/assets.", "c")
        self.assertEqual(needed.block(entries["undertale"], "undertale"),
                         f"Undertale\n    Line one\n    Copy it to ports/undertale/assets.\n"
                         f"    Put the files in {self.root}/os/portmaster/gamedata/undertale/assets/")
        with mock.patch.object(runtime, "ROOT", None), mock.patch.object(runtime, "BUCKET", "b"):
            self.assertTrue(needed.block(entries["undertale"], "undertale").endswith(
                "Put the files in s3://b/os/portmaster/gamedata/undertale/assets/"))


if __name__ == "__main__":
    unittest.main()
