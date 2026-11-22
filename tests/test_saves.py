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
from sync_roms import commands, picker, saves, store, ui  # noqa: E402

LAYOUTS = store.repo_json("layouts")
SYSTEMS = [{"bucket": "gba", "folders": {"onion": "GBA", "knulli": "gba", "esde": "gba", "allium": "GBA",
                                         "spruce": "GBA", "emudeck": "gba", "rocknix": "gba", "nextui": "Game Boy Advance (GBA)"}},
           {"bucket": "gb", "folders": {"onion": "GB", "knulli": "gb", "esde": "gb", "allium": "GB",
                                        "spruce": "GB", "emudeck": "gb", "rocknix": "gb"}},
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


    def test_rtc_is_a_save(self):
        self.assertEqual(saves.classify("Crystal.rtc"), ("Crystal", "save"))

    def test_appledouble_and_empty_stems(self):
        for n in ("._Game.srm", "._Game.state", "._Game.state.png", "._Game.rtc", ".srm", ".rtc", "..srm", ".state"):
            self.assertIsNone(saves.classify(n), n)


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())

    def p(self, *a):
        return os.path.join(self.base, *a)

    def test_onion(self):
        helpers.touch(self.p("Roms", "GBA", "Game.zip"), "r")
        helpers.touch(self.p("Saves/CurrentProfile/saves/gpSP/Game.srm"), "abc")
        helpers.touch(self.p("Saves/CurrentProfile/states/gpSP/Game.state.auto"), "s")
        helpers.touch(self.p("Saves/CurrentProfile/states/gpSP/Game.state.auto.png"), "p")
        helpers.touch(self.p("Saves/CurrentProfile/saves/Other.srm"), "x")
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

    def test_loose_in_core_parent(self):
        helpers.touch(self.p("Roms", "GBA", "Game.zip"), "r")
        helpers.touch(self.p("Saves/CurrentProfile/saves/Game.srm"), "s")
        helpers.touch(self.p("Saves/CurrentProfile/saves/gpSP/Game.srm"), "t")
        games, skipped = saves.scan(self.base, "onion", LAYOUTS["onion"], SYSTEMS)
        self.assertEqual(skipped, 0)
        self.assertEqual(sorted(str(x["core"]) for x in games[("gba", "Game")]), ["None", "gpSP"])

    def test_shared_rom_folder(self):
        systems = SYSTEMS + [{"bucket": "ngp", "folders": {"onion": "NGP"}}, {"bucket": "ngpc", "folders": {"onion": "NGP"}}]
        helpers.touch(self.p("Roms", "NGP", "Game.zip"), "r")
        helpers.touch(self.p("Saves/CurrentProfile/saves/NeoCD/Game.srm"), "s")
        games, skipped = saves.scan(self.base, "onion", LAYOUTS["onion"], systems)
        self.assertEqual((list(games), skipped), ([("ngp", "Game")], 0))

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

    def test_rocknix_saves_beside_rom_and_states_in_savestates(self):
        helpers.touch(self.p("roms", "gba", "Game.zip"), "r")
        helpers.touch(self.p("roms/gba/Game.srm"), "s")
        helpers.touch(self.p("roms/savestates/gba/Game.state"), "t")
        helpers.touch(self.p("roms/savestates/gba/Game.state.png"), "p")
        helpers.touch(self.p("roms/gba/notes.txt"), "x")
        games, skipped = saves.scan(self.base, "rocknix", LAYOUTS["rocknix"], SYSTEMS)
        self.assertEqual(list(games), [("gba", "Game")])
        self.assertEqual(skipped, 0)
        self.assertEqual(sorted(x["kind"] for x in games[("gba", "Game")]), ["save", "state", "thumbnail"])
        self.assertEqual({x["path"] for x in games[("gba", "Game")] if x["kind"] == "save"}, {self.p("roms/gba/Game.srm")})

    def test_rocknix_stem_in_two_systems_goes_by_folder(self):
        for f in ("gba", "gb"):
            helpers.touch(self.p("roms", f, "Game.zip"), "r")
        helpers.touch(self.p("roms/gba/Game.srm"), "a")
        helpers.touch(self.p("roms/savestates/gb/Game.state"), "b")
        games, skipped = saves.scan(self.base, "rocknix", LAYOUTS["rocknix"], SYSTEMS)
        self.assertEqual(sorted(games), [("gb", "Game"), ("gba", "Game")])
        self.assertEqual(skipped, 0)

    def test_rocknix_save_with_no_rom_skipped(self):
        helpers.touch(self.p("roms", "gba", "Game.zip"), "r")
        helpers.touch(self.p("roms/gba/Orphan.srm"), "s")
        helpers.touch(self.p("roms/savestates/gba/Orphan.state"), "s")
        games, skipped = saves.scan(self.base, "rocknix", LAYOUTS["rocknix"], SYSTEMS)
        self.assertEqual((games, skipped), ({}, 2))

    def test_rocknix_roms_folder_is_not_a_broken_link(self):
        os.makedirs(self.p("roms/gba"))
        self.assertEqual(saves.broken_links(self.base, LAYOUTS["rocknix"]), [])
        helpers.touch(self.p("roms/savestates"), "file")
        self.assertEqual(saves.broken_links(self.base, LAYOUTS["rocknix"]), [self.p("roms/savestates")])

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

    def test_nextui_shared_tag_folder_by_rom(self):
        systems = [{"bucket": "neogeo", "folders": {"nextui": "Neo Geo (FBN)"}},
                   {"bucket": "cps2", "folders": {"nextui": "CPS2 (FBN)"}},
                   {"bucket": "gba", "folders": {"nextui": "Game Boy Advance (GBA)"}}]
        helpers.touch(self.p("Roms", "CPS2 (FBN)", "sf2.zip"), "r")
        helpers.touch(self.p("Roms", "Neo Geo (FBN)", "mslug.zip"), "r")
        helpers.touch(self.p("Roms", "Neo Geo (FBN)", ".media", "art.png"), "r")
        helpers.touch(self.p("Saves", "FBN", "sf2.zip.sav"), "s")
        helpers.touch(self.p("Saves", "FBN", "mslug.zip.sav"), "s")
        helpers.touch(self.p("Saves", "FBN", "art.zip.sav"), "s")
        helpers.touch(self.p(".userdata", "shared", "FBN-fbneo", "sf2.zip.state"), "s")
        helpers.touch(self.p("Saves", "GBA", "Game.gba.sav"), "s")
        games, skipped = saves.scan(self.base, "nextui", LAYOUTS["nextui"], systems)
        self.assertEqual(sorted(games), [("cps2", "sf2"), ("cps2", "sf2.zip"), ("gba", "Game"), ("neogeo", "mslug")])
        self.assertEqual([e["kind"] for e in games[("cps2", "sf2.zip")]], ["state"])
        self.assertEqual(skipped, 1)

    def test_nextui_shared_tag_folder_stem_in_two_systems_skipped(self):
        systems = [{"bucket": "neogeo", "folders": {"nextui": "Neo Geo (FBN)"}},
                   {"bucket": "cps2", "folders": {"nextui": "CPS2 (FBN)"}}]
        helpers.touch(self.p("Roms", "CPS2 (FBN)", "game.zip"), "r")
        helpers.touch(self.p("Roms", "Neo Geo (FBN)", "game.zip"), "r")
        helpers.touch(self.p("Saves", "FBN", "game.zip.sav"), "s")
        games, skipped = saves.scan(self.base, "nextui", LAYOUTS["nextui"], systems)
        self.assertEqual((games, skipped), ({}, 1))

    def test_appledouble_rom_skipped(self):
        helpers.touch(self.p("Roms", "GBA", "._Game.zip"), "r")
        self.assertEqual(saves.rom_stems(self.base, "onion", LAYOUTS["onion"], SYSTEMS), {})

    def test_unreadable_folder_warned_and_skipped(self):
        helpers.touch(self.p("Roms", "GBA", "Game.zip"), "r")
        helpers.touch(self.p("Saves/CurrentProfile/saves/gpSP/Game.srm"), "s")
        real = os.listdir

        def fake(path="."):
            if str(path).endswith("gpSP"):
                raise OSError(5, "Input/output error")
            return real(path)
        with mock.patch.object(os, "listdir", fake), mock.patch.object(ui, "warn") as warn:
            games, _ = saves.scan(self.base, "onion", LAYOUTS["onion"], SYSTEMS)
        self.assertEqual(games, {})
        self.assertIn("gpSP", warn.call_args[0][0])

    def test_broken_links(self):
        ra = self.p("Emulation/saves/retroarch")
        os.makedirs(ra)
        self.assertEqual(saves.broken_links(self.base, LAYOUTS["emudeck"]), [])
        os.symlink(self.p("nowhere"), os.path.join(ra, "saves"))
        helpers.touch(os.path.join(ra, "states"), "file")
        self.assertEqual(saves.broken_links(self.base, LAYOUTS["emudeck"]),
                         [os.path.join(ra, "saves"), os.path.join(ra, "states")])
        self.assertEqual(saves.broken_links(self.base, LAYOUTS["emudeck"], retroarch_dir=self.p("x")), [])

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
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        import datetime
        self.enterContext(mock.patch.object(store, "data_dir", return_value=os.path.join(self.tmp, "data")))
        self.now = datetime.datetime(2026, 11, 18, 10, 2, 3)

    def entries(self):
        a = os.path.join(self.tmp, "src", "Game.srm")
        b = os.path.join(self.tmp, "src", "Game.state.auto")
        helpers.touch(a, "save")
        helpers.touch(b, "state")
        return [{"path": a, "name": "Game.srm", "kind": "save", "core": "gpSP", "size": 4, "mtime": 0},
                {"path": b, "name": "Game.state.auto", "kind": "state", "core": "gpSP", "size": 5, "mtime": 0}]

    def meta(self, d):
        with open(os.path.join(d, "stash.json")) as f:
            return json.load(f)

    def test_round_trip(self):
        d = saves.write_stash("SHARE", "onion", "gba", "Game", "gpSP", self.entries(), now=self.now)
        self.assertEqual(d, os.path.join(saves.stash_root(), "gba", "Game", "20261118-100203-SHARE"))
        with open(os.path.join(d, "Game.srm")) as f:
            self.assertEqual(f.read(), "save")
        meta = self.meta(d)
        self.assertEqual(meta, {"system": "gba", "game": "Game", "card": "SHARE", "layout": "onion",
                                "core": "gpSP", "stashed": "2026-11-18T10:02:03",
                                "files": [{"name": "Game.srm", "kind": "save"},
                                          {"name": "Game.state.auto", "kind": "state"}]})
        out = saves.load_stashes()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["dir"], d)
        self.assertEqual(out[0]["game"], "Game")

    def test_rel_and_core_kept_when_present(self):
        e = [dict(x, rel="GBA/Hacks") for x in self.entries()]
        d = saves.write_stash("MU", "muos", "gba", "Game", "gpSP", e, now=self.now)
        meta = self.meta(d)
        self.assertEqual(meta["files"], [{"name": "Game.srm", "kind": "save", "rel": "GBA/Hacks", "core": "gpSP"},
                                         {"name": "Game.state.auto", "kind": "state", "rel": "GBA/Hacks",
                                          "core": "gpSP"}])
        self.assertEqual(saves.load_stashes()[0]["files"], meta["files"])

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

    def test_load_skips_unsafe(self):
        d = saves.write_stash("A", "onion", "gba", "Good", None, self.entries(), now=self.now)
        with open(os.path.join(d, "stash.json")) as f:
            good = json.load(f)
        for i, change in enumerate(({"files": [{"name": "../x.srm", "kind": "save"}]},
                                    {"files": [{"name": "a/b.srm", "kind": "save"}]},
                                    {"game": 5}, {"system": None}, {"stashed": 1},
                                    {"files": [{"name": "a.srm", "kind": "save", "rel": "../x"}]},
                                    {"files": [{"name": "a.srm", "kind": "save", "rel": "/x"}]},
                                    {"files": [{"name": "a.srm", "kind": "save", "rel": 5}]},
                                    {"core": None, "files": [{"name": "a.srm", "kind": "save", "rel": "x"}]},
                                    {"core": "../c", "files": [{"name": "a.srm", "kind": "save", "rel": "x"}]},
                                    {"game": "..", "files": [{"name": "a.srm", "kind": "save", "rel": "x"}]})):
            helpers.touch(os.path.join(saves.stash_root(), "gba", f"bad{i}", "stash.json"),
                          json.dumps({**good, **change}))
        self.assertEqual([s["game"] for s in saves.load_stashes()], ["Good"])


