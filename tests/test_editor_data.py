import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardedit, collectionedit, commands, edit, picker, store  # noqa: E402
from helpers import Cmd, DataDir  # noqa: E402


def target(games):
    raw = {"gba": games}
    return edit.new_target("c", raw)


class NoPersonalSets(DataDir):
    def test_load_sets_ignores_the_data_folder_sets(self):
        os.makedirs(self.path("sets"))
        self.write_json("sets/mine.json", {"name": "Mine", "games": []})
        self.write_json("sets/pinball.json", {"name": "Fake", "games": []})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            sets = store.load_sets()
        self.assertEqual(sorted(x["id"] for x in sets), sorted(x["id"] for x in store.repo_set_files()))
        self.assertEqual([x["name"] for x in sets if x["id"] == "pinball"], ["Pinball"])
        self.assertEqual(err.getvalue(), "")

    def test_personal_set_helpers_are_gone(self):
        for name in ("personal_sets_dir", "save_personal_set", "personal_set_problem"):
            self.assertFalse(hasattr(store, name), name)
        self.assertFalse(hasattr(edit, "make_set_from_extras"))


class Notes(DataDir):
    def test_note_edit_counts_as_a_change_and_is_saved(self):
        t = target([{"title": "A", "bucket": "gba/A.zip"}])
        self.assertEqual(edit.target_changes(t), ({}, {}))
        s = t["data"]["systems"][[x["bucket"] for x in t["data"]["systems"]].index("gba")]
        edit.set_note(s, "gba/A.zip", "great")
        self.assertEqual(s["games"][0]["note"], "great")
        added, _ = edit.target_changes(t)
        self.assertEqual(added, {"gba": ["gba/A.zip (note)"]})
        edit.set_note(s, "gba/A.zip", "")
        self.assertNotIn("note", s["games"][0])
        self.assertEqual(edit.target_changes(t), ({}, {}))

    def test_note_on_a_game_not_listed_is_refused(self):
        s = {"bucket": "gba", "games": []}
        self.assertFalse(edit.set_note(s, "gba/A.zip", "x"))


class Sorting(DataDir):
    def test_save_sorts_systems_and_games(self):
        store.save_lists({"c": {"snes": [{"bucket": "snes/2"}, {"bucket": "snes/1"}], "gba": [{"bucket": "gba/Z.zip"}, {"bucket": "gba/a.zip"}],
                                "sets": ["z", "a"]}})
        card = self.read("cards.json")["c"]["games"]
        self.assertEqual(list(card), ["gba", "sets", "snes"])
        self.assertEqual([g["bucket"] for g in card["gba"]], ["gba/a.zip", "gba/Z.zip"])
        self.assertEqual(card["sets"], ["a", "z"])
        self.assertEqual([g["bucket"] for g in card["snes"]], ["snes/1", "snes/2"])


class Schemas(unittest.TestCase):
    def load(self, name):
        with open(os.path.join(store.REPO_DATA, name)) as f:
            return json.load(f)

    def test_schemas_exist_and_cover_what_cards_store(self):
        games, cards = self.load("games.schema.json"), self.load("cards.schema.json")
        self.assertIn("sets", games["properties"])
        card = cards["additionalProperties"]["properties"]
        for key in ("device", "layout", "android_media", "systems", "games", "collections", "frontend_collections",
                    "surprise", "surprises"):
            self.assertIn(key, card)
        self.assertEqual(card["systems"]["items"]["type"], "string")
        self.assertEqual(self.load("collections.schema.json")["required"], ["name", "games"])


