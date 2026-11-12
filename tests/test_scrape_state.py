import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import scrape_state  # noqa: E402

H = {"md5": "a", "sha1": "b", "crc": "c"}


class ScrapeStateTest(DataDir):
    def test_hashes_round_trip(self):
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 10, 5))
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)

    def test_hash_cache_misses_when_size_or_mtime_changes(self):
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 11, 5))
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 10, 6))

    def test_hashes_are_written_in_groups_and_by_flush(self):
        path = os.path.join(self.tmp.name, "scrape-hashes.json")
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)  # served from memory
        scrape_state.flush_hashes()
        self.assertTrue(os.path.exists(path))
        with mock.patch.object(scrape_state, "HASH_FLUSH", 2):
            scrape_state.save_hashes("gba", "b.zip", 1, 1, H)
            mtime = os.stat(path).st_mtime_ns
            scrape_state.save_hashes("gba", "c.zip", 1, 1, H)
        self.assertNotEqual(os.stat(path).st_mtime_ns, mtime)
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)  # earlier ones are kept

    def test_unchanged_file_is_not_parsed_again(self):
        scrape_state.save_match("gba", "a.zip", 1)
        with mock.patch.object(scrape_state, "_read", side_effect=AssertionError("parsed again")):
            self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 1)

    def test_match_round_trip(self):
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        scrape_state.save_match("gba", "a.zip", 42)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 42)
        self.assertIsNone(scrape_state.manual_match("nes", "a.zip"))

    def test_mark_and_clear_notgame(self):
        info = {"name": "Bios", "genre": "", "year": "1985", "desc": ""}
        scrape_state.mark_notgame("fbneo", "bubsys.zip", info)
        scrape_state._cache.clear()  # read back from disk
        self.assertEqual(scrape_state.notgames(), {"fbneo/bubsys.zip": info})
        self.assertTrue(scrape_state.snapshot().is_notgame("fbneo", "bubsys.zip"))
        scrape_state.clear_notgame("fbneo", "bubsys.zip")
        self.assertEqual(scrape_state.notgames(), {})
        self.assertFalse(scrape_state.snapshot().is_notgame("fbneo", "bubsys.zip"))

    def test_unknown_round_trip(self):
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        scrape_state.mark_unknown("gba", "a.zip")
        self.assertTrue(scrape_state.is_unknown("gba", "a.zip"))

    def test_clear_unknown_one_system_only(self):
        scrape_state.mark_unknown("gb", "a.zip")
        scrape_state.mark_unknown("gba", "b.zip")
        scrape_state.mark_unknown("nes", "c.zip")
        scrape_state.clear_unknown("gb")
        self.assertFalse(scrape_state.is_unknown("gb", "a.zip"))
        self.assertTrue(scrape_state.is_unknown("gba", "b.zip"))
        self.assertTrue(scrape_state.is_unknown("nes", "c.zip"))
        scrape_state.clear_unknown()
        self.assertFalse(scrape_state.is_unknown("gba", "b.zip"))
        self.assertFalse(scrape_state.is_unknown("nes", "c.zip"))

    def test_second_save_keeps_the_first(self):
        scrape_state.save_match("gba", "a.zip", 1)
        scrape_state.save_match("gba", "b.zip", 2)
        self.assertEqual((scrape_state.manual_match("gba", "a.zip"), scrape_state.manual_match("gba", "b.zip")), (1, 2))
        scrape_state.save_hashes("gba", "a.zip", 1, 1, H)
        scrape_state.save_hashes("gba", "b.zip", 2, 2, H)
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 1, 1), H)
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.mark_unknown("gba", "b.zip")
        self.assertTrue(scrape_state.is_unknown("gba", "a.zip"))

    def test_bool_is_not_a_game_id(self):
        with open(os.path.join(self.tmp.name, "scrape-matches.json"), "w") as f:
            f.write('{"gba/a.zip": true}')
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        for bad in (True, False, "7", 0, -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scrape_state.save_match("gba", "a.zip", bad)

    def test_corrupt_matches_file_warns_once(self):
        with open(os.path.join(self.tmp.name, "scrape-matches.json"), "w") as f:
            f.write("{nope")
        with mock.patch.object(scrape_state.ui, "warn") as warn:
            scrape_state.manual_match("gba", "a.zip")
            scrape_state.manual_match("gba", "b.zip")
        warn.assert_called_once()
        self.assertIn("scrape-matches.json", warn.call_args.args[0])
        with open(os.path.join(self.tmp.name, "scrape-unknown.json"), "w") as f:
            f.write("{nope")
        with mock.patch.object(scrape_state.ui, "warn") as warn:
            scrape_state.is_unknown("gba", "a.zip")
        warn.assert_not_called()

    def test_clear_unknown_one_rom_only(self):
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.mark_unknown("gba", "b.zip")
        scrape_state.clear_unknown("gba", "a.zip")
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertTrue(scrape_state.is_unknown("gba", "b.zip"))

    def test_save_uses_a_unique_temp_file(self):
        os.makedirs(os.path.join(self.tmp.name, "scrape-matches.json.tmp"))  # a fixed temp name would be blocked
        scrape_state.save_match("gba", "a.zip", 1)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 1)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["scrape-matches.json", "scrape-matches.json.tmp"])

    def test_corrupt_file_reads_as_empty(self):
        for name in ("scrape-hashes.json", "scrape-matches.json", "scrape-unknown.json"):
            with open(os.path.join(self.tmp.name, name), "w") as f:
                f.write("{nope")
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 1, 1))
        with mock.patch.object(scrape_state.ui, "warn"):
            self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        scrape_state.save_match("gba", "a.zip", 1)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 1)


if __name__ == "__main__":
    unittest.main()