class TargetTest(unittest.TestCase):
    def test_every_layout(self):
        system = SYSTEMS[0]
        for name, layout in LAYOUTS.items():
            if "retroarch" not in layout:
                continue
            ra = layout["retroarch"]
            for kind in ("save", "state", "thumbnail"):
                if "{core}" in (ra["saves"] if kind == "save" else ra["states"]):
                    with self.assertRaises(ValueError):
                        saves.target_dir("/c", name, layout, system, kind, None)
                got = saves.target_dir("/c", name, layout, system, kind, "Core")
                tmpl = ra["saves"] if kind == "save" else ra["states"]
                want = os.path.join("/c", *ra["dir"].split("/"), *tmpl.format(
                    system=system["folders"][name], core="Core", tag=store.folder_tag(system["folders"][name])).split("/"))
                self.assertEqual(got, want)

    def test_tag_template(self):
        layout = {"retroarch": {"dir": "", "saves": "Saves/{tag}", "states": ".userdata/shared/{tag}-{core}"}}
        system = {"folders": {"nextui": "Game Boy (GB)"}}
        self.assertEqual(saves.target_dir("/c", "nextui", layout, system, "save", None), "/c/Saves/GB")
        self.assertEqual(saves.target_dir("/c", "nextui", layout, system, "state", "gambatte"),
                         "/c/.userdata/shared/GB-gambatte")
        with self.assertRaises(ValueError):
            saves.target_dir("/c", "nextui", layout, {"folders": {"nextui": None}}, "save", None)
        with self.assertRaises(ValueError):
            saves.target_dir("/c", "nextui", layout, {"folders": {"nextui": "ARCADE"}}, "save", None)

    def test_tag_folders_scanned_once_per_folder(self):
        systems = [{"bucket": "gb", "folders": {"nextui": "Game Boy (GB)"}},
                   {"bucket": "gbc", "folders": {"nextui": "Game Boy Color (GBC)"}},
                   {"bucket": "x", "folders": {"nextui": None}}]
        got = saves._folders("/c", "Saves/{tag}", systems, "nextui")
        self.assertEqual(got, [("/c/Saves/GB", "gb", None), ("/c/Saves/GBC", "gbc", None)])

    def test_empty_core_is_the_parent(self):
        got = saves.target_dir("/c", "onion", LAYOUTS["onion"], SYSTEMS[0], "save", "")
        self.assertEqual(got, os.path.join("/c", "Saves", "CurrentProfile", "saves"))

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
            if "pickles" in layout:  # muOS: Pickles saves, not RetroArch
                self.assertEqual(set(layout["pickles"]), {"dir"}, name)
                continue
            self.assertEqual(set(layout["retroarch"]) - {"create"}, {"dir", "saves", "states"}, name)


