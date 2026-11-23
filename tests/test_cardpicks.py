import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from test_cardedit import DEVICE, GBA, Flow, g  # noqa: E402
from sync_roms import store  # noqa: E402
from sync_roms.cardpicks import CardPicks  # noqa: E402


def load_tests(loader, tests, pattern):
    """Only this file's tests: Flow's own run in test_cardedit."""
    return unittest.TestSuite(Picks(n) for n in vars(Picks) if n.startswith("test_"))


class Picks(Flow):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch("builtins.print"))  # without a storage cache, listing a folder says so

    def picks(self):
        return CardPicks("c", (DEVICE, "esde"))

    def switch(self, p, key, on):
        sp = p.system(GBA)
        notes = p.cover()
        sp.apply([key], notes, sp.states(notes), [on])

    def test_apply_on_adds_a_direct_pick_and_save_writes_it(self):
        self.card()
        p = self.picks()
        self.switch(p, "gba/Zelda.zip", True)
        self.assertTrue(p.save())
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")]})

    def test_off_on_a_set_reference_game_is_excluded(self):
        self.card(games={store.SETS_KEY: ["pk"]})
        p = self.picks()
        self.switch(p, "gba/Ruby.zip", False)
        self.assertTrue(p.save())
        self.assertEqual(store.card_excluded("c"), {"gba": ["gba/Ruby.zip"]})

    def test_one_pass_turning_several_games_on_and_off_keeps_the_card_order(self):
        self.card(games={"gba": [g("gba/Emerald.zip"), g("gba/Ruby.sav"), g("gba/Ruby.zip")]})
        p = self.picks()
        sp, notes = p.system(GBA), p.cover()
        keys = ["gba/Emerald.zip", "gba/Ruby.zip", "gba/Zelda.zip"]
        sp.apply(keys, notes, sp.states(notes), [False, False, True])
        self.assertEqual([x["bucket"] for x in sp.games], ["gba/Ruby.sav", "gba/Zelda.zip"])
        sp.apply(keys, notes, sp.states(notes), [True, False, True])
        self.assertEqual([x["bucket"] for x in sp.games], ["gba/Ruby.sav", "gba/Zelda.zip", "gba/Emerald.zip"])

    def test_save_without_changes_returns_false(self):
        self.card(games={"gba": [g("gba/Zelda.zip")]})
        p = self.picks()
        p.system(GBA)
        self.assertFalse(p.save())

    def keep(self, p, *keys):
        sp = p.system(GBA)
        return sp, sp.keep(list(keys), p.cover())

    def test_keep_picks_unpicked_keys(self):
        self.card()
        sp, n = self.keep(self.picks(), "gba/Emerald.zip", "gba/Zelda.zip")
        self.assertEqual(n, 2)
        self.assertEqual(sp.games, [g("gba/Emerald.zip"), g("gba/Zelda.zip")])

    def test_keep_skips_picked_and_set_covered(self):
        self.card(games={"gba": [g("gba/Zelda.zip")], store.SETS_KEY: ["pk"]})
        sp, n = self.keep(self.picks(), "gba/Zelda.zip", "gba/Ruby.zip")
        self.assertEqual(n, 0)
        self.assertEqual(sp.games, [g("gba/Zelda.zip")])

    def test_keep_ignores_keys_without_a_row(self):
        self.card()
        sp, n = self.keep(self.picks(), "gba/Emerald.zip", "gba/NoRow.zip")
        self.assertEqual((n, sp.games), (1, [g("gba/Emerald.zip")]))

    def test_keep_unexcludes(self):
        self.card(games={store.SETS_KEY: ["pk"]}, excluded={"gba": ["gba/Ruby.zip"]})
        sp, n = self.keep(self.picks(), "gba/Ruby.zip")
        self.assertEqual(n, 1)
        self.assertEqual((sp.excluded, sp.games), (set(), []))

    def test_keep_skips_locked(self):
        self.favs()
        self.card(collections=["favs"])
        sp, n = self.keep(self.picks(), "gba/Ruby.zip")
        self.assertEqual((n, sp.games), (0, []))

    def test_a_collection_game_on_a_system_not_shown_is_on_the_card(self):
        self.favs()
        self.card(collections=["favs"])
        p = self.picks()
        self.assertTrue(p.on_card("gb/Red.gb"))
        self.assertFalse(p.on_card("gb/Blue.gb"))
        p.toggle_variant(self.RED)
        self.assertFalse(p.save())
        self.assertEqual(store.card_games("c"), {})

    def test_off_on_a_collection_game_excludes_it(self):
        self.favs()
        self.card(collections=["favs"])
        p = self.picks()
        self.switch(p, "gba/Ruby.zip", False)
        self.assertTrue(p.save())
        self.assertEqual(store.card_excluded("c"), {"gba": ["gba/Ruby.zip"]})
        self.assertEqual(store.card_games("c"), {})

    def test_on_again_removes_the_exclusion_and_adds_no_pick(self):
        self.favs()
        self.card(collections=["favs"], excluded={"gba": ["gba/Ruby.zip"]})
        p = self.picks()
        self.assertFalse(p.system(GBA).states(p.cover())["gba/Ruby.zip"])
        self.switch(p, "gba/Ruby.zip", True)
        self.assertTrue(p.save())
        self.assertEqual(store.card_excluded("c"), {})
        self.assertEqual(store.card_games("c"), {})

    def test_keep_switches_an_excluded_collection_game_back_on(self):
        self.favs()
        self.card(collections=["favs"], excluded={"gba": ["gba/Ruby.zip"]})
        sp, n = self.keep(self.picks(), "gba/Ruby.zip")
        self.assertEqual(n, 1)
        self.assertEqual((sp.games, sp.excluded), ([], set()))

    def test_on_card_of_an_excluded_collection_game_on_a_system_not_shown_is_false(self):
        self.favs()
        self.card(collections=["favs"], excluded={"gb": ["gb/Red.gb"]})
        self.assertFalse(self.picks().on_card("gb/Red.gb"))

    def test_surprise_rows_stay_on_and_untouched_by_apply(self):
        self.card(surprises=[{"system": "gba", "bucket": "gba/Zelda.zip", "title": "Zelda"}])
        p = self.picks()
        sp = p.system(GBA)
        self.assertEqual(sp.surprise, {"gba/Zelda.zip"})
        self.switch(p, "gba/Zelda.zip", False)
        self.assertEqual((sp.games, sp.excluded), ([], set()))
        self.assertTrue(sp.states(p.cover())["gba/Zelda.zip"])

    def test_a_surprise_that_is_also_an_excluded_collection_game_stays_on(self):
        self.favs()
        self.card(collections=["favs"], excluded={"gba": ["gba/Ruby.zip"]},
                  surprises=[{"system": "gba", "bucket": "gba/Ruby.zip", "title": "Ruby"}])
        p = self.picks()
        sp = p.system(GBA)
        self.assertIn("gba/Ruby.zip", sp.surprise)
        self.assertNotIn("gba/Ruby.zip", sp.collected)
        self.assertTrue(sp.states(p.cover())["gba/Ruby.zip"])
        self.switch(p, "gba/Ruby.zip", False)
        self.assertEqual((sp.games, sp.excluded), ([], {"gba/Ruby.zip"}))
        self.assertTrue(sp.states(p.cover())["gba/Ruby.zip"])

    def test_on_card_of_a_surprise_that_is_also_an_excluded_collection_game_is_true(self):
        self.favs()
        self.card(collections=["favs"], excluded={"gb": ["gb/Red.gb"]},
                  surprises=[{"system": "gb", "bucket": "gb/Red.gb", "title": "Red"}])
        self.assertTrue(self.picks().on_card("gb/Red.gb"))

    def test_a_surprise_game_on_a_system_not_shown_is_on_the_card(self):
        self.card(surprises=[{"title": "Red", "system": "gb", "bucket": "gb/Red.gb"}])
        p = self.picks()
        self.assertTrue(p.on_card("gb/Red.gb"))
        p.toggle_variant(self.RED)
        self.assertFalse(p.save())

    def test_system_is_built_once_per_bucket(self):
        self.card()
        p = self.picks()
        self.assertIs(p.system(GBA), p.system(GBA))


if __name__ == "__main__":
    unittest.main()
