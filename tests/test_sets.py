import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir, storage_sets  # noqa: E402
from sync_roms import commands, inventory, runtime, shared, store, themeart  # noqa: E402


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

    def test_a_set_file_that_isnt_utf8_is_skipped_with_a_warning(self):
        storage_sets(self, {"mix": SET}, self.root)
        self.put("sets/b.json", '{"name": "Café", "games": []}'.encode("latin-1"))
        sets, err = self.load()
        self.assertEqual([x["id"] for x in sets], ["mix"])
        self.assertIn("sets/b.json isn't a set", err)
        self.assertEqual(store.skipped_sets(), ["sets/b.json"])

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

    def test_a_storage_error_on_a_later_set_uses_its_local_copy_and_warns_once(self):
        storage_sets(self, {"a": SET, "b": SET, "c": SET}, self.root)
        self.load()  # leaves the local copies
        store.reset_sets()
        for i in "abc":
            with open(os.path.join(self.root, "sets", f"{i}.json"), "w", encoding="utf-8") as f:
                f.write(store.set_text({**SET, "name": f"New {i}"}))
        real_tag = inventory.tag

        def tag(key):
            if key == "sets/b.json":
                raise OSError("down")
            return real_tag(key)
        with mock.patch.object(inventory, "tag", tag):
            sets, err = self.load()
        # c was read at the same time as b, so its local copy is already storage's
        self.assertEqual({x["id"]: x["name"] for x in sets}, {"a": "New a", "b": "Mix", "c": "New c"})
        self.assertEqual(err.count("\n"), 1, err)
        self.assertTrue(store.sets_from_fallback())

    def test_sets_read_at_once_keep_every_local_copys_tag(self):
        storage_sets(self, {f"s{i:02}": SET for i in range(40)}, self.root)
        self.assertEqual([x["id"] for x in self.load()[0]], [f"s{i:02}" for i in range(40)])
        with open(os.path.join(self.data, "storage", ".tags.json"), encoding="utf-8") as f:
            self.assertEqual(sorted(json.load(f)), [f"sets/s{i:02}.json" for i in range(40)])


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

    def test_a_set_file_that_isnt_utf8_counts_as_changed(self):
        self.put("sets/b.json", '{"name": "Café", "games": []}'.encode("latin-1"))
        self.assertTrue(store.set_changed("b", None))  # a new set whose id storage has, as an unreadable file
        self.assertTrue(store.set_changed("b", store.set_files()[0]))


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

    def test_a_file_that_isnt_utf8_is_a_problem(self):
        self.put("sets/b.json", '{"name": "Café", "games": []}'.encode("latin-1"))
        problems, keys, _ = self.check({})
        self.assertEqual(problems, ["sets/b.json: isn't a set (a JSON object with a games list)"])
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


if __name__ == "__main__":
    unittest.main()
