import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from test_inventory import StorageFolder  # noqa: E402
import tempfile  # noqa: E402
from sync_roms import inventory, names, runtime  # noqa: E402


class Names(StorageFolder):
    def setUp(self):
        super().setUp()
        names.reset()
        self.addCleanup(setattr, names, "_scraped", {s: {} for s in names.SYSTEMS})

    def metadata(self, data, system="mame", mtime=None):
        path = os.path.join(self.root.name, "scrapes", system, "metadata.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        if mtime is not None:
            os.utime(path, ns=(mtime, mtime))

    def lookup(self, key):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            return names.title(key), err.getvalue()


class TitleTest(Names):
    def test_clone_gets_dat_name(self):
        self.assertEqual(names.title("fbneo/1941j.zip"), "1941: Counter Attack (Japan)")

    def test_parent_gets_dat_name(self):
        self.assertEqual(names.title("mame/1942.zip"), "1942 (set 1)")

    def test_scraped_name_for_standalone_set(self):
        self.metadata({"zzstand.zip": {"name": "Stand Alone"}})
        self.assertEqual(names.title("mame/zzstand.zip"), "Stand Alone")

    def test_falls_back_to_set_name(self):
        self.assertEqual(names.title("mame/zzstand.zip"), "zzstand")

    def test_other_systems_untouched(self):
        with mock.patch.object(inventory, "tag", side_effect=AssertionError("storage")):
            self.assertEqual(names.title("gba/Some Game.zip"), "Some Game")

    def test_malformed_entries_skipped(self):
        self.metadata({"a.zip": "x", "b.zip": {"name": 3}, "c.zip": {"name": "C"}})
        self.assertEqual([names.title(f"mame/{r}.zip") for r in "abc"], ["a", "b", "C"])

    def test_subfolder_path(self):
        self.metadata({"zzfolder": {"name": "Killer Instinct"}})
        self.assertEqual(names.title("mame/zzfolder"), "Killer Instinct")


class LocalCopyTest(Names):
    def test_saves_local_copy_and_reuses_it_on_same_tag(self):
        self.metadata({"zzstand.zip": {"name": "Stand Alone"}})
        names.title("mame/zzstand.zip")
        self.assertEqual(self.read(names.KEY)["mame"]["names"], {"zzstand.zip": "Stand Alone"})
        names.reset()
        with mock.patch.object(names, "_read", side_effect=AssertionError("read again")):
            self.assertEqual(names.title("mame/zzstand.zip"), "Stand Alone")

    def test_rereads_on_tag_change(self):
        self.metadata({"zzstand.zip": {"name": "Old"}}, mtime=1_000_000_000_000_000_000)
        self.assertEqual(names.title("mame/zzstand.zip"), "Old")
        self.metadata({"zzstand.zip": {"name": "New"}}, mtime=1_000_000_001_000_000_000)
        names.reset()
        self.assertEqual(names.title("mame/zzstand.zip"), "New")

    def test_removed_metadata_drops_names(self):
        self.metadata({"zzstand.zip": {"name": "Stand Alone"}})
        names.title("mame/zzstand.zip")
        os.remove(os.path.join(self.root.name, "scrapes", "mame", "metadata.json"))
        names.reset()
        self.assertEqual(names.title("mame/zzstand.zip"), "zzstand")
        self.assertNotIn("mame", self.read(names.KEY))

    def test_storage_error_uses_local_copy_with_warning(self):
        self.metadata({"zzstand.zip": {"name": "Stand Alone"}})
        names.title("mame/zzstand.zip")
        names.reset()
        with mock.patch.object(inventory, "tag", side_effect=OSError("share offline")):
            title, err = self.lookup("mame/zzstand.zip")
        self.assertEqual(title, "Stand Alone")
        self.assertIn("names", err)

    def test_metadata_read_once_per_run(self):
        self.metadata({"zzstand.zip": {"name": "Stand Alone"}})
        with mock.patch.object(names, "_read", wraps=names._read) as read:
            for _ in range(20):
                names.title("mame/zzstand.zip")
        read.assert_called_once()

    def test_reads_storage_not_mirror(self):
        self.metadata({"zzstand.zip": {"name": "Stand Alone"}})
        with tempfile.TemporaryDirectory() as mirror, mock.patch.object(runtime, "_mirror_root", mirror):
            self.assertEqual(names.title("mame/zzstand.zip"), "Stand Alone")


if __name__ == "__main__":
    unittest.main()
