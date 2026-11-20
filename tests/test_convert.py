import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import touch  # noqa: E402
from sync_roms import convert  # noqa: E402

LAYOUTS = {
    "knulli": {"roms_dir": "roms", "bios_dir": "bios",
               "retroarch": {"dir": "saves", "saves": "{system}", "states": "{system}"}},
    "nextui": {"roms_dir": "Roms", "bios_dir": "Bios", "bios_by_tag": True, "disc_folders": True,
               "save_naming": "minui",
               "retroarch": {"dir": "", "saves": "Saves/{tag}", "states": ".userdata/shared/{tag}-{core}"}},
    "onion": {"roms_dir": "Roms", "bios_dir": "BIOS", "disc_dir": ".multi-disc"},
    "esde": {"roms_dir": "ROMs", "bios_dir": "BIOS",
             "retroarch": {"dir": "RetroArch", "saves": "saves/{core}", "states": "states/{core}"}},
}
SYSTEMS = [
    {"bucket": "gba", "folders": {"knulli": "gba", "nextui": "Game Boy Advance (GBA)", "onion": "GBA", "esde": "gba"},
     "nextui_bios_tags": ["MGBA"], "bios": {"files": ["gba_bios.bin"]}},
    {"bucket": "psx", "folders": {"knulli": "psx", "nextui": "PlayStation (PS)", "onion": "PS"},
     "bios": {"files": []}},
    {"bucket": "arcade", "folders": {"knulli": "mame", "nextui": None}, "bios": {"files": []}},
]
K, N, O = LAYOUTS["knulli"], LAYOUTS["nextui"], LAYOUTS["onion"]


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = os.path.realpath(self._tmp.name)

    def p(self, *parts):
        return os.path.join(self.base, *parts)

    def roms(self, old=("knulli", K), new=("nextui", N)):
        return convert.plan_roms(self.base, SYSTEMS, old[0], old[1], new[0], new[1])

    def bios(self, old=("knulli", K), new=("nextui", N)):
        return convert.plan_bios(self.base, SYSTEMS, old[0], old[1], new[0], new[1])

    def test_roms_move_to_new_folder(self):
        touch(self.p("roms", "gba", "Game.zip"))
        moves, skipped = self.roms()
        self.assertEqual(moves, [(self.p("roms", "gba", "Game.zip"), self.p("Roms", "Game Boy Advance (GBA)", "Game.zip"))])
        self.assertEqual(skipped, [])

    def test_disc_game_gets_its_own_folder(self):
        names = ["Game (Disc 1).cue", "Game (Disc 2).cue", "Game.m3u"]
        for n in names:
            touch(self.p("roms", "psx", n))
        moves, _ = self.roms()
        self.assertEqual(sorted(moves), sorted(
            (self.p("roms", "psx", n), self.p("Roms", "PlayStation (PS)", "Game", n)) for n in names))

    def test_disc_folders_flatten_when_leaving(self):
        names = ["Game (Disc 1).cue", "Game (Disc 2).cue", "Game.m3u"]
        for n in names:
            touch(self.p("Roms", "PlayStation (PS)", "Game", n))
        moves, _ = self.roms(("nextui", N), ("knulli", K))
        self.assertEqual(sorted(moves), sorted(
            (self.p("Roms", "PlayStation (PS)", "Game", n), self.p("roms", "psx", n)) for n in names))

    def test_system_without_new_folder_is_skipped(self):
        touch(self.p("roms", "mame", "x.zip"))
        moves, skipped = self.roms()
        self.assertEqual(moves, [])
        self.assertEqual([s[0] for s in skipped], ["arcade"])

    def test_bios_goes_into_tag_folder(self):
        touch(self.p("bios", "gba_bios.bin"))
        moves, skipped = self.bios()
        self.assertEqual(moves, [(self.p("bios", "gba_bios.bin"), self.p("Bios", "GBA", "gba_bios.bin"))])
        self.assertEqual(skipped, [("gba_bios.bin", "extra tag folder; sync will add it")])

    def test_dotfiles_ignored(self):
        for n in ("._x", ".DS_Store"):
            touch(self.p("roms", "gba", n))
            touch(self.p("bios", n))
        self.assertEqual(self.roms()[0], [])
        self.assertEqual(self.bios()[0], [])

    def test_playlist_paths_differ_is_reported_and_left(self):
        touch(self.p("roms", "psx", "Game.m3u"))
        moves, skipped = self.roms(("knulli", K), ("onion", O))
        self.assertEqual(moves, [])
        self.assertEqual(skipped[0][1], "playlist paths differ between layouts; sync rewrites it")

    def test_case_only_rename_is_a_move(self):
        touch(self.p("roms", "gba", "Game.zip"), b"abc")
        src, dst = self.p("roms", "gba", "Game.zip"), self.p("Roms", "gba", "Game.zip")
        done, conflicts = convert.apply_moves([(src, dst)])
        self.assertEqual((done, conflicts), ([(src, dst)], []))
        self.assertEqual(os.listdir(self.base), ["Roms"])
        self.assertEqual(os.listdir(self.p("Roms")), ["gba"])
        self.assertEqual(os.listdir(self.p("Roms", "gba")), ["Game.zip"])

    def test_existing_destination_is_a_conflict(self):
        src, dst = self.p("roms", "gba", "Game.zip"), self.p("Roms", "Game Boy Advance (GBA)", "Game.zip")
        touch(src, b"a")
        touch(dst, b"b")
        done, conflicts = convert.apply_moves([(src, dst)])
        self.assertEqual((done, conflicts), ([], [(src, dst)]))
        with open(src, "rb") as f:
            self.assertEqual(f.read(), b"a")

    def test_rerun_plans_nothing(self):
        touch(self.p("roms", "gba", "Game.zip"))
        touch(self.p("bios", "gba_bios.bin"))
        done, conflicts = convert.apply_moves(self.roms()[0] + self.bios()[0])
        self.assertEqual(len(done), 2)
        self.assertEqual(self.roms()[0], [])
        self.assertEqual(self.bios()[0], [])
        self.assertFalse(os.path.exists(self.p("roms", "gba")))

    def test_case_rename_to_missing_spelling_does_not_crash(self):
        src, dst = self.p("roms", "gba", "Game.zip"), self.p("Roms", "gba", "Game.zip")
        touch(src)
        real = os.path.samefile

        def same(a, b):
            if os.path.isdir(a):
                raise FileNotFoundError(b)
            return real(a, b)
        with mock.patch.object(convert.os.path, "samefile", side_effect=same):
            done, conflicts = convert.apply_moves([(src, dst)])
        self.assertEqual((done, conflicts), ([(src, dst)], []))
        self.assertTrue(os.path.exists(dst))

    def test_source_gone_is_not_a_crash(self):
        src, dst = self.p("roms", "gba", "Game.zip"), self.p("Roms", "x", "Game.zip")
        touch(dst)
        self.assertEqual(convert.apply_moves([(src, dst)]), ([], []))

    def test_real_subfolder_stays_and_game_folder_flattens(self):
        touch(self.p("Roms", "Game Boy Advance (GBA)", "Foo", "bar.zip"))
        for n in ("G (Disc 1).cue", "G (Disc 2).cue", "G.m3u"):
            touch(self.p("Roms", "PlayStation (PS)", "G", n))
        moves, _ = self.roms(("nextui", N), ("knulli", K))
        self.assertIn((self.p("Roms", "Game Boy Advance (GBA)", "Foo", "bar.zip"), self.p("roms", "gba", "Foo", "bar.zip")), moves)
        self.assertIn((self.p("Roms", "PlayStation (PS)", "G", "G.m3u"), self.p("roms", "psx", "G.m3u")), moves)

    def test_bios_with_a_path(self):
        systems = [{"bucket": "x", "folders": {"knulli": "x", "nextui": "X (X)"}, "bios": {"files": ["fbneo/neogeo.zip"]}}]
        touch(self.p("bios", "fbneo", "neogeo.zip"))
        moves, _ = convert.plan_bios(self.base, systems, "knulli", K, "nextui", N)
        self.assertEqual(moves, [(self.p("bios", "fbneo", "neogeo.zip"), self.p("Bios", "X", "fbneo", "neogeo.zip"))])
        done, _ = convert.apply_moves(moves)
        self.assertTrue(os.path.isfile(self.p("Bios", "X", "fbneo", "neogeo.zip")))

    def test_shared_rom_folder_moves_once(self):
        systems = [{"bucket": "a", "folders": {"knulli": "s", "nextui": "S (S)"}, "bios": {"files": []}},
                   {"bucket": "b", "folders": {"knulli": "s", "nextui": "S (S)"}, "bios": {"files": []}}]
        touch(self.p("roms", "s", "g.zip"))
        moves, _ = convert.plan_roms(self.base, systems, "knulli", K, "nextui", N)
        self.assertEqual(len(moves), 1)

    def test_shared_bios_tag_moves_once(self):
        systems = [{"bucket": "a", "folders": {"knulli": "a", "nextui": "A (T)"}, "bios": {"files": ["b.bin"]}},
                   {"bucket": "b", "folders": {"knulli": "b", "nextui": "B (T)"}, "bios": {"files": ["b.bin"]}}]
        touch(self.p("bios", "b.bin"))
        moves, _ = convert.plan_bios(self.base, systems, "knulli", K, "nextui", N)
        self.assertEqual(len(moves), 1)

    def test_dotfiles_in_game_folders_ignored(self):
        touch(self.p("Roms", "PlayStation (PS)", "G", "._G.m3u"))
        touch(self.p("Roms", "PlayStation (PS)", "G", ".DS_Store"))
        self.assertEqual(self.roms(("nextui", N), ("knulli", K))[0], [])

    def test_extra_old_bios_copies_are_reported(self):
        touch(self.p("Bios", "GBA", "gba_bios.bin"))
        touch(self.p("Bios", "MGBA", "gba_bios.bin"))
        moves, skipped = self.bios(("nextui", N), ("knulli", K))
        self.assertEqual(moves, [(self.p("Bios", "GBA", "gba_bios.bin"), self.p("bios", "gba_bios.bin"))])
        self.assertEqual(len(skipped), 1)
        self.assertIn("another copy", skipped[0][1])

    def saves(self, old=("knulli", K), new=("nextui", N), rom_moves=()):
        return convert.plan_saves(self.base, SYSTEMS, old[0], old[1], new[0], new[1], rom_moves)

    def test_knulli_save_to_nextui_gets_rom_name(self):
        touch(self.p("saves", "gba", "Game.srm"))
        touch(self.p("roms", "gba", "Game.gba"))
        rom_moves = self.roms()[0]
        moves, skipped = self.saves(rom_moves=rom_moves)
        self.assertEqual(moves, [(self.p("saves", "gba", "Game.srm"), self.p("Saves", "GBA", "Game.gba.sav"))])
        self.assertEqual(skipped, [])

    def test_knulli_state_has_no_core_for_nextui(self):
        touch(self.p("saves", "gba", "Game.srm"))
        touch(self.p("saves", "gba", "Game.state"))
        touch(self.p("roms", "gba", "Game.gba"))
        moves, skipped = self.saves(rom_moves=self.roms()[0])
        self.assertEqual(len(moves), 1)
        self.assertEqual(len(skipped), 1)
        self.assertIn("core", skipped[0][1])

    def test_save_without_rom_is_left_alone(self):
        touch(self.p("saves", "gba", "Game.srm"))
        self.assertEqual(self.saves(), ([], []))

    def test_nextui_to_esde_save_needs_a_core(self):
        touch(self.p("Saves", "GBA", "Game.gba.sav"))
        touch(self.p("Roms", "Game Boy Advance (GBA)", "Game.gba"))
        moves, skipped = self.saves(("nextui", N), ("esde", LAYOUTS["esde"]))
        self.assertEqual(moves, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("needs a core", skipped[0][1])

    def test_core_save_keeps_name_between_core_layouts(self):
        touch(self.p("RetroArch", "saves", "mGBA", "Game.srm"))
        touch(self.p("ROMs", "gba", "Game.gba"))
        esde = LAYOUTS["esde"]
        moves, _ = self.saves(("esde", esde), ("esde", esde))
        self.assertEqual(moves, [])

    def test_romless_save_left_alone_for_non_minui_target(self):
        touch(self.p("saves", "gba", "Game.srm"))
        self.assertEqual(self.saves(new=("esde", LAYOUTS["esde"])), ([], []))

    def test_esde_to_nextui_plans_with_rom_only_in_old_location(self):
        touch(self.p("RetroArch", "saves", "mGBA", "Game.srm"))
        touch(self.p("RetroArch", "states", "mGBA", "Game.state"))
        touch(self.p("ROMs", "gba", "Game.gba"))
        esde = LAYOUTS["esde"]
        rom_moves = self.roms(("esde", esde), ("nextui", N))[0]
        moves, skipped = self.saves(("esde", esde), ("nextui", N), rom_moves)
        self.assertEqual(sorted(moves), sorted([
            (self.p("RetroArch", "saves", "mGBA", "Game.srm"), self.p("Saves", "GBA", "Game.gba.sav")),
            (self.p("RetroArch", "states", "mGBA", "Game.state"),
             self.p(".userdata", "shared", "GBA-mGBA", "Game.state"))]))
        self.assertEqual(skipped, [])

    def test_nextui_to_esde_with_rom_only_in_old_location_needs_core_for_saves(self):
        touch(self.p("Saves", "GBA", "Game.gba.sav"))
        touch(self.p(".userdata", "shared", "GBA-mGBA", "Game.state"))
        touch(self.p("Roms", "Game Boy Advance (GBA)", "Game.gba"))
        esde = LAYOUTS["esde"]
        rom_moves = self.roms(("nextui", N), ("esde", esde))[0]
        moves, skipped = self.saves(("nextui", N), ("esde", esde), rom_moves)
        self.assertEqual(moves, [(self.p(".userdata", "shared", "GBA-mGBA", "Game.state"),
                                  self.p("RetroArch", "states", "mGBA", "Game.state"))])
        self.assertEqual(len(skipped), 1)
        self.assertIn("needs a core", skipped[0][1])

    def test_psx_save_keeps_srm_name_for_minui(self):
        touch(self.p("saves", "psx", "Game.srm"))
        touch(self.p("roms", "psx", "Game.cue"))
        moves, _ = self.saves(rom_moves=self.roms()[0])
        self.assertEqual(moves, [(self.p("saves", "psx", "Game.srm"), self.p("Saves", "PS", "Game.srm"))])

    def test_two_roms_sharing_a_stem_are_reported(self):
        touch(self.p("saves", "gba", "Game.srm"))
        touch(self.p("roms", "gba", "Game.gba"))
        touch(self.p("roms", "gba", "Game.zip"))
        moves, skipped = self.saves(rom_moves=self.roms()[0])
        self.assertEqual(moves, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("several ROMs", skipped[0][1])

    def test_apple_double_files_not_planned(self):
        touch(self.p("saves", "gba", "._Game.srm"))
        touch(self.p("roms", "gba", "Game.gba"))
        self.assertEqual(self.saves(rom_moves=self.roms()[0]), ([], []))


if __name__ == "__main__":
    unittest.main()


class ConvertCommandTest(unittest.TestCase):
    def setUp(self):
        import argparse
        import contextlib
        import io
        import json
        from sync_roms import store
        self.argparse, self.json, self.store = argparse, json, store
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = os.path.realpath(self._tmp.name)
        self.data = os.path.join(root, "data")
        os.makedirs(self.data)
        patch = mock.patch.object(store, "data_dir", lambda: self.data)
        patch.start()
        self.addCleanup(patch.stop)
        self.base = os.path.join(root, "SD")
        os.makedirs(self.base)
        self.set_card({"device": "anbernic-rg-sp", "layout": "knulli"})
        touch(os.path.join(self.base, "roms", "gba", "Game.zip"))
        self.out, self.err = io.StringIO(), io.StringIO()
        self.redirect = contextlib.redirect_stdout
        self.redirect_err = contextlib.redirect_stderr

    def set_card(self, entry):
        with open(os.path.join(self.data, "cards.json"), "w") as f:
            self.json.dump({"SD": entry} if entry is not None else {}, f)

    def layout(self):
        with open(os.path.join(self.data, "cards.json")) as f:
            return self.json.load(f)["SD"].get("layout")

    def run_cmd(self, layout="nextui", dry_run=False, yes=True, terminal=False):
        args = self.argparse.Namespace(card=self.base, layout=layout, dry_run=dry_run, yes=yes)
        with mock.patch("sync_roms.ui.has_terminal", return_value=terminal), self.redirect(self.out), self.redirect_err(self.err):
            try:
                return convert.convert_command(args)
            except SystemExit as e:
                return e.code

    def moved(self):
        return os.path.exists(os.path.join(self.base, "Roms", "Game Boy Advance (GBA)", "Game.zip"))

    def test_dry_run_moves_nothing_and_keeps_layout(self):
        self.assertEqual(self.run_cmd(dry_run=True, yes=False), 0)
        self.assertFalse(self.moved())
        self.assertTrue(os.path.exists(os.path.join(self.base, "roms", "gba", "Game.zip")))
        self.assertEqual(self.layout(), "knulli")
        self.assertIn("gba: 1 to move", self.out.getvalue())

    def test_convert_moves_files_and_saves_layout(self):
        self.assertEqual(self.run_cmd(), 0)
        self.assertTrue(self.moved())
        self.assertFalse(os.path.exists(os.path.join(self.base, "roms", "gba", "Game.zip")))
        self.assertEqual(self.layout(), "nextui")

    def test_save_follows_its_rom(self):
        touch(os.path.join(self.base, "saves", "gba", "Game.srm"))
        self.assertEqual(self.run_cmd(), 0)
        self.assertTrue(os.path.exists(os.path.join(self.base, "Saves", "GBA", "Game.zip.sav")))

    def test_unsupported_layout_fails(self):
        self.assertEqual(self.run_cmd(layout="windows-pc-nope"), 2)
        self.assertEqual(self.run_cmd(layout="onion"), 2)
        self.assertFalse(self.moved())
        self.assertEqual(self.layout(), "knulli")

    def test_unsaved_card_fails(self):
        self.set_card({})
        self.assertEqual(self.run_cmd(), 2)
        self.assertIn("cards set", self.err.getvalue())
        self.assertFalse(self.moved())

    def test_conflicts_reported_and_layout_still_saved(self):
        touch(os.path.join(self.base, "Roms", "Game Boy Advance (GBA)", "Game.zip"), b"other")
        self.assertEqual(self.run_cmd(), 0)
        self.assertIn("already exists", self.out.getvalue() + self.err.getvalue())
        self.assertTrue(os.path.exists(os.path.join(self.base, "roms", "gba", "Game.zip")))
        self.assertEqual(self.layout(), "nextui")

    def test_rerun_is_noop(self):
        self.run_cmd()
        self.out.truncate(0)
        self.out.seek(0)
        self.assertEqual(self.run_cmd(layout="nextui"), 0)
        self.assertIn("Nothing to move", self.out.getvalue())

    def test_no_yes_and_no_terminal_fails(self):
        self.assertEqual(self.run_cmd(yes=False), 2)
        self.assertFalse(self.moved())
