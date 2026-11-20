import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import touch  # noqa: E402
from sync_roms import convert  # noqa: E402

LAYOUTS = {
    "knulli": {"roms_dir": "roms", "bios_dir": "bios"},
    "nextui": {"roms_dir": "Roms", "bios_dir": "Bios", "bios_by_tag": True, "disc_folders": True},
    "onion": {"roms_dir": "Roms", "bios_dir": "BIOS", "disc_dir": ".multi-disc"},
}
SYSTEMS = [
    {"bucket": "gba", "folders": {"knulli": "gba", "nextui": "Game Boy Advance (GBA)", "onion": "GBA"},
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


if __name__ == "__main__":
    unittest.main()
