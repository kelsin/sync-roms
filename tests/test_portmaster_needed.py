import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import StorageDir  # noqa: E402  (imports isolate first)
from sync_roms import portmaster_needed as needed, runtime, store  # noqa: E402


class SubfolderTest(unittest.TestCase):
    def test_subfolder_cases(self):
        cases = [
            ("undertale", "Copy the contents of your Steam or GOG installation to ports/undertale/assets.", "assets"),
            ("celeste", 'Copy the game\'s data into "celeste/gamedata".', "gamedata"),
            ("tmntsr", "Copy the game files to ports/tmntsr/gamedata/.", "gamedata"),
            ("zeroranger", "Copy the data.win into the assets folder.", "assets"),
            ("slaythespire", "copy the desktop-1.0.jar to the slaythespire folder!", ""),
            ("celeste", "Copy it to the Steam folder.", ""),
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


class DoneNeededTest(StorageDir):
    def setUp(self):
        super().setUp()
        store.update_card("c", layout="spruce")
        store.update_card("d", layout="spruce")
        self.put("scrapes/ports/metadata.json", json.dumps({"celeste.zip": {"name": "Celeste", "portmaster": {"folder": "Celeste64"}}}).encode())
        entries = {}
        needed.add(entries, "Celeste64", "Celeste", "celeste.zip", "", "c")
        needed.add(entries, "Celeste64", "Celeste", "celeste.zip", "", "d")
        needed.add(entries, "undertale", "Aardvark", "undertale.zip", "Copy it to ports/undertale/assets.", "c")
        needed.save(entries)

    def run_cmd(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = fn(*args)
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_done_adds_portmaster_data_and_clears_card_from_needed(self):
        self.run_cmd(needed.done_command, "c", ["Celeste64", "undertale"], False)
        self.assertEqual(store.load_cards()["c"]["portmaster_data"], ["Celeste64", "undertale"])
        self.assertEqual(list(needed.load()), ["Celeste64"])
        self.assertEqual(needed.load()["Celeste64"]["cards"], ["d"])

    def test_done_accepts_zip_name(self):
        self.run_cmd(needed.done_command, "c", ["celeste.zip"], False)
        self.run_cmd(needed.done_command, "d", ["celeste"], False)
        self.assertEqual(store.load_cards()["c"]["portmaster_data"], ["Celeste64"])
        self.assertEqual(store.load_cards()["d"]["portmaster_data"], ["Celeste64"])
        self.assertNotIn("Celeste64", needed.load())

    def test_done_undo_removes(self):
        self.run_cmd(needed.done_command, "c", ["celeste", "undertale"], False)
        self.run_cmd(needed.done_command, "c", ["celeste"], True)
        self.assertEqual(store.load_cards()["c"]["portmaster_data"], ["undertale"])
        self.run_cmd(needed.done_command, "c", ["undertale"], True)
        self.assertNotIn("portmaster_data", store.load_cards()["c"])

    def check_fallback(self, err):
        self.assertIn("Couldn't read the ports' titles from storage", err.getvalue())
        self.assertEqual(store.load_cards()["c"]["portmaster_data"], ["celeste"])

    def test_done_with_unreachable_storage_uses_the_names_given(self):
        err = io.StringIO()
        with mock.patch.object(runtime, "ROOT", os.path.join(self.root, "gone")), contextlib.redirect_stderr(err):
            self.assertEqual(needed.done_command("c", ["celeste.zip"], False), 0)
        self.check_fallback(err)

    def test_done_with_malformed_metadata_uses_the_names_given(self):
        err = io.StringIO()
        with mock.patch("sync_roms.scrape_plan.load_metadata", side_effect=ValueError("bad")), contextlib.redirect_stderr(err):
            self.assertEqual(needed.done_command("c", ["celeste.zip"], False), 0)
        self.check_fallback(err)

    def test_done_unknown_card_fails(self):
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
            needed.done_command("nope", ["celeste"], False)
        self.assertEqual(e.exception.code, 2)

    def test_needed_prints_blocks_in_title_order(self):
        out = self.run_cmd(needed.needed_command)
        entries = needed.load()
        self.assertEqual(out, needed.block(entries["undertale"], "undertale") + "\n    Cards: c\n"
                         + needed.block(entries["Celeste64"], "Celeste64") + "\n    Cards: c, d\n")

    def test_needed_prunes_entries_with_storage_data(self):
        self.put("os/portmaster/gamedata/Celeste64/x")
        out = self.run_cmd(needed.needed_command)
        self.assertTrue(out.startswith("Game data now in storage: Celeste\n"))
        self.assertEqual(list(needed.load()), ["undertale"])

    def test_needed_keeps_entries_when_storage_unreachable(self):
        with mock.patch.object(runtime, "ROOT", os.path.join(self.root, "gone")):
            out = self.run_cmd(needed.needed_command)
        self.assertNotIn("Game data now", out)
        self.assertEqual(sorted(needed.load()), ["Celeste64", "undertale"])

    def test_needed_empty_message(self):
        os.remove(needed.path())
        self.assertEqual(self.run_cmd(needed.needed_command), "No ports are waiting for game data\n")


if __name__ == "__main__":
    unittest.main()
