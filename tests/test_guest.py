import os
import tempfile
import unittest
from unittest import mock

from realdir_guard import RealDataDirGuard
import helpers  # noqa: F401  (imports isolate first)
from sync_roms import guest, store


class GuestTest(RealDataDirGuard):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = os.path.join(tmp.name, "gba")
        data = os.path.join(tmp.name, "data")
        self.enterContext(mock.patch.object(store, "data_dir", lambda: data))

    def card(self, name, data=b"x" * 5):
        path = os.path.join(self.dest, name)
        helpers.touch(path, data)
        return path

    def test_is_guest(self):
        self.assertTrue(guest.is_guest({"guest": True}))
        for v in ({}, {"guest": "yes"}, None):
            self.assertFalse(guest.is_guest(v))

    def test_recognized_matches_name_and_size(self):
        self.card("Game.zip")
        self.card("Mine.zip")
        got = guest.recognized(self.dest, ["gba/Game.zip", "gba/Other.zip"], {"gba/Game.zip": 5, "gba/Other.zip": 3})
        self.assertEqual(got, {"gba/Game.zip": os.path.join(self.dest, "Game.zip")})

    def test_named_matches_names_at_any_size(self):
        self.card("GAME.zip", b"x" * 4)
        self.card("Mine.zip")
        got = guest.named(self.dest, ["gba/Game.zip", "gba/Other.zip"])
        self.assertEqual(got, {"gba/Game.zip": os.path.join(self.dest, "GAME.zip")})

    def test_recognized_skips_a_different_size(self):
        self.card("Game.zip", b"x" * 4)
        self.assertEqual(guest.recognized(self.dest, ["gba/Game.zip"], {"gba/Game.zip": 5}), {})

    def test_recognized_keeps_the_card_spelling(self):
        self.card("GAME.zip")
        got = guest.recognized(self.dest, ["gba/Game.zip"], {"gba/Game.zip": 5})
        self.assertTrue(got["gba/Game.zip"].endswith("GAME.zip"))

    def test_recognized_finds_discs_in_disc_dir(self):
        m3u = self.card("G.m3u", b".discs/G (Disc 1).chd\n.discs/G (Disc 2).chd\n")
        disc = self.card(".discs/G (Disc 1).chd", b"d" * 7)
        keys = ["psx/G.m3u", "psx/G (Disc 1).chd", "psx/G (Disc 2).chd"]
        sizes = {"psx/G.m3u": len(b"G (Disc 1).chd\nG (Disc 2).chd\n"), "psx/G (Disc 1).chd": 7, "psx/G (Disc 2).chd": 7}
        self.card(".discs/G (Disc 2).chd", b"d" * 7)
        got = guest.recognized(self.dest, keys, sizes, disc_dir=".discs")
        self.assertEqual(got, {"psx/G.m3u": m3u, "psx/G (Disc 1).chd": disc,
                       "psx/G (Disc 2).chd": disc.replace("Disc 1", "Disc 2")})

    def test_save_seed_replaces_picks_and_keeps_setup(self):
        store.write_cards({"card": {"device": "x", "layout": "esde", "games": {"nes": ["nes/A.zip"]},
                                    "excluded": {"nes": ["nes/B.zip"]}, "collections": ["c"], "systems_off": ["nes"],
                                    "surprises": [{"system": "nes"}], "guest": True}})
        guest.save_seed("card", {"gba": {"gba/Game.zip": "/p"}, "nes": {}})
        self.assertEqual(store.load_cards()["card"], {"device": "x", "layout": "esde",
                                                       "games": {"gba": ["gba/Game.zip"]}, "guest": True})

    def test_guest_card_surprises_are_not_in_the_manifest(self):
        entry = {"device": "full", "layout": "esde",
                 "surprises": [{"system": "gba", "bucket": "gba/S.zip", "title": "S"}]}
        self.assertIn("gba/S.zip", [g["bucket"] for g in store.card_locked_games(entry, {})["gba"]])
        self.assertEqual(store.card_locked_games({**entry, "guest": True}, {}), {})

    def test_apply_seed(self):
        systems = [{"bucket": "gba", "games": [], "full_system": True}]
        guest.apply_seed(systems, {"gba": {"gba/B.zip": "/b", "gba/A.zip": "/a"}})
        self.assertEqual(systems[0]["games"], [{"bucket": "gba/A.zip", "title": "A"}, {"bucket": "gba/B.zip", "title": "B"}])
        self.assertFalse(systems[0]["full_system"])

    def test_deletions_are_seed_minus_picks_without_skipped(self):
        seed = {"gba": {"gba/A.zip": "/a", "gba/B.zip": "/b"}, "nes": {"nes/C.zip": "/c"}}
        self.assertEqual(guest.deletions(seed, {"gba": {"gba/A.zip"}}, {"nes"}), ["/b"])

    def test_deletions_keep_a_file_another_kept_key_was_found_at(self):
        seed = {"ws": {"ws/G.ws": "/g"}, "wsc": {"wsc/G.ws": "/g", "wsc/H.ws": "/h"}, "off": {"off/G.ws": "/h"}}
        self.assertEqual(guest.deletions(seed, {"ws": {"ws/G.ws"}, "wsc": set()}, {"off"}), [])

    def test_new_files_drops_existing_paths(self):
        have = self.card("A.zip")
        missing = os.path.join(self.dest, "B.zip")
        self.assertEqual(guest.new_files([("gba/A.zip", have, 5), ("gba/B.zip", missing, 5)]), [("gba/B.zip", missing, 5)])

    def test_new_gamelist_entries_skips_roms_already_listed(self):
        path = os.path.join(self.dest, "gamelist.xml")
        helpers.touch(path, "<gameList><game><path>./A.zip</path></game></gameList>")
        missing = os.path.join(self.dest, "other", "gamelist.xml")
        got = guest.new_gamelist_entries({path: {"A.zip": {"name": "A"}, "B.zip": {"name": "B"}},
                                          missing: {"C.zip": {"name": "C"}}})
        self.assertEqual(got, {path: {"B.zip": {"name": "B"}}, missing: {"C.zip": {"name": "C"}}})
        helpers.touch(path, "<gameList><game><path>./A.zip</path></game></gameList>")
        self.assertEqual(guest.new_gamelist_entries({path: {"A.zip": {}}}), {})


if __name__ == "__main__":
    unittest.main()
