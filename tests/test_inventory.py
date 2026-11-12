import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import commands, ignore, inventory, runtime, s3, store, ui, usersettings  # noqa: E402


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*args)
    return result, out.getvalue()


class StorageFolder(helpers.DataDir):
    """runtime.ROOT is a throwaway storage folder holding gba/a.zip (1 byte), gba/b.zip (2) and BIOS/x.bin (3)."""

    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        for key, size in (("gba/a.zip", 1), ("gba/b.zip", 2), ("BIOS/x.bin", 3)):
            self.put(key, size)
        for name, value in (("ROOT", self.root.name), ("BUCKET", None), ("ENDPOINT", None), ("_mirror_root", None)):
            p = mock.patch.object(runtime, name, value)
            p.start()
            self.addCleanup(p.stop)

    def put(self, key, size):
        path = os.path.join(self.root.name, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * size)

    def build(self, full=True):
        return quiet(inventory.update, full)[0]


class NoCacheTest(StorageFolder):
    def test_reads_go_to_storage_without_a_cache(self):
        self.assertIsNone(inventory.current())
        self.assertIsNone(inventory.cached("gba/"))
        with mock.patch.object(s3, "list_sizes", return_value={"gba/z.zip": 9}) as live:
            self.assertEqual(inventory.files("gba/", sizes=False), {"gba/z.zip": 9})
        live.assert_called_once_with("gba/", False)

    def test_a_cache_from_other_storage_is_not_used(self):
        self.build()
        with mock.patch.object(runtime, "ROOT", "/elsewhere"):
            self.assertIsNone(inventory.current())
            with mock.patch.object(s3, "stat_sizes", return_value={}) as live:
                inventory.stat(["gba/a.zip"])
            live.assert_called_once()


class FolderCacheTest(StorageFolder):
    def test_update_reads_every_file_and_reads_come_from_the_cache(self):
        self.assertEqual(self.build(), (3, 0, 0))
        with mock.patch.object(s3, "list_sizes", side_effect=AssertionError("listed storage")), \
                mock.patch.object(s3, "stat_sizes", side_effect=AssertionError("statted storage")), \
                mock.patch.object(s3, "list_folders", side_effect=AssertionError("listed storage")):
            self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2})
            self.assertEqual(inventory.files("gb/"), {})
            self.assertEqual(inventory.stat(["gba/a.zip", "gba/gone.zip"]), {"gba/a.zip": 1})
            self.assertEqual(inventory.folders(), {"gba", "BIOS"})
            self.assertEqual(inventory.etags("gba/"), {"a.zip": (1, "-"), "b.zip": (2, "-")})
            self.assertEqual(inventory.cached("BIOS/"), {"BIOS/x.bin": 3})

    def test_the_cache_survives_a_new_run(self):
        self.build()
        inventory.reset()
        self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2})

    def test_full_update_counts_what_changed(self):
        self.build()
        os.remove(os.path.join(self.root.name, "gba/a.zip"))
        self.put("gba/b.zip", 20)
        self.put("gba/c.zip", 4)
        self.assertEqual(self.build(), (1, 1, 1))
        self.assertEqual(inventory.files("gba/"), {"gba/b.zip": 20, "gba/c.zip": 4})

    def test_update_stats_only_new_files(self):
        self.build()
        os.remove(os.path.join(self.root.name, "gba/a.zip"))
        self.put("gba/b.zip", 20)  # same name: keeps its cached size
        self.put("gba/c.zip", 4)
        statted = []
        real = os.stat

        def spy(p, *a, **k):
            if str(p).endswith(".zip"):
                statted.append(os.path.relpath(p, self.root.name))
            return real(p, *a, **k)
        with mock.patch.object(inventory.os, "stat", side_effect=spy), mock.patch.object(inventory, "_progress"):
            self.assertEqual(inventory.update(), (1, 1, 0))
        self.assertEqual(statted, [os.path.join("gba", "c.zip")])
        self.assertEqual(inventory.files("gba/"), {"gba/b.zip": 2, "gba/c.zip": 4})
        inventory.reset()
        self.assertEqual(inventory.files("gba/"), {"gba/b.zip": 2, "gba/c.zip": 4})

    def test_update_without_a_cache_reads_everything(self):
        with mock.patch.object(inventory, "_progress"):
            self.assertEqual(inventory.update(), (3, 0, 0))
        self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2})

    def test_a_missing_folder_keeps_the_cache(self):
        self.build()
        with mock.patch.object(runtime, "ROOT", os.path.join(self.root.name, "unmounted")), \
                self.assertRaises(FileNotFoundError):
            inventory.update()

    def test_an_empty_listing_keeps_the_cache(self):
        self.build()
        with mock.patch.object(inventory, "_read_folder", return_value={}), self.assertRaises(FileNotFoundError):
            inventory.update()
        self.assertEqual(len(inventory.current().files), 3)


class BucketCacheTest(helpers.DataDir):
    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        for name, value in (("ROOT", None), ("BUCKET", "roms"), ("ENDPOINT", None)):
            p = mock.patch.object(runtime, name, value)
            p.start()
            self.addCleanup(p.stop)
        client = mock.Mock()
        client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "gba/a.zip", "Size": 1, "ETag": '"aa"'}]},
            {"Contents": [{"Key": "BIOS/x.bin", "Size": 3, "ETag": '"bb-2"'}]}]
        p = mock.patch.object(s3, "s3_client", return_value=client)
        p.start()
        self.addCleanup(p.stop)

    def test_one_listing_gives_sizes_and_etags(self):
        quiet(inventory.update)
        self.assertEqual(inventory.current().source, "s3://roms")
        self.assertEqual(inventory.etags("gba/"), {"a.zip": (1, '"aa"')})
        self.assertEqual(inventory.files("BIOS/"), {"BIOS/x.bin": 3})

    def test_the_endpoint_is_part_of_the_source(self):
        quiet(inventory.update)
        with mock.patch.object(runtime, "ENDPOINT", "http://minio"):
            self.assertIsNone(inventory.current())


