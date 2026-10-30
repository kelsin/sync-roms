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


class FullToggles(EditFlow):
    def run_with(self, picks, bucket_files=None, confirmed=True):
        picks, calls = iter(picks), []

        def fake(*a, **k):
            calls.append(k)
            return next(picks)
        files = bucket_files or {}
        with mock.patch.object(sync_roms, "BUCKET", "b", create=True), \
                mock.patch.object(sync_roms, "list_sizes", side_effect=lambda prefix: files.get(prefix, {})), \
                mock.patch.object(sync_roms, "filter_list", side_effect=fake), \
                mock.patch.object(sync_roms, "confirm", return_value=confirmed), \
                contextlib.redirect_stdout(io.StringIO()):
            sync_roms.edit_manifest()
        return calls

    def test_toggle_set_ref(self):
        self.assertEqual(sync_roms.toggle_set_ref(["a"], "b"), ["a", "b"])
        self.assertEqual(sync_roms.toggle_set_ref(["a", "b"], "a"), ["b"])

    def test_toggle_full_system_keeps_games(self):
        s = {"full_system": False, "games": [{"bucket": "gba/A.zip"}]}
        sync_roms.toggle_full_system(s)
        self.assertTrue(s["full_system"])
        self.assertEqual(len(s["games"]), 1)

    def test_set_menu_hotkey_toggles_and_redraws(self):
        first = sync_roms.load_sets()[1]["id"]
        calls = self.run_with([0, 1, (sync_roms.FULL_KEY, 1), None, None, None])
        self.assertEqual(self.read("games.json"), {"sets": [first]})
        self.assertEqual(calls[3]["cursor"], 1)
        self.assertEqual(calls[3]["extras"][1], [("  📦 full set", "green")])
        self.assertIn(sync_roms.FULL_KEY, calls[2]["hotkeys"])

    def test_system_hotkey_toggles_full_system(self):
        self.run_with([0, 0, (sync_roms.FULL_KEY, 0), None, None, None], {"gba/": {"gba/A.zip": 1}})
        self.assertEqual(self.read("games.json"), {"gba": {"full_system": True}})

    def test_core_full_system_blocks_card_toggle(self):
        self.write_json("games.json", {"gba": {"full_system": True}})
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_with([1, 0, (sync_roms.FULL_KEY, 0), None, None, None], {"gba/": {"gba/A.zip": 1}})
        self.assertNotIn("games", self.read("cards.json")["c"])

    def test_set_ref_rows_locked(self):
        self.write_json("games.json", {"sets": ["mario"]})
        tracked = []
        with mock.patch.object(sync_roms, "toggle_games",
                               side_effect=lambda *a, **k: tracked.append((a, k))):
            ids = [x["id"] for x in sync_roms.load_sets()]
            self.run_with([0, 1, ids.index("mario"), None, None, None])
        rows = tracked[0][0][1]
        note = tracked[0][1]["covered"](rows[0][0], rows[0][1])
        self.assertEqual(note, "Full set: Mario")

    def test_card_named_core_leaves_core_list_alone(self):
        self.write_json("games.json", {"gba": [{"title": "A", "bucket": "gba/A.zip"}]})
        self.write_json("cards.json", {"core": {"layout": "esde", "device": "full"}})
        self.run_with([1, 1, (sync_roms.FULL_KEY, 0), None, None, None], confirmed=True)
        self.assertEqual(self.read("games.json"), {"gba": [{"title": "A", "bucket": "gba/A.zip"}]})

    def test_by_set_locks_systems_full_in_core(self):
        self.write_json("games.json", {"nes": {"full_system": True}})
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        tracked = []
        nes_set = next(x["id"] for x in sync_roms.load_sets() if any(g["system"] == "nes" for g in x["games"]))
        ids = [x["id"] for x in sync_roms.load_sets()]
        with mock.patch.object(sync_roms, "toggle_games", side_effect=lambda *a, **k: tracked.append((a, k))):
            self.run_with([1, 1, ids.index(nes_set), None, None, None])
        rows, covered = tracked[0][0][1], tracked[0][1]["covered"]
        nes_row = next(r for r in rows if r[0]["bucket"] == "nes")
        self.assertTrue(covered(nes_row[0], nes_row[1]))

    def write_json(self, name, data):
        with open(self.path(name), "w") as f:
            json.dump(data, f)


if __name__ == "__main__":
    unittest.main()