class BesideRomsTest(unittest.TestCase):
    """ROCKNIX keeps RetroArch saves beside the ROMs: sync never offers them for deletion."""
    NAMES = ("Game.gba", "Game.srm", "Old.gba", "Old.srm", "Old.state1", "Old.state1.png", "Old.rtc")

    def setUp(self):
        self.dest = self.enterContext(tempfile.TemporaryDirectory())
        for name in self.NAMES:
            helpers.touch(os.path.join(self.dest, name))

    def test_only_rocknix_keeps_saves_beside_the_roms(self):
        self.assertEqual([n for n, layout in LAYOUTS.items() if saves.beside_roms(layout)], ["rocknix"])

    def test_saves_beside_kept_and_removed_roms_are_never_extras(self):
        from sync_roms import downloads
        self.assertEqual(downloads.find_extras(self.dest, ["gba/Game.gba"], skip_saves=True),
                         [os.path.join(self.dest, "Old.gba")])

    def test_other_layouts_still_offer_stray_saves(self):
        from sync_roms import downloads
        self.assertEqual(sorted(os.path.basename(p) for p in downloads.find_extras(self.dest, ["gba/Game.gba"])),
                         sorted(n for n in self.NAMES if n != "Game.gba"))


CATALOG_SYSTEMS = [
    {"name": "Game Boy Advance", "bucket": "gba",
     "folders": {"onion": "GBA", "knulli": "gba", "esde": "gba", "allium": "GBA", "emudeck": "gba",
                 "rocknix": "gba", "nextui": "Game Boy Advance (GBA)", "spruce": "GBA"}},
    {"name": "PlayStation", "bucket": "psx", "folders": {"nextui": "PlayStation (PS)"}},
    {"name": "Neo Geo Pocket", "bucket": "ngp", "folders": {"onion": "NGP", "knulli": "ngp"}},
    {"name": "Neo Geo Pocket Color", "bucket": "ngpc", "folders": {"onion": "NGP", "knulli": "ngpc"}},
]


class SessionFree:
    """picker.one_app runs its function in place (no Textual app) while has_terminal is true."""
    def run(self, fn, args, kwargs):
        return fn(*args, **kwargs)


