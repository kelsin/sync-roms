import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import surprise  # noqa: E402

GBA = {"bucket": "gba", "bios": {"files": ["gba_bios.bin"]}}
IN = ["Super Mario Advance (USA, Europe).zip", "Castlevania - Aria of Sorrow (USA).zip",
      "Golden Sun (Europe) (En,Fr,De).zip", "Sonic Advance (Japan) (En,Ja).zip", "Tetris (World) (Rev 1).zip",
      "Final Fantasy Tactics Advance (USA, Australia).zip", "Pokemon Stadium (Australia).zip",
      "Hockey Night (Canada).zip", "Lemmings (UK).zip", "VitaShell.vpk", "Homebrew Game (2019).zip"]
OUT = ["Mother 3 (Japan).zip", "Rhythm Tengoku (Japan).zip", "Densetsu no Stafy (Japan) (Rev 1).zip",
       "Super Mario Bros. (Europe) (Fr,De).zip", "Star Fox 2 (Japan) (Proto).zip",
       "Pokemon - Ruby Version (USA) (Beta).zip", "Metroid Fusion (USA) (Demo) (Kiosk).zip",
       "Sonic Jam (Japan) (Sample).zip", "Action 52 (USA) (Unl).zip", "Street Fighter II (World) (Pirate).zip",
       "Zelda (USA) (Hack).zip", "Tetris (World) [h1].zip", "Tetris (World) [b2].zip", "[BIOS] Game Boy Advance (World).zip",
       "gba_bios.bin", "Kirby's Adventure (USA) (Virtual Console).zip", "Super Mario Bros. 3 (USA) (Switch Online).zip",
       "Castlevania (USA) (Castlevania Anniversary Collection).zip", "Mega Man 2 (USA) (Capcom Classics Mini Mix).zip",
       "Contra (USA) (Classic Mini).zip"]


class SurpriseRulesTest(unittest.TestCase):
    def test_full_english_names(self):
        bios = {"gba_bios.bin"}
        self.assertEqual([n for n in IN if not surprise.is_candidate("gba/" + n, GBA, None, bios)], [])
        self.assertEqual([n for n in OUT if surprise.is_candidate("gba/" + n, GBA, None, bios)], [])

    def test_unlisted_regions_are_not_english_and_more_rules(self):
        ok = lambda n: surprise.is_candidate("gba/" + n, GBA, None, set())
        for n in ("Game (Denmark).zip", "Game (Spain).zip", "Game (China).zip", "Game (Mexico, Portugal).zip"):
            self.assertFalse(ok(n), n)
        for n in ("Game (United Kingdom).zip", "Game (Europe, Netherlands).zip", "Game (Spain, UK).zip"):
            self.assertTrue(ok(n), n)
        self.assertFalse(ok("Game (USA)[Beta 2.1].zip"))
        self.assertTrue(ok("Game (USA) [!].zip"))
        self.assertFalse(ok("Game (USA) (QUByte Classics).zip"))

    def test_arcade_parents_only_and_not_japan(self):
        family = {"parents": {"10yard": "10-Yard Fight (World, set 1)", "armedf": "Armed F (Japan)",
                              "1943j2": "1943 Kai (Japan 900227)"},
                  "clones": {"10yardj": ["10yard", "10-Yard Fight (Japan)"]}}
        mame = {"bucket": "mame", "bios": {"files": []}}
        got = {k: surprise.is_candidate(f"mame/{k}.zip", mame, family, set())
               for k in ("10yard", "armedf", "1943j2", "10yardj", "neogeo")}
        self.assertEqual(got, {"10yard": True, "armedf": False, "1943j2": False, "10yardj": False, "neogeo": False})

    def test_multi_disc_game_is_one_unit_playlist_first(self):
        psx = {"bucket": "psx", "bios": {"files": []}}
        keys = {"psx/FF7 (USA) (Disc 1).chd", "psx/FF7 (USA) (Disc 2).chd", "psx/FF7 (USA).m3u",
                "psx/Spyro (USA).chd", "psx/Demo Disc (USA) (Demo).chd", "psx/sub/"}
        self.assertEqual(sorted(surprise.units(psx, keys, None, set())),
                         [["psx/FF7 (USA).m3u", "psx/FF7 (USA) (Disc 1).chd", "psx/FF7 (USA) (Disc 2).chd"],
                          ["psx/Spyro (USA).chd"]])


if __name__ == "__main__":
    unittest.main()
