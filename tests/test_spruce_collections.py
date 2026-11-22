import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import tempfile  # noqa: E402
from sync_roms import spruce_collections  # noqa: E402

SYSTEMS = [{"bucket": "snes", "folders": {"spruce": "SFC"}}, {"bucket": "ps1", "folders": {"spruce": None}}]


def entry(rel):
    return {"rom_file_path": f"/mnt/SDCARD/Roms/SFC/{rel}", "game_system_name": "SFC"}


class WantedTests(unittest.TestCase):
    def games(self, *pairs):
        return [{"name": "Best: Of", "games": [{"system": s, "bucket": f"{s}/{r}"} for s, r in pairs]}]

    def test_entries_use_the_device_path_and_the_folder_as_system(self):
        wanted = spruce_collections.wanted(self.games(("snes", "A.sfc"), ("snes", "disc/B.sfc")), SYSTEMS, lambda s, r: True)
        self.assertEqual(wanted, {"Best Of": [entry("A.sfc"), entry("disc/B.sfc")]})

    def test_systems_without_a_spruce_folder_and_roms_off_the_card_are_left_out(self):
        wanted = spruce_collections.wanted(self.games(("ps1", "A.bin"), ("snes", "A.sfc"), ("snes", "B.sfc")), SYSTEMS,
                                           lambda s, r: r == "A.sfc")
        self.assertEqual(wanted, {"Best Of": [entry("A.sfc")]})

    def test_a_collection_with_nothing_on_the_card_is_left_out(self):
        self.assertEqual(spruce_collections.wanted(self.games(("snes", "A.sfc")), SYSTEMS, lambda s, r: False), {})

    def test_names_that_sanitise_alike_share_one_list_and_a_game_listed_again_stays(self):
        colls = [*self.games(("snes", "A.sfc"), ("snes", "B.sfc"), ("snes", "A.sfc")),
                 {"name": "Best Of", "games": [{"system": "snes", "bucket": "snes/A.sfc"}]},
                 {"name": "...", "games": [{"system": "snes", "bucket": "snes/A.sfc"}]}]
        wanted = spruce_collections.wanted(colls, SYSTEMS, lambda s, r: True)
        self.assertEqual(wanted, {"Best Of": [entry("A.sfc"), entry("B.sfc"), entry("A.sfc"), entry("A.sfc")]})


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name
        self.path = os.path.join(self.base, spruce_collections.FILE)

    def put(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def read(self):
        with open(self.path) as f:
            return json.load(f)

    def run_plan(self, wanted, owned):
        plan = spruce_collections.plan(self.base, wanted, owned)
        spruce_collections.apply(plan)
        return plan

    def test_writes_the_collections_file_and_owns_the_names(self):
        plan = self.run_plan({"Fav": [entry("A.sfc")]}, [])
        self.assertEqual(self.read(), [{"collection_name": "Fav", "game_list": [entry("A.sfc")]}])
        self.assertEqual(plan["owned"], ["Fav"])

    def test_keeps_collections_made_on_the_device(self):
        mine = {"collection_name": "Mine", "game_list": [entry("M.sfc")]}
        self.put([mine, {"collection_name": "Fav", "game_list": [entry("Old.sfc")]}])
        self.run_plan({"Fav": [entry("A.sfc")]}, ["Fav"])
        self.assertEqual(self.read(), [mine, {"collection_name": "Fav", "game_list": [entry("A.sfc")]}])

    def test_skips_a_wanted_name_the_device_made(self):
        mine = {"collection_name": "Fav", "game_list": [entry("M.sfc")]}
        self.put([mine])
        plan = self.run_plan({"Fav": [entry("A.sfc")]}, [])
        self.assertEqual(self.read(), [mine])
        self.assertEqual(plan["owned"], [])
        self.assertEqual(len(plan["warnings"]), 1)

    def test_the_skipped_collection_is_warned_about_before_the_recorded_names(self):
        self.put([{"collection_name": "Mine", "game_list": [entry("M.sfc")]}])
        plan = self.run_plan({"Mine": [entry("A.sfc")]}, ["a/b", "Old", "Old", ""])
        self.assertEqual([w.split(";")[0].split(" that ")[0] for w in plan["warnings"]],
                         ["Spruce already has a collection Mine", "ignoring the recorded collection name 'a/b'",
                          "ignoring the recorded collection name ''"])
        self.assertEqual((plan["disable"], plan["owned"]), ({"Old"}, []))

    def test_a_dropped_collection_is_removed_and_the_others_stay(self):
        mine = {"collection_name": "Mine", "game_list": [entry("M.sfc")]}
        self.put([mine, {"collection_name": "Old", "game_list": [entry("A.sfc")]}])
        plan = self.run_plan({}, ["Old"])
        self.assertEqual(self.read(), [mine])
        self.assertEqual(plan["disable"], {"Old"})

    def test_nothing_to_write_when_the_file_is_already_right(self):
        self.run_plan({"Fav": [entry("A.sfc")]}, [])
        self.assertEqual(spruce_collections.plan(self.base, {"Fav": [entry("A.sfc")]}, ["Fav"])["writes"], [])

    def test_no_file_and_nothing_wanted_writes_nothing(self):
        self.assertEqual(spruce_collections.plan(self.base, {}, [])["writes"], [])
        self.assertFalse(os.path.exists(self.path))

    def test_an_unreadable_file_is_left_alone_with_a_warning(self):
        self.put("not json")
        plan = self.run_plan({"Fav": [entry("A.sfc")]}, [])
        with open(self.path) as f:
            self.assertEqual(f.read(), "not json")
        self.assertEqual(len(plan["warnings"]), 1)
        self.assertEqual(plan["owned"], [])

    def test_an_unreadable_file_keeps_the_owned_names(self):
        self.put({"bad": 1})
        plan = self.run_plan({"Favs": [entry("A.sfc")]}, ["Favs", "Surprise"])
        self.assertEqual(plan["owned"], ["Favs", "Surprise"])


if __name__ == "__main__":
    unittest.main()
