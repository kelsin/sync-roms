import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import saves, store  # noqa: E402

LAYOUTS = store.repo_json("layouts")
SYSTEMS = [{"bucket": "gba", "folders": {"onion": "GBA", "knulli": "gba", "esde": "gba", "allium": "GBA",
                                         "emudeck": "gba"}},
           {"bucket": "gb", "folders": {"onion": "GB", "knulli": "gb", "esde": "gb", "allium": "GB",
                                        "emudeck": "gb"}},
           {"bucket": "none", "folders": {"onion": None, "knulli": None}}]


class ClassifyTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(saves.classify("Game.srm"), ("Game", "save"))
        self.assertEqual(saves.classify("Game.state"), ("Game", "state"))
        self.assertEqual(saves.classify("Game.state12"), ("Game", "state"))
        self.assertEqual(saves.classify("Game.state.auto"), ("Game", "state"))
        self.assertEqual(saves.classify("Game.state1.png"), ("Game", "thumbnail"))
        self.assertEqual(saves.classify("Game.state.auto.png"), ("Game", "thumbnail"))
        self.assertEqual(saves.classify("Game.state.png"), ("Game", "thumbnail"))
        self.assertEqual(saves.classify("A.B.srm"), ("A.B", "save"))

    def test_rejects(self):
        for n in ("x.sav", "x.png", "x.state.bak", "x.srm.png", "x.statex"):
            self.assertIsNone(saves.classify(n), n)


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name

    def p(self, *a):
        return os.path.join(self.base, *a)

    def test_onion(self):
        helpers.touch(self.p("Roms", "GBA", "Game.zip"), "r")
        helpers.touch(self.p("Saves/CurrentProfile/saves/gpSP/Game.srm"), "abc")
        helpers.touch(self.p("Saves/CurrentProfile/states/gpSP/Game.state.auto"), "s")
        helpers.touch(self.p("Saves/CurrentProfile/states/gpSP/Game.state.auto.png"), "p")
        helpers.touch(self.p("Saves/CurrentProfile/saves/gpSP/Other.srm"), "x")
        helpers.touch(self.p("Saves/CurrentProfile/saves/gpSP/notes.txt"), "x")
        games, skipped = saves.scan(self.base, "onion", LAYOUTS["onion"], SYSTEMS)
        self.assertEqual(list(games), [("gba", "Game")])
        self.assertEqual(skipped, 1)
        e = games[("gba", "Game")]
        self.assertEqual(sorted(x["kind"] for x in e), ["save", "state", "thumbnail"])
        self.assertTrue(all(x["core"] == "gpSP" for x in e))
        sav = [x for x in e if x["kind"] == "save"][0]
        self.assertEqual((sav["name"], sav["size"]), ("Game.srm", 3))
        self.assertEqual(sav["path"], self.p("Saves/CurrentProfile/saves/gpSP/Game.srm"))
        self.assertIn("mtime", sav)

    def test_knulli(self):
        helpers.touch(self.p("roms", "gba", "Game.zip"), "r")
        helpers.touch(self.p("saves/gba/Game.state1"), "s")
        helpers.touch(self.p("saves/gba/Game.state1.png"), "p")
        helpers.touch(self.p("saves/gba/Game.srm"), "s")
        games, skipped = saves.scan(self.base, "knulli", LAYOUTS["knulli"], SYSTEMS)
        self.assertEqual(skipped, 0)
        e = games[("gba", "Game")]
        self.assertEqual(len(e), 3)
        self.assertTrue(all(x["core"] is None for x in e))

    def test_orphan_thumbnail_kept(self):
        helpers.touch(self.p("roms", "gba", "Game.zip"), "r")
        helpers.touch(self.p("saves/gba/Game.state1.png"), "p")
        games, _ = saves.scan(self.base, "knulli", LAYOUTS["knulli"], SYSTEMS)
        self.assertEqual([x["kind"] for x in games[("gba", "Game")]], ["thumbnail"])

    def test_system_folder_needs_no_rom(self):
        helpers.touch(self.p("saves/gba/Game.srm"), "s")
        games, skipped = saves.scan(self.base, "knulli", LAYOUTS["knulli"], SYSTEMS)
        self.assertEqual(list(games), [("gba", "Game")])
        self.assertEqual(skipped, 0)

    def test_retroarch_dir(self):
        helpers.touch(self.p("Roms", "GBA", "Game.zip"), "r")
        ra = os.path.join(self.base, "elsewhere")
        helpers.touch(os.path.join(ra, "saves/mGBA/Game.srm"), "s")
        games, _ = saves.scan(self.base, "onion", LAYOUTS["onion"], SYSTEMS, retroarch_dir=ra)
        self.assertEqual(games[("gba", "Game")][0]["core"], "mGBA")

    def test_ambiguous_stem_skipped(self):
        helpers.touch(self.p("Roms", "GBA", "Game.zip"), "r")
        helpers.touch(self.p("Roms", "GB", "Game.gb"), "r")
        helpers.touch(self.p("Saves/CurrentProfile/saves/X/Game.srm"), "s")
        games, skipped = saves.scan(self.base, "onion", LAYOUTS["onion"], SYSTEMS)
        self.assertEqual((games, skipped), ({}, 1))

    def test_rom_stems_recursive_hidden(self):
        helpers.touch(self.p("Roms", "GBA", ".multi-disc", "Disc.cue"), "r")
        helpers.touch(self.p("Roms", "GBA", "Sub", "A.b.zip"), "r")
        stems = saves.rom_stems(self.base, "onion", LAYOUTS["onion"], SYSTEMS)
        self.assertEqual(stems, {"Disc": {"gba"}, "A.b": {"gba"}})

    def test_missing_folders(self):
        self.assertEqual(saves.scan(self.base, "esde", LAYOUTS["esde"], SYSTEMS), ({}, 0))

    def test_follows_symlinks(self):
        real = self.p("real")
        helpers.touch(os.path.join(real, "Game.srm"), "s")
        os.makedirs(self.p("Emulation/saves/retroarch"))
        os.symlink(real, self.p("Emulation/saves/retroarch/saves"))
        helpers.touch(self.p("Emulation/roms/gba/Game.zip"), "r")
        games, _ = saves.scan(self.base, "emudeck", LAYOUTS["emudeck"], SYSTEMS)
        self.assertIn(("gba", "Game"), games)


class StashTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        import datetime
        patch = mock.patch.object(store, "data_dir", return_value=os.path.join(self.tmp.name, "data"))
        patch.start()
        self.addCleanup(patch.stop)
        self.now = datetime.datetime(2026, 11, 18, 10, 2, 3)

    def entries(self):
        a = os.path.join(self.tmp.name, "src", "Game.srm")
        b = os.path.join(self.tmp.name, "src", "Game.state.auto")
        helpers.touch(a, "save")
        helpers.touch(b, "state")
        return [{"path": a, "name": "Game.srm", "kind": "save", "core": "gpSP", "size": 4, "mtime": 0},
                {"path": b, "name": "Game.state.auto", "kind": "state", "core": "gpSP", "size": 5, "mtime": 0}]

    def test_round_trip(self):
        d = saves.write_stash("SHARE", "onion", "gba", "Game", "gpSP", self.entries(), now=self.now)
        self.assertEqual(d, os.path.join(saves.stash_root(), "gba", "Game", "20261118-100203-SHARE"))
        self.assertEqual(open(os.path.join(d, "Game.srm")).read(), "save")
        meta = json.load(open(os.path.join(d, "stash.json")))
        self.assertEqual(meta, {"system": "gba", "game": "Game", "card": "SHARE", "layout": "onion",
                                "core": "gpSP", "stashed": "2026-11-18T10:02:03",
                                "files": [{"name": "Game.srm", "kind": "save"},
                                          {"name": "Game.state.auto", "kind": "state"}]})
        out = saves.load_stashes()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["dir"], d)
        self.assertEqual(out[0]["game"], "Game")

    def test_same_second_suffix(self):
        e = self.entries()
        d1 = saves.write_stash("SHARE", "onion", "gba", "Game", "gpSP", e, now=self.now)
        d2 = saves.write_stash("SHARE", "onion", "gba", "Game", "gpSP", e, now=self.now)
        d3 = saves.write_stash("SHARE", "onion", "gba", "Game", "gpSP", e, now=self.now)
        self.assertEqual([d2, d3], [d1 + "-2", d1 + "-3"])

    def test_dry_run(self):
        d = saves.write_stash("SHARE", "onion", "gba", "Game", None, self.entries(), now=self.now, dry_run=True)
        self.assertFalse(os.path.exists(d))

    def test_load_sorted_filtered_and_skips_bad(self):
        import datetime
        e = self.entries()
        saves.write_stash("A", "onion", "gba", "Zed", None, e, now=self.now)
        saves.write_stash("A", "onion", "gb", "alpha", None, e, now=self.now)
        saves.write_stash("A", "onion", "gba", "alpha", None, e, now=self.now)
        saves.write_stash("B", "onion", "gba", "alpha", None, e, now=self.now + datetime.timedelta(seconds=5))
        bad = os.path.join(saves.stash_root(), "gba", "bad")
        helpers.touch(os.path.join(bad, "stash.json"), "{nope")
        helpers.touch(os.path.join(saves.stash_root(), "gba", "bad2", "stash.json"), '{"system": "gba"}')
        out = saves.load_stashes()
        self.assertEqual([(s["game"], s["system"], s["card"]) for s in out],
                         [("alpha", "gb", "A"), ("alpha", "gba", "B"), ("alpha", "gba", "A"),
                          ("Zed", "gba", "A")])
        self.assertEqual({s["system"] for s in saves.load_stashes({"gb"})}, {"gb"})