class CommandTest(helpers.Cmd):
    def setUp(self):
        super().setUp()
        self.cards_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.cards_dir.cleanup)
        catalog = {"layouts": LAYOUTS, "systems": CATALOG_SYSTEMS, "devices": []}
        for p in (mock.patch.object(store, "load_catalog", lambda: catalog),
                  mock.patch.object(ui, "has_terminal", lambda: True),
                  mock.patch.object(picker, "_Session", SessionFree)):
            self.enterContext(p)
        self.cards = {}
        self.calls = []

    def card(self, name, layout, device="full"):
        self.cards[name] = {"device": device, "layout": layout}
        helpers.write_json(self.path("cards.json"), self.cards)
        base = os.path.join(self.cards_dir.name, name)
        os.makedirs(base, exist_ok=True)
        return base

    def lists(self, *answers):
        """picker.filter_list answers in turn: a value, or a callable(labels) giving one; calls are kept."""
        it = iter(answers)

        def fake(title, labels, multi=False, **kw):
            self.calls.append((title, list(labels), kw))
            a = next(it)
            return a(labels) if callable(a) else a
        self.enterContext(mock.patch.object(picker, "filter_list", fake))

    def read_file(self, *parts):
        with open(os.path.join(*parts)) as f:
            return f.read()

    def onion_card(self):
        base = self.card("SHARE", "onion")
        helpers.touch(os.path.join(base, "Roms/GBA/Game.zip"), "r")
        helpers.touch(os.path.join(base, "Roms/GBA/Other.zip"), "r")
        helpers.touch(os.path.join(base, "Saves/CurrentProfile/saves/gpSP/Game.srm"), "save")
        helpers.touch(os.path.join(base, "Saves/CurrentProfile/states/gpSP/Game.state.auto"), "state")
        helpers.touch(os.path.join(base, "Saves/CurrentProfile/states/gpSP/Game.state.auto.png"), "png")
        helpers.touch(os.path.join(base, "Saves/CurrentProfile/saves/mGBA/Other.srm"), "other")
        return base

    def stash(self, core="gpSP", game="Game", system="gba", card="SHARE", layout="onion", files=None):
        tmp = os.path.join(self.cards_dir.name, "src", system, game)
        entries = []
        for name, data in (files or {f"{game}.srm": "save", f"{game}.state.auto": "state"}).items():
            helpers.touch(os.path.join(tmp, name), data)
            entries.append({"path": os.path.join(tmp, name), "name": name, "kind": saves.classify(name)[1]})
        return saves.write_stash(card, layout, system, game, core, entries)


class NamingTest(unittest.TestCase):
    def test_minui_name(self):
        self.assertEqual(saves.minui_name("Game.srm", ["Game.gba", "Other.gba"]), "Game.gba.sav")
        self.assertIsNone(saves.minui_name("Missing.srm", ["Game.gba"]))
        self.assertEqual(saves.minui_name("Mr. Driller.srm", ["Mr. Driller.gba"]), "Mr. Driller.gba.sav")

    def test_minui_name_picks_the_right_rom(self):
        self.assertEqual(saves.minui_name("Game.srm", ["Game.bin", "Game.cue"]), "Game.cue.sav")
        self.assertEqual(saves.minui_name("Game.srm", ["Game.cue", "Game.bin", "Game.m3u"]), "Game.m3u.sav")
        self.assertIsNone(saves.minui_name("Game.srm", ["Game.gba", "Game.zip"]))

    def test_rom_names_skip_dot_entries(self):
        with tempfile.TemporaryDirectory() as b:
            for n in (".media/Game.png", "Game.gba", ".hidden", "._Game.gba", "sub/Other.gba", "sub/.media/Other.png"):
                helpers.touch(os.path.join(b, "Roms/GBA", n), "x")
            layout = {"roms_dir": "Roms"}
            got = saves.rom_names(b, "n", layout, {"folders": {"n": "GBA"}})
            self.assertEqual(sorted(got), ["Game.gba", "Other.gba"])

    def test_retroarch_name(self):
        self.assertEqual(saves.retroarch_name("Game.gba.sav"), "Game.srm")
        self.assertEqual(saves.retroarch_name("Mr. Driller.gba.sav"), "Mr. Driller.srm")
        self.assertEqual(saves.retroarch_name("Game.sav"), "Game.srm")

    def test_nextui_state_folders_scanned(self):
        with tempfile.TemporaryDirectory() as b:
            helpers.touch(os.path.join(b, ".userdata/shared/GBA-mgba/Game.state"), "s")
            helpers.touch(os.path.join(b, ".userdata/shared/GBC-x/Other.state"), "s")
            systems = [{"bucket": "gba", "folders": {"nextui": "Game Boy Advance (GBA)"}}]
            got = saves._folders(b, ".userdata/shared/{tag}-{core}", systems, "nextui")
            self.assertEqual(got, [(os.path.join(b, ".userdata/shared/GBA-mgba"), "gba", "mgba")])
            self.assertEqual(saves.core_folders(b, LAYOUTS["nextui"]), [])


