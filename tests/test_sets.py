import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir, feed_list, storage_sets, write_json  # noqa: E402
from sync_roms import commands, edit, inventory, listedit, picker, runtime, shared, store, themeart  # noqa: E402


def systems():
    return {
        "gba": {"name": "Game Boy Advance", "bucket": "gba", "full_system": False,
                "games": [{"title": "A", "bucket": "gba/A.zip"}]},
        "gen": {"name": "Genesis", "bucket": "gen", "full_system": False, "games": []},
        "ful": {"name": "Full", "bucket": "ful", "full_system": True, "games": []},
    }


SET = {"name": "Mix", "games": [
    {"title": "Zed", "system": "gen", "bucket": "gen/Zed.zip"},
    {"title": "A", "system": "gba", "bucket": "gba/A.zip"},
    {"title": "Gone", "system": "gba", "bucket": "gba/Gone.zip"},
    {"title": "Nope", "system": "nes", "bucket": "nes/Nope.zip"},
    {"title": "Skip", "system": "ful", "bucket": "ful/Skip.zip"},
]}


class StorageSetsTest(StorageDir):
    def load(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            sets = store.load_sets()
        return sets, err.getvalue()

    def test_a_fresh_storage_has_no_sets(self):
        store.reset_sets()
        self.addCleanup(setattr, store, "_sets", "[]")
        self.addCleanup(store.reset_sets)  # first: no fallback flag outlives the test
        self.assertEqual(self.load(), ([], ""))

    def test_sets_load_sorted_by_name_with_ids_from_file_names(self):
        storage_sets(self, {"mix": SET, "b-side": {"name": "another", "description": "d", "games": []}}, self.root)
        sets, err = self.load()
        self.assertEqual(err, "")
        self.assertEqual([(x["id"], x["name"]) for x in sets], [("b-side", "another"), ("mix", "Mix")])
        self.assertEqual(sets[0]["description"], "d")
        self.assertEqual(sets[1]["games"], SET["games"])
        self.assertNotIn("art", sets[1])
        self.assertEqual([x["id"] for x in store.set_files()], ["b-side", "mix"])  # file-name order

    def test_only_json_files_directly_under_sets_are_sets(self):
        storage_sets(self, {"mix": SET}, self.root)
        self.put("sets/notes.txt")
        self.put("sets/old/x.json", store.set_text(SET).encode())
        self.assertEqual([x["id"] for x in self.load()[0]], ["mix"])

    def test_art_round_trips_and_is_written_only_when_set(self):
        with_art = {"name": "Mix", "description": "d", "art": "shmups", "games": SET["games"]}
        text = store.set_text(with_art)
        self.assertEqual(list(json.loads(text)), ["name", "description", "art", "games"])
        self.assertNotIn('"art"', store.set_text({"name": "Mix", "games": []}))
        storage_sets(self, {"mix": text}, self.root)
        loaded = self.load()[0][0]
        self.assertEqual(loaded["art"], "shmups")
        self.assertEqual(store.set_text(loaded), text)  # byte for byte

    def test_a_malformed_set_file_is_skipped_with_a_warning(self):
        storage_sets(self, {"mix": SET, "bad": "{oops", "list": "[]", "nogames": '{"name": "X"}'}, self.root)
        sets, err = self.load()
        self.assertEqual([x["id"] for x in sets], ["mix"])
        for key in ("sets/bad.json", "sets/list.json", "sets/nogames.json"):
            self.assertIn(key, err)

    def test_sets_are_read_once_per_run_and_reset_reads_them_again(self):
        storage_sets(self, {"mix": SET}, self.root)
        self.load()
        self.put("sets/new.json", store.set_text({"name": "New", "games": []}).encode())
        with mock.patch.object(shared, "load", side_effect=AssertionError("read again")), \
                mock.patch.object(inventory, "files", side_effect=AssertionError("listed again")):
            self.assertEqual([x["id"] for x in self.load()[0]], ["mix"])
        store.reset_sets()
        self.assertEqual([x["id"] for x in self.load()[0]], ["mix", "new"])

    def test_callers_get_their_own_copy(self):
        storage_sets(self, {"mix": SET}, self.root)
        store.load_sets()[0]["games"].clear()
        store.set_files()[0].pop("id")
        self.assertEqual(store.load_sets()[0]["id"], "mix")
        self.assertEqual(len(store.load_sets()[0]["games"]), 5)

    def test_writing_a_set_puts_it_in_storage_and_reads_the_sets_again(self):
        storage_sets(self, {"mix": SET}, self.root)
        self.load()
        store.write_set("new", {"name": "New", "games": [], "art": "shmups"})
        with open(os.path.join(self.root, "sets", "new.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), store.set_text({"name": "New", "art": "shmups", "games": []}))
        self.assertEqual([x["id"] for x in self.load()[0]], ["mix", "new"])

    def test_a_storage_error_falls_back_to_the_local_copies(self):
        storage_sets(self, {"mix": SET}, self.root)
        self.load()  # leaves the local copies
        store.reset_sets()
        with mock.patch.object(runtime, "ROOT", self.root + "-unmounted"):
            sets, err = self.load()
        self.assertEqual([x["name"] for x in sets], ["Mix"])
        self.assertIn("Couldn't list sets/", err)
        self.assertEqual(err.count("\n"), 1)  # one warning, not one per set

    def test_a_listing_error_with_no_local_copies_gives_no_sets(self):
        store.reset_sets()
        self.addCleanup(setattr, store, "_sets", "[]")
        self.addCleanup(store.reset_sets)  # first: no fallback flag outlives the test
        with mock.patch.object(inventory, "files", side_effect=OSError("down")):
            sets, err = self.load()
        self.assertEqual(sets, [])
        self.assertIn("Couldn't list sets/", err)


    def test_dot_files_are_not_sets(self):
        storage_sets(self, {"mix": SET, "._mix": "\x00\x05junk", ".hidden": SET}, self.root)
        sets, err = self.load()
        self.assertEqual(([x["id"] for x in sets], err), (["mix"], ""))

    def test_sets_are_listed_past_a_syncs_local_mirror(self):
        storage_sets(self, {"mix": SET}, self.root)
        empty_mirror = os.path.join(self.tmp.name, "mirror")
        os.makedirs(empty_mirror)
        with mock.patch.object(runtime, "_mirror_root", empty_mirror):
            self.assertEqual([x["id"] for x in self.load()[0]], ["mix"])
        self.assertEqual(runtime._mirror_root, None)

    def test_a_storage_error_while_checking_warns_once_and_uses_the_local_copies(self):
        storage_sets(self, {"a": SET, "b": SET, "c": SET}, self.root)
        self.load()  # leaves the local copies
        store.reset_sets()
        with mock.patch.object(inventory, "tag", side_effect=OSError("down")):
            sets, err = self.load()
            self.assertEqual([x["id"] for x in sets], ["a", "b", "c"])
        self.assertEqual(err.count("\n"), 1, err)
        self.assertIn("Couldn't check sets/ in storage", err)


class UnknownCardSetsTest(StorageDir):
    """A card's set ids that aren't in storage are warned about and skipped; cards.json is never changed for them."""
    CARDS = {"SD": {"device": "full", "layout": "esde", "games": {"gba": [{"title": "B", "bucket": "gba/B.zip"}],
                                                                  "sets": ["gone", "mix"]}}}

    def setUp(self):
        super().setUp()
        os.makedirs(self.data)
        self.cards = os.path.join(self.data, "cards.json")
        write_json(self.cards, self.CARDS)
        with open(self.cards, "rb") as f:
            self.before = f.read()

    def manifest(self, sets):
        storage_sets(self, sets, self.root)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            manifest = store.load_manifest(["SD"])
        return manifest, err.getvalue()

    def assert_cards_unchanged(self):
        with open(self.cards, "rb") as f:
            self.assertEqual(f.read(), self.before)

    def gba(self, manifest):
        return sorted(g["bucket"] for s in manifest["systems"] if s["bucket"] == "gba" for g in s["games"])

    def test_an_unknown_set_is_skipped_warned_about_once_and_the_card_kept(self):
        manifest, err = self.manifest({"mix": SET})
        self.assertEqual(self.gba(manifest), ["gba/A.zip", "gba/B.zip", "gba/Gone.zip"])  # mix's games and the pick
        self.assertEqual(err.count("sets that aren't in storage"), 1, err)
        self.assertIn("card SD: sets that aren't in storage (run `sync-roms cache update` if another machine added them): gone", err)
        self.assertNotIn("mix", err)
        with contextlib.redirect_stderr(io.StringIO()) as again:
            store.load_manifest(["SD"])
        self.assertEqual(again.getvalue(), "")  # once per run
        self.assert_cards_unchanged()

    def test_no_sets_in_storage_keeps_every_reference(self):
        manifest, err = self.manifest({})
        self.assertEqual(self.gba(manifest), ["gba/B.zip"])
        self.assertIn("gone, mix", err)
        self.assert_cards_unchanged()

    def test_unmounted_storage_keeps_every_reference(self):
        storage_sets(self, {"mix": SET}, self.root)
        with mock.patch.object(runtime, "ROOT", self.root + "-unmounted"), contextlib.redirect_stderr(io.StringIO()):
            store.load_manifest(["SD"])
        self.assert_cards_unchanged()

    def test_games_sets_remove_drops_an_unknown_set_from_the_card(self):
        storage_sets(self, {"mix": SET}, self.root)
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = commands.games_sets(mock.Mock(card="SD", verb="remove", set_id="gone", dry_run=False))
        self.assertEqual(code, 0)
        with open(self.cards, encoding="utf-8") as f:
            card = json.load(f)["SD"]
        self.assertEqual(card["games"], {"gba": [{"title": "B", "bucket": "gba/B.zip"}], "sets": ["mix"]})
        self.assertEqual({k: v for k, v in card.items() if k != "games"},
                         {k: v for k, v in self.CARDS["SD"].items() if k != "games"})

    def test_games_sets_add_refuses_an_unknown_set_and_names_the_cache_update(self):
        storage_sets(self, {"mix": SET}, self.root)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            commands.games_sets(mock.Mock(card="SD", verb="add", set_id="other", dry_run=False))
        self.assertIn("sync-roms cache update", err.getvalue())
        self.assert_cards_unchanged()

    def test_budget_listing_and_check_take_an_unknown_set(self):
        from sync_roms import budget
        storage_sets(self, {"mix": SET}, self.root)
        system = next(s for s in store.repo_json("systems") if s["bucket"] == "gba")
        card = store.load_cards()["SD"]
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            budget.system_usage(card, system)
            budget.system_usages(card, [system])
            self.assertEqual(commands.games_sets(mock.Mock(card="SD", verb="list", set_id=None, json=False)), 0)
            self.assertEqual(commands.games_list(mock.Mock(card="SD", json=True)), 0)
            problems = commands.check_data()
        self.assertIn("cards.json: SD: unknown set 'gone'", "\n".join(problems))
        self.assert_cards_unchanged()


class StaleSetsTest(StorageDir):
    def setUp(self):
        super().setUp()
        storage_sets(self, {"mix": SET}, self.root)

    def test_a_read_from_the_local_copies_is_flagged_until_read_again(self):
        store.set_files()
        self.assertFalse(store.sets_from_fallback())
        store.reset_sets()
        with mock.patch.object(runtime, "ROOT", self.root + "-unmounted"), contextlib.redirect_stderr(io.StringIO()):
            store.set_files()
            self.assertTrue(store.sets_from_fallback())
        store.reset_sets()
        self.assertFalse(store.sets_from_fallback())

    def test_a_missing_aws_profile_reads_the_local_copies(self):
        store.set_files()  # local copies saved
        store.reset_sets()
        err = io.StringIO()
        with mock.patch.object(inventory, "files", side_effect=SystemExit(3)), contextlib.redirect_stderr(err):
            self.assertEqual([s["id"] for s in store.set_files()], ["mix"])
            self.assertTrue(store.sets_from_fallback())
        self.assertIn("Couldn't list sets/ in storage (see the error above)", err.getvalue())
        store.reset_sets()
        with mock.patch.object(inventory, "tag", side_effect=SystemExit(3)), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([s["id"] for s in store.set_files()], ["mix"])

    def test_a_storage_error_while_checking_a_set_is_flagged(self):
        store.reset_sets()
        with mock.patch.object(inventory, "tag", side_effect=OSError("timed out")), contextlib.redirect_stderr(io.StringIO()):
            store.set_files()
            self.assertTrue(store.sets_from_fallback())

    def test_set_changed_reads_storage_itself(self):
        loaded = store.set_files()[0]
        self.assertFalse(store.set_changed("mix", loaded))
        self.assertTrue(store.set_changed("mix", {**loaded, "name": "Other"}))
        self.assertTrue(store.set_changed("mix", None))  # a new set whose id storage now has
        self.assertFalse(store.set_changed("new", None))
        self.assertTrue(store.set_changed("new", loaded))  # deleted meanwhile
        self.put("sets/bad.json", b"{")
        self.assertTrue(store.set_changed("bad", loaded))
        with mock.patch.object(runtime, "ROOT", self.root + "-unmounted"), self.assertRaises(FileNotFoundError):
            store.set_changed("new", None)  # an unmounted folder isn't a missing file


class CheckStorageSetsTest(StorageDir):
    def check(self, sets):
        if sets is not None:
            storage_sets(self, sets, self.root)
        else:
            store.reset_sets()
            self.addCleanup(setattr, store, "_sets", "[]")
            self.addCleanup(store.reset_sets)  # first: no fallback flag outlives the test
        problems = []
        with contextlib.redirect_stderr(io.StringIO()):
            keys = commands.check_sets(problems, {"gba", "gen"})
            notices = commands.check_set_notices()
        return problems, keys, notices

    def art(self, n):
        return [i for i in themeart.art_choices()][n]

    def test_a_fresh_storage_has_nothing_to_check(self):
        self.assertEqual(self.check(None), ([], {}, []))

    def test_storage_sets_are_checked_with_the_set_file_rules(self):
        problems, keys, _ = self.check({self.art(0): {"name": "Good", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/A.zip", "files": ["gba/A2.zip"]}]},
            "bad": {"name": "Bad", "games": [{"title": "", "system": "gba", "bucket": "gba/B.zip"},
                                             {"title": "N", "system": "nes", "bucket": "nes/N.zip"},
                                             {"title": "W", "system": "gen", "bucket": "gba/W.zip"}]}})
        self.assertEqual(problems, ["sets/bad.json: gba/B.zip: missing 'title'",
                                    "sets/bad.json: nes/N.zip: unknown system 'nes'",
                                    "sets/bad.json: 'gba/W.zip' isn't under gen/"])
        self.assertEqual(keys, {f"sets/{self.art(0)}.json": [("gba", "gba/A.zip"), ("gba", "gba/A2.zip")],
                                "sets/bad.json": [("gba", "gba/B.zip")]})

    def test_a_file_that_isnt_a_set_is_a_problem(self):
        problems, keys, _ = self.check({"broken": "{not json", "list": "[]"})
        self.assertEqual(problems, ["sets/broken.json: isn't a set (a JSON object with a games list)",
                                    "sets/list.json: isn't a set (a JSON object with a games list)"])
        self.assertEqual(keys, {})

    def test_unknown_art_is_a_problem(self):
        problems, _, _ = self.check({"s": {"name": "S", "art": "nope", "games": []}})
        self.assertEqual(problems, ["sets/s.json: unknown art 'nope'"])

    def test_sets_without_art_or_sharing_art_are_noticed(self):
        a, b = self.art(0), self.art(1)
        problems, _, notices = self.check({a: {"name": "A", "games": []}, "new": {"name": "N", "games": []},
                                           "other": {"name": "O", "art": a, "games": []},
                                           "picked": {"name": "P", "art": b, "games": []}})
        self.assertEqual(problems, [])
        self.assertEqual(notices, [f"sets: 1 set(s) have no art in art.json, so they show {themeart.SET_EMOJI} "
                                   "and get no picture: new",
                                   f"sets: {', '.join(sorted([a, 'other']))} share the art {a!r}"])

    def test_storage_set_keys_are_checked_against_storage(self):
        storage_sets(self, {"s": {"name": "S", "games": [{"title": "A", "system": "gba", "bucket": "gba/A.zip"}]}},
                     self.root)
        with contextlib.redirect_stderr(io.StringIO()):
            problems = commands.check_data(lambda system: set())
        self.assertIn("sets/s.json: 'gba/A.zip' isn't in storage", problems)


class SetsTest(unittest.TestCase):
    def test_rows_sorted_by_system_skip_unknown(self):
        rows = edit.set_rows(SET, systems(), lambda s: {"gba/A.zip", "gen/Zed.zip"})
        self.assertEqual([r[1] for r in rows], ["ful/Skip.zip", "gba/A.zip", "gba/Gone.zip", "gen/Zed.zip"])
        self.assertIn("not in storage", rows[2][3])
        self.assertNotIn("not in storage", rows[1][3])

    def test_rows_grouped_by_category_in_file_order(self):
        game_set = {"games": [{"title": "Z", "system": "gba", "bucket": "gba/Z.zip", "category": "First"},
                              {"title": "A", "system": "gba", "bucket": "gba/A.zip", "category": "Second"},
                              {"title": "B", "system": "gba", "bucket": "gba/B.zip", "category": "First"}]}
        rows = edit.set_rows(game_set, systems(), lambda s: set())
        self.assertEqual([r[1] for r in rows], ["gba/B.zip", "gba/Z.zip", "gba/A.zip"])
        self.assertTrue(rows[0][3].startswith("First — "))

    def test_toggle_adds_and_removes(self):
        by = systems()
        rows = edit.set_rows(SET, by, lambda s: set())
        with mock.patch.object(picker, "filter_list", return_value=[True, False, True, True]) as fl:
            edit.toggle_games("t", rows)
        self.assertEqual(fl.call_args.kwargs["initial"], [True, True, False, False])
        self.assertEqual(fl.call_args.kwargs["locked"], [True, False, False, False])
        self.assertEqual(by["ful"]["games"], [])
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/Gone.zip"])
        self.assertEqual([g["bucket"] for g in by["gen"]["games"]], ["gen/Zed.zip"])

    def test_toggle_games_shows_variant_notes(self):
        by = systems()
        game_set = {"name": "Mix", "games": [
            {"title": "A", "system": "gba", "bucket": "gba/A.zip",
             "variants": [{"bucket": "gb/A.gb", "note": "GB: x"}]},
            {"title": "Zed", "system": "gen", "bucket": "gen/Zed.zip"}]}
        rows = edit.set_rows(game_set, by, lambda s: set())
        with mock.patch.object(store, "load_sets", return_value=[game_set]), \
                mock.patch.object(store, "repo_json", return_value=list(by.values())), \
                mock.patch.object(picker, "filter_list", return_value=[False, False]) as fl:
            edit.toggle_games("t", rows)
        row_note = fl.call_args.kwargs["row_note"]
        a = [r[1] for r in rows].index("gba/A.zip")
        z = [r[1] for r in rows].index("gen/Zed.zip")
        self.assertEqual(row_note(a), "\u21b3 Variant: GB: x")
        self.assertEqual(row_note(z), "")

    def test_toggle_extra_files(self):
        by = systems()
        game_set = {"name": "M", "games": [{"title": "Multi", "system": "gen", "bucket": "gen/M.m3u",
                                            "files": ["gen/M (Disc 1).chd", "gen/M (Disc 2).chd"]}]}
        rows = edit.set_rows(game_set, by, lambda s: {"gen/M.m3u", "gen/M (Disc 1).chd"})
        self.assertIn("not in storage", rows[0][3])
        extras = {"gen/M.m3u": game_set["games"][0]["files"]}
        with mock.patch.object(picker, "filter_list", return_value=[True]):
            edit.toggle_games("t", rows, extras)
        self.assertEqual([g["bucket"] for g in by["gen"]["games"]],
                         ["gen/M.m3u", "gen/M (Disc 1).chd", "gen/M (Disc 2).chd"])
        with mock.patch.object(picker, "filter_list", return_value=[False]):
            edit.toggle_games("t", rows, extras)
        self.assertEqual(by["gen"]["games"], [])

    def test_overlapping_extras_never_duplicate_a_game(self):
        by = {"gen": {"bucket": "gen", "games": [{"title": "A1", "bucket": "gen/A1.chd"},
                                                 {"title": "A2", "bucket": "gen/A2.chd"}]}}
        rows = [(by["gen"], "gen/A1.chd", "A", ""), (by["gen"], "gen/B1.chd", "B", "")]
        extras = {"gen/A1.chd": ["gen/A2.chd"], "gen/B1.chd": ["gen/A2.chd"]}
        with mock.patch.object(picker, "filter_list", return_value=[False, True]):
            edit.toggle_games("t", rows, extras)
        buckets = [g["bucket"] for g in by["gen"]["games"]]
        self.assertEqual(sorted(buckets), sorted(set(buckets)))
        self.assertIn("gen/A2.chd", buckets)

    def test_locked_rows_cannot_toggle(self):
        keys = iter(["tab", "ctrl+a", "escape", "y"])
        state = self.run_list(keys, locked=[True, False])
        self.assertEqual(state, [False, True])

    def test_multi_esc_keeps_state(self):
        self.assertEqual(self.run_list(iter(["tab", "escape", "y"])), [True, False])

    def test_multi_esc_without_changes_just_leaves(self):
        self.assertEqual(self.run_list(iter(["escape"])), [False, False])

    def test_multi_esc_can_revert(self):
        self.assertEqual(self.run_list(iter(["tab", "escape", "u"])), [False, False])

    def test_multi_esc_any_other_key_keeps_editing(self):
        self.assertEqual(self.run_list(iter(["tab", "escape", "z", "enter"])), [True, False])

    def test_ctrl_r_reverts_the_list(self):
        self.assertEqual(self.run_list(iter(["tab", "u", "enter"])), [False, False])

    def test_space_toggles_in_normal_mode_and_is_text_while_typing(self):
        self.assertEqual(self.run_list(iter(["space", "enter"])), [True, False])
        self.assertEqual(self.run_list(iter(["/", "y", "enter", "space", "enter"])), [False, True])
        self.assertEqual(self.run_list(iter(["/", "x", "space", "y", "enter", "escape", "space", "enter"])), [True, False])  # "x y" matches nothing; Esc clears it

    def test_view_cycle_shows_only_changed_rows(self):
        # toggle row 0, then ^O twice: "changed only" lists just it, and Tab then toggles that row back
        self.assertEqual(self.run_list(iter(["tab", "ctrl+o", "ctrl+o", "tab", "enter"])), [False, False])

    def test_hotkey_returns_pair(self):
        self.assertEqual(self.run_list(iter(["f"]), multi=False, hotkeys=("f",)), ("f", 0))
        self.assertEqual(self.run_list(iter(["j", "f"]), multi=False, hotkeys=("f",)), ("f", 1))

    def test_hotkey_ignored_without_rows(self):
        self.assertIsNone(self.run_list(iter(["/", "z", "enter", "f", "escape", "escape"]), multi=False, hotkeys=("f",)))

    def test_covered_rows_locked_with_note(self):
        by = systems()
        rows = edit.set_rows(SET, by, lambda s: set())
        covered = lambda s, key: "Full set: x" if key == "gba/Gone.zip" else None  # noqa: E731
        with mock.patch.object(picker, "filter_list", return_value=[True, True, True, True]) as fl:
            edit.toggle_games("t", rows, covered=covered)
        self.assertEqual(fl.call_args.kwargs["locked"], [True, False, True, False])
        self.assertEqual(fl.call_args.kwargs["locked_note"][2], "Full set: x")
        self.assertNotIn("gba/Gone.zip", [g["bucket"] for g in by["gba"]["games"]])

    def test_excluded_unlocks_covered_rows_and_records_off_ones(self):
        by = systems()
        rows = edit.set_rows(SET, by, lambda s: set())
        covered = lambda s, key: "From core" if key in ("gba/Gone.zip", "gba/A.zip") else None  # noqa: E731
        excluded = {"gba": ["gba/A.zip"]}
        with mock.patch.object(picker, "filter_list") as fl:
            fl.side_effect = lambda *a, **k: [not x for x in k["initial"]]
            edit.toggle_games("t", rows, covered=covered, excluded=excluded)
        kw = fl.call_args.kwargs
        keys = [r[1] for r in rows]
        for key in ("gba/A.zip", "gba/Gone.zip"):
            self.assertFalse(kw["locked"][keys.index(key)])
        self.assertTrue(kw["locked"][keys.index("ful/Skip.zip")])  # full systems stay locked
        self.assertFalse(kw["initial"][keys.index("gba/A.zip")])  # excluded starts off
        self.assertTrue(kw["initial"][keys.index("gba/Gone.zip")])
        self.assertEqual(excluded["gba"], ["gba/Gone.zip"])  # A switched on, Gone switched off

    def run_list(self, keys, locked=None, multi=True, hotkeys=()):
        return feed_list(keys, "t", ["x", "y"], multi=multi, locked=locked, hotkeys=hotkeys)


VARIANT_SETS = [
    {"id": "a", "games": [
        {"system": "snes", "bucket": "snes/CT.zip", "title": "Chrono Trigger",
         "variants": [{"bucket": "nds/CT.zip", "note": "DS: adds the Lost Sanctum"}]},
        {"system": "snes", "bucket": "snes/Plain.zip", "title": "Plain"},
        {"system": "snes", "title": "No bucket", "variants": [{"bucket": "nds/X.zip", "note": "x"}]},
    ]},
    {"id": "b", "games": [
        {"system": "snes", "bucket": "snes/CT.zip", "title": "Chrono Trigger",
         "variants": [{"bucket": "nds/CT.zip", "note": "DS: adds the Lost Sanctum"},
                      {"bucket": "psx/CT.chd", "note": "PS1: anime scenes"}]},
    ]},
]


class VariantTests(unittest.TestCase):
    def test_variant_index_maps_both_ways(self):
        variants, parents = store.variant_index(VARIANT_SETS)
        self.assertEqual(variants["snes/CT.zip"], [{"bucket": "nds/CT.zip", "note": "DS: adds the Lost Sanctum"},
                                                   {"bucket": "psx/CT.chd", "note": "PS1: anime scenes"}])
        self.assertEqual(parents["nds/CT.zip"], {"bucket": "snes/CT.zip", "system": "snes", "title": "Chrono Trigger"})
        self.assertNotIn("snes/Plain.zip", variants)
        self.assertNotIn("nds/X.zip", parents)

    def test_variant_line_texts(self):
        variants, parents = store.variant_index(VARIANT_SETS)
        names = {"snes": "SNES", "nds": "Nintendo DS"}
        one = {"snes/CT.zip": variants["snes/CT.zip"][:1]}
        line = lambda key, v=variants, on=None: edit.variant_line(key, v, parents, names, on)  # noqa: E731
        self.assertEqual(line("snes/CT.zip", one), "↳ Variant: DS: adds the Lost Sanctum")
        self.assertEqual(line("snes/CT.zip", one, lambda b: False), "↳ Variant: DS: adds the Lost Sanctum (v adds it)")
        self.assertEqual(line("snes/CT.zip", one, lambda b: True),
                         "↳ Variant: DS: adds the Lost Sanctum · ✅ on the card (v removes it)")
        self.assertEqual(line("snes/CT.zip", on=lambda b: False),
                         "↳ 2 variants (v picks): DS: adds the Lost Sanctum; PS1: anime scenes")
        self.assertEqual(line("snes/CT.zip"), "↳ Variants: DS: adds the Lost Sanctum; PS1: anime scenes")
        self.assertEqual(line("nds/CT.zip"), "Variant of SNES — Chrono Trigger")
        self.assertEqual(line("gba/none.zip"), "")
        both = {"nds/CT.zip": [{"bucket": "x/Y.zip", "note": "n"}]}
        self.assertEqual(line("nds/CT.zip", both), "↳ Variant: n")


if __name__ == "__main__":
    unittest.main()


class SeriesTest(unittest.TestCase):
    GAMES = {"games": [
        {"title": "A", "system": "gba", "bucket": "gba/A.zip", "series": "Mario"},
        {"title": "B", "system": "gba", "bucket": "gba/B.zip"},
        {"title": "C", "system": "gba", "bucket": "gba/C.zip", "series": "Zelda"},
        {"title": "D", "system": "gba", "bucket": "gba/D.zip", "series": "Mario", "files": ["gba/D2.zip"]},
        {"title": "E", "system": "gba", "bucket": "gba/E.zip", "series": "Metroid"},
        {"title": "F", "system": "gba", "bucket": "gba/F.zip", "series": "Metroid"},
        {"title": "G", "system": "gba", "bucket": "gba/G.zip", "series": "Zelda"},
    ]}

    def test_series_of_skips_small_series_in_file_order(self):
        self.assertEqual(listedit.series_of(self.GAMES), [("Mario", 2), ("Zelda", 2), ("Metroid", 2)])
        self.assertEqual(listedit.series_of({"games": self.GAMES["games"][:3]}), [])
        self.assertEqual(listedit.series_of({"games": self.GAMES["games"][:3]}, min_games=1),
                         [("Mario", 1), ("Zelda", 1)])

    def test_series_keys_include_files(self):
        self.assertEqual(listedit.series_keys(self.GAMES, "Mario"), {"gba/A.zip", "gba/D.zip", "gba/D2.zip"})
        self.assertEqual(listedit.series_keys(self.GAMES, "None"), set())

    def test_check_game_file_rejects_non_string_series(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            write_json(path, {"name": "S", "games": [
                {"title": "A", "system": "gba", "bucket": "gba/A.zip", "series": 3}]})
            problems = []
            commands.check_game_file(problems, path, "s.json", {"gba"})
        self.assertEqual(problems, ["s.json: gba/A.zip: 'series' must be a string"])
