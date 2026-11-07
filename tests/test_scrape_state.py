import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import scrape_state, store  # noqa: E402

H = {"md5": "a", "sha1": "b", "crc": "c"}


class ScrapeStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(store, "data_dir", return_value=self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def test_hashes_round_trip(self):
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 10, 5))
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertEqual(scrape_state.cached_hashes("gba", "a.zip", 10, 5), H)

    def test_hash_cache_misses_when_size_or_mtime_changes(self):
        scrape_state.save_hashes("gba", "a.zip", 10, 5, H)
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 11, 5))
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 10, 6))

    def test_match_round_trip(self):
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        scrape_state.save_match("gba", "a.zip", 42)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 42)
        self.assertIsNone(scrape_state.manual_match("nes", "a.zip"))

    def test_unknown_round_trip(self):
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        scrape_state.mark_unknown("gba", "a.zip")
        self.assertTrue(scrape_state.is_unknown("gba", "a.zip"))

    def test_clear_unknown_one_system_only(self):
        scrape_state.mark_unknown("gba", "a.zip")
        scrape_state.mark_unknown("nes", "b.zip")
        scrape_state.clear_unknown("gba")
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        self.assertTrue(scrape_state.is_unknown("nes", "b.zip"))
        scrape_state.clear_unknown()
        self.assertFalse(scrape_state.is_unknown("nes", "b.zip"))

    def test_corrupt_file_reads_as_empty(self):
        for name in ("scrape-hashes.json", "scrape-matches.json", "scrape-unknown.json"):
            with open(os.path.join(self.tmp.name, name), "w") as f:
                f.write("{nope")
        self.assertIsNone(scrape_state.cached_hashes("gba", "a.zip", 1, 1))
        self.assertIsNone(scrape_state.manual_match("gba", "a.zip"))
        self.assertFalse(scrape_state.is_unknown("gba", "a.zip"))
        scrape_state.save_match("gba", "a.zip", 1)
        self.assertEqual(scrape_state.manual_match("gba", "a.zip"), 1)


if __name__ == "__main__":
    unittest.main()