class StashCommandTest(CommandTest):
    def test_nextui_sav_becomes_srm(self):
        base = self.card("NX", "nextui")
        helpers.touch(os.path.join(base, "Roms/Game Boy Advance (GBA)/Game.gba"), "r")
        helpers.touch(os.path.join(base, "Saves/GBA/Game.gba.sav"), "save")
        helpers.touch(os.path.join(base, ".userdata/shared/GBA-mgba/Game.gba.state"), "st")
        self.lists([True, True], lambda labels: [True] * len(labels))
        code, out, err = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 0, err)
        by_core = {s["core"]: s for s in saves.load_stashes()}
        self.assertEqual(sorted(by_core, key=str), [None, "mgba"])
        self.assertEqual(self.read_file(by_core[None]["dir"], "Game.srm"), "save")
        self.assertEqual(by_core[None]["system"], "gba")

    def test_stash_end_to_end(self):
        base = self.onion_card()
        self.lists([True, False], lambda labels: [True] * len(labels))
        code, out, err = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 0, err)
        title, labels, kw = self.calls[0]
        self.assertEqual(labels, ["Game", "Other"])
        self.assertEqual(kw["initial"], [False, False])
        self.assertEqual([t for t, _ in kw["extras"][0]], ["Game Boy Advance", "1 save · 1 state", "gpSP"])
        _, files, kw = self.calls[1]
        self.assertEqual(files, ["Game · Game.srm", "Game · Game.state.auto", "Game · Game.state.auto.png"])
        self.assertEqual(kw["initial"], [True, True, True])
        self.assertEqual([t for t, _ in kw["extras"][2]][0], "thumbnail")
        self.assertEqual(kw["extras"][0][-1][0], "gpSP")
        [stash] = saves.load_stashes()
        self.assertEqual((stash["card"], stash["layout"], stash["core"], stash["game"]), ("SHARE", "onion", "gpSP", "Game"))
        self.assertEqual(sorted(os.listdir(stash["dir"])),
                         ["Game.srm", "Game.state.auto", "Game.state.auto.png", "stash.json"])
        self.assertIn(f"Stashed 3 file(s) of 1 game(s) to {saves.stash_root()}", out)
        self.assertIn("gpSP", out.split("Stashed", 1)[1])

    def test_one_stash_per_core(self):
        base = self.onion_card()
        helpers.touch(os.path.join(base, "Saves/CurrentProfile/states/Game.state"), "loose")
        self.lists([True, False], lambda labels: [True] * len(labels))
        code, out, err = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(str(s["core"]) for s in saves.load_stashes()), ["None", "gpSP"])
        self.assertIn("the core they were made with", out)

    def test_nothing_chosen(self):
        base = self.onion_card()
        self.lists(None)
        code, out, _ = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 0)
        self.assertIn("Nothing stashed", out)
        self.assertFalse(os.path.exists(saves.stash_root()))

    def test_dry_run_writes_nothing(self):
        base = self.onion_card()
        self.lists([True, True], lambda labels: [True] * len(labels))
        code, out, err = self.run_cmd("saves", "stash", base, "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("Would stash 4 file(s) of 2 game(s)", out)
        self.assertFalse(os.path.exists(saves.stash_root()))

    def test_broken_link_warned(self):
        base = self.card("DECK", "emudeck")
        os.makedirs(os.path.join(base, "Emulation/saves/retroarch"))
        os.symlink("/nonexistent/saves", os.path.join(base, "Emulation/saves/retroarch/saves"))
        code, out, err = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 0)
        self.assertIn("--retroarch", err)
        self.assertIn("No RetroArch saves", out)

    def test_no_saves(self):
        base = self.card("EMPTY", "onion")
        code, out, _ = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 0)
        self.assertIn("No RetroArch saves", out)

    def test_unknown_card(self):
        base = os.path.join(self.cards_dir.name, "NOPE")
        os.makedirs(base)
        code, _, err = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 2)
        self.assertIn("NOPE", err)

    def test_card_without_layout(self):
        self.cards["BARE"] = {"device": "full"}
        helpers.write_json(self.path("cards.json"), self.cards)
        os.makedirs(os.path.join(self.cards_dir.name, "BARE"))
        code, _, err = self.run_cmd("saves", "apply", os.path.join(self.cards_dir.name, "BARE"))
        self.assertEqual(code, 2)
        self.assertIn("sync-roms cards set BARE --layout", err)

    def test_needs_terminal(self):
        base = self.onion_card()
        with mock.patch.object(ui, "has_terminal", lambda: False):
            code, _, err = self.run_cmd("saves", "stash", base)
        self.assertEqual(code, 2)
        self.assertIn("`saves stash` needs a terminal to pick from", err)

    def test_missing_folder_is_reported_before_the_terminal(self):
        base = self.onion_card()
        os.rename(base, base + "-gone")
        with mock.patch.object(ui, "has_terminal", lambda: False):
            code, _, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 2)
        self.assertIn(f"No folder {base}", err)
        self.assertNotIn("needs a terminal", err)

    def test_retroarch_flag(self):
        base = self.card("PHONE", "esde")
        helpers.touch(os.path.join(base, "ROMs/gba/Game.zip"), "r")
        ra = os.path.join(self.cards_dir.name, "copy")
        helpers.touch(os.path.join(ra, "saves/mGBA/Game.srm"), "s")
        self.lists([True], [True])
        code, out, err = self.run_cmd("saves", "stash", base, "--retroarch", ra)
        self.assertEqual(code, 0, err)
        self.assertEqual(saves.load_stashes()[0]["core"], "mGBA")


