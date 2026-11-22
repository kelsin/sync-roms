import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import touch  # noqa: E402
from sync_roms import nextui_folders  # noqa: E402

SNES_OLD, SNES_NEW = "Super Nintendo (SFC)", "Super Nintendo Entertainment System (SFC)"


class MigrateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.roms = os.path.join(tmp.name, "Roms")

    def test_an_old_folder_is_renamed_with_its_contents(self):
        touch(os.path.join(self.roms, SNES_OLD, "game.sfc"))
        touch(os.path.join(self.roms, SNES_OLD, ".media", "game.png"))
        self.assertEqual(nextui_folders.migrate(self.roms, False), [(SNES_OLD, SNES_NEW)])
        self.assertEqual(os.listdir(self.roms), [SNES_NEW])
        self.assertTrue(os.path.exists(os.path.join(self.roms, SNES_NEW, "game.sfc")))
        self.assertTrue(os.path.exists(os.path.join(self.roms, SNES_NEW, ".media", "game.png")))

    def test_a_case_only_rename_changes_the_name_on_disk(self):
        touch(os.path.join(self.roms, "PICO-8 (P8)", "a.p8.png"))
        nextui_folders.migrate(self.roms, False)
        self.assertEqual(os.listdir(self.roms), ["Pico-8 (P8)"])

    def test_the_new_name_is_nfc(self):
        touch(os.path.join(self.roms, "Pokemon Mini (PKM)", "a.min"))
        nextui_folders.migrate(self.roms, False)
        self.assertEqual(os.listdir(self.roms), ["Pokémon mini (PKM)"])

    def test_both_folders_present_are_left_alone(self):
        touch(os.path.join(self.roms, SNES_OLD, "a.sfc"))
        touch(os.path.join(self.roms, SNES_NEW, "b.sfc"))
        self.assertEqual(nextui_folders.migrate(self.roms, False), [])
        self.assertEqual(sorted(os.listdir(self.roms)), sorted([SNES_NEW, SNES_OLD]))

    def test_dry_run_changes_nothing(self):
        touch(os.path.join(self.roms, SNES_OLD, "a.sfc"))
        self.assertEqual(nextui_folders.migrate(self.roms, True), [(SNES_OLD, SNES_NEW)])
        self.assertEqual(os.listdir(self.roms), [SNES_OLD])

    def test_no_roms_folder(self):
        self.assertEqual(nextui_folders.migrate(self.roms, False), [])


if __name__ == "__main__":
    unittest.main()