class TargetTest(unittest.TestCase):
    def test_every_layout(self):
        system = SYSTEMS[0]
        for name, layout in LAYOUTS.items():
            ra = layout["retroarch"]
            needs = "{core}" in ra["saves"] or "{core}" in ra["states"]
            for kind in ("save", "state", "thumbnail"):
                if needs:
                    with self.assertRaises(ValueError):
                        saves.target_dir("/c", name, layout, system, kind, None)
                got = saves.target_dir("/c", name, layout, system, kind, "Core")
                tmpl = ra["saves"] if kind == "save" else ra["states"]
                want = os.path.join("/c", *ra["dir"].split("/"), *tmpl.format(
                    system=system["folders"][name], core="Core").split("/"))
                self.assertEqual(got, want)

    def test_retroarch_dir_override(self):
        got = saves.target_dir("/c", "onion", LAYOUTS["onion"], SYSTEMS[0], "state", "mGBA", retroarch_dir="/x")
        self.assertEqual(got, os.path.join("/x", "states", "mGBA"))

    def test_core_folders(self):
        with tempfile.TemporaryDirectory() as b:
            helpers.touch(os.path.join(b, "Saves/CurrentProfile/saves/gpSP/a.srm"), "x")
            helpers.touch(os.path.join(b, "Saves/CurrentProfile/states/mGBA/a.state"), "x")
            helpers.touch(os.path.join(b, "Saves/CurrentProfile/states/loose.state"), "x")
            self.assertEqual(saves.core_folders(b, LAYOUTS["onion"]), ["gpSP", "mGBA"])
            self.assertEqual(saves.core_folders(b, LAYOUTS["knulli"]), [])
            self.assertEqual(saves.core_folders(b, LAYOUTS["esde"]), [])


class PlanApplyTest(unittest.TestCase):
    def test_states(self):
        with tempfile.TemporaryDirectory() as b:
            src = os.path.join(b, "stash")
            files = {"G.srm": "a", "G.state": "b", "G.state.png": "c"}
            for n, c in files.items():
                helpers.touch(os.path.join(src, n), c)
            stash = {"dir": src, "system": "gba", "game": "G", "core": "mGBA",
                     "files": [{"name": n, "kind": saves.classify(n)[1]} for n in files]}
            card = os.path.join(b, "card")
            sd = os.path.join(card, "Saves/CurrentProfile/saves/mGBA")
            td = os.path.join(card, "Saves/CurrentProfile/states/mGBA")
            helpers.touch(os.path.join(sd, "G.srm"), "a")
            helpers.touch(os.path.join(td, "G.state"), "zzz")
            plan = saves.plan_apply(stash, card, "onion", LAYOUTS["onion"], SYSTEMS[0], "mGBA")
            self.assertEqual(plan, [
                (os.path.join(src, "G.srm"), os.path.join(sd, "G.srm"), "same"),
                (os.path.join(src, "G.state"), os.path.join(td, "G.state"), "differs"),
                (os.path.join(src, "G.state.png"), os.path.join(td, "G.state.png"), "new")])


class LayoutDataTest(unittest.TestCase):
    def test_every_layout_has_retroarch(self):
        for name, layout in LAYOUTS.items():
            self.assertEqual(set(layout["retroarch"]), {"dir", "saves", "states"}, name)


if __name__ == "__main__":
    unittest.main()
