import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardshare, picker, ui  # noqa: E402
from helpers import Cmd  # noqa: E402


class CardShareTest(unittest.TestCase):
    def test_export_keeps_only_card_fields(self):
        entry = {"device": "d", "layout": "l", "size": 1, "games": {}, "excluded": [], "collections": [],
                 "surprises": [], "surprise": True, "frontend_collections": [], "drivers": [], "pico8": "z",
                 "android_media": 1, "systems": []}
        self.assertLessEqual(set(cardshare.export_entry(entry, {})), set(cardshare.KEPT))

    def test_export_flattens_surprises_and_collections(self):
        a = {"title": "A", "bucket": "gba/A.zip"}
        entry = {"games": {"gba": [a], "sets": ["shmups"]}, "surprise": False,
                 "surprises": [{"system": "gba", "bucket": "gba/B.zip", "title": "B"},
                               {"system": "gba", "bucket": "gba/A.zip", "title": "A"}],
                 "collections": ["c", "gone"]}
        colls = {"c": {"name": "C", "games": [{"system": "psx", "bucket": "psx/D.cue", "title": "D",
                                               "files": ["psx/D.bin"], "note": "n"}]}}
        out = cardshare.export_entry(entry, colls)
        self.assertEqual(out["games"], {
            "gba": [a, {"title": "B", "bucket": "gba/B.zip"}], "sets": ["shmups"],
            "psx": [{"title": "D", "bucket": "psx/D.cue", "files": ["psx/D.bin"], "note": "n"}]})
        self.assertEqual(entry["games"], {"gba": [a], "sets": ["shmups"]})

    def test_export_full_system_gets_nothing(self):
        entry = {"games": {"gba": {"full_system": True}},
                 "surprises": [{"system": "gba", "bucket": "gba/B.zip", "title": "B"}]}
        self.assertEqual(cardshare.export_entry(entry, {})["games"], {"gba": {"full_system": True}})

    def test_export_without_games_key_still_flattens(self):
        entry = {"surprises": [{"system": "gba", "bucket": "gba/B.zip", "title": "B"}]}
        self.assertEqual(cardshare.export_entry(entry, {})["games"], {"gba": [{"title": "B", "bucket": "gba/B.zip"}]})
        self.assertNotIn("games", cardshare.export_entry({"device": "d"}, {}))

    def test_import_entry_turns_surprise_off(self):
        entry = {"device": "x", "surprise": True, "collections": ["c"], "surprises": [{}]}
        self.assertEqual(cardshare.import_entry(entry), {"device": "x", "surprise": False})

    def test_final_name_and_problems(self):
        self.assertEqual(cardshare.final_name("A", "Bob ", {}), "Bob A")
        self.assertEqual(cardshare.final_name("A", "Bob ", {"A": "Z"}), "Z")
        self.assertEqual(cardshare.name_problem("Z", {"Z"}), "taken")
        self.assertEqual(cardshare.name_problem(" ", set()), "invalid")
        self.assertEqual(cardshare.name_problem("a/b", set()), "invalid")
        self.assertIsNone(cardshare.name_problem("ok", set()))


if __name__ == "__main__":
    unittest.main()


