import collections
import os
import random
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
        for n in ("Game (Denmark).zip", "Game (Spain).zip", "Game (China).zip", "Game (Mexico, Portugal).zip",
                  "Game (Ukraine).zip", "Game (Thailand).zip"):
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


def pool(system, n):
    return [[f"{system}/G{i} (USA).zip"] for i in range(n)]


def count(picked):
    return collections.Counter(p["system"] for p in picked)


class SurprisePickTest(unittest.TestCase):
    def test_seven_three_split_counts_kept(self):
        pools = {s: pool(s, 20) for s in "abcd"}
        kept = [{"system": "a", "bucket": "a/K1.zip", "title": "K1"},
                {"system": "a", "bucket": "a/K2.zip", "title": "K2"},
                {"system": "c", "bucket": "c/K3.zip", "title": "K3"}]
        got = count(surprise.pick(pools, kept, 7, {"a", "b"}, set(), set(), random.Random(1)))
        self.assertEqual(got["a"] + got["b"], 5)
        self.assertEqual(got["c"] + got["d"], 2)
        self.assertEqual(sum(got.values()), 7)

    def test_full_ten_is_seven_three_spread_evenly(self):
        pools = {s: pool(s, 20) for s in "abcde"}
        got = count(surprise.pick(pools, [], 10, {"a", "b", "c"}, set(), set(), random.Random(2)))
        self.assertEqual(sorted(got[s] for s in "abc"), [2, 2, 3])
        self.assertEqual(sorted(got[s] for s in "de"), [1, 2])

    def test_recommended_system_with_few_candidates_passes_slots_on(self):
        pools = {"a": pool("a", 2), "b": pool("b", 20), "c": pool("c", 20)}
        got = count(surprise.pick(pools, [], 10, {"a"}, set(), set(), random.Random(3)))
        self.assertEqual(got["a"], 2)
        self.assertEqual(got["b"] + got["c"], 8)
        self.assertEqual(sorted((got["b"], got["c"])), [4, 4])

    def test_two_systems_both_recommended_split_five_five(self):
        pools = {"a": pool("a", 20), "b": pool("b", 20)}
        got = count(surprise.pick(pools, [], 10, {"a", "b"}, set(), set(), random.Random(4)))
        self.assertEqual(got, {"a": 5, "b": 5})

    def test_no_recommended_systems_gives_all_slots_to_the_others(self):
        got = count(surprise.pick({"a": pool("a", 20)}, [], 10, set(), set(), set(), random.Random(5)))
        self.assertEqual(got, {"a": 10})

    def test_multi_disc_game_takes_one_slot(self):
        disc = ["p/FF7 (USA).m3u", "p/FF7 (USA) (Disc 1).chd", "p/FF7 (USA) (Disc 2).chd"]
        got = surprise.pick({"p": [disc, ["p/Spyro (USA).chd"]]}, [], 10, set(), set(), set(), random.Random(6))
        self.assertEqual(len(got), 2)
        ff7 = next(x for x in got if x["bucket"] == "p/FF7 (USA).m3u")
        self.assertEqual(ff7, {"system": "p", "bucket": "p/FF7 (USA).m3u", "title": "FF7 (USA)", "files": disc[1:]})
        self.assertNotIn("files", next(x for x in got if x["bucket"] == "p/Spyro (USA).chd"))

    def test_best_tier_first(self):
        units = [["a/Fresh.zip"], ["a/Past.zip"], ["a/Other.zip"]]
        for seed in range(20):
            got1 = surprise.pick({"a": units}, [], 1, set(), {"a/Past.zip"}, {"a/Other.zip"}, random.Random(seed))
            got2 = surprise.pick({"a": units}, [], 2, set(), {"a/Past.zip"}, {"a/Other.zip"}, random.Random(seed))
            got3 = surprise.pick({"a": units}, [], 3, set(), {"a/Past.zip"}, {"a/Other.zip"}, random.Random(seed))
            self.assertEqual([x["bucket"] for x in got1], ["a/Fresh.zip"])
            self.assertEqual({x["bucket"] for x in got2}, {"a/Fresh.zip", "a/Past.zip"})
            self.assertEqual(len(got3), 3)

    def test_need_zero_picks_nothing(self):
        self.assertEqual(surprise.pick({"a": pool("a", 5)}, [], 0, {"a"}, set(), set(), random.Random(0)), [])

    def test_every_system_runs_out_returns_what_there_is(self):
        got = surprise.pick({"a": pool("a", 2), "b": pool("b", 1), "c": []}, [], 10, {"a"}, set(), set(),
                            random.Random(7))
        self.assertEqual(count(got), {"a": 2, "b": 1})
        self.assertEqual(surprise.pick({}, [], 10, set(), set(), set(), random.Random(7)), [])


if __name__ == "__main__":
    unittest.main()
