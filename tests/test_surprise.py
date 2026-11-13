import collections
import contextlib
import datetime
import io
import json
import os
import random
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
import isolate  # noqa: E402,F401
from sync_roms import cardedit, mirroring, picker, runtime, store, surprise, usersettings  # noqa: E402

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


G = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"
DLC = "psvita/D [PCSE00349] [USA] [DLC-X].zip"
NEW = "psvita/G [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"
H = "psvita/H [PCSE00001] [USA] [NoNpDRM].zip"


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

    def test_vita_dlc_and_updates_are_never_units(self):
        vita_sys = {"bucket": "psvita", "bios": {"files": []}}
        self.assertEqual(surprise.units(vita_sys, {G, DLC, NEW}, None, set()), [[G]])


def pool(system, n):
    return [[f"{system}/G{i} (USA).zip"] for i in range(n)]


def count(picked):
    return collections.Counter(p["system"] for p in picked)


class SurprisePickTest(unittest.TestCase):
    def test_surprise_uses_arcade_name(self):
        self.assertEqual(surprise._surprise("fbneo", ["fbneo/1941j.zip"])["title"], "1941: Counter Attack (Japan)")

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

    def test_more_kept_than_slots_picks_nothing(self):
        kept = [{"system": "a", "bucket": f"a/K{i}.zip", "title": f"K{i}"} for i in range(12)]
        need = max(surprise.SLOTS - len(kept), 0)
        self.assertEqual(surprise.pick({"a": pool("a", 500)}, kept, need, {"a"}, set(), set(), random.Random(0)), [])
        self.assertEqual(surprise.pick({"a": pool("a", 500)}, kept, -2, {"a"}, set(), set(), random.Random(0)), [])

    def test_need_zero_picks_nothing(self):
        self.assertEqual(surprise.pick({"a": pool("a", 5)}, [], 0, {"a"}, set(), set(), random.Random(0)), [])

    def test_every_system_runs_out_returns_what_there_is(self):
        got = surprise.pick({"a": pool("a", 2), "b": pool("b", 1), "c": []}, [], 10, {"a"}, set(), set(),
                            random.Random(7))
        self.assertEqual(count(got), {"a": 2, "b": 1})
        self.assertEqual(surprise.pick({}, [], 10, set(), set(), set(), random.Random(7)), [])

    def test_kept_surprises_count_in_the_even_spread(self):
        pools = {s: pool(s, 20) for s in "abc"}
        kept = [{"system": "a", "bucket": f"a/K{i}.zip", "title": f"K{i}"} for i in range(2)]
        for seed in range(50):
            got = count(surprise.pick(pools, kept, 8, {"a", "b"}, set(), set(), random.Random(seed)))
            self.assertIn((got["a"] + 2, got["b"]), [(4, 3), (3, 4)], seed)
            self.assertEqual(got["c"], 3)

    def test_ties_between_systems_vary_with_the_seed(self):
        pools = {"a": pool("a", 5), "b": pool("b", 5)}
        firsts = {surprise.pick(pools, [], 1, {"a", "b"}, set(), set(), random.Random(i))[0]["system"]
                  for i in range(30)}
        self.assertEqual(firsts, {"a", "b"})


