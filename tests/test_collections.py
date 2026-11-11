import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import collections, commands, store, ui  # noqa: E402

FAVS = {"name": "Favs", "games": [{"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}]}


class Files(DataDir):
    def test_save_and_load_round_trip_sorted_by_name_without_the_id(self):
        collections.save_collection({"id": "zelda", "name": "zelda", "description": "", "games": []})
        collections.save_collection({"id": "favs", **FAVS})
        self.assertEqual([c["id"] for c in collections.load_collections()], ["favs", "zelda"])
        self.assertEqual(self.read("collections/favs.json"), FAVS)
        self.assertEqual(self.read("collections/zelda.json"), {"name": "zelda", "games": []})
        with open(self.path("collections/favs.json"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith("}\n"))

    def test_unreadable_file_is_warned_and_skipped(self):
        collections.save_collection({"id": "favs", **FAVS})
        with open(self.path("collections/bad.json"), "w") as f:
            f.write("{")
        with mock.patch.object(ui, "warn") as warn:
            self.assertEqual([c["id"] for c in collections.load_collections()], ["favs"])
        self.assertIn("collections/bad.json", warn.call_args[0][0])

    def test_no_folder_is_no_collections_and_delete_removes_the_file(self):
        self.assertEqual(collections.load_collections(), [])
        collections.save_collection({"id": "favs", **FAVS})
        collections.delete_collection("favs")
        self.assertFalse(os.path.exists(self.path("collections/favs.json")))

    def test_collection_problem(self):
        self.assertEqual(collections.collection_problem(" ** ", []), "A collection needs a name with letters or digits.")
        self.assertEqual(collections.collection_problem("Favs!", ["favs"]), "There is already a collection with the id favs.")
        self.assertIsNone(collections.collection_problem("Favs 2", ["favs"]))
        for name in ("Surprise", "surprise.", "SUR*PRISE"):  # safe_name drops * and .
            self.assertEqual(collections.collection_problem(name, []), "Surprise is used by the Surprise option.")

    def test_collection_games_skips_entries_without_a_bucket(self):
        self.assertEqual(collections.collection_games({"games": [{"title": "x"}, *FAVS["games"]]}), FAVS["games"])

    def test_remove_from_cards_rewrites_only_cards_that_use_it(self):
        self.write_json("cards.json", {"a": {"collections": ["favs", "x"]}, "b": {"collections": ["favs"]}, "c": {}})
        self.assertEqual(collections.remove_from_cards("favs"), ["a", "b"])
        self.assertEqual(self.read("cards.json"), {"a": {"collections": ["x"]}, "b": {"collections": []}, "c": {}})


class Check(DataDir):
    def test_collection_files_are_checked(self):
        os.makedirs(self.path("collections"))
        self.write_json("collections/mine.json", {"name": "Mine", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/A.zip"},
            {"title": "B", "system": "nope", "bucket": "nope/B.zip"},
            {"title": "C", "system": "gba", "bucket": "nes/C.zip"}]})
        with open(self.path("collections/bad.json"), "w") as f:
            f.write("{")
        problems = commands.check_data()
        self.assertIn("collections/mine.json: nope/B.zip: unknown system 'nope'", problems)
        self.assertIn("collections/mine.json: 'nes/C.zip' isn't under gba/", problems)
        self.assertTrue(any(p.startswith("collections/bad.json: not valid JSON") for p in problems))
        self.assertEqual(len(problems), 3)

    def test_card_collection_fields_are_checked(self):
        collections.save_collection({"id": "mine", "name": "Mine", "games": []})
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde", "collections": ["mine", "ghost"],
                                             "frontend_collections": "Mine"}})
        self.assertEqual(commands.check_data(), ["cards.json: c: unknown collection 'ghost'",
                                                 "cards.json: c: 'frontend_collections' must be a list of names"])


if __name__ == "__main__":
    unittest.main()