class CardsExportTest(Cmd):
    def setUp(self):
        super().setUp()
        self.write_json("cards.json", {
            "SD": {"device": "full", "layout": "esde", "surprise": False, "drivers": ["x"],
                   "surprises": [{"system": "gba", "bucket": "gba/B.zip", "title": "B"}]},
            "Other": {"device": "full", "layout": "esde"}})
        self.out = self.path("out.json")

    def test_export_writes_chosen_cards(self):
        with mock.patch.object(cardshare, "pick_export", return_value=["SD"]):
            code = self.run_cmd("cards", "export", self.out)[0]
        self.assertEqual(code, 0)
        with open(self.out) as f:
            self.assertEqual(json.load(f), {"SD": {"device": "full", "layout": "esde",
                                                   "games": {"gba": [{"title": "B", "bucket": "gba/B.zip"}]}}})

    def test_export_declined_overwrite_keeps_file(self):
        with open(self.out, "w") as f:
            f.write("old")
        with mock.patch.object(cardshare, "pick_export", return_value=["SD"]), \
                mock.patch.object(ui, "confirm", return_value=False):
            code = self.run_cmd("cards", "export", self.out)[0]
        self.assertEqual(code, 0)
        with open(self.out) as f:
            self.assertEqual(f.read(), "old")

    def test_export_dry_run_writes_nothing(self):
        with mock.patch.object(cardshare, "pick_export", return_value=["SD"]):
            code, out, _ = self.run_cmd("cards", "export", self.out, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Would export 1 card(s)", out)
        self.assertFalse(os.path.exists(self.out))


class CardsImportTest(Cmd):
    def setUp(self):
        super().setUp()
        self.mine = {"Mine": {"device": "full", "layout": "esde", "games": {"gba": []}}}
        self.write_json("cards.json", self.mine)
        self.file = self.path("in.json")
        self.write_json("in.json", {"A": {"device": "full", "layout": "esde", "drivers": ["x"],
                                          "surprises": [{"system": "gba", "bucket": "gba/B.zip", "title": "B"}]},
                                    "bad": []})

    def test_import_adds_cards_with_surprise_off(self):
        with mock.patch.object(cardshare, "pick_import", return_value={"Bob A": "A"}) as pick:
            code = self.run_cmd("cards", "import", self.file)[0]
        self.assertEqual(code, 0)
        self.assertEqual(list(pick.call_args.args[0]), ["A"])
        cards = self.read("cards.json")
        self.assertEqual(cards["Bob A"], {"device": "full", "layout": "esde", "surprise": False})
        self.assertEqual(cards["Mine"], self.mine["Mine"])

    def test_import_bad_file_fails(self):
        with open(self.file, "w") as f:
            f.write("{")
        self.assertEqual(self.run_cmd("cards", "import", self.file)[0], 2)
        self.write_json("in.json", [])
        self.assertEqual(self.run_cmd("cards", "import", self.file)[0], 2)

    def test_import_refuses_unreadable_cards_json(self):
        with open(self.path("cards.json"), "w") as f:
            f.write("{")
        with mock.patch.object(cardshare, "pick_import") as pick:
            self.assertEqual(self.run_cmd("cards", "import", self.file)[0], 3)
        pick.assert_not_called()


class PickImportTest(unittest.TestCase):
    CARDS = {"A": {"device": "full", "layout": "esde"}, "SD": {"device": "full", "layout": "esde"}}

    def pick(self, results, answers, cards=None, existing=()):
        results = iter(results)

        def scripted(*args, **kwargs):  # like the real list, the session keeps the rows' states
            result = next(results)
            if isinstance(result, list):
                kwargs["session"]["sel"] = list(result)
            return result

        with mock.patch.object(picker, "filter_list", side_effect=scripted) as fl, \
                mock.patch.object(ui, "ask", side_effect=answers), \
                mock.patch.object(picker, "queue_note", return_value=True) as note:
            out = cardshare.pick_import(cards or self.CARDS, set(existing), set(), {"esde"})
        return out, fl, note

    def test_pick_import_marks_clash_and_applies_prefix(self):
        out, fl, note = self.pick([("p", 0), [True, True], [True, False]], ["Bob "], existing={"Bob SD"})
        self.assertEqual(out, {"Bob A": "A"})
        self.assertEqual(fl.call_args_list[1].args[1], ["Bob A", "Bob SD"])
        note.assert_called_once()
        self.assertIn("Bob SD", note.call_args.args[0])
        self.assertEqual(fl.call_count, 3)
        self.assertIn(("taken", "red"), fl.call_args_list[2].kwargs["extras"][1])

    def test_pick_import_rename_overrides_prefix(self):
        out, _, _ = self.pick([("p", 0), ("r", 0), [True]], ["X-", "Mine"], cards={"A": self.CARDS["A"]})
        self.assertEqual(out, {"Mine": "A"})

    def test_pick_import_locks_unknown_device(self):
        cards = {"A": self.CARDS["A"], "B": {"device": "nope", "layout": "esde"}}
        _, fl, _ = self.pick([None], [], cards=cards)
        self.assertEqual(fl.call_args.kwargs["locked"], [False, True])

    def test_pick_import_rename_with_no_row_shown_is_ignored(self):
        out, fl, _ = self.pick([("r", None), ("p", None), [True]], ["X-"], cards={"A": self.CARDS["A"]})
        self.assertEqual(out, {"X-A": "A"})
        self.assertEqual(fl.call_count, 3)

    def test_pick_import_empty_prefix_clears_it(self):
        out, _, _ = self.pick([("p", 0), ("p", 0), [True]], ["X-", ""], cards={"A": self.CARDS["A"]})
        self.assertEqual(out, {"A": "A"})

    def test_pick_import_locks_non_string_device_or_layout(self):
        cards = {"A": {"device": ["x"], "layout": "esde"}, "B": {"device": "full", "layout": {"a": 1}}}
        _, fl, _ = self.pick([None], [], cards=cards)
        self.assertEqual(fl.call_args.kwargs["locked"], [True, True])


class ExportExcludedTest(unittest.TestCase):
    def test_flattened_games_leave_excluded(self):
        entry = {"games": {"gba": []}, "excluded": {"gba": ["gba/B.zip"], "psx": ["psx/D.cue", "psx/E.cue"]},
                 "surprises": [{"system": "gba", "bucket": "gba/B.zip", "title": "B"},
                               {"system": "psx", "bucket": "psx/D.cue", "title": "D"}]}
        out = cardshare.export_entry(entry, {})
        self.assertEqual(out["excluded"], {"psx": ["psx/E.cue"]})
        self.assertEqual(entry["excluded"], {"gba": ["gba/B.zip"], "psx": ["psx/D.cue", "psx/E.cue"]})

    def test_excluded_dropped_when_empty(self):
        entry = {"excluded": {"gba": ["gba/B.zip"]}, "surprises": [{"system": "gba", "bucket": "gba/B.zip", "title": "B"}]}
        self.assertNotIn("excluded", cardshare.export_entry(entry, {}))
