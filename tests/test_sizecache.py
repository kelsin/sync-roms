import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import runtime, s3, sizecache  # noqa: E402


class FakeStore:
    """Stands in for s3 listing and stat: files is {key: size}; counts the stats made."""

    def __init__(self, files):
        self.files = dict(files)
        self.stats = []
        self.fail = False

    def list_sizes(self, prefix, sizes=True):
        if self.fail:
            raise OSError("share is gone")
        return {k: (v if sizes else None) for k, v in self.files.items() if k.startswith(prefix)}

    def stat_sizes(self, keys):
        keys = list(keys)
        self.stats.extend(keys)
        return {k: self.files[k] for k in keys if k in self.files}


class SizeCacheTest(helpers.DataDir):
    def setUp(self):
        super().setUp()
        self.fake = FakeStore({"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3})
        self.now = 1000.0
        for target, value in (("list_sizes", self.fake.list_sizes), ("stat_sizes", self.fake.stat_sizes),
                              ("location", lambda: "/nas"),
                              ("read_root", lambda: "/nas")):
            p = mock.patch.object(s3, target, value)
            p.start()
            self.addCleanup(p.stop)
        for target, value in (("_clock", lambda: self.now), ("_sample", lambda pop, n: list(pop)[:n]),
                              ("_is_folder", lambda path: True)):
            p = mock.patch.object(sizecache, target, value)
            p.start()
            self.addCleanup(p.stop)

    def test_uncached_is_none_then_first_refresh_fills(self):
        self.assertIsNone(sizecache.cached("gba/"))
        self.assertEqual(sizecache.refresh("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3})
        self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3})

    def test_second_refresh_stats_only_the_new_file(self):
        sizecache.refresh("gba/")
        del self.fake.files["gba/a.zip"]
        self.fake.files["gba/d.zip"] = 4
        self.fake.stats.clear()
        self.assertEqual(sizecache.refresh("gba/"), {"gba/b.zip": 2, "gba/c.zip": 3, "gba/d.zip": 4})
        self.assertEqual(self.fake.stats, ["gba/b.zip", "gba/c.zip", "gba/d.zip"])  # spot checks plus the one new file
        self.assertEqual(sizecache.cached("gba/"), {"gba/b.zip": 2, "gba/c.zip": 3, "gba/d.zip": 4})

    def test_spot_check_mismatch_rebuilds(self):
        sizecache.refresh("gba/")
        self.fake.files["gba/b.zip"] = 20
        self.assertEqual(sizecache.refresh("gba/")["gba/b.zip"], 20)

    def test_spot_check_missing_file_rebuilds(self):
        sizecache.refresh("gba/")
        names = dict.fromkeys(self.fake.files)
        with mock.patch.object(s3, "stat_sizes", lambda keys: {}), \
                mock.patch.object(s3, "list_sizes", lambda p, sizes=True: dict(self.fake.files) if sizes else names):
            self.assertEqual(sizecache.refresh("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3})

    def test_old_entry_rebuilds_and_fresh_one_does_not(self):
        sizecache.refresh("gba/")
        self.now += sizecache.MAX_AGE
        self.fake.stats.clear()
        sizecache.refresh("gba/")
        self.assertTrue(self.fake.stats)  # exactly at the limit: still fresh, so spot checks ran
        self.now += sizecache.MAX_AGE + 1
        self.fake.stats.clear()
        with mock.patch.object(s3, "list_sizes", wraps=s3.list_sizes) as ls:
            sizecache.refresh("gba/")
        self.assertIn(mock.call("gba/"), ls.call_args_list)  # older than 30 days: full listing with sizes
        self.assertEqual(self.fake.stats, [])

    def test_incremental_keeps_built_and_old_built_rebuilds(self):
        sizecache.refresh("gba/")
        self.now += 100
        self.fake.files["gba/d.zip"] = 4
        sizecache.refresh("gba/")
        self.assertEqual(self.read("sizes.json")["prefixes"]["gba/"]["built"], 1000.0)
        self.now = 1000.0 + sizecache.MAX_AGE + 1
        self.fake.files["gba/b.zip"] = 99
        with mock.patch.object(sizecache, "_sample", lambda pop, n: []):
            sizecache.refresh("gba/")
        self.assertEqual(self.read("sizes.json")["prefixes"]["gba/"]["built"], self.now)
        self.assertEqual(sizecache.cached("gba/")["gba/b.zip"], 99)

    def test_missing_built_counts_as_old(self):
        self.write_json("sizes.json", {"source": "/nas", "prefixes": {"gba/": {"files": {"gba/a.zip": 50}}}})
        self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 50})
        self.now = sizecache.MAX_AGE + 1
        with mock.patch.object(sizecache, "_sample", lambda pop, n: []):
            self.assertEqual(sizecache.refresh("gba/")["gba/a.zip"], 1)

    def test_bucket_mode_never_stats(self):
        def boom(keys):
            raise TypeError("stat_sizes needs a folder")
        with mock.patch.object(s3, "read_root", lambda: None), mock.patch.object(s3, "stat_sizes", boom):
            sizecache.refresh("gba/")
            del self.fake.files["gba/a.zip"]
            self.fake.files["gba/d.zip"] = 4
            self.assertEqual(sizecache.refresh("gba/"), {"gba/b.zip": 2, "gba/c.zip": 3, "gba/d.zip": 4})
            self.fake.files["gba/b.zip"] = 20  # a changed size is caught by the spot check
            self.assertEqual(sizecache.refresh("gba/")["gba/b.zip"], 20)

    def test_bucket_mode_takes_every_size_from_the_listing(self):
        for n in range(4, 9):
            self.fake.files[f"gba/{n}.zip"] = n
        with mock.patch.object(s3, "read_root", lambda: None):
            sizecache.refresh("gba/")
            self.fake.files["gba/8.zip"] = 80  # past the 5 spot checks: still picked up from the listing
            self.assertEqual(sizecache.refresh("gba/")["gba/8.zip"], 80)

    def test_interleaved_refreshes_of_two_prefixes_both_survive(self):
        self.fake.files["nes/z.zip"] = 7
        real = self.fake.list_sizes
        done = []

        def listing(prefix, sizes=True):
            if prefix == "gba/" and not done:
                done.append(1)
                sizecache.refresh("nes/")  # finishes while gba is still being listed
            return real(prefix, sizes)
        with mock.patch.object(s3, "list_sizes", listing):
            sizecache.refresh("gba/")
        self.assertEqual(sizecache.cached("nes/"), {"nes/z.zip": 7})
        self.assertEqual(len(sizecache.cached("gba/")), 3)

    def test_corrupt_file_is_empty(self):
        with open(self.path("sizes.json"), "w") as f:
            f.write("{nope")
        self.assertIsNone(sizecache.cached("gba/"))
        self.assertEqual(sizecache.refresh("gba/")["gba/a.zip"], 1)

    def test_wrong_shape_is_empty(self):
        self.write_json("sizes.json", {"source": "/nas", "prefixes": {"gba/": "x"}})
        self.assertIsNone(sizecache.cached("gba/"))
        self.write_json("sizes.json", [1])
        self.assertIsNone(sizecache.cached("gba/"))

    def test_an_older_file_with_a_source_still_loads(self):
        self.write_json("sizes.json", {"source": "s3://other", "prefixes": {"gba/": {"built": 1, "files": {"gba/x": 9}}}})
        self.assertEqual(sizecache.cached("gba/"), {"gba/x": 9})
        self.now = 1000.0 + sizecache.MAX_AGE + 10  # old: rebuilt from the listing, the removed file dropped
        sizecache.refresh("gba/")
        self.assertNotIn("source", self.read("sizes.json"))
        self.assertNotIn("gba/x", sizecache.cached("gba/"))

    def test_other_prefixes_survive_a_refresh(self):
        self.fake.files["nes/z.zip"] = 7
        sizecache.refresh("nes/")
        sizecache.refresh("gba/")
        self.assertEqual(sizecache.cached("nes/"), {"nes/z.zip": 7})

    def test_async_calls_on_done_with_result(self):
        got = []
        sizecache.refresh_async("gba/", got.append).join(5)
        self.assertEqual(got, [{"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3}])

    def test_async_failure_falls_back_to_cache(self):
        sizecache.refresh("gba/")
        self.fake.fail = True
        got = []
        sizecache.refresh_async("gba/", got.append).join(5)
        self.assertEqual(got, [{"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3}])
        got.clear()
        sizecache.refresh_async("nes/", got.append).join(5)
        self.assertEqual(got, [{}])


    def test_entries_are_shared_by_every_source(self):
        sizecache.refresh("gba/")  # read from the /nas folder
        with mock.patch.object(s3, "read_root", return_value=None), mock.patch.object(s3, "location",
                                                                                     return_value="s3://b"):
            self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3})

    def test_a_mirror_refresh_adds_and_updates_but_never_drops(self):
        sizecache.refresh("gba/")
        self.fake.files = {"gba/a.zip": 100, "gba/new.zip": 4}  # the mirror has only some files
        with mock.patch.object(runtime, "_mirror_root", "/mirror"), \
                mock.patch.object(s3, "read_root", return_value="/mirror"):
            sizecache.refresh("gba/")  # the spot check sees a.zip changed: rebuilt, merged into what was there
            self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 100, "gba/b.zip": 2, "gba/c.zip": 3,
                                                        "gba/new.zip": 4})
            self.fake.files["gba/more.zip"] = 5
            sizecache.refresh("gba/")  # incremental: adds the new name, keeps the ones the mirror lacks
            self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 100, "gba/b.zip": 2, "gba/c.zip": 3,
                                                        "gba/new.zip": 4, "gba/more.zip": 5})
            self.now += sizecache.MAX_AGE + 10  # old: rebuilt, still merged
            sizecache.refresh("gba/")
            self.assertIn("gba/b.zip", sizecache.cached("gba/"))
        sizecache.refresh("gba/")  # the storage folder itself: removed files drop
        self.assertNotIn("gba/b.zip", sizecache.cached("gba/"))

    def test_a_missing_storage_folder_keeps_the_cache(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "nas")
            os.makedirs(root)
            with mock.patch.object(s3, "read_root", return_value=root), \
                    mock.patch.object(sizecache, "_is_folder", os.path.isdir):
                sizecache.refresh("gba/")
                os.rename(root, root + ".gone")  # the share is unmounted: its listing would be empty
                self.fake.files = {}
                with self.assertRaises(FileNotFoundError):
                    sizecache.refresh("gba/")
                got = []
                sizecache.refresh_async("gba/", got.append).join(5)
        self.assertEqual(got, [{"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3}])
        self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2, "gba/c.zip": 3})

    def test_an_empty_listing_never_replaces_cached_sizes(self):
        sizecache.refresh("gba/")
        self.write_json("sizes.json", {"prefixes": {"gba/": {"built": 500.0, "files": {"gba/a.zip": 1}}}})
        self.fake.files = {}  # an unmounted share on Linux lists as an empty folder
        with self.assertRaises(FileNotFoundError):
            sizecache.refresh("gba/")
        self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 1})
        self.now += sizecache.MAX_AGE + 1  # an old entry is rebuilt, but not from nothing
        with self.assertRaises(FileNotFoundError):
            sizecache.refresh("gba/")
        self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 1})

    def test_bad_sizes_are_dropped(self):
        self.write_json("sizes.json", {"prefixes": {"gba/": {"built": 1, "files": {
            "gba/a.zip": 1, "gba/b.zip": True, "gba/c.zip": "3", "gba/d.zip": None, "gba/e.zip": 2.5}}}})
        self.assertEqual(sizecache.cached("gba/"), {"gba/a.zip": 1})

    def test_async_exit_from_a_worker_still_calls_on_done(self):
        got = []
        with mock.patch.object(sizecache, "refresh", side_effect=SystemExit(3)):
            sizecache.refresh_async("gba/", got.append).join(5)
        self.assertEqual(got, [{}])


if __name__ == "__main__":
    unittest.main()
