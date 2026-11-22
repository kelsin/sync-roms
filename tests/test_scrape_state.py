import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir  # noqa: E402
from sync_roms import ignore, inventory, runtime, s3, scrape_files, scrape_state, shared  # noqa: E402

H = {"md5": "a", "sha1": "b", "crc": "c"}
INFO = {"name": "Bios", "genre": "", "year": "1985", "desc": ""}


class ScrapeStateTest(StorageDir):
    def setUp(self):
        super().setUp()
        scrape_state.reset()
        self.addCleanup(scrape_state.reset)

    def stored(self, key):
        """The storage file's JSON, or None when it isn't there."""
        try:
            return self.read_json(key)
        except FileNotFoundError:
            return None

    def store(self, key, data):
        self.put(key, (data if isinstance(data, str) else json.dumps(data)).encode())

    def new_run(self):
        """What the next run sees: everything read again from storage."""
        scrape_state.reset()

    # round trips and placement

    def test_hashes_round_trip(self):
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 10, 5))
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)
        scrape_state.flush()
        self.assertEqual(self.stored("scrapes/gba/hashes.json"), {"a.zip": {"size": 10, "mtime": 5, "hashes": H}})
        self.new_run()
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)

    def test_hash_cache_misses_when_size_or_mtime_changes(self):
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 11, 5))
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 10, 6))

    def test_hashes_are_written_in_groups_and_by_flush(self):
        self.assertEqual(scrape_state.HASH_FLUSH, 1000)
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertIsNone(self.stored("scrapes/gba/hashes.json"))
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)  # served from memory
        scrape_state.flush()
        self.assertEqual(set(self.stored("scrapes/gba/hashes.json")), {"a.zip"})
        with mock.patch.object(scrape_state, "HASH_FLUSH", 2):
            scrape_state.save_hashes("gba", "b.zip", 1, 1, H)
            self.assertEqual(set(self.stored("scrapes/gba/hashes.json")), {"a.zip"})
            scrape_state.save_hashes("nes", "c.zip", 1, 1, H)  # two pending, across systems
        self.assertEqual(set(self.stored("scrapes/gba/hashes.json")), {"a.zip", "b.zip"})
        self.assertEqual(set(self.stored("scrapes/nes/hashes.json")), {"c.zip"})
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)  # earlier ones are kept

    def test_a_full_hash_group_writes_hashes_only_and_flush_writes_every_kind(self):
        scrape_state.mark_unknown("gba", "u.zip")
        scrape_state.mark_nomedia("gba", "n.zip", {"manuals"})
        with mock.patch.object(scrape_state, "HASH_FLUSH", 1), mock.patch.object(s3, "put_text", wraps=s3.put_text) as put:
            scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
            self.assertEqual([c.args[0] for c in put.call_args_list], ["scrapes/gba/hashes.json"])
            scrape_state.forget_hashes("gba", "a.zip")
            put.reset_mock()
            scrape_state.flush()
            self.assertEqual([c.args[0] for c in put.call_args_list],
                             [f"scrapes/gba/{name}.json" for name in ("unknown", "hashes", "nomedia")])
            put.reset_mock()
            scrape_state.flush()  # nothing left
            put.assert_not_called()
        self.assertEqual(self.stored("scrapes/gba/hashes.json"), {})

    def test_match_round_trip_is_written_at_once_per_system(self):
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        scrape_state.save_match("gba", "a.zip", 42)
        scrape_state.save_match("nes", "Sub/b.zip", 7)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 42)
        self.assertIsNone(scrape_state.manual_match("nes", "a.zip"))
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {"a.zip": 42})
        self.assertEqual(self.stored("scrapes/nes/matches.json"), {"Sub/b.zip": 7})
        self.new_run()
        self.assertEqual(scrape_state.manual_match("nes", "Sub/b.zip"), 7)
        scrape_state.forget_match("gba", "a.zip")
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {})

    def test_move_match_is_one_write(self):
        self.store("scrapes/gba/matches.json", {"a.zip": 42, "c.zip": 7})
        with mock.patch.object(s3, "put_text", wraps=s3.put_text) as put_text:
            scrape_state.move_match("gba", "a.zip", "b.zip")
            scrape_state.move_match("gba", "none.zip", "d.zip")
        self.assertEqual(put_text.call_count, 1)
        self.assertEqual((scrape_state.manual_match("gba", "a.zip"), scrape_state.manual_match("gba", "b.zip")), (None, 42))
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {"b.zip": 42, "c.zip": 7})

    def test_mark_and_clear_notgame(self):
        scrape_state.mark_notgame("fbneo", "bubsys.zip", INFO)
        self.assertEqual(self.stored("scrapes/notgames.json"), {"fbneo/bubsys.zip": INFO})
        self.new_run()
        self.assertEqual(scrape_state.notgames(), {"fbneo/bubsys.zip": INFO})
        self.assertTrue(scrape_state.snapshot().is_notgame("fbneo", "bubsys.zip"))
        scrape_state.clear_notgame("fbneo", "bubsys.zip")
        self.assertEqual(scrape_state.notgames(), {})
        self.assertFalse(scrape_state.snapshot().is_notgame("fbneo", "bubsys.zip"))
        self.assertEqual(self.stored("scrapes/notgames.json"), {})

    def test_keep_unkeep_and_a_new_notgame_mark(self):
        scrape_state.keep("gb", "a.zip")
        scrape_state.keep("gb", "b.zip")
        scrape_state.keep("gb", "c.zip")
        self.assertEqual(self.stored("scrapes/notgames.json"), {"kept": ["gb/a.zip", "gb/b.zip", "gb/c.zip"]})
        scrape_state.unkeep({"gb/a.zip", "gb/zzz.zip"})
        self.assertEqual(scrape_state.kept(), {"gb/b.zip", "gb/c.zip"})
        scrape_state.mark_notgame("gb", "b.zip", INFO)  # a new mark drops the kept one
        scrape_state.clear_notgame("gb", "c.zip")  # not a non-game, but kept: the mark goes
        self.new_run()
        self.assertEqual(scrape_state.kept(), set())
        self.assertEqual(scrape_state.notgames(), {"gb/b.zip": INFO})

    def test_unknown_and_nomedia_round_trip_per_system(self):
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.mark_nomedia("nes", "b.zip", {"manuals", "fanart"})
        self.assertTrue(scrape_state.is_unknown("gba", "a.zip"))  # pending marks are read before a flush
        self.assertEqual(scrape_state.unknown(), {"gba/a.zip"})
        self.assertEqual(scrape_state.nomedia(), {"nes/b.zip": ["fanart", "manuals"]})
        self.assertEqual(scrape_state.snapshot().not_offered("nes", "b.zip"), {"fanart", "manuals"})
        self.assertIsNone(self.stored("scrapes/gba/unknown.json"))
        self.assertIsNone(self.stored("scrapes/nes/nomedia.json"))
        scrape_state.flush()
        self.assertEqual(self.stored("scrapes/gba/unknown.json"), {"a.zip": True})
        self.assertEqual(self.stored("scrapes/nes/nomedia.json"), {"b.zip": ["fanart", "manuals"]})
        self.new_run()
        self.assertEqual(scrape_state.unknown(), {"gba/a.zip"})
        scrape_state.mark_nomedia("nes", "b.zip", set())  # none forgets it
        self.assertEqual(scrape_state.nomedia(), {})
        scrape_state.flush()
        self.assertEqual(self.stored("scrapes/nes/nomedia.json"), {})

    # merging with another writer

    def test_flush_merges_into_storage_changed_by_another_machine(self):
        self.store("scrapes/gba/unknown.json", {"old.zip": True, "gone.zip": True})
        self.assertTrue(scrape_state.is_unknown("gba", "old.zip"))  # loaded
        self.store("scrapes/gba/unknown.json", {"old.zip": True, "gone.zip": True, "theirs.zip": True})
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.mark_unknown("gba", "b.zip")
        scrape_state.clear_unknown("gba", "b.zip")  # a mark, then a clear
        scrape_state.clear_unknown("gba", "gone.zip")
        scrape_state.flush_unknown()
        self.assertEqual(self.stored("scrapes/gba/unknown.json"), {"old.zip": True, "theirs.zip": True, "a.zip": True})

    def test_two_marks_for_one_rom_keep_the_last(self):
        self.store("scrapes/gba/nomedia.json", {"x.zip": ["manuals"]})
        scrape_state.mark_nomedia("gba", "a.zip", {"manuals"})
        scrape_state.mark_nomedia("gba", "a.zip", {"fanart"})
        self.store("scrapes/gba/nomedia.json", {"x.zip": ["manuals"], "y.zip": ["fanart"]})
        scrape_state.flush()
        self.assertEqual(self.stored("scrapes/gba/nomedia.json"), {"x.zip": ["manuals"], "y.zip": ["fanart"], "a.zip": ["fanart"]})

    def test_match_and_notgame_writes_merge(self):
        scrape_state.save_match("gba", "a.zip", 1)
        scrape_state.mark_notgame("gba", "n.zip", INFO)
        self.store("scrapes/gba/matches.json", {"a.zip": 1, "theirs.zip": 2})
        self.store("scrapes/notgames.json", {"gba/n.zip": INFO, "gba/t.zip": INFO, "kept": ["gba/k.zip"]})
        scrape_state.save_match("gba", "b.zip", 3)
        scrape_state.clear_notgame("gba", "n.zip")
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {"a.zip": 1, "b.zip": 3, "theirs.zip": 2})
        self.assertEqual(self.stored("scrapes/notgames.json"), {"gba/t.zip": INFO, "kept": ["gba/k.zip"]})

    def test_clear_unknown_of_a_system_or_all_touches_only_those(self):
        scrape_state.mark_unknown("gb", "a.zip")
        scrape_state.mark_unknown("gba", "b.zip")
        scrape_state.mark_unknown("nes", "c.zip")
        scrape_state.flush_unknown()
        scrape_state.mark_unknown("gb", "d.zip")  # pending, cleared with its system
        scrape_state.clear_unknown("gb")
        self.assertFalse(scrape_state.is_unknown("gb", "a.zip"))
        self.assertFalse(scrape_state.is_unknown("gb", "d.zip"))
        self.assertTrue(scrape_state.is_unknown("gba", "b.zip"))
        self.assertEqual(self.stored("scrapes/gb/unknown.json"), {})
        self.assertEqual(self.stored("scrapes/gba/unknown.json"), {"b.zip": True})
        scrape_state.flush_unknown()
        self.assertEqual(self.stored("scrapes/gb/unknown.json"), {})
        self.new_run()
        scrape_state.clear_unknown()
        self.assertFalse(scrape_state.is_unknown("gba", "b.zip"))
        self.assertFalse(scrape_state.is_unknown("nes", "c.zip"))
        self.assertEqual(self.stored("scrapes/nes/unknown.json"), {})

    def test_clear_unknown_of_a_system_also_clears_entries_another_machine_added(self):
        self.store("scrapes/gba/unknown.json", {"a.zip": True})
        self.assertTrue(scrape_state.is_unknown("gba", "a.zip"))  # loaded
        self.store("scrapes/gba/unknown.json", {"a.zip": True, "theirs.zip": True})
        scrape_state.clear_unknown("gba")  # clears the system, not only the entries this run knew
        self.assertEqual(self.stored("scrapes/gba/unknown.json"), {})

    def test_clear_unknown_one_rom_only(self):
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.mark_unknown("gba", "b.zip")
        scrape_state.clear_unknown("gba", "a.zip")
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertTrue(scrape_state.is_unknown("gba", "b.zip"))

    # failures and bad files

    def test_write_failure_only_warns_and_keeps_the_run_state(self):
        with mock.patch.object(s3, "put_text", side_effect=OSError("share gone")), \
                mock.patch.object(scrape_state.ui, "warn") as warn:
            scrape_state.save_match("gba", "a.zip", 5)
            scrape_state.mark_unknown("gba", "b.zip")
            scrape_state.flush_unknown()
            scrape_state.mark_notgame("gba", "c.zip", INFO)
        self.assertEqual(warn.call_count, 3)
        self.assertIn("scrapes/gba/matches.json", warn.call_args_list[0].args[0])
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 5)
        self.assertTrue(scrape_state.is_unknown("gba", "b.zip"))
        self.assertIn("gba/c.zip", scrape_state.notgames())
        scrape_state.flush_unknown()  # the failed marks were dropped, not retried
        self.assertIsNone(self.stored("scrapes/gba/unknown.json"))

    def test_unmounted_share_is_not_written(self):
        scrape_state.manual_match("gba", "a.zip")
        missing = os.path.join(self.tmp.name, "unmounted")
        with mock.patch.object(runtime, "ROOT", missing), mock.patch.object(scrape_state.ui, "warn") as warn:
            scrape_state.save_match("gba", "a.zip", 5)
        self.assertIn("is missing", warn.call_args.args[0])
        self.assertFalse(os.path.exists(missing))
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 5)

    def test_bool_is_not_a_game_id(self):
        self.store("scrapes/gba/matches.json", '{"a.zip": true}')
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        for bad in (True, False, "7", 0, -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scrape_state.save_match("gba", "a.zip", bad)

    def test_corrupt_matches_file_warns_once(self):
        self.store("scrapes/gba/matches.json", "{nope")
        self.store("scrapes/gba/unknown.json", "{nope")
        with mock.patch.object(scrape_state.ui, "warn") as warn:
            scrape_state.manual_match("gba", "a.zip")
            scrape_state.manual_match("gba", "b.zip")
            scrape_state.is_unknown("gba", "a.zip")
        warn.assert_called_once()
        self.assertIn("scrapes/gba/matches.json isn't a valid JSON object", warn.call_args.args[0])
        self.assertIn("the next `scrape match` replaces it", warn.call_args.args[0])

    def test_corrupt_notgames_file_warns_once_and_is_replaced(self):
        self.store("scrapes/notgames.json", "[1]")
        with mock.patch.object(scrape_state.ui, "warn") as warn:
            self.assertEqual(scrape_state.notgames(), {})
            self.assertEqual(scrape_state.kept(), set())
        warn.assert_called_once()
        self.assertIn("scrapes/notgames.json isn't a valid JSON object", warn.call_args.args[0])
        scrape_state.mark_notgame("gba", "n.zip", INFO)
        self.assertEqual(self.stored("scrapes/notgames.json"), {"gba/n.zip": INFO})

    def test_removals_never_create_an_empty_file(self):
        scrape_state.clear_unknown("gba", "found.zip")  # what a scraped ROM gets
        scrape_state.mark_unknown("gba", "x.zip")
        scrape_state.clear_unknown("gba", "x.zip")  # a mark, then a clear, in one run
        scrape_state.flush_unknown()
        scrape_state.mark_nomedia("gba", "found.zip", set())
        scrape_state.flush()
        scrape_state.clear_unknown("nes")
        self.assertEqual(os.listdir(self.root), [])

    def test_failed_write_does_not_claim_the_changes_are_lost(self):
        with mock.patch.object(shared, "_save_mirror", side_effect=OSError("disk full")), \
                mock.patch.object(scrape_state.ui, "warn") as warn:
            scrape_state.save_match("gba", "a.zip", 5)
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {"a.zip": 5})
        self.assertNotIn("not kept", warn.call_args.args[0])
        self.assertIn("may not be in storage", warn.call_args.args[0])

    def test_corrupt_file_reads_as_empty_and_is_replaced(self):
        for name in ("hashes", "matches", "unknown", "nomedia"):
            self.store(f"scrapes/gba/{name}.json", "{nope")
        self.store("scrapes/notgames.json", "[1]")
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 1, 1))
        with mock.patch.object(scrape_state.ui, "warn"):
            self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertEqual((scrape_state.notgames(), scrape_state.kept(), scrape_state.nomedia()), ({}, set(), {}))
        scrape_state.save_match("gba", "a.zip", 1)
        self.assertEqual(self.stored("scrapes/gba/matches.json"), {"a.zip": 1})

    def test_kept_list_with_bad_entries_is_read_as_its_strings(self):
        self.store("scrapes/notgames.json", {"kept": [["x"], {"y": 1}, 3, "gb/a.zip"]})
        self.assertEqual(scrape_state.kept(), {"gb/a.zip"})

    def test_reads_come_from_the_mirror_once_per_run(self):
        self.store("scrapes/gba/matches.json", {"a.zip": 3})
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 3)
        scrape_state.snapshot()  # reads notgames.json
        with mock.patch.object(shared, "load", side_effect=AssertionError("loaded again")):
            self.assertEqual(scrape_state.manual_match("gba", "b.zip"), None)
            scrape_state.snapshot()
        self.assertTrue(os.path.exists(shared.local_path("scrapes/gba/matches.json")))

    def test_a_file_the_storage_cache_does_not_list_is_not_looked_for(self):
        self.store("scrapes/gba/matches.json", {"a.zip": 3})
        tree = inventory.Tree(inventory.source(), 0, {"scrapes/gba/matches.json": 12}, {})
        with mock.patch.object(inventory, "current", return_value=tree), \
                mock.patch.object(inventory, "files", lambda prefix, sizes=True: tree.under(prefix)):
            self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 3)
            with mock.patch.object(shared, "load", side_effect=AssertionError("looked for")):
                self.assertIsNone(scrape_state.manual_match("gb", "a.zip"))
                self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))

    def test_without_a_storage_cache_every_file_is_looked_for(self):
        self.store("scrapes/gb/matches.json", {"a.zip": 4})
        with mock.patch.object(inventory, "current", return_value=None), \
                mock.patch.object(inventory, "files", side_effect=AssertionError("listed")):
            self.assertEqual(scrape_state.manual_match("gb", "a.zip"), 4)

    def test_another_data_folder_starts_afresh(self):
        scrape_state.save_match("gba", "a.zip", 3)
        os.remove(os.path.join(self.root, "scrapes/gba/matches.json"))
        with mock.patch.object(scrape_state.store, "data_dir", return_value=os.path.join(self.tmp.name, "other")):
            self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))


