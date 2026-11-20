import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import muos_saves, store  # noqa: E402

LAYOUT = store.repo_json("layouts")["muos"]
SYSTEMS = [{"bucket": "gba", "folders": {"muos": "gba"}},
           {"bucket": "snes", "folders": {"muos": "snes"}},
           {"bucket": "none", "folders": {"muos": None}}]


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name

    def p(self, *a):
        return os.path.join(self.base, "MUOS", "pickles", *a)

    def scan(self):
        return muos_saves.scan(self.base, LAYOUT, SYSTEMS)

    def test_scan_finds_a_save_and_maps_its_system(self):
        helpers.touch(self.p("sram/mgba/GBA/Game.srm"), "abc")
        helpers.touch(self.p("sram/mgba/GBA/Game.rtc"), "c")
        helpers.touch(self.p("sram/mgba/GBA/notes.txt"), "x")
        helpers.touch(self.p("sram/mgba/GBA/._Game.srm"), "x")
        games, skipped = self.scan()
        self.assertEqual((list(games), skipped), ([("gba", "Game")], 0))
        e = sorted(games[("gba", "Game")], key=lambda x: x["name"])
        self.assertEqual([(x["name"], x["kind"], x["core"], x["rel"]) for x in e],
                         [("Game.rtc", "save", "mgba", "GBA"), ("Game.srm", "save", "mgba", "GBA")])
        self.assertEqual((e[1]["path"], e[1]["size"]), (self.p("sram/mgba/GBA/Game.srm"), 3))
        self.assertIn("mtime", e[1])

    def test_scan_groups_state_slots_and_states_ini_under_one_game(self):
        for n in ("slot_0.state", "slot_1.state", "states.ini"):
            helpers.touch(self.p("state/mgba/gba/Game", n), "s")
        helpers.touch(self.p("sram/mgba/gba/Game.srm"), "s")
        games, skipped = self.scan()
        self.assertEqual((list(games), skipped), ([("gba", "Game")], 0))
        e = games[("gba", "Game")]
        self.assertEqual(sorted((x["name"], x["kind"]) for x in e),
                         [("Game.srm", "save"), ("slot_0.state", "state"), ("slot_1.state", "state"),
                          ("states.ini", "state")])
        self.assertTrue(all(x["rel"] == "gba" and x["core"] == "mgba" for x in e))

    def test_scan_maps_a_nested_rom_dir(self):
        helpers.touch(self.p("sram/snes9x/snes/Hacks/Game.srm"), "s")
        helpers.touch(self.p("state/snes9x/snes/Hacks/Game/slot_1.state"), "s")
        games, skipped = self.scan()
        self.assertEqual((list(games), skipped), ([("snes", "Game")], 0))
        self.assertEqual({x["rel"] for x in games[("snes", "Game")]}, {"snes/Hacks"})

    def test_scan_matches_folder_case_insensitively(self):
        systems = [{"bucket": "sfc", "folders": {"muos": "Super Famicom"}}]
        helpers.touch(self.p("sram/snes9x/super-famicom/Game.srm"), "s")
        helpers.touch(self.p("sram/snes9x/SUPER_FAMI+COM/Other.srm"), "s")
        games, skipped = muos_saves.scan(self.base, LAYOUT, systems)
        self.assertEqual((sorted(games), skipped), ([("sfc", "Game"), ("sfc", "Other")], 0))

    def test_scan_skips_unknown_folders_and_counts_them(self):
        helpers.touch(self.p("sram/mgba/Nope/Game.srm"), "s")
        helpers.touch(self.p("state/mgba/Nope/Game/slot_1.state"), "s")
        helpers.touch(self.p("state/mgba/Nope/Game/states.ini"), "s")
        helpers.touch(self.p("sram/mgba/gba/Game.srm"), "s")
        games, skipped = self.scan()
        self.assertEqual((list(games), skipped), ([("gba", "Game")], 3))

    def test_scan_without_a_rom_dir_maps_by_rom(self):
        helpers.touch(os.path.join(self.base, "ROMS", "gba", "Game.zip"), "r")
        helpers.touch(self.p("sram/mgba/Game.srm"), "s")
        helpers.touch(self.p("sram/mgba/Lost.srm"), "s")
        games, skipped = self.scan()
        self.assertEqual((list(games), skipped), ([("gba", "Game")], 1))
        self.assertEqual(games[("gba", "Game")][0]["rel"], "")

    def test_scan_missing_pickles(self):
        self.assertEqual(self.scan(), ({}, 0))


class PlanApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "stash")
        self.card = os.path.join(self.tmp.name, "card")
        files = {"Game.srm": "a", "slot_1.state": "b", "states.ini": "c"}
        for n, c in files.items():
            helpers.touch(os.path.join(self.src, n), c)
        self.stash = {"dir": self.src, "system": "snes", "game": "Game", "core": "snes9x",
                      "files": [{"name": n, "kind": "save" if n.endswith(".srm") else "state", "rel": "snes/Hacks",
                                 "core": "snes9x"} for n in files]}

    def pk(self, *a):
        return os.path.join(self.card, "MUOS", "pickles", *a)

    def test_plan_apply_writes_the_same_relative_paths(self):
        plan = muos_saves.plan_apply(self.stash, self.card, LAYOUT, SYSTEMS[1], "snes9x")
        self.assertEqual(plan, [
            (os.path.join(self.src, "Game.srm"), self.pk("sram/snes9x/snes/Hacks/Game.srm"), "new"),
            (os.path.join(self.src, "slot_1.state"), self.pk("state/snes9x/snes/Hacks/Game/slot_1.state"), "new"),
            (os.path.join(self.src, "states.ini"), self.pk("state/snes9x/snes/Hacks/Game/states.ini"), "new")])

    def test_plan_apply_marks_a_differing_file_as_differs(self):
        helpers.touch(self.pk("sram/snes9x/snes/Hacks/Game.srm"), "a")
        helpers.touch(self.pk("state/snes9x/snes/Hacks/Game/slot_1.state"), "zzz")
        plan = muos_saves.plan_apply(self.stash, self.card, LAYOUT, SYSTEMS[1], "snes9x")
        self.assertEqual([s for _, _, s in plan], ["same", "differs", "new"])

    def test_plan_apply_without_a_rom_dir(self):
        stash = dict(self.stash, files=[dict(f, rel="") for f in self.stash["files"]])
        plan = muos_saves.plan_apply(stash, self.card, LAYOUT, SYSTEMS[1], "snes9x")
        self.assertEqual([d for _, d, _ in plan][:2], [self.pk("sram/snes9x/Game.srm"),
                                                       self.pk("state/snes9x/Game/slot_1.state")])


if __name__ == "__main__":
    unittest.main()
