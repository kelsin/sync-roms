import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardedit, edit, languages  # noqa: E402


class LanguagesTest(unittest.TestCase):
    def test_english_language_tag(self):
        self.assertIs(languages.english("Golden Sun (Europe) (En,Fr,De)"), True)
        self.assertIs(languages.english("Super Mario Bros. (Europe) (Fr,De)"), False)

    def test_translated(self):
        self.assertTrue(languages.translated("gba/Mother 3 [T-En by X].gba"))
        self.assertFalse(languages.translated("gba/Mother 3 (Japan).gba"))
        self.assertFalse(languages.translated("snes/Super Mario World (USA).zip"))

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

    def test_flag_regional_beats_language_tag_when_not_english(self):
        for key, want in (("gba/G (Brazil) (Pt).zip", "\U0001F1E7\U0001F1F7"),
                          ("gba/G (Taiwan) (Zh-Hant).zip", "\U0001F1F9\U0001F1FC"),
                          ("gba/G (Switzerland) (De,Fr).zip", "\U0001F1E8\U0001F1ED"),
                          ("gba/G (USA) (Es).zip", "\U0001F1EA\U0001F1F8"),
                          ("gba/G (Europe) (Fr,De).zip", "\U0001F1EB\U0001F1F7")):
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


class EditorColumnsTest(unittest.TestCase):
    def test_row_extras_flag_column(self):
        sp = types.SimpleNamespace(bucket="gba", groups={}, bundled={}, locked_from={}, surprise=set(), in_storage=set())
        work = {"costs": {"gba": {"gba/Mother 3 (Japan).zip": 2048}}}
        out = cardedit._row_extras(sp, work, "gba/Mother 3 (Japan).zip")
        self.assertEqual(out[2], ("  \U0001F1EF\U0001F1F5", "dim"))
        self.assertEqual(out[3], ("  " + cardedit.size_text(2048), "dim"))
        out = cardedit._row_extras(sp, work, "gba/VitaShell.vpk")
        self.assertEqual(out[2], ("", "dim"))
        self.assertEqual(len(out), 4)

    def test_full_system_row_flag_extras(self):
        key = "psx/Parappa (Japan).zip"
        system = {"bucket": "psx"}
        picks = types.SimpleNamespace()
        seen = {}

        def fake(title, labels, **kw):
            seen.update(kw)
            return kw["initial"]
        with mock.patch.object(cardedit.picker, "filter_list", fake), \
                mock.patch.object(cardedit.previews, "game_pane", return_value={}):
            cardedit._games_pass("t", [(system, key, "Parappa", "Parappa")], picks, {}, {}, {key: True}, {}, None,
                                 None, {})
        self.assertEqual(seen["extras"], [[("", "dim")] * 2 + [("  \U0001F1EF\U0001F1F5", "dim"), ("", "")]])

    def test_variant_picker_flag_extras(self):
        picks = types.SimpleNamespace(
            variants={"gba/A.zip": [{"bucket": "gba/A (Japan).zip", "note": "x"}, {"bucket": "gba/A (USA).zip", "note": "y"}]},
            on_card=lambda b: False)
        seen = {}

        def fake(title, labels, **kw):
            seen.update(kw)
            return None
        with mock.patch.object(cardedit.picker, "filter_list", fake):
            cardedit._toggle_variant(picks, "gba/A.zip", "A")
        self.assertEqual(seen["extras"], [[("  \U0001F1EF\U0001F1F5", "dim"), ("", "")], [("  \U0001F1FA\U0001F1F8", "dim"), ("", "")]])

    def test_toggle_games_flag_extras(self):
        system = {"bucket": "gba", "games": [{"bucket": "gba/Mother 3 (Japan).zip"}]}
        rows = [(system, "gba/Mother 3 (Japan).zip", "Mother 3", "Mother 3")]
        seen = {}

        def fake(title, labels, **kw):
            seen.update(kw)
            return kw["initial"]
        with mock.patch.object(edit.picker, "filter_list", fake):
            edit.toggle_games("t", rows)
        self.assertEqual([e[2:] for e in seen["extras"]], [[("  \U0001F1EF\U0001F1F5", "dim"), ("", "")]])  # after System, Year


if __name__ == "__main__":
    unittest.main()
