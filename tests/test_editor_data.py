import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import commands, edit, picker, store  # noqa: E402
from test_edit import DataDir  # noqa: E402
from test_commands import Cmd  # noqa: E402


def target(games):
    raw = {"gba": games}
    return edit.new_target("c", raw)


class PersonalSets(DataDir):
    def systems(self):
        return [{"bucket": "gba", "full_system": False,
                 "games": [{"title": "B", "bucket": "gba/B.zip", "note": "fun"}, {"title": "A", "bucket": "gba/A.zip"}]},
                {"bucket": "nes", "full_system": False, "games": []}]

    def test_save_and_load_alongside_repo_sets(self):
        set_id = store.save_personal_set("My Picks", self.systems())
        self.assertEqual(set_id, "my-picks")
        data = self.read("sets/my-picks.json")
        self.assertEqual(data["name"], "My Picks")
        self.assertEqual([g["bucket"] for g in data["games"]], ["gba/A.zip", "gba/B.zip"])
        self.assertEqual(data["games"][1], {"title": "B", "system": "gba", "bucket": "gba/B.zip", "note": "fun"})
        ids = [x["id"] for x in store.load_sets()]
        self.assertIn("my-picks", ids)
        self.assertIn("pinball", ids)

    def test_ids_cannot_collide(self):
        self.assertIn("already", store.personal_set_problem("Pinball"))
        store.save_personal_set("Mine", self.systems())
        self.assertIn("already", store.personal_set_problem("mine"))
        self.assertIsNone(store.personal_set_problem("Other"))
        self.assertIsNotNone(store.personal_set_problem("   "))
        self.assertIsNotNone(store.personal_set_problem("!!!"))

    def test_hand_placed_colliding_file_is_skipped_and_bad_json_ignored(self):
        os.makedirs(self.path("sets"))
        with open(self.path("sets/pinball.json"), "w") as f:
            json.dump({"name": "Fake", "games": []}, f)
        with open(self.path("sets/bad.json"), "w") as f:
            f.write("{oops")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            sets = store.load_sets()
        self.assertEqual([x["name"] for x in sets if x["id"] == "pinball"], ["Pinball"])
        self.assertNotIn("bad", [x["id"] for x in sets])
        self.assertIn("pinball", err.getvalue())

    def test_editor_makes_a_set_from_extras(self):
        t = target([{"title": "A", "bucket": "gba/A.zip"}])
        sets = store.load_sets()
        by_id = {x["id"]: x for x in sets}
        with mock.patch.object(edit.ui, "ask", return_value="Road Trip"), \
                contextlib.redirect_stdout(io.StringIO()):
            made = edit.make_set_from_extras(t, sets, by_id)
        self.assertEqual(made, "road-trip")
        self.assertIn("road-trip", by_id)
        self.assertTrue(os.path.exists(self.path("sets/road-trip.json")))

    def test_editor_refuses_empty_extras_and_colliding_name(self):
        sets = store.load_sets()
        with mock.patch.object(edit, "note") as n:
            self.assertIsNone(edit.make_set_from_extras(target([]), sets, {}))
        self.assertTrue(n.called)
        t = target([{"title": "A", "bucket": "gba/A.zip"}])
        with mock.patch.object(edit.ui, "ask", side_effect=["Pinball", ""]), mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(edit.make_set_from_extras(t, sets, {}))
        self.assertFalse(os.path.exists(self.path("sets")))


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
        store.save_lists({"nes": [{"bucket": "nes/b.zip"}], "gba": [{"bucket": "gba/Z.zip"}, {"bucket": "gba/a.zip"}],
                          "sets": ["z", "a"]},
                         {"c": {"snes": [{"bucket": "snes/2"}, {"bucket": "snes/1"}], "gba": []}})
        text = open(self.path("games.json")).read()
        data = json.loads(text)
        self.assertEqual(list(data), ["gba", "nes", "sets"])
        self.assertEqual([g["bucket"] for g in data["gba"]], ["gba/a.zip", "gba/Z.zip"])
        self.assertEqual(data["sets"], ["a", "z"])
        card = self.read("cards.json")["c"]["games"]
        self.assertEqual(list(card), ["gba", "snes"])
        self.assertEqual([g["bucket"] for g in card["snes"]], ["snes/1", "snes/2"])


class Schemas(unittest.TestCase):
    def load(self, name):
        with open(os.path.join(store.REPO_DATA, name)) as f:
            return json.load(f)

    def test_schemas_exist_and_cover_what_cards_store(self):
        games, cards = self.load("games.schema.json"), self.load("cards.schema.json")
        self.assertIn("sets", games["properties"])
        card = cards["additionalProperties"]["properties"]
        for key in ("device", "layout", "android_media", "systems", "games"):
            self.assertIn(key, card)
        self.assertEqual(card["systems"]["items"]["type"], "string")


class CheckSystemsKey(Cmd):
    def write(self, name, data):
        with open(self.path(name), "w") as f:
            json.dump(data, f)

    def test_card_systems_must_be_known_system_ids(self):
        self.write("cards.json", {"c": {"device": "full", "layout": "esde", "systems": ["gba"]}})
        self.assertEqual(commands.check_data(), [])
        self.write("cards.json", {"c": {"device": "full", "layout": "esde", "systems": ["nope", 3]}})
        self.assertEqual(len(commands.check_data()), 2)
        self.write("cards.json", {"c": {"device": "full", "layout": "esde", "systems": "gba"}})
        self.assertEqual(len(commands.check_data()), 1)

    def test_personal_set_files_are_checked(self):
        os.makedirs(self.path("sets"))
        self.write("sets/mine.json", {"name": "Mine", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/A.zip"},
            {"title": "B", "system": "nope", "bucket": "nope/B.zip"},
            {"system": "gba", "bucket": "nes/C.zip"}]})
        with open(self.path("sets/bad.json"), "w") as f:
            f.write("{oops")
        problems = commands.check_data()
        self.assertTrue(any("mine" in p and "nope" in p for p in problems))
        self.assertTrue(any("mine" in p and "nes/C.zip" in p for p in problems))
        self.assertTrue(any("mine" in p and "title" in p for p in problems))
        self.assertTrue(any("bad" in p for p in problems))


class CheckBucketKeys(Cmd):
    def test_missing_keys_are_reported_per_file(self):
        with open(self.path("games.json"), "w") as f:
            json.dump({"gba": [{"title": "A", "bucket": "gba/A.zip"}, {"title": "B", "bucket": "gba/B.zip"}]}, f)
        os.makedirs(self.path("sets"))
        with open(self.path("sets/mine.json"), "w") as f:
            json.dump({"name": "Mine", "games": [{"title": "D", "system": "nes", "bucket": "nes/D.zip",
                                                  "files": ["nes/D2.zip"]}]}, f)
        listings = {"gba": {"gba/A.zip"}, "nes": {"nes/D.zip"}}
        problems = commands.check_data(lambda system: listings.get(system, set()))
        self.assertTrue(any("gba/B.zip" in p for p in problems))
        self.assertTrue(any("nes/D2.zip" in p for p in problems))
        self.assertFalse(any("gba/A.zip" in p or "nes/D.zip" in p for p in problems))
        self.assertEqual(commands.check_data(), [])

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
                 edit.FULL_HINT.format(what="full system"), edit.MENU_HINT, edit.GAMES_HINT]
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

            def getch(self):
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
        self.assertEqual(self.run_keys([curses.KEY_END, ord(" "), 10]), [2])
        self.assertEqual(self.run_keys([curses.KEY_END, curses.KEY_HOME, ord(" "), 10]), [0])


if __name__ == "__main__":
    unittest.main()
