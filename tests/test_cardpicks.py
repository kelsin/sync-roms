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
        p = mock.patch("builtins.print")  # without a storage cache, listing a folder says so
        p.start()
        self.addCleanup(p.stop)

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

    def test_system_is_built_once_per_bucket(self):
        self.card()
        p = self.picks()
        self.assertIs(p.system(GBA), p.system(GBA))


if __name__ == "__main__":
    unittest.main()