class CleanTest(unittest.TestCase):
    def test_clean_keeps_the_scrape_state_files(self):
        existing = {f"scrapes/gba/{n}.json": 5 for n in ("matches", "unknown", "nomedia", "hashes")}
        existing["scrapes/notgames.json"] = 5
        delete, rewrites, per, warnings = scrape_files.plan_clean(existing, {"gba": set()}, {})
        self.assertEqual((delete, rewrites, warnings), ([], [], []))

    def test_clean_scrapes_removes_spruce_art_of_a_gone_rom(self):
        existing = {f"scrapes/gba/{t}/gone.qoi": 5 for t in ("spruce", "spruce_med", "spruce_small")}
        existing.update({f"scrapes/gba/{t}/a.qoi": 5 for t in ("spruce", "spruce_med", "spruce_small")})
        delete = scrape_files.plan_clean(existing, {"gba": {"a.zip"}}, {})[0]
        self.assertEqual(sorted(delete), sorted(f"scrapes/gba/{t}/gone.qoi" for t in ("spruce", "spruce_med", "spruce_small")))


class CleanBadMetadataTest(StorageDir):
    """clean scrapes with a metadata.json that can't be used: the file is left alone, the system's media is still cleaned."""
    META = "scrapes/gba/metadata.json"

    def test_metadata_that_is_not_an_object_is_skipped_like_invalid_json(self):
        self.put("gba/a.zip")
        self.put("scrapes/gba/covers/a.png")
        self.put("scrapes/gba/covers/gone.png")
        inventory.reset()
        self.addCleanup(inventory.reset)
        for text in ("{nope", "[]", '["a.zip"]', '[{"name": "A"}]', "5", '"a.zip"', "null"):
            with self.subTest(text=text):
                self.put(self.META, text.encode())
                out = io.StringIO()
                with mock.patch.object(scrape_files.store, "load_manifest", return_value={"systems": [{"bucket": "gba"}]}), \
                        contextlib.redirect_stdout(out):
                    self.assertEqual(scrape_files.clean_scrapes(mock.Mock(dry_run=True)), 0)
                self.assertIn(f"⚠️  {self.META} isn't valid JSON, skipped", out.getvalue())
                self.assertIn("gba: 1 media file(s) (3 B), 0 metadata entries", out.getvalue())
                self.assertIn("scrapes/gba/covers/gone.png", out.getvalue())

    def test_plan_leaves_such_a_file_out_of_the_deletes_and_rewrites(self):
        for text in ("{nope", "[]", '["a.zip"]', "5", '"a.zip"', "null"):
            with self.subTest(text=text):
                self.assertEqual(scrape_files.metadata_roms({self.META: text}), set())
                delete, rewrites, per, warnings = scrape_files.plan_clean({self.META: 9}, {"gba": {"a.zip"}}, {self.META: text})
                self.assertEqual((delete, rewrites, dict(per)), ([], [], {}))
                self.assertEqual(warnings, [f"{self.META} isn't valid JSON, skipped"])


