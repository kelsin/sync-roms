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
from sync_roms import inventory, runtime, s3, shared, store  # noqa: E402


def parse(text):
    return json.loads(text)


class WriteTextTest(unittest.TestCase):
    def test_writes_utf8_and_leaves_no_temp_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.txt")
            store.write_text(path, "héllo ✓")
            with open(path, "rb") as f:
                self.assertEqual(f.read(), "héllo ✓".encode("utf-8"))
            self.assertEqual(os.listdir(tmp), ["a.txt"])
            store.write_text(path, "second", backup=True)
            self.assertEqual(sorted(os.listdir(tmp)), ["a.txt", "a.txt.bak"])


class SharedTest(StorageFolder):
    def store_file(self, key, text, mtime=None):
        path = os.path.join(self.root.name, *key.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        if mtime is not None:
            os.utime(path, ns=(mtime, mtime))

    def mirror(self, key):
        with open(shared.local_path(key)) as f:
            return f.read()

    def tags(self):
        with open(os.path.join(store.data_dir(), "storage", ".tags.json")) as f:
            return json.load(f)

    def load(self, key="x.json", empty=None):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            value = shared.load(key, parse, {} if empty is None else empty)
        return value, err.getvalue()


class LocalPathTest(SharedTest):
    def test_local_path_is_under_the_storage_folder(self):
        self.assertEqual(shared.local_path("sets/a.json"), os.path.join(store.data_dir(), "storage", "sets", "a.json"))


class LoadTest(SharedTest):
    def test_missing_in_storage_gives_empty_and_removes_mirror_and_tag(self):
        self.store_file("x.json", '{"a": 1}')
        self.load()
        os.remove(os.path.join(self.root.name, "x.json"))
        self.assertEqual(self.load(empty={"none": True})[0], {"none": True})
        self.assertFalse(os.path.exists(shared.local_path("x.json")))
        self.assertNotIn("x.json", self.tags())

    def test_reads_storage_and_saves_mirror_and_tag(self):
        self.store_file("x.json", '{"a": 1}')
        self.assertEqual(self.load()[0], {"a": 1})
        self.assertEqual(self.mirror("x.json"), '{"a": 1}')
        self.assertEqual(self.tags()["x.json"], inventory.tag("x.json"))

    def test_same_tag_reuses_mirror_without_reading_storage(self):
        self.store_file("x.json", '{"a": 1}')
        self.load()
        with mock.patch.object(shared, "read", side_effect=AssertionError("read again")):
            self.assertEqual(self.load()[0], {"a": 1})

    def test_changed_tag_reads_again(self):
        self.store_file("x.json", '{"a": 1}', mtime=1_000_000_000_000_000_000)
        self.load()
        self.store_file("x.json", '{"a": 2}', mtime=1_000_000_001_000_000_000)
        self.assertEqual(self.load()[0], {"a": 2})
        self.assertEqual(self.mirror("x.json"), '{"a": 2}')

    def test_reads_storage_not_the_storage_mirror(self):
        self.store_file("x.json", '{"a": 1}')
        with mock.patch.object(runtime, "_mirror_root", self.root.name + "-mirror"):
            self.assertEqual(self.load()[0], {"a": 1})

    def test_without_fallback_a_storage_error_is_raised_and_not_warned(self):
        self.store_file("x.json", '{"a": 1}')
        self.load()
        err = io.StringIO()
        with mock.patch.object(inventory, "tag", side_effect=OSError("down")), contextlib.redirect_stderr(err), \
                self.assertRaises(OSError):
            shared.load("x.json", parse, {}, fallback=False)
        self.assertEqual(err.getvalue(), "")

    def test_storage_error_falls_back_to_mirror_with_warning(self):
        self.store_file("x.json", '{"a": 1}')
        self.load()
        with mock.patch.object(inventory, "tag", side_effect=OSError("share offline")):
            value, err = self.load()
        self.assertEqual(value, {"a": 1})
        self.assertEqual(err.count("⚠️"), 1)
        self.assertIn("x.json", err)

    def test_malformed_storage_file_falls_back_to_mirror_with_warning(self):
        self.store_file("x.json", '{"a": 1}', mtime=1_000_000_000_000_000_000)
        self.load()
        self.store_file("x.json", "{nope", mtime=1_000_000_001_000_000_000)
        value, err = self.load()
        self.assertEqual(value, {"a": 1})
        self.assertIn("x.json", err)

    def test_error_without_mirror_gives_empty(self):
        with mock.patch.object(inventory, "tag", side_effect=OSError("share offline")):
            value, err = self.load(empty={"e": 1})
        self.assertEqual(value, {"e": 1})
        self.assertIn("x.json", err)

    def test_unmounted_storage_folder_keeps_mirror(self):
        self.store_file("x.json", '{"a": 1}')
        self.load()
        with mock.patch.object(runtime, "ROOT", os.path.join(self.root.name, "not-mounted")):
            value, err = self.load()
        self.assertEqual(value, {"a": 1})
        self.assertTrue(os.path.exists(shared.local_path("x.json")))
        self.assertIn("x.json", err)

    def test_corrupt_tags_file_is_treated_as_empty(self):
        self.store_file("x.json", '{"a": 1}')
        self.load()
        with open(os.path.join(store.data_dir(), "storage", ".tags.json"), "w") as f:
            f.write("{nope")
        with mock.patch.object(shared, "read", wraps=shared.read) as read:
            self.assertEqual(self.load()[0], {"a": 1})
        read.assert_called_once()
        self.assertEqual(self.tags()["x.json"], inventory.tag("x.json"))

    def test_nested_keys_create_folders(self):
        self.store_file("sets/a.json", '{"a": 1}')
        self.assertEqual(self.load("sets/a.json")[0], {"a": 1})
        self.assertEqual(self.mirror("sets/a.json"), '{"a": 1}')
        self.assertIn("sets/a.json", self.tags())


class WriteTest(SharedTest):
    def test_write_puts_storage_and_saves_mirror_and_tag(self):
        shared.write("sets/a.json", '{"a": 1}')
        with open(os.path.join(self.root.name, "sets", "a.json")) as f:
            self.assertEqual(f.read(), '{"a": 1}')
        self.assertEqual(self.mirror("sets/a.json"), '{"a": 1}')
        self.assertEqual(self.tags()["sets/a.json"], inventory.tag("sets/a.json"))
        with mock.patch.object(shared, "read", side_effect=AssertionError("read again")):
            self.assertEqual(self.load("sets/a.json")[0], {"a": 1})

    def test_read_returns_storage_text(self):
        self.store_file("x.json", "hello")
        self.assertEqual(shared.read("x.json"), "hello")

    def test_read_missing_raises_a_storage_error(self):
        with self.assertRaises(s3.ERRORS):
            shared.read("nope.json")


class UpdateTest(SharedTest):
    def update(self, change, key="x.json"):
        return shared.update(key, parse, {}, change, lambda d: json.dumps(d))

    def test_creates_a_missing_file(self):
        self.assertEqual(self.update(lambda d: d.update(a=1)), {"a": 1})
        self.assertEqual(self.mirror("x.json"), '{"a": 1}')
        self.assertEqual(self.tags()["x.json"], inventory.tag("x.json"))

    def test_merges_into_storage_changed_after_the_mirror_was_saved(self):
        self.store_file("x.json", '{"a": 1}', mtime=1_000_000_000_000_000_000)
        self.load()
        self.store_file("x.json", '{"a": 1, "b": 2}', mtime=1_000_000_001_000_000_000)
        self.assertEqual(self.update(lambda d: d.update(c=3)), {"a": 1, "b": 2, "c": 3})
        self.assertEqual(self.mirror("x.json"), '{"a": 1, "b": 2, "c": 3}')

    def test_change_may_return_a_new_value(self):
        self.store_file("x.json", '{"a": 1}')
        self.assertEqual(self.update(lambda d: {"z": 0}), {"z": 0})
        self.assertEqual(self.mirror("x.json"), '{"z": 0}')

    def test_writes_nothing_when_unchanged(self):
        self.store_file("x.json", '{"a": 1}')
        with mock.patch.object(shared, "write", side_effect=AssertionError("wrote")):
            self.assertEqual(self.update(lambda d: d.update(a=1)), {"a": 1})

    def test_empty_change_still_creates_a_missing_file(self):
        self.update(lambda d: None)
        self.assertEqual(self.mirror("x.json"), "{}")

    def test_unmounted_storage_folder_raises_and_writes_nothing(self):
        missing = os.path.join(self.root.name, "unmounted")
        with mock.patch.object(runtime, "ROOT", missing), self.assertRaises(FileNotFoundError):
            shared.update("x.json", parse, {}, lambda d: d.update(a=1), json.dumps)
        self.assertFalse(os.path.exists(missing))
        self.assertFalse(os.path.exists(shared.local_path("x.json")))


class DeleteTest(SharedTest):
    def delete(self, key):
        with contextlib.redirect_stdout(io.StringIO()):
            shared.delete(key)

    def test_deletes_the_file_its_mirror_and_tag(self):
        self.store_file("sets/a.json", "{}")
        self.load("sets/a.json")
        self.delete("sets/a.json")
        self.assertFalse(os.path.exists(os.path.join(self.root.name, "sets", "a.json")))
        self.assertFalse(os.path.exists(shared.local_path("sets/a.json")))
        self.assertNotIn("sets/a.json", self.tags())

    def test_a_file_already_gone_counts_as_deleted_and_drops_the_mirror_and_tag(self):
        self.store_file("sets/a.json", "{}")
        self.load("sets/a.json")
        self.store_file("sets/b.json", "{}")
        self.load("sets/b.json")
        os.remove(os.path.join(self.root.name, "sets", "a.json"))  # another machine deleted it
        self.delete("sets/a.json")
        self.assertFalse(os.path.exists(shared.local_path("sets/a.json")))
        self.assertEqual(set(self.tags()), {"sets/b.json"})

    def test_a_delete_error_is_raised_and_keeps_the_mirror(self):
        self.store_file("sets/a.json", "{}")
        self.load("sets/a.json")
        with mock.patch.object(s3, "delete_keys", return_value=[{"Key": "sets/a.json", "Message": "denied"}]), \
                self.assertRaisesRegex(OSError, "denied"):
            self.delete("sets/a.json")
        self.assertIn("sets/a.json", self.tags())


if __name__ == "__main__":
    unittest.main()
