import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import languages  # noqa: E402


class LanguagesTest(unittest.TestCase):
    def test_english_language_tag(self):
        self.assertIs(languages.english("Golden Sun (Europe) (En,Fr,De)"), True)
        self.assertIs(languages.english("Super Mario Bros. (Europe) (Fr,De)"), False)

    def test_english_region(self):
        self.assertIs(languages.english("Mother 3 (Japan)"), False)
        self.assertIs(languages.english("Lemmings (UK)"), True)
        self.assertIsNone(languages.english("Homebrew Game (2019)"))

    def test_english_translation(self):
        self.assertIs(languages.english("Mother 3 (Japan) [T-En by Chewy v1.3]"), True)
        self.assertIs(languages.english("Game (Japan) (Ja) [T-En by X]"), True)

    def test_flag(self):
        for key, want in (("gba/Mother 3 (Japan).zip", "\U0001F1EF\U0001F1F5"),
                          ("gba/Golden Sun (Europe) (En,Fr,De).zip", "\U0001F1FA\U0001F1F8"),
                          ("gba/Super Mario Bros. (Europe) (Fr,De).zip", "\U0001F1EB\U0001F1F7"),
                          ("gba/Game (Japan, Korea).zip", "\U0001F1EF\U0001F1F5"),
                          ("gba/Mother 3 (Japan) [T-En by Chewy].zip", "\U0001F1FA\U0001F1F8")):
            self.assertEqual(languages.flag(key), want, key)

    def test_flag_unrecognised_groups_blank(self):
        for key in ("gba/Tetris (Rev 1).zip", "gba/VitaShell.vpk", "gba/Game (Unknown).zip"):
            self.assertEqual(languages.flag(key), "", key)

    def test_flag_arcade_uses_scraped_title(self):
        with mock.patch.object(languages.names, "title", return_value="Armed F (Japan)"):
            self.assertEqual(languages.flag("mame/armedf.zip"), "\U0001F1EF\U0001F1F5")
        with mock.patch.object(languages.names, "title", return_value="10-Yard Fight (World, set 1)"):
            self.assertEqual(languages.flag("mame/10yard.zip"), "")

    def test_column(self):
        self.assertEqual(languages.column("gba/Mother 3 (Japan).zip"), ("  \U0001F1EF\U0001F1F5", "dim"))
        self.assertEqual(languages.column("gba/VitaShell.vpk"), ("", "dim"))

    def test_every_flag_mapped_region_is_a_region(self):
        self.assertLessEqual(set(languages.REGION_FLAGS), languages.REGIONS)
        self.assertEqual(set(languages.REGIONS) - set(languages.REGION_FLAGS) - languages.ENGLISH_REGIONS, {"Unknown"})


if __name__ == "__main__":
    unittest.main()