class StorageCase(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        os.makedirs(self.data)

    def write_cards(self, cards):
        store.write_cards(cards)

    def read_cards(self):
        with open(os.path.join(self.data, "cards.json")) as f:
            return json.load(f)

    def card(self, **entry):
        self.write_cards({"SD": {"device": "full", "layout": "esde", **entry}})

    def chosen(self):
        return [s for s in store.load_manifest(["SD"])["systems"] if s["bucket"] in ("gba", "gb")]

    def surprise(self, system, i):
        ext = "gb" if system == "gb" else "zip"
        return {"system": system, "bucket": f"{system}/G{i} (USA).{ext}", "title": f"G{i} (USA)"}

    def fail_call(self, *a, **k):
        raise AssertionError(f"unexpected call {a!r} {k!r}")

    @contextlib.contextmanager
    def patched(self, filter_list=None, edit_card=None):
        """picker.filter_list and cardedit.edit_card replaced; one left out does nothing and returns None."""
        noop = lambda *a, **k: None  # noqa: E731
        with mock.patch.object(picker, "filter_list", filter_list or noop), \
                mock.patch.object(cardedit, "edit_card", edit_card or noop):
            yield


class History(helpers.DataDir):
    def test_save_prunes_past_the_ttl_and_recent_reads_within_it(self):
        today = datetime.date(2026, 11, 11)
        old = {"system": "gba", "bucket": "gba/Old.zip", "title": "Old", "card": "SD", "date": "2026-05-01"}
        new = {"system": "gba", "bucket": "gba/New.zip", "title": "New", "card": "SD", "date": "2026-10-01"}
        surprise.save_history([old, new], today)
        self.assertEqual(self.read("surprises.json"), [new])
        self.assertEqual(surprise.recent([old, new], today, 183), {"gba/New.zip"})

    def test_ttl_comes_from_settings_default_183(self):
        self.assertEqual(surprise.ttl_days(), 183)
        self.write_json("settings.json", {"surprise_ttl_days": 30})
        self.assertEqual(surprise.ttl_days(), 30)

    def test_unreadable_history_is_empty_and_not_overwritten(self):
        with open(self.path("surprises.json"), "w") as f:
            f.write("{nope")
        with mock.patch.object(surprise.ui, "warn") as warn:
            self.assertEqual(surprise.load_history(), [])
            surprise.save_history([], datetime.date(2026, 11, 11))
        self.assertEqual(warn.call_count, 2)
        with open(self.path("surprises.json")) as f:
            self.assertEqual(f.read(), "{nope")

    def test_past_keys_limits_to_a_bucket(self):
        today = datetime.date.today().isoformat()
        self.write_json("surprises.json", [
            {"system": "gba", "bucket": "gba/A.zip", "title": "A", "card": "SD", "date": today},
            {"system": "gbc", "bucket": "gbc/B.zip", "title": "B", "card": "SD", "date": today}])
        self.assertEqual(surprise.past_keys("gba"), {"gba/A.zip"})


class Locked(unittest.TestCase):
    def test_card_locked_games_adds_surprises_only_when_on(self):
        s = {"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}
        disc = {"system": "psx", "bucket": "psx/F (USA).m3u", "title": "F (USA)",
                "files": ["psx/F (USA) (Disc 1).chd", "psx/F (USA) (Disc 2).chd"]}
        got = store.card_locked_games({"surprises": [s, disc]}, {})
        self.assertEqual([g["bucket"] for g in got["gba"]], ["gba/A (USA).zip"])
        self.assertEqual(got["gba"][0]["from"], "\U0001F381 Surprise")
        self.assertEqual([g["bucket"] for g in got["psx"]], [disc["bucket"]] + disc["files"])
        self.assertEqual(store.card_locked_games({"surprise": False, "surprises": [s]}, {}), {})

    def test_malformed_games_add_no_bogus_keys(self):
        for files in (5, "ab", [1], [None, "gba/B.zip"]):
            game = {"system": "gba", "bucket": "gba/A.zip", "title": "A", "files": files}
            for entry, colls in (({"surprises": [game, 7, {"system": "", "bucket": "x"}]}, {}),
                                 ({"collections": ["c"]}, {"c": {"name": "Mine", "games": [game, 7]}})):
                got = store.card_locked_games(entry, colls)
                keys = [g["bucket"] for g in got["gba"]]
                self.assertEqual(keys, ["gba/A.zip", "gba/B.zip"] if files == [None, "gba/B.zip"] else ["gba/A.zip"])

    def test_collection_games_come_first(self):
        s = {"system": "gba", "bucket": "gba/A.zip", "title": "A"}
        coll = {"c": {"name": "Mine", "games": [dict(s)]}}
        got = store.card_locked_games({"collections": ["c"], "surprises": [s]}, coll)
        self.assertEqual([(g["bucket"], g["from"]) for g in got["gba"]], [("gba/A.zip", "\U0001F496 Mine")])


class Mirror(StorageCase):
    def test_mirror_wanted_includes_current_surprises(self):
        self.put("gba/A (USA).zip")
        self.write_cards({"SD": {"device": "full", "layout": "esde",
                                 "surprises": [{"system": "gba", "bucket": "gba/A (USA).zip", "title": "A (USA)"}]}})
        self.assertIn("gba/A (USA).zip", mirroring.mirror_wanted(store.load_manifest(store.all_card_names())))


class Step(StorageCase):
    def setUp(self):
        super().setUp()
        for i in range(15):
            self.put(f"gba/G{i} (USA).zip")
            self.put(f"gb/G{i} (USA).gb")
        self.card()
        quiet = contextlib.redirect_stdout(io.StringIO())  # the step prints its picks
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def run_step(self, interactive, dry_run, seed):
        """run_surprise on the dry-run tests, with its printed lines."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), interactive, dry_run, rng=random.Random(seed))
        return got, out.getvalue()

    def test_interactive_asks_which_to_replace_then_opens_the_editor(self):
        current = [self.surprise("gba", i) for i in range(5)] + [self.surprise("gb", i) for i in range(5)]
        self.card(surprises=current)
        lists, edits = [], []
        with self.patched(filter_list=lambda title, labels, **kw: lists.append((title, labels, kw)) or [True] + [False] * 9,
                          edit_card=lambda name, setup=None, to_fetch=None: edits.append(name)):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False, rng=random.Random(1))
        title, labels, kw = lists[0]
        self.assertEqual(title, "Pick the surprises to replace")
        self.assertEqual(kw["initial"], [False] * 10)
        self.assertEqual(len(got), 10)
        self.assertNotIn(current[0], got)
        self.assertTrue(all(c in got for c in current[1:]))
        self.assertEqual(store.load_cards()["SD"]["surprises"], got)
        self.assertEqual([h["bucket"] for h in surprise.load_history()], [g["bucket"] for g in got if g not in current])
        self.assertEqual(edits, ["SD"])

    def test_surprises_outside_the_run_are_dropped(self):
        self.card(surprises=[self.surprise("gba", 0), self.surprise("psx", 0)])
        with self.patched(filter_list=lambda t, labels, **kw: [False] * len(labels)):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False, rng=random.Random(2))
        self.assertNotIn("psx", {g["system"] for g in got})
        self.assertIn(self.surprise("gba", 0), got)

    def test_excluded_systems_are_never_picked_and_their_surprises_are_replaced(self):
        usersettings.save_setting("surprise_excluded_systems", ["gb"])
        self.card(surprises=[self.surprise("gba", 0), self.surprise("gb", 0)])
        got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(3))
        self.assertEqual(len(got), 10)
        self.assertEqual({g["system"] for g in got}, {"gba"})

    def test_dry_run_keeps_every_surprise_and_only_previews_the_empty_slots(self):
        self.card(surprises=[self.surprise("gba", 0)])
        before = self.read_cards()
        with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            got, out = self.run_step(True, True, 3)
        self.assertEqual(got, [self.surprise("gba", 0)])  # the saved ones; the 9 fills are only printed
        self.assertIn("🎁 would ask which surprises to replace", out)
        self.assertIn("9 new pick(s)", out)
        self.assertEqual(self.read_cards(), before)
        self.assertFalse(os.path.exists(os.path.join(self.data, "surprises.json")))

    def test_unattended_dry_run_says_it_would_replace_them_all(self):
        current = [self.surprise("gba", i) for i in range(5)] + [self.surprise("gb", i) for i in range(5)]
        self.card(surprises=current)
        before = self.read_cards()
        with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            got, out = self.run_step(False, True, 3)
        self.assertEqual(got, current)
        self.assertIn("🎁 would replace all 10 surprises", out)
        self.assertNotIn("new pick", out)  # no empty slot to preview
        self.assertEqual(self.read_cards(), before)
        self.assertFalse(os.path.exists(os.path.join(self.data, "surprises.json")))

    def test_unattended_replaces_all_ten_and_saves(self):
        current = [self.surprise("gba", i) for i in range(5)] + [self.surprise("gb", i) for i in range(5)]
        self.card(surprises=current)
        with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(4))
        self.assertEqual(len(got), 10)
        self.assertFalse(any(c in got for c in current))
        self.assertEqual(store.load_cards()["SD"]["surprises"], got)
        self.assertEqual(len(surprise.load_history()), 10)

    def test_card_selection_and_other_cards_current_are_respected(self):
        picks = {"gba": [{"bucket": f"gba/G{i} (USA).zip"} for i in range(14)]}  # one GBA game left unpicked
        self.card(games=picks)
        with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(5))
        self.assertEqual([g["bucket"] for g in got if g["system"] == "gba"], ["gba/G14 (USA).zip"])

    def test_full_systems_are_left_out_of_the_pools(self):
        self.card(games={"gb": {"full_system": True}})
        with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(7))
        self.assertEqual(len(got), 10)
        self.assertEqual({g["system"] for g in got}, {"gba"})

    def test_off_clears_surprises_keeps_history_and_picks_nothing(self):
        self.card(surprise=False, surprises=[self.surprise("gba", 0)])
        surprise.save_history([{**self.surprise("gba", 0), "card": "SD", "date": "2026-11-01"}], datetime.date(2026, 11, 11))
        edits = []
        with self.patched(filter_list=self.fail_call, edit_card=lambda name, setup=None, to_fetch=None: edits.append(name)):
            self.assertEqual(surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False), [])
        self.assertNotIn("surprises", store.load_cards()["SD"])
        self.assertEqual(len(surprise.load_history()), 1)
        self.assertEqual(edits, ["SD"])  # the card editor still opens

    def test_off_unattended_or_dry_run_opens_no_editor(self):
        self.card(surprise=False)
        with self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            self.assertEqual(surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False), [])
            self.assertEqual(surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, True), [])

    def test_twelve_kept_surprises_get_no_new_picks(self):
        current = [self.surprise("gba", i) for i in range(12)]
        self.card(surprises=current)
        with self.patched(filter_list=lambda t, labels, **kw: [False] * len(labels)):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False, rng=random.Random(8))
        self.assertEqual(got, current)

    def test_storage_listing_failure_keeps_the_surprises(self):
        current = [self.surprise("gba", i) for i in range(5)] + [self.surprise("gb", i) for i in range(5)]
        self.card(surprises=current)
        surprise.save_history([{**self.surprise("gba", 0), "card": "SD", "date": "2026-11-01"}], datetime.date(2026, 11, 11))
        before, history = self.read_cards(), surprise.load_history()

        def down(*a, **k):
            raise SystemExit("offline")
        with mock.patch.object(surprise.s3, "list_folders", down), contextlib.redirect_stderr(io.StringIO()), \
                self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(9))
        self.assertEqual(got, current)
        self.assertEqual(self.read_cards(), before)
        self.assertEqual(surprise.load_history(), history)

    def test_storage_listing_failure_interactive_keeps_them_and_opens_the_editor(self):
        current = [self.surprise("gba", i) for i in range(10)]
        self.card(surprises=current)
        edits = []

        def down(*a, **k):
            raise SystemExit("offline")
        with mock.patch.object(surprise.s3, "list_folders", down), contextlib.redirect_stderr(io.StringIO()), \
                self.patched(filter_list=lambda t, labels, **kw: [True] * len(labels),
                             edit_card=lambda name, setup=None, to_fetch=None: edits.append(name)):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), True, False, rng=random.Random(9))
        self.assertEqual(got, current)
        self.assertEqual(store.load_cards()["SD"]["surprises"], current)
        self.assertEqual(edits, ["SD"])

    def test_candidates_come_from_storage_not_the_mirror(self):
        mirror = os.path.join(self.tmp.name, "mirror")  # holds nothing
        os.makedirs(mirror)
        with mock.patch.object(runtime, "_mirror_root", mirror), self.patched(filter_list=self.fail_call, edit_card=self.fail_call):
            got = surprise.run_surprise("SD", (None, "esde"), self.chosen(), False, False, rng=random.Random(6))
            self.assertEqual(runtime._mirror_root, mirror)  # restored after the step
        self.assertEqual(len(got), 10)


if __name__ == "__main__":
    unittest.main()
