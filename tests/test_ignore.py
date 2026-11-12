import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from test_inventory import StorageFolder  # noqa: E402
from sync_roms import ignore, inventory, runtime  # noqa: E402


class IgnoreList(StorageFolder):
    def setUp(self):
        super().setUp()
        ignore.reset()
        self.addCleanup(setattr, ignore, "_keys", frozenset())

    def store_list(self, data, mtime=None):
        path = os.path.join(self.root.name, ignore.KEY)
        with open(path, "w") as f:
            json.dump(data, f)
        if mtime is not None:
            os.utime(path, ns=(mtime, mtime))

    def local(self):
        return self.read(ignore.KEY)

    def load(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            keys = ignore.keys()
        return keys, err.getvalue()


class LoadTest(IgnoreList):
    def test_no_file_in_storage_means_nothing_ignored(self):
        self.assertEqual(ignore.keys(), frozenset())
        self.assertFalse(os.path.exists(self.path(ignore.KEY)))

    def test_reads_storage_file_and_saves_local_copy(self):
        self.store_list({"fbneo": ["bubsys.zip"]})
        self.assertTrue(ignore.is_ignored("fbneo/bubsys.zip"))
        self.assertFalse(ignore.is_ignored("fbneo/sf2.zip"))
        self.assertEqual(self.local()["ignored"], {"fbneo": ["bubsys.zip"]})

    def test_reads_storage_not_mirror(self):
        self.store_list({"gb": ["x.zip"]})
        with tempfile.TemporaryDirectory() as mirror, mock.patch.object(runtime, "_mirror_root", mirror):
            self.assertEqual(ignore.keys(), frozenset({"gb/x.zip"}))

    def test_same_tag_uses_local_copy(self):
        self.store_list({"gb": ["x.zip"]})
        ignore.keys()
        ignore.reset()
        with mock.patch.object(ignore, "_read", side_effect=AssertionError("read again")) as read:
            self.assertEqual(ignore.keys(), frozenset({"gb/x.zip"}))
        read.assert_not_called()

    def test_changed_file_is_downloaded_again(self):
        self.store_list({"gb": ["a.zip"]}, mtime=1_000_000_000_000_000_000)
        ignore.keys()
        self.store_list({"gb": ["b.zip"]}, mtime=1_000_000_001_000_000_000)  # same length, new contents
        ignore.reset()
        self.assertEqual(ignore.keys(), frozenset({"gb/b.zip"}))

    def test_storage_error_falls_back_to_local_copy_with_warning(self):
        self.store_list({"gb": ["a.zip"]})
        ignore.keys()
        ignore.reset()
        with mock.patch.object(inventory, "tag", side_effect=OSError("share offline")):
            keys, err = self.load()
        self.assertEqual(keys, frozenset({"gb/a.zip"}))
        self.assertEqual(err.count("⚠️"), 1)

    def test_unmounted_storage_folder_keeps_local_copy(self):
        self.store_list({"gb": ["a.zip"]})
        ignore.keys()
        ignore.reset()
        with mock.patch.object(runtime, "ROOT", os.path.join(self.root.name, "not-mounted")):
            keys, err = self.load()
        self.assertEqual(keys, frozenset({"gb/a.zip"}))
        self.assertTrue(os.path.exists(self.path(ignore.KEY)))
        self.assertIn("ignored.json", err)

    def test_storage_error_without_local_copy_is_empty(self):
        with mock.patch.object(inventory, "tag", side_effect=OSError("share offline")):
            keys, err = self.load()
        self.assertEqual(keys, frozenset())
        self.assertIn("ignored.json", err)

    def test_invalid_json_in_storage_falls_back(self):
        with open(os.path.join(self.root.name, ignore.KEY), "w") as f:
            f.write("{nope")
        keys, err = self.load()
        self.assertEqual(keys, frozenset())
        self.assertIn("ignored.json", err)

    def test_malformed_parts_are_skipped(self):
        self.store_list({"gb": ["a.zip", 3], "nds": "b.zip", "gba": ["c.zip"]})
        self.assertEqual(ignore.keys(), frozenset({"gb/a.zip", "gba/c.zip"}))

    def test_storage_file_removed_drops_local_copy(self):
        self.store_list({"gb": ["a.zip"]})
        ignore.keys()
        os.remove(os.path.join(self.root.name, ignore.KEY))
        ignore.reset()
        self.assertEqual(ignore.keys(), frozenset())
        self.assertFalse(os.path.exists(self.path(ignore.KEY)))


class AddTest(IgnoreList):
    def test_add_merges_sorted_and_counts_new(self):
        self.store_list({"nds": ["b.zip"]})
        self.assertEqual(ignore.add({"nds": ["a.zip", "b.zip"], "gb": ["c.zip"]}), 2)
        with open(os.path.join(self.root.name, ignore.KEY)) as f:
            self.assertEqual(json.load(f), {"gb": ["c.zip"], "nds": ["a.zip", "b.zip"]})
        self.assertTrue(ignore.is_ignored("nds/a.zip"))
        self.assertEqual(self.local()["ignored"], {"gb": ["c.zip"], "nds": ["a.zip", "b.zip"]})

    def test_add_creates_the_file(self):
        self.assertEqual(ignore.add({"gb": ["c.zip"]}), 1)
        self.assertTrue(ignore.is_ignored("gb/c.zip"))


class TagTest(StorageFolder):
    def test_tag_for_folder_changes_with_content(self):
        self.put("gba/t.zip", 2)
        first = inventory.tag("gba/t.zip")
        self.put("gba/t.zip", 3)
        self.assertNotEqual(inventory.tag("gba/t.zip"), first)
        self.assertIsNotNone(first)

    def test_tag_missing_is_none(self):
        self.assertIsNone(inventory.tag("nope.json"))


if __name__ == "__main__":
    unittest.main()
