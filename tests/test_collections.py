import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import collections, commands, store, ui  # noqa: E402

FAVS = {"name": "Favs", "games": [{"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}]}

FF7 = {"title": "FF7", "system": "psx", "bucket": "psx/FF7.m3u",
       "files": ["psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]}


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

    def test_malformed_files_are_warned_and_skipped_and_check_reports_them(self):
        collections.save_collection({"id": "favs", **FAVS})
        bad = {"a": {}, "b": [], "c": {"name": 5, "games": []}, "d": {"name": "X", "games": None}}
        for n, data in bad.items():
            self.write_json(f"collections/{n}.json", data)
        with mock.patch.object(ui, "warn") as warn:
            self.assertEqual([c["id"] for c in collections.load_collections()], ["favs"])
        self.assertEqual(warn.call_count, 4)
        problems = commands.check_data()
        self.assertEqual(len(problems), 4)
        self.assertTrue(all(p.startswith("collections/") for p in problems))

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


class Selection(DataDir):
    def setUp(self):
        super().setUp()
        collections.save_collection({"id": "favs", "name": "Favs", "games": FAVS["games"] + [FF7]})
        collections.save_collection({"id": "more", "name": "More", "games": [{"title": "Zelda", "system": "gba", "bucket": "gba/Zelda.zip"}]})

    def by_id(self):
        return {c["id"]: c for c in collections.load_collections()}

    def test_locked_games_expand_files_and_say_where_they_come_from(self):
        locked = store.card_locked_games({"collections": ["favs", "ghost"]}, self.by_id())
        self.assertEqual(sorted(locked), ["gba", "psx"])
        self.assertEqual(locked["gba"], [{"title": "Ruby", "bucket": "gba/Ruby.zip", "from": "💖 Favs"}])
        self.assertEqual([g["bucket"] for g in locked["psx"]], ["psx/FF7.m3u", "psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"])
        self.assertEqual(store.card_locked_games({}, self.by_id()), {})

    def test_load_manifest_adds_them_after_picks_and_excluded_never_drops_them(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde", "collections": ["favs"],
                                             "games": {"gba": [{"bucket": "gba/A.zip"}, {"bucket": "gba/Ruby.zip"}]},
                                             "excluded": {"gba": ["gba/Ruby.zip"]}}})
        gba = next(s for s in store.load_manifest(["c"])["systems"] if s["bucket"] == "gba")
        self.assertEqual([g["bucket"] for g in gba["games"]], ["gba/A.zip", "gba/Ruby.zip"])

    def test_every_cards_collections_are_in_the_mirror_list(self):
        self.write_json("cards.json", {"a": {"collections": ["favs"]}, "b": {"collections": ["more"]}})
        gba = next(s for s in store.load_manifest(store.all_card_names())["systems"] if s["bucket"] == "gba")
        self.assertEqual(sorted(g["bucket"] for g in gba["games"]), ["gba/Ruby.zip", "gba/Zelda.zip"])


if __name__ == "__main__":
    unittest.main()
