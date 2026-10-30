import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import cli as sync_roms  # noqa: E402


def systems():
    return {
        "gba": {"name": "Game Boy Advance", "bucket": "gba", "full_system": False,
                "games": [{"title": "A", "bucket": "gba/A.zip"}]},
        "gen": {"name": "Genesis", "bucket": "gen", "full_system": False, "games": []},
        "ful": {"name": "Full", "bucket": "ful", "full_system": True, "games": []},
    }


SET = {"name": "Mix", "games": [
    {"title": "Zed", "system": "gen", "bucket": "gen/Zed.zip"},
    {"title": "A", "system": "gba", "bucket": "gba/A.zip"},
    {"title": "Gone", "system": "gba", "bucket": "gba/Gone.zip"},
    {"title": "Nope", "system": "nes", "bucket": "nes/Nope.zip"},
    {"title": "Skip", "system": "ful", "bucket": "ful/Skip.zip"},
]}


class SetsTest(unittest.TestCase):
    def test_load_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "sets"))
            with open(os.path.join(tmp, "sets", "mix.json"), "w") as f:
                json.dump(SET, f)
            with mock.patch.object(sync_roms, "REPO_DATA", tmp):
                sets = sync_roms.load_sets()
        self.assertEqual([x["name"] for x in sets], ["Mix"])
        self.assertEqual(len(sets[0]["games"]), 5)

    def test_rows_sorted_by_system_skip_unknown(self):
        rows = sync_roms.set_rows(SET, systems(), lambda s: {"gba/A.zip", "gen/Zed.zip"})
        self.assertEqual([r[1] for r in rows], ["ful/Skip.zip", "gba/A.zip", "gba/Gone.zip", "gen/Zed.zip"])
        self.assertIn("not in bucket", rows[2][3])
        self.assertNotIn("not in bucket", rows[1][3])

    def test_toggle_adds_and_removes(self):
        by = systems()
        rows = sync_roms.set_rows(SET, by, lambda s: set())
        with mock.patch.object(sync_roms, "filter_list", return_value=[True, False, True, True]) as fl:
            sync_roms.toggle_games("t", rows)
        self.assertEqual(fl.call_args.kwargs["initial"], [True, True, False, False])
        self.assertEqual(fl.call_args.kwargs["locked"], [True, False, False, False])
        self.assertEqual(by["ful"]["games"], [])
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/Gone.zip"])
        self.assertEqual([g["bucket"] for g in by["gen"]["games"]], ["gen/Zed.zip"])

    def test_toggle_extra_files(self):
        by = systems()
        game_set = {"name": "M", "games": [{"title": "Multi", "system": "gen", "bucket": "gen/M.m3u",
                                            "files": ["gen/M (Disc 1).chd", "gen/M (Disc 2).chd"]}]}
        rows = sync_roms.set_rows(game_set, by, lambda s: {"gen/M.m3u", "gen/M (Disc 1).chd"})
        self.assertIn("not in bucket", rows[0][3])
        extras = {"gen/M.m3u": game_set["games"][0]["files"]}
        with mock.patch.object(sync_roms, "filter_list", return_value=[True]):
            sync_roms.toggle_games("t", rows, extras)
        self.assertEqual([g["bucket"] for g in by["gen"]["games"]],
                         ["gen/M.m3u", "gen/M (Disc 1).chd", "gen/M (Disc 2).chd"])
        with mock.patch.object(sync_roms, "filter_list", return_value=[False]):
            sync_roms.toggle_games("t", rows, extras)
        self.assertEqual(by["gen"]["games"], [])

    def test_locked_rows_cannot_toggle(self):
        keys = iter(["\t", "\x01", "\x1b"])
        state = self.run_list(keys, locked=[True, False])
        self.assertEqual(state, [False, True])

    def test_multi_esc_keeps_state(self):
        self.assertEqual(self.run_list(iter(["\t", "\x1b"])), [True, False])

    def test_hotkey_returns_pair(self):
        self.assertEqual(self.run_list(iter(["\x06"]), multi=False, hotkeys=("\x06",)), ("\x06", 0))
        self.assertEqual(self.run_list(iter(["y", "\x06"]), multi=False, hotkeys=("\x06",)), ("\x06", 1))

    def test_hotkey_ignored_without_rows(self):
        self.assertIsNone(self.run_list(iter(["z", "\x06", "\x1b"]), multi=False, hotkeys=("\x06",)))

    def test_covered_rows_locked_with_note(self):
        by = systems()
        rows = sync_roms.set_rows(SET, by, lambda s: set())
        covered = lambda s, key: "Full set: x" if key == "gba/Gone.zip" else None  # noqa: E731
        with mock.patch.object(sync_roms, "filter_list", return_value=[True, True, True, True]) as fl:
            sync_roms.toggle_games("t", rows, covered=covered)
        self.assertEqual(fl.call_args.kwargs["locked"], [True, False, True, False])
        self.assertEqual(fl.call_args.kwargs["locked_note"][2], "Full set: x")
        self.assertNotIn("gba/Gone.zip", [g["bucket"] for g in by["gba"]["games"]])

    def run_list(self, keys, locked=None, multi=True, hotkeys=()):
        screen = mock.MagicMock()
        screen.getmaxyx.return_value = (24, 80)
        screen.get_wch.side_effect = lambda: next(keys)
        with mock.patch.object(sync_roms.curses, "wrapper", lambda run: run(screen)), \
                mock.patch.object(sync_roms.curses, "curs_set"), \
                mock.patch.object(sync_roms.curses, "use_default_colors"), \
                mock.patch.object(sync_roms.curses, "has_colors", return_value=False):
            return sync_roms.filter_list("t", ["x", "y"], multi=multi, locked=locked, hotkeys=hotkeys)


if __name__ == "__main__":
    unittest.main()