class PatchTest(StorageFolder):
    def test_writes_moves_and_deletes_patch_the_cache_and_flush_saves_them(self):
        self.build()
        s3.write_file("gba/new.zip", lambda tmp: open(tmp, "wb").write(b"12345"))
        quiet(s3.move_keys, [("gba/a.zip", "gba/moved.zip")])
        quiet(s3.delete_keys, ["gba/b.zip"])
        want = {"gba/new.zip": 5, "gba/moved.zip": 1}
        self.assertEqual(inventory.files("gba/"), want)
        inventory.flush()
        inventory.reset()
        self.assertEqual(inventory.files("gba/"), want)

    def test_unflushed_patches_are_not_saved(self):
        self.build()
        inventory.wrote("gba/z.zip", 9)
        inventory.reset()
        self.assertNotIn("gba/z.zip", inventory.files("gba/"))

    def test_a_rewrite_drops_a_known_etag(self):
        self.build()
        inventory.current().etags["gba/a.zip"] = '"aa"'
        inventory.wrote("gba/a.zip", 7)
        self.assertEqual(inventory.etags("gba/")["a.zip"], (7, "-"))

    def test_without_a_cache_patches_do_nothing(self):
        inventory.wrote("gba/z.zip", 9)
        inventory.flush()
        self.assertFalse(os.path.exists(inventory.path()))


class PrepareTest(StorageFolder):
    def prepare(self, tty=True, answer=True):
        with mock.patch.object(sys.stdin, "isatty", return_value=tty), \
                mock.patch.object(ui, "confirm", return_value=answer) as asked:
            quiet(inventory.prepare)
        return asked

    def test_yes_builds_the_cache(self):
        self.prepare()
        self.assertEqual(len(inventory.current().files), 3)

    def test_no_is_remembered_and_not_asked_again(self):
        self.prepare(answer=False)
        self.assertIsNone(inventory.current())
        self.assertTrue(usersettings.load_settings()[inventory.DECLINED])
        self.prepare().assert_not_called()

    def test_no_terminal_no_question(self):
        self.prepare(tty=False).assert_not_called()
        self.assertNotIn(inventory.DECLINED, usersettings.load_settings())

    def test_a_usable_cache_is_not_asked_about(self):
        self.build()
        self.prepare().assert_not_called()


class CacheCommandTest(StorageFolder):
    def run_cmd(self, *argv):
        with mock.patch.object(usersettings, "ensure_bucket"):
            return quiet(commands.run, list(argv))

    def test_status_without_a_cache(self):
        code, out = self.run_cmd("cache")
        self.assertEqual(code, 0)
        self.assertIn("sync-roms cache update", out)

    def test_update_then_status(self):
        code, out = self.run_cmd("cache", "update")
        self.assertEqual(code, 0)
        self.assertIn("3 files", out)
        code, out = self.run_cmd("cache")
        self.assertIn(f"from {self.root.name}", out)
        self.assertIn("gba/", out)
        self.assertIn("BIOS/", out)
        self.assertIn("just now", out)

    def test_full_update_command(self):
        self.run_cmd("cache", "update")
        code, out = self.run_cmd("cache", "update", "--full")
        self.assertEqual(code, 0)
        self.assertIn("3 files", out)

    def test_status_says_when_storage_changed(self):
        self.run_cmd("cache", "update")
        with mock.patch.object(runtime, "ROOT", "/elsewhere"):
            _, out = self.run_cmd("cache")
        self.assertIn("Not used", out)


class StoreUsesTheCacheTest(StorageFolder):
    def test_list_system_and_folder_keys(self):
        self.build()
        with mock.patch.object(s3, "list_sizes", side_effect=AssertionError("listed storage")), \
                mock.patch.object(s3, "stat_sizes", side_effect=AssertionError("statted storage")):
            self.assertEqual(store.folder_keys("gba"), {"gba/a.zip", "gba/b.zip"})
            self.assertEqual(store.list_system({"bucket": "gba", "games": [{"bucket": "gba/a.zip"}]}), {"gba/a.zip": 1})


if __name__ == "__main__":
    unittest.main()


class IgnoredTest(StorageFolder):
    """gba/b.zip is ignored: every read leaves it out, with or without a cache, but the cache file keeps it."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(ignore, "_keys", frozenset({"gba/b.zip"}))
        p.start()
        self.addCleanup(p.stop)

    def each(self, check):
        with self.subTest(cache=False):
            check()
        self.build()
        with self.subTest(cache=True):
            check()

    def test_files_drops_ignored(self):
        self.each(lambda: self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1}))

    def test_cached_drops_ignored(self):
        self.build()
        self.assertEqual(inventory.cached("gba/"), {"gba/a.zip": 1})

    def test_stat_drops_ignored(self):
        self.each(lambda: self.assertEqual(inventory.stat(["gba/a.zip", "gba/b.zip"]), {"gba/a.zip": 1}))

    def test_etags_drops_ignored(self):
        self.each(lambda: self.assertEqual(set(inventory.etags("gba/")), {"a.zip"}))

    def test_cache_file_still_holds_ignored(self):
        self.build()
        self.assertIn("gba/b.zip", self.read("storage-cache.json")["files"])

    def test_listed_drops_ignored(self):
        self.assertEqual(store.listed({"games": [{"bucket": "gba/a.zip"}, {"bucket": "gba/b.zip"}]}), ["gba/a.zip"])