class ApplyCommandTest(CommandTest):
    def test_stash_and_apply_round_trip_on_a_muos_card(self):
        catalog = {"layouts": LAYOUTS, "systems": [dict(s, folders=dict(s["folders"], muos=s["bucket"]))
                                                   for s in CATALOG_SYSTEMS], "devices": []}
        p = mock.patch.object(store, "load_catalog", lambda: catalog)
        p.start()
        self.addCleanup(p.stop)
        old = self.card("MU", "muos")
        pk = os.path.join(old, "MUOS", "pickles")
        helpers.touch(os.path.join(old, "ROMS/GBA/Hacks/Game.zip"), "r")
        helpers.touch(os.path.join(pk, "sram/mGBA/GBA/Hacks/Game.srm"), "save")
        helpers.touch(os.path.join(pk, "state/mGBA/GBA/Hacks/Game/slot_1.state"), "slot")
        helpers.touch(os.path.join(pk, "state/mGBA/GBA/Hacks/Game/states.ini"), "ini")
        helpers.touch(os.path.join(pk, "sram/mGBA/Nope/Lost.srm"), "x")
        self.lists([True], lambda labels: [True] * len(labels))
        code, out, err = self.run_cmd("saves", "stash", old)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls[1][1], ["Game · GBA/Hacks/Game.srm", "Game · GBA/Hacks/slot_1.state",
                                            "Game · GBA/Hacks/states.ini"])
        self.assertIn("Stashed 3 file(s) of 1 game(s)", out)
        self.assertIn("skipped 1 file", out)
        [stash] = saves.load_stashes()
        self.assertEqual((stash["layout"], stash["core"]), ("muos", "mGBA"))
        self.assertEqual({(f["rel"], f["core"]) for f in stash["files"]}, {("GBA/Hacks", "mGBA")})
        self.stash()  # a RetroArch stash never goes onto a muOS card
        new = self.card("MU2", "muos")
        helpers.touch(os.path.join(new, "MUOS/pickles/state/mGBA/GBA/Hacks/Game/states.ini"), "other")
        self.calls.clear()
        self.lists([True])
        with mock.patch.object(ui, "confirm", return_value=False) as confirm:
            code, out, err = self.run_cmd("saves", "apply", new)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls[0][1], ["Game · GBA/Hacks"])
        self.assertIn("states.ini", confirm.call_args[0][0] + out)
        pk = os.path.join(new, "MUOS", "pickles")
        self.assertEqual(self.read_file(pk, "sram/mGBA/GBA/Hacks/Game.srm"), "save")
        self.assertEqual(self.read_file(pk, "state/mGBA/GBA/Hacks/Game/slot_1.state"), "slot")
        self.assertEqual(self.read_file(pk, "state/mGBA/GBA/Hacks/Game/states.ini"), "other")
        self.assertIn("Applied 2 file(s) of 1 game(s) to MU2", out)
        self.assertIn("1 different file(s) kept", out)

    def muos_catalog(self):
        catalog = {"layouts": LAYOUTS, "systems": [dict(s, folders=dict(s["folders"], muos=s["bucket"]))
                                                   for s in CATALOG_SYSTEMS], "devices": []}
        self.enterContext(mock.patch.object(store, "load_catalog", lambda: catalog))

    def test_same_stem_in_sibling_rom_dirs_stays_apart(self):
        self.muos_catalog()
        old = self.card("MU", "muos")
        pk = os.path.join(old, "MUOS", "pickles")
        for rel, data in (("GBA", "orig"), ("GBA/Hacks", "hack")):
            helpers.touch(os.path.join(pk, "sram/mGBA", rel, "Game.srm"), f"{data}-save")
            helpers.touch(os.path.join(pk, "state/mGBA", rel, "Game/slot_1.state"), f"{data}-slot")
            helpers.touch(os.path.join(pk, "state/mGBA", rel, "Game/states.ini"), f"{data}-ini")
        self.lists([True], lambda labels: [True] * len(labels))
        code, out, err = self.run_cmd("saves", "stash", old)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(set(self.calls[1][1])), 6)
        self.assertIn("Stashed 6 file(s) of 2 game(s)", out)
        stashes = saves.load_stashes()
        self.assertEqual(sorted({f["rel"] for f in s["files"]}.pop() for s in stashes), ["GBA", "GBA/Hacks"])
        self.assertTrue(all(len({f["rel"] for f in s["files"]}) == 1 for s in stashes))
        new = self.card("MU2", "muos")
        self.calls.clear()
        self.lists(lambda labels: [True] * len(labels))
        code, out, err = self.run_cmd("saves", "apply", new)
        self.assertEqual(code, 0, err)
        self.assertNotIn("one stash per game", out)
        pk = os.path.join(new, "MUOS", "pickles")
        for rel, data in (("GBA", "orig"), ("GBA/Hacks", "hack")):
            self.assertEqual(self.read_file(pk, "sram/mGBA", rel, "Game.srm"), f"{data}-save")
            self.assertEqual(self.read_file(pk, "state/mGBA", rel, "Game/slot_1.state"), f"{data}-slot")
            self.assertEqual(self.read_file(pk, "state/mGBA", rel, "Game/states.ini"), f"{data}-ini")
        self.assertIn("Applied 6 file(s) of 2 game(s) to MU2", out)

    def test_retroarch_flag_warned_on_muos(self):
        self.muos_catalog()
        base = self.card("MU", "muos")
        code, _, err = self.run_cmd("saves", "stash", base, "--retroarch", base)
        self.assertEqual(code, 0)
        self.assertIn("--retroarch is ignored on muOS cards", err)

    def test_muos_stash_never_goes_onto_a_retroarch_card(self):
        tmp = os.path.join(self.cards_dir.name, "src", "slot_1.state")
        helpers.touch(tmp, "slot")
        saves.write_stash("MU", "muos", "gba", "Game", "mGBA",
                          [{"path": tmp, "name": "slot_1.state", "kind": "state", "core": "mGBA", "rel": "gba"}])
        base = self.card("NEW", "knulli")
        self.lists(lambda labels: self.fail(f"offered {labels}"))
        code, out, _ = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0)
        self.assertIn("No stashed saves", out)

    def nextui_card(self, rom="Game.gba", folder="Game Boy Advance (GBA)"):
        base = self.card("NX", "nextui")
        if rom:
            helpers.touch(os.path.join(base, "Roms", folder, rom), "r")
        return base

    def test_onto_nextui_renames(self):
        self.stash(files={"Game.srm": "save"})
        base = self.nextui_card()
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(base, "Saves/GBA/Game.gba.sav"), "save")
        self.assertFalse(os.path.exists(os.path.join(base, "Saves/GBA/Game.srm")))

    def test_onto_nextui_no_rom_keeps_name_and_warns(self):
        self.stash(files={"Game.srm": "save"})
        base = self.nextui_card(rom=None)
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(base, "Saves/GBA/Game.srm"), "save")
        self.assertIn("no ROM on the card for Game.srm", err)

    def test_onto_nextui_media_art_ignored(self):
        self.stash(files={"Game.srm": "save"})
        base = self.nextui_card()
        helpers.touch(os.path.join(base, "Roms/Game Boy Advance (GBA)/.media/Game.png"), "p")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(base, "Saves/GBA/Game.gba.sav"), "save")

    def test_onto_nextui_ambiguous_keeps_srm_and_warns(self):
        self.stash(files={"Game.srm": "save"})
        base = self.nextui_card()
        helpers.touch(os.path.join(base, "Roms/Game Boy Advance (GBA)/Game.zip"), "r")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(base, "Saves/GBA/Game.srm"), "save")
        self.assertIn("several ROMs share the name of Game.srm", err)

    def test_onto_nextui_psx_not_renamed(self):
        self.stash(system="psx", files={"Game.srm": "save"})
        base = self.nextui_card(rom="Game.cue", folder="PlayStation (PS)")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(base, "Saves/PS/Game.srm"), "save")

    def test_onto_nextui_save_needs_no_core(self):
        self.stash(core=None, files={"Game.srm": "save"})
        base = self.nextui_card()
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", "--yes", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(base, "Saves/GBA/Game.gba.sav"), "save")

    def test_onto_nextui_state_without_core_skipped_not_literal_tag(self):
        self.stash(core=None, files={"Game.state": "st"})
        base = self.nextui_card()
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", "--yes", base)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(os.path.join(base, ".userdata")))

    def test_broken_link_fails_before_copying(self):
        self.stash(files={"Game.srm": "save"})
        base = self.card("DECK", "emudeck")
        helpers.touch(os.path.join(base, "Emulation/roms/gba/Game.zip"), "r")
        os.makedirs(os.path.join(base, "Emulation/saves/retroarch"))
        os.symlink("/nonexistent/saves", os.path.join(base, "Emulation/saves/retroarch/saves"))
        self.lists([True])
        code, _, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 2)
        self.assertIn("--retroarch", err)
        self.assertFalse(os.path.lexists(os.path.join(base, "Emulation/saves/retroarch/states")))

    def test_missing_stash_file_skipped(self):
        d = self.stash()
        os.remove(os.path.join(d, "Game.state.auto"))
        base = self.card("NEW", "knulli")
        helpers.touch(os.path.join(base, "roms/gba/Game.zip"), "r")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertIn("Game.state.auto", err)
        self.assertEqual(self.read_file(base, "saves/gba/Game.srm"), "save")
        self.assertFalse(os.path.exists(os.path.join(base, "saves/gba/Game.state.auto")))

    def test_onto_knulli(self):
        self.stash()
        base = self.card("NEW", "knulli")
        helpers.touch(os.path.join(base, "roms/gba/Game.zip"), "r")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        _, labels, kw = self.calls[0]
        self.assertEqual(labels, ["Game"])
        shown = [t for t, _ in kw["extras"][0]]
        self.assertEqual(shown[:2], ["Game Boy Advance", "from SHARE"])
        self.assertEqual(shown[3:], ["1 save · 1 state", "gpSP", ""])
        self.assertEqual(self.read_file(base, "saves/gba/Game.srm"), "save")
        self.assertEqual(self.read_file(base, "saves/gba/Game.state.auto"), "state")
        self.assertIn("Applied 2 file(s) of 1 game(s) to NEW", out)
        self.assertIn("gpSP", out.split("Applied", 1)[1])

    def test_rocknix_stash_and_apply_round_trip(self):
        src = self.card("RX", "rocknix")
        helpers.touch(os.path.join(src, "roms/gba/Game.zip"), "r")
        helpers.touch(os.path.join(src, "roms/gba/Game.srm"), "save")
        helpers.touch(os.path.join(src, "roms/savestates/gba/Game.state"), "state")
        helpers.touch(os.path.join(src, "roms/gba/Orphan.srm"), "x")
        all_on = lambda labels: [True] * len(labels)  # noqa: E731
        self.lists(all_on, all_on)
        code, out, err = self.run_cmd("saves", "stash", src)
        self.assertEqual(code, 0, err)
        self.assertIn("Stashed 2 file(s) of 1 game(s)", out)
        self.assertIn("skipped 1 file", out)
        new = self.card("RX2", "rocknix")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", new)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(new, "roms/gba/Game.srm"), "save")
        self.assertEqual(self.read_file(new, "roms/savestates/gba/Game.state"), "state")
        self.assertFalse(os.path.exists(os.path.join(new, "roms/gba/Game.zip")))

    def test_spruce_stash_and_apply_round_trip(self):
        src = self.card("SP", "spruce")
        helpers.touch(os.path.join(src, "Roms/GBA/Game.zip"), "r")
        helpers.touch(os.path.join(src, "Saves/saves/gpSP/Game.srm"), "save")
        helpers.touch(os.path.join(src, "Saves/states/gpSP/Game.state.auto"), "state")
        all_on = lambda labels: [True] * len(labels)  # noqa: E731
        self.lists(all_on, all_on)
        code, out, err = self.run_cmd("saves", "stash", src)
        self.assertEqual(code, 0, err)
        self.assertIn("Stashed 2 file(s) of 1 game(s)", out)
        new = self.card("SP2", "spruce")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", new)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(new, "Saves/saves/gpSP/Game.srm"), "save")
        self.assertEqual(self.read_file(new, "Saves/states/gpSP/Game.state.auto"), "state")

    def test_onto_esde_reuses_core(self):
        self.stash()
        base = self.card("PHONE", "esde")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls[0][2]["extras"][0][-1], ("not on card", "red"))
        self.assertEqual(self.read_file(base, "RetroArch/states/gpSP/Game.state.auto"), "state")
        self.assertEqual(self.read_file(base, "RetroArch/saves/gpSP/Game.srm"), "save")

    def test_differing_declined_keeps_old(self):
        self.stash()
        base = self.card("PHONE", "esde")
        helpers.touch(os.path.join(base, "RetroArch/saves/gpSP/Game.srm"), "old")
        self.lists([True])
        with mock.patch.object(ui, "confirm", return_value=False) as confirm:
            code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(confirm.call_args.kwargs.get("default"), False)
        self.assertEqual(self.read_file(base, "RetroArch/saves/gpSP/Game.srm"), "old")
        self.assertEqual(self.read_file(base, "RetroArch/states/gpSP/Game.state.auto"), "state")
        self.assertIn("Applied 1 file(s) of 1 game(s)", out)

    def test_differing_confirmed_and_same_skipped(self):
        self.stash()
        base = self.card("PHONE", "esde")
        helpers.touch(os.path.join(base, "RetroArch/saves/gpSP/Game.srm"), "old")
        helpers.touch(os.path.join(base, "RetroArch/states/gpSP/Game.state.auto"), "state")
        self.lists([True])
        with mock.patch.object(ui, "confirm", return_value=True):
            code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_file(base, "RetroArch/saves/gpSP/Game.srm"), "save")
        self.assertIn("Applied 1 file(s) of 1 game(s)", out)
        self.assertIn("1 identical", out)

    def test_dry_run_writes_nothing(self):
        self.stash()
        base = self.card("NEW", "knulli")
        self.lists([True])
        with mock.patch.object(ui, "confirm", side_effect=AssertionError("asked")):
            code, out, err = self.run_cmd("saves", "apply", base, "-n")
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(os.path.join(base, "saves")))
        self.assertIn("Would apply 2 file(s) of 1 game(s) to NEW", out)

    def test_nothing_chosen(self):
        self.stash()
        base = self.card("NEW", "knulli")
        self.lists(None)
        code, out, _ = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0)
        self.assertIn("Nothing applied", out)

    def test_no_stashes_for_card(self):
        self.stash(system="ngp", game="Pocket")
        base = self.card("PHONE", "esde")  # esde has no ngp folder in these systems
        code, out, _ = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0)
        self.assertIn("No stashed saves", out)

    def test_device_filters_systems(self):
        self.stash()
        catalog = {"layouts": LAYOUTS, "systems": CATALOG_SYSTEMS,
                   "devices": [{"id": "dev", "firmwares": ["knulli"], "systems": ["ngp"]}]}
        base = self.card("NEW", "knulli", device="dev")
        with mock.patch.object(store, "load_catalog", lambda: catalog):
            code, out, _ = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0)
        self.assertIn("No stashed saves", out)

    def test_shared_rom_folder_resolves_to_target_rom(self):
        self.stash(system="ngp", game="Pocket", core="RACE")
        base = self.card("NEW", "knulli")
        helpers.touch(os.path.join(base, "roms/ngpc/Pocket.zip"), "r")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls[0][2]["extras"][0][0][0], "Neo Geo Pocket Color")
        self.assertEqual(self.read_file(base, "saves/ngpc/Pocket.srm"), "save")

    def test_two_stashes_of_one_game_reopens(self):
        import datetime
        self.stash()
        tmp = os.path.join(self.cards_dir.name, "src2", "Game.srm")
        helpers.touch(tmp, "newer")
        saves.write_stash("OTHER", "onion", "gba", "Game", "gpSP", [{"path": tmp, "name": "Game.srm", "kind": "save"}],
                          now=datetime.datetime.now() + datetime.timedelta(minutes=5))
        base = self.card("NEW", "knulli")
        self.lists([True, True], [True, False])
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.calls), 2)
        self.assertIn("one stash per game", out)
        self.assertEqual(self.calls[0][2]["extras"][0][1][0], "from OTHER")  # newest first
        self.assertEqual(self.read_file(base, "saves/gba/Game.srm"), "newer")

    def test_core_asked_once_per_system(self):
        self.stash(core=None, card="KN", layout="knulli")
        self.stash(core=None, game="Other", card="KN", layout="knulli")
        base = self.card("SHARE", "onion")
        os.makedirs(os.path.join(base, "Saves/CurrentProfile/states/gpSP"))
        self.lists([True, True], 0)
        code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1][1], ["gpSP", "Type a name…", "No core folder (sort by core off)"])
        self.assertEqual(self.read_file(base, "Saves/CurrentProfile/saves/gpSP/Other.srm"), "save")
        self.assertEqual(self.read_file(base, "Saves/CurrentProfile/states/gpSP/Game.state.auto"), "state")
        self.assertIn("the core they were made with", out)

    def test_core_typed_or_none(self):
        self.stash(core=None, card="KN", layout="knulli")
        base = self.card("SHARE", "onion")
        self.lists([True], 0)  # no core folders yet: Type a name…, No core folder
        with mock.patch.object(ui, "ask", return_value=" mGBA "):
            code, out, err = self.run_cmd("saves", "apply", base)
        self.assertEqual(code, 0, err + out)
        self.assertTrue(os.path.exists(os.path.join(base, "Saves/CurrentProfile/saves/mGBA/Game.srm")))
        self.calls.clear()
        other = self.card("TWO", "onion")
        self.lists([True], 1)
        code, out, err = self.run_cmd("saves", "apply", other)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(os.path.join(other, "Saves/CurrentProfile/saves/Game.srm")))

    def test_core_unknown_with_yes_skips(self):
        self.stash(core=None, card="KN", layout="knulli")
        base = self.card("SHARE", "onion")
        self.lists([True])
        code, out, err = self.run_cmd("saves", "apply", base, "--yes")
        self.assertEqual(code, 0, err)
        self.assertIn("Skipped", err + out)
        self.assertFalse(os.path.exists(os.path.join(base, "Saves")))


class SavesCliTest(unittest.TestCase):
    def test_completion_and_words(self):
        self.assertEqual(commands.second_words()["saves"], ["stash", "apply"])
        self.assertIn("saves", helpers.script_for("bash"))
        self.assertIn("--retroarch", commands.all_flags())
        from sync_roms import cli
        self.assertIn("saves", cli.SUBCOMMANDS)
        self.assertIn("sync-roms saves stash", cli.TOPICS["saves"])
        self.assertIn("saves", commands.COMMANDS)


if __name__ == "__main__":
    unittest.main()
