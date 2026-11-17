import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from test_cardedit import DEVICE, GBA, Flow, g  # noqa: E402
from sync_roms import store  # noqa: E402
from sync_roms.cardpicks import CardPicks  # noqa: E402


def load_tests(loader, tests, pattern):
    """Only this file's tests: Flow's own run in test_cardedit."""
    return unittest.TestSuite(Picks(n) for n in vars(Picks) if n.startswith("test_"))


class Picks(Flow):
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

    def test_save_without_changes_returns_false(self):
        self.card(games={"gba": [g("gba/Zelda.zip")]})
        p = self.picks()
        p.system(GBA)
        self.assertFalse(p.save())

    def test_system_is_built_once_per_bucket(self):
        self.card()
        p = self.picks()
        self.assertIs(p.system(GBA), p.system(GBA))


if __name__ == "__main__":
    unittest.main()