class CleanStaleCacheTest(StorageDir):
    """--clean-scrapes with a storage cache built before another machine added gba/new.zip and scraped it."""
    META = "scrapes/gba/metadata.json"

    def setUp(self):
        super().setUp()
        self.put("gba/a.zip")
        self.put(self.META, json.dumps({"a.zip": {"name": "A"}, "gone.zip": {"name": "Gone"}}).encode())
        inventory.reset()
        self.addCleanup(inventory.reset)
        with contextlib.redirect_stdout(io.StringIO()):
            inventory.update()
        self.put("gba/new.zip")
        self.put(self.META, json.dumps({"a.zip": {"name": "A"}, "gone.zip": {"name": "Gone"},
                                        "new.zip": {"name": "New"}}).encode())

    def clean(self):
        """Run it, saying yes; returns (what it printed, the ROMs metadata.json has entries for afterwards)."""
        out = io.StringIO()
        with mock.patch.object(scrape_files.store, "load_manifest", return_value={"systems": [{"bucket": "gba"}]}), \
                mock.patch.object(scrape_files.ui, "confirm", return_value=True), contextlib.redirect_stdout(out):
            self.assertEqual(scrape_files.clean_scrapes(mock.Mock(dry_run=False)), 0)
        return out.getvalue(), sorted(self.read_json(self.META))

    def test_clean_keeps_the_entry_of_a_rom_the_cache_lacks(self):
        said, entries = self.clean()
        self.assertEqual(entries, ["a.zip", "new.zip"])  # gone.zip is in neither: dropped
        self.assertIn("1 ROM(s) are in storage but not in the storage cache", said)
        self.assertIn("sync-roms cache update", said)

    def test_clean_drops_the_entry_of_an_ignored_rom_the_cache_lacks(self):
        with mock.patch.object(ignore, "_keys", frozenset({"gba/new.zip"})):
            self.assertEqual(self.clean()[1], ["a.zip"])


if __name__ == "__main__":
    unittest.main()