class CheckSystemsKey(Cmd):
    def test_card_systems_must_be_known_system_ids(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde", "systems": ["gba"]}})
        self.assertEqual(commands.check_data(), [])
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde", "systems": ["nope", 3]}})
        self.assertEqual(len(commands.check_data()), 2)
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde", "systems": "gba"}})
        self.assertEqual(len(commands.check_data()), 1)

    def test_files_in_the_data_folder_sets_are_not_checked(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde"}})
        os.makedirs(self.path("sets"))
        self.write_json("sets/mine.json", {"name": "Mine", "games": [{"title": "B", "system": "nope", "bucket": "nope/B.zip"}]})
        with open(self.path("sets/bad.json"), "w") as f:
            f.write("{oops")
        self.assertEqual(commands.check_data(), [])


class CheckSurprise(Cmd):
    def test_check_flags_bad_surprise_data(self):
        self.write_json("cards.json", {"SD": {"surprise": "yes", "surprises": [{"system": "gba"}]}})
        self.write_json("surprises.json", [{"system": "nope", "bucket": "x", "title": "t", "card": "SD", "date": "soon"}])
        problems = commands.check_data()
        self.assertIn("cards.json: SD: 'surprise' must be true or false", problems)
        self.assertIn("cards.json: SD: surprises: each must have system, bucket and title", problems)
        self.assertIn("surprises.json: unknown system 'nope'", problems)
        self.assertIn("surprises.json: 'soon' isn't an ISO date", problems)

    def test_good_surprise_data_passes_and_buckets_are_checked(self):
        s = {"system": "gba", "bucket": "gba/A.zip", "title": "A"}
        self.write_json("cards.json", {"SD": {"device": "full", "layout": "esde", "surprise": True, "surprises": [s]}})
        self.write_json("surprises.json", [dict(s, card="SD", date="2026-11-11")])
        self.assertEqual(commands.check_data(), [])
        self.assertTrue(any("gba/A.zip" in p for p in commands.check_data(lambda system: set())))

    def test_surprises_file_must_be_a_list(self):
        self.write_json("surprises.json", {})
        self.assertEqual(commands.check_data(), ["surprises.json: must be a list"])


class CheckBucketKeys(Cmd):
    def test_missing_keys_are_reported_per_file(self):
        with open(self.path("cards.json"), "w") as f:
            json.dump({"c": {"device": "full", "layout": "esde",
                             "games": {"gba": [{"title": "A", "bucket": "gba/A.zip"}, {"title": "B", "bucket": "gba/B.zip"}]}}}, f)
        problems = commands.check_data(lambda system: {"gba/A.zip"} if system == "gba" else set())
        self.assertTrue(any("gba/B.zip" in p for p in problems))
        self.assertFalse(any("gba/A.zip" in p for p in problems))
        self.assertEqual(commands.check_data(), [])

    def test_bucket_keys_cover_every_key_of_a_collection_game(self):
        os.makedirs(self.path("collections"))
        self.write_json("collections/mine.json", {"name": "Mine", "games": [
            {"title": "D", "system": "nes", "bucket": "nes/D.zip", "files": ["nes/D2.zip"]}]})
        problems = commands.check_data(lambda system: {"nes/D.zip"} if system == "nes" else set())
        self.assertTrue(any("nes/D2.zip" in p for p in problems))
        self.assertFalse(any("nes/D.zip" in p for p in problems))

    def test_flag_uses_the_readonly_profile_and_refuses_the_write_profile(self):
        from sync_roms import runtime, s3
        with mock.patch.object(s3, "list_sizes", return_value={}) as ls, \
                mock.patch.object(runtime, "PROFILE", "roms-readonly"), mock.patch.object(runtime, "WRITE_PROFILE", "roms"):
            code, _, _ = self.run_cmd("check", "--bucket-keys")
        self.assertEqual(code, 1)  # every key of the shipped sets is "missing" from an empty listing
        self.assertTrue(ls.called)
        with mock.patch.object(s3, "list_sizes", return_value={}) as ls, \
                mock.patch.object(runtime, "PROFILE", "roms"), mock.patch.object(runtime, "WRITE_PROFILE", "roms"):
            code, _, err = self.run_cmd("check", "--bucket-keys")
        self.assertNotEqual(code, 0)
        ls.assert_not_called()


class Hints(unittest.TestCase):
    def test_hints_fit_a_narrow_terminal_and_lead_with_the_main_keys(self):
        hints = [picker.SYSTEMS_HINT, picker.systems_hint(True), picker.MULTI_HINT, picker.SINGLE_HINT,
                 edit.MENU_HINT, edit.GAMES_HINT, cardedit.LIST_HINT, cardedit.GAMES_HINT, cardedit.SETS_HINT,
                 cardedit.META_HINT, cardedit.VALUES_HINT, collectionedit.GAMES_HINT]
        for h in hints:
            self.assertLessEqual(picker.cell_width(h), 80, h)
        self.assertTrue(picker.systems_hint(False).startswith("Space toggle · Enter go"))
        self.assertTrue(picker.MULTI_HINT.startswith("Space toggle · Enter done"))
        self.assertTrue(edit.MENU_HINT.startswith("Enter open"))


class SystemsPickerKeys(unittest.TestCase):
    def run_keys(self, keys):
        import curses

        class Screen:
            def __init__(self):
                self.keys = iter(keys)

            def getmaxyx(self):
                return 24, 80

            def get_wch(self):
                return next(self.keys)

            def __getattr__(self, name):
                return lambda *a, **k: None
        rows = [("a", True, 1, 1), ("b", True, 1, 1), ("c", True, 1, 1)]
        with mock.patch.object(picker.ui, "require_terminal"), \
                mock.patch.object(curses, "curs_set"), mock.patch.object(curses, "use_default_colors"), \
                mock.patch.object(curses, "has_colors", return_value=False), \
                mock.patch.object(curses, "wrapper", side_effect=lambda f: f(Screen())):
            return picker.pick_systems(rows)

    def test_home_and_end_move_the_cursor(self):
        import curses
        self.assertEqual(self.run_keys([curses.KEY_END, " ", "\n"]), [2])
        self.assertEqual(self.run_keys([curses.KEY_END, curses.KEY_HOME, " ", "\n"]), [0])

    def test_o_shows_only_selected_systems(self):
        import curses
        # select a and c, press o: b is hidden, so Down from a lands on c; space unselects it
        keys = [" ", curses.KEY_END, " ", "o", curses.KEY_HOME, curses.KEY_DOWN, " ", "\n"]
        self.assertEqual(self.run_keys(keys), [0])


class CheckRatios(Cmd):
    def test_repo_data_is_clean(self):
        self.assertEqual(commands.check_data(), [])

    def test_unknown_system_in_ratio_systems_is_reported(self):
        good = store.repo_json("ratio-systems")
        bad = {"ratios": {"3:5": ["nope"], "wide": ["gb"]}, "dual_screen": ["ghost"]}
        for data, expect in ((good, 0), (bad, 3)):
            with mock.patch.object(store, "repo_json", lambda n, real=store.repo_json, data=data:
                                   data if n == "ratio-systems" else real(n)):
                self.assertEqual(len(commands.check_data()), expect)

    def test_malformed_system_ratio_is_reported(self):
        systems = store.repo_json("systems")
        systems[0]["ratio"] = "4/3"
        problems = commands.check_data(repo_systems=systems)
        self.assertEqual(len(problems), 1)
        self.assertIn("ratio", problems[0])
        for ok in ("4:3", "31:27"):
            self.assertTrue(commands.valid_ratio(ok))
        for bad in ("4:", "0:3", "4:3:2", " 4:3", 43, None):
            self.assertFalse(commands.valid_ratio(bad), bad)


class RepoDataSurvivesRemoval(unittest.TestCase):
    """An upgrade deletes the installed data folder under a running sync; data read up front must still be served."""

    def test_preloaded_file_is_served_after_it_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "clones.json"), "w") as f:
                json.dump({"mame": {}}, f)
            with mock.patch.object(store, "REPO_DATA", tmp):
                store.preload_repo_data()
                os.remove(os.path.join(tmp, "clones.json"))
                self.assertEqual(store.repo_json("clones"), {"mame": {}})
                with self.assertRaises(FileNotFoundError):
                    store.repo_json("never-there")


if __name__ == "__main__":
    unittest.main()
