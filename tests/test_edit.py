import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli as sync_roms  # noqa: E402

SETS = {"s": {"id": "s", "name": "Mix", "games": [{"system": "gba", "bucket": "gba/A.zip", "files": ["gba/A2.zip"]}]}}


class DataDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(sync_roms, "data_dir", lambda: self.tmp.name)
        patch.start()
        self.addCleanup(patch.stop)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def read(self, name):
        with open(self.path(name)) as f:
            return json.load(f)


class Helpers(unittest.TestCase):
    def test_valid_card_name(self):
        for bad in ("", "  ", "a/b"):
            self.assertIsNotNone(sync_roms.valid_card_name(bad, set()))
        self.assertIsNotNone(sync_roms.valid_card_name("RG SP", {"RG SP"}))
        self.assertIsNone(sync_roms.valid_card_name("RG SP", {"other"}))

    def test_dump_list_shapes(self):
        systems = [{"bucket": "gba", "full_system": True, "games": [{"bucket": "gba/A.zip"}]},
                   {"bucket": "ps2", "full_system": False, "games": [{"bucket": "ps2/B.iso"}]},
                   {"bucket": "nes", "full_system": False, "games": []}]
        self.assertEqual(sync_roms.dump_list(systems, ["s"]),
                         {"gba": {"full_system": True}, "ps2": [{"bucket": "ps2/B.iso"}], "sets": ["s"]})
        self.assertEqual(sync_roms.dump_list(systems[2:], []), {})

    def test_cover_notes(self):
        core = {"nes": {"full_system": True}, "gba": [{"bucket": "gba/C.zip"}], "sets": ["s"]}
        full, keys = sync_roms.cover_notes(SETS, ["s", "missing"], core)
        self.assertEqual(full, {"nes": "From core: full system"})
        self.assertEqual(keys["gba/C.zip"], "From core")
        self.assertEqual(keys["gba/A2.zip"], "From core: Mix")
        full, keys = sync_roms.cover_notes(SETS, ["s"])
        self.assertEqual((full, keys["gba/A.zip"]), ({}, "Full set: Mix"))


class Saving(DataDir):
    def test_save_lists_writes_core_and_card(self):
        sync_roms.update_card("c", device="x", layout="esde")
        sync_roms.save_lists({"gba": [{"bucket": "gba/A.zip"}]}, {"c": {"sets": ["s"]}})
        with open(self.path("games.json")) as f:
            text = f.read()
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text), {"gba": [{"bucket": "gba/A.zip"}]})
        self.assertEqual(self.read("cards.json")["c"], {"device": "x", "layout": "esde", "games": {"sets": ["s"]}})

    def test_save_lists_without_core_leaves_games_json(self):
        sync_roms.save_lists(None, {"c": {}})
        self.assertFalse(os.path.exists(self.path("games.json")))


class EditFlow(DataDir):
    def run_edit(self, picks, confirmed, name="newcard"):
        picks = iter(picks)
        with mock.patch.object(sync_roms, "BUCKET", "b", create=True), \
                mock.patch.object(sync_roms, "list_sizes", return_value={}), \
                mock.patch.object(sync_roms, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch("builtins.input", return_value=name), \
                mock.patch.object(sync_roms, "choose_setup", return_value=(None, "esde")), \
                mock.patch.object(sync_roms, "confirm", return_value=confirmed), \
                contextlib.redirect_stdout(io.StringIO()):
            return sync_roms.edit_manifest()

    def test_cancel_writes_nothing(self):
        # main menu: "New card" is the last option; inside the card menu Esc; then Esc to finish
        self.assertEqual(self.run_edit([1, None, None], confirmed=False), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))

    def test_new_card_saved_with_setup(self):
        self.assertEqual(self.run_edit([1, None, None], confirmed=True), 0)
        self.assertEqual(self.read("cards.json")["newcard"], {"device": "full", "layout": "esde", "games": {}})
        self.assertEqual(self.read("games.json"), {})

    def test_no_changes_nothing_saved(self):
        self.assertEqual(self.run_edit([0, None, None], confirmed=True), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))


if __name__ == "__main__":
    unittest.main()
