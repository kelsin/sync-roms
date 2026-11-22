import json
import os
import sys
import unittest
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import tempfile  # noqa: E402
from sync_roms import cardfs, spruce_emu  # noqa: E402

CONFIG = {
    "label": "Arcade",
    "menuOptions": {"Emulator": {"options": ["fbneo"], "selected": "fbneo", "overrides": {}}},
    "default_emulator": "fbneo",
    "ignoreList": ["neogeo.zip", "neocd.zip"],
}


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())
        self.path = os.path.join(self.base, "Emu", "ARCADE", "config.json")

    def put(self, data, indent=2, newline="\n"):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data, indent=indent) + newline)

    def read(self):
        with open(self.path) as f:
            return json.load(f)

    def run_plan(self, names, owned=None):
        plan = spruce_emu.plan(self.base, {"ARCADE": names}, owned or {})
        spruce_emu.apply(plan)
        cardfs.flush()
        return plan

    def test_adds_bios_names_and_keeps_the_ones_spruce_ships(self):
        self.put(CONFIG)
        plan = self.run_plan(["neogeo.zip", "pgm.zip"])
        self.assertEqual(self.read()["ignoreList"], ["neogeo.zip", "neocd.zip", "pgm.zip"])
        self.assertEqual(plan["owned"], {"ARCADE": ["pgm.zip"]})

    def test_the_rest_of_the_file_and_its_format_are_kept(self):
        self.put(CONFIG, indent=4, newline="")
        self.run_plan(["pgm.zip"])
        with open(self.path) as f:
            text = f.read()
        self.assertTrue(text.startswith('{\n    "label": "Arcade",\n    "menuOptions": {\n        "Emulator"'))
        self.assertFalse(text.endswith("\n"))
        data = json.loads(text)
        self.assertEqual(list(data), list(CONFIG))
        self.assertEqual(data["menuOptions"], CONFIG["menuOptions"])

    def test_nothing_is_written_when_nothing_changes(self):
        self.put(json.dumps(CONFIG, separators=(",", ":")))  # odd format: left alone
        plan = spruce_emu.plan(self.base, {"ARCADE": ["neogeo.zip"]}, {})
        self.assertEqual((plan["writes"], plan["owned"]), ([], {}))

    def test_a_second_run_changes_nothing(self):
        self.put(CONFIG)
        first = self.run_plan(["pgm.zip"])
        second = spruce_emu.plan(self.base, {"ARCADE": ["pgm.zip"]}, first["owned"])
        self.assertEqual(second["writes"], [])
        self.assertEqual(second["owned"], first["owned"])

    def test_names_sync_added_go_when_not_wanted_and_the_others_stay(self):
        self.put(CONFIG)
        first = self.run_plan(["neogeo.zip", "pgm.zip", "skns.zip"])
        data = self.read()
        data["ignoreList"].append("mine.zip")
        self.put(data)
        second = self.run_plan(["neogeo.zip", "skns.zip"], first["owned"])
        self.assertEqual(self.read()["ignoreList"], ["neogeo.zip", "neocd.zip", "skns.zip", "mine.zip"])
        self.assertEqual(second["owned"], {"ARCADE": ["skns.zip"]})
        third = self.run_plan([], second["owned"])
        self.assertEqual(self.read()["ignoreList"], ["neogeo.zip", "neocd.zip", "mine.zip"])
        self.assertEqual(third["owned"], {})

    def test_names_are_added_again_when_an_update_replaced_the_config(self):
        self.put(CONFIG)
        first = self.run_plan(["pgm.zip"])
        self.put(CONFIG)
        second = self.run_plan(["pgm.zip"], first["owned"])
        self.assertIn("pgm.zip", self.read()["ignoreList"])
        self.assertEqual(second["owned"], first["owned"])

    def test_a_missing_or_unreadable_config_is_skipped_with_a_warning_and_the_record_kept(self):
        owned = {"ARCADE": ["pgm.zip"]}
        plan = spruce_emu.plan(self.base, {"ARCADE": ["pgm.zip"]}, owned)
        self.assertEqual((plan["writes"], plan["owned"], len(plan["warnings"])), ([], owned, 1))
        self.put("{not json")
        plan = spruce_emu.plan(self.base, {"ARCADE": ["pgm.zip"]}, owned)
        self.assertEqual((plan["writes"], plan["owned"], len(plan["warnings"])), ([], owned, 1))

    def test_a_folder_with_nothing_wanted_or_owned_is_left_alone_even_without_a_config(self):
        plan = spruce_emu.plan(self.base, {"ARCADE": []}, {})
        self.assertEqual((plan["writes"], plan["warnings"], plan["owned"]), ([], [], {}))

    def test_a_config_with_no_ignore_list_gets_one(self):
        self.put({k: v for k, v in CONFIG.items() if k != "ignoreList"})
        self.run_plan(["pgm.zip"])
        self.assertEqual(self.read()["ignoreList"], ["pgm.zip"])

    def test_describe_says_what_would_change_and_writes_nothing(self):
        self.put(CONFIG)
        plan = spruce_emu.plan(self.base, {"ARCADE": ["pgm.zip"]}, {})
        with mock.patch("sys.stdout", new_callable=StringIO) as out:
            spruce_emu.describe(plan)
        self.assertIn("Emu/ARCADE/config.json", out.getvalue())
        self.assertEqual(self.read(), CONFIG)


class WantedTests(unittest.TestCase):
    SYSTEMS = [{"bucket": "mame", "folders": {"spruce": "MAME2003PLUS"}, "bios": {"rom_files": []}},
               {"bucket": "fbneo", "folders": {"spruce": "ARCADE"}, "bios": {"rom_files": ["fbneo/neogeo.zip", "pgm.zip"]}},
               {"bucket": "other", "folders": {"spruce": "ARCADE"}, "bios": {"rom_files": ["x/pgm.zip", "x/a.zip"]}},
               {"bucket": "snes", "folders": {"spruce": "SFC"}, "bios": {}}]

    def test_the_basenames_of_the_bios_of_systems_with_roms_by_folder(self):
        got = spruce_emu.wanted(self.SYSTEMS, lambda s: s["bucket"] != "other")
        self.assertEqual(got, {"ARCADE": ["neogeo.zip", "pgm.zip"]})
        got = spruce_emu.wanted(self.SYSTEMS, lambda s: True)
        self.assertEqual(got, {"ARCADE": ["a.zip", "neogeo.zip", "pgm.zip"]})

    def test_a_system_with_no_roms_wants_nothing(self):
        self.assertEqual(spruce_emu.wanted(self.SYSTEMS, lambda s: False), {})


class LegacyTests(unittest.TestCase):
    def test_the_old_fbneo_folder_is_a_stand_in_system_unless_a_system_uses_it(self):
        self.assertEqual([s["folders"] for s in spruce_emu.legacy_systems([{"folders": {"spruce": "ARCADE"}}])],
                         [{"spruce": "FBNEO"}])
        self.assertEqual(spruce_emu.legacy_systems([{"folders": {"spruce": "FBNEO"}}]), [])


if __name__ == "__main__":
    unittest.main()
