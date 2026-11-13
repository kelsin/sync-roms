import contextlib
import io
import json
import os
import sys
import tempfile
import unicodedata
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

    def test_ds_store_is_never_cached_or_read(self):
        self.put(".DS_Store", 4)
        self.put("gba/.DS_Store", 4)
        self.assertEqual(self.build(), (3, 0, 0))
        self.assertNotIn("gba/.DS_Store", inventory.current().files)
        self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2})

    def test_ds_store_in_an_old_cache_or_a_live_listing_is_dropped(self):
        self.build()
        inventory.wrote("gba/.DS_Store", 4)
        self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2})
        self.assertEqual(inventory.stat(["gba/.DS_Store"]), {})
        self.assertEqual(inventory.etags("gba/"), {"a.zip": (1, "-"), "b.zip": (2, "-")})
        inventory.reset()
        os.remove(inventory.path())
        self.put("gba/.DS_Store", 4)
        self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2})

    def test_part_files_are_never_cached_or_listed(self):
        self.put("gba/c.gba.part", 4)
        self.assertEqual(inventory.files("gba/"), {"gba/a.zip": 1, "gba/b.zip": 2})
        self.assertEqual(inventory.etags("gba/"), {"a.zip": (1, "-"), "b.zip": (2, "-")})
        self.assertEqual(self.build(), (3, 0, 0))
        self.assertNotIn("gba/c.gba.part", inventory.current().files)

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
        with mock.patch.object(inventory, "_read_folder", return_value=({}, {})), self.assertRaises(FileNotFoundError):
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
            {"Contents": [{"Key": "BIOS/x.bin", "Size": 3, "ETag": '"bb-2"'},
                          {"Key": "gba/.DS_Store", "Size": 4, "ETag": '"cc"'}]}]
        p = mock.patch.object(s3, "s3_client", return_value=client)
        p.start()
        self.addCleanup(p.stop)

    def test_one_listing_gives_sizes_and_etags(self):
        quiet(inventory.update)
        self.assertEqual(inventory.current().source, "s3://roms")
        self.assertEqual(inventory.etags("gba/"), {"a.zip": (1, '"aa"')})
        self.assertEqual(inventory.files("BIOS/"), {"BIOS/x.bin": 3})
        self.assertNotIn("gba/.DS_Store", inventory.current().files)

    def test_the_endpoint_is_part_of_the_source(self):
        quiet(inventory.update)
        with mock.patch.object(runtime, "ENDPOINT", "http://minio"):
            self.assertIsNone(inventory.current())


class FolderMtimeTest(StorageFolder):
    """The default update lists only folders whose mtime changed since the cache stored it."""

    def setUp(self):
        super().setUp()
        self.age()

    def age(self):
        """Set every folder's mtime to one in the past, so the update trusts it."""
        old = 1_600_000_000 * 10**9
        for folder, _, _ in os.walk(self.root.name):
            os.utime(folder, ns=(old, old))

    def update(self, full=False):
        """(update's counts, the folders it listed, relative to the root: "." is the root)."""
        listed, real = [], os.scandir

        def spy(p=".", *a):
            listed.append(os.path.relpath(p, self.root.name))
            return real(p, *a)
        with mock.patch.object(os, "scandir", side_effect=spy), mock.patch.object(inventory, "_progress"):
            counts = inventory.update(full)
        return counts, sorted(listed)

    def test_an_unchanged_folder_is_not_listed(self):
        self.assertEqual(self.update(), ((3, 0, 0), [".", "BIOS", "gba"]))
        self.assertEqual(self.update(), ((0, 0, 0), []))
        self.assertEqual(inventory.files(""), {"gba/a.zip": 1, "gba/b.zip": 2, "BIOS/x.bin": 3})
        inventory.reset()
        self.assertEqual(self.update(), ((0, 0, 0), []))

    def test_a_new_file_in_a_subfolder_is_found(self):
        self.put("gba/sub/c.zip", 4)
        self.age()
        self.update()
        self.put("gba/sub/d.zip", 5)
        self.assertEqual(self.update(), ((1, 0, 0), [os.path.join("gba", "sub")]))
        self.assertEqual(inventory.files("gba/sub/"), {"gba/sub/c.zip": 4, "gba/sub/d.zip": 5})

    def test_a_new_subfolder_is_found_and_a_removed_one_dropped(self):
        self.update()
        self.put("gba/sub/c.zip", 4)
        self.assertEqual(self.update(), ((1, 0, 0), ["gba", os.path.join("gba", "sub")]))
        os.remove(os.path.join(self.root.name, "gba/sub/c.zip"))
        os.rmdir(os.path.join(self.root.name, "gba/sub"))
        self.assertEqual(self.update(), ((0, 1, 0), ["gba"]))
        self.assertNotIn("gba/sub", inventory.current().dirs)

    def test_a_removed_file_is_dropped(self):
        self.update()
        os.remove(os.path.join(self.root.name, "gba/a.zip"))
        self.assertEqual(self.update(), ((0, 1, 0), ["gba"]))
        self.assertEqual(inventory.files("gba/"), {"gba/b.zip": 2})

    def test_full_rereads_every_folder_and_file(self):
        self.update()
        self.put("gba/b.zip", 20)  # replaced in place: the folder's mtime stays
        self.age()
        self.assertEqual(self.update(), ((0, 0, 0), []))
        self.assertEqual(self.update(full=True), ((0, 0, 1), [".", "BIOS", "gba"]))
        self.assertEqual(inventory.files("gba/")["gba/b.zip"], 20)
        self.assertEqual(self.update(), ((0, 0, 0), []))

    def test_an_old_cache_without_dirs_loads_and_lists_everything(self):
        store.write_json(inventory.path(), {"source": self.root.name, "updated": 1, "files": {"gba/a.zip": 1}})
        self.assertEqual(inventory.current().files, {"gba/a.zip": 1})
        self.assertEqual(inventory.current().dirs, {})
        self.assertEqual(self.update(), ((2, 0, 0), [".", "BIOS", "gba"]))

    def test_the_cache_file_stores_folder_mtimes_beside_the_files(self):
        self.update()
        with open(inventory.path()) as f:
            data = json.load(f)
        self.assertEqual(set(data["files"]), {"gba/a.zip", "gba/b.zip", "BIOS/x.bin"})
        self.assertEqual(set(data["dirs"]), {"", "gba", "BIOS"})
        self.assertEqual(data["dirs"]["gba"], os.stat(os.path.join(self.root.name, "gba")).st_mtime_ns)

    def test_a_fresh_mtime_is_not_stored(self):
        self.put("gba/c.zip", 4)  # gba's mtime is now
        self.update()
        self.assertIsNone(inventory.current().dirs["gba"])
        self.assertIsInstance(inventory.current().dirs["BIOS"], int)
        self.assertEqual(self.update(), ((0, 0, 0), ["gba"]))

    def test_an_mtime_is_stored_only_when_older_than_five_minutes(self):
        now = 1_700_000_000
        os.utime(os.path.join(self.root.name, "gba"), ns=((now - 300) * 10**9,) * 2)
        os.utime(os.path.join(self.root.name, "BIOS"), ns=((now - 300) * 10**9 - 1,) * 2)
        with mock.patch.object(inventory, "_clock", return_value=float(now)):
            self.update()
        self.assertIsNone(inventory.current().dirs["gba"])
        self.assertEqual(inventory.current().dirs["BIOS"], (now - 300) * 10**9 - 1)

    def test_a_file_added_while_a_folder_is_listed_is_found_next_time(self):
        later = inventory._clock() + 3600  # every mtime is old enough to store, even the one after the add
        p = mock.patch.object(inventory, "_clock", return_value=later)
        p.start()
        self.addCleanup(p.stop)
        real = os.scandir

        class Listing(list):  # what os.scandir read, before the file was added
            def __enter__(self):
                return iter(self)

            def __exit__(self, *exc):
                pass

        def adding(p=".", *a):
            with real(p, *a) as it:
                entries = Listing(it)
            if os.path.basename(p) == "gba":
                self.put("gba/c.zip", 4)
            return entries
        with mock.patch.object(os, "scandir", side_effect=adding), mock.patch.object(inventory, "_progress"):
            inventory.update()
        self.assertNotIn("gba/c.zip", inventory.current().files)
        self.assertEqual(self.update(), ((1, 0, 0), ["gba"]))

    def test_a_reused_folder_drops_what_a_listing_leaves_out(self):
        self.update()
        with open(inventory.path()) as f:
            data = json.load(f)
        data["files"]["gba/c.gba.part"] = 4  # from an older sync-roms that cached .part files
        store.write_json(inventory.path(), data)
        inventory.reset()
        self.assertEqual(self.update(), ((0, 1, 0), []))
        self.assertNotIn("gba/c.gba.part", inventory.current().files)

    def test_a_listing_error_raises_and_keeps_the_cache(self):
        self.update()
        self.put("gba/c.zip", 4)
        real = os.scandir

        def failing(p=".", *a):
            if os.path.basename(p) == "gba":
                raise PermissionError(p)
            return real(p, *a)
        with mock.patch.object(os, "scandir", side_effect=failing), mock.patch.object(inventory, "_progress"), \
                self.assertRaises(PermissionError):
            inventory.update()
        self.assertEqual(len(inventory.current().files), 3)

    def test_own_writes_drop_the_folder_mtime(self):
        self.update()
        inventory.wrote("gba/z.zip", 9)  # not really there: only a listing can tell
        inventory.moved("BIOS/x.bin", "BIOS/y.bin")
        self.assertIsNone(inventory.current().dirs["gba"])
        self.assertIsNone(inventory.current().dirs["BIOS"])
        inventory.flush()
        inventory.reset()
        self.assertEqual(self.update(), ((1, 2, 0), ["BIOS", "gba"]))
        self.assertEqual(inventory.files(""), {"gba/a.zip": 1, "gba/b.zip": 2, "BIOS/x.bin": 3})

    def test_a_delete_given_as_a_generator_drops_the_folder_mtime(self):
        self.update()
        inventory.removed(k for k in ["gba/a.zip"])
        self.assertIsNone(inventory.current().dirs["gba"])
        self.assertNotIn("gba/a.zip", inventory.current().files)

    def test_a_write_drops_the_mtime_of_the_folder_spelled_either_way(self):
        nfd, nfc = unicodedata.normalize("NFD", "Pokémon"), unicodedata.normalize("NFC", "Pokémon")
        self.put(f"{nfd}/a.zip", 1)
        self.age()
        self.update()
        self.assertIsInstance(inventory.current().dirs[nfd], int)
        inventory.wrote(f"{nfc}/b.zip", 2)
        self.assertIsNone(inventory.current().dirs[nfd])

    def test_a_write_into_a_new_folder_drops_the_nearest_known_folder_mtime(self):
        self.update()
        inventory.wrote("gba/new/sub/z.zip", 9)
        self.assertEqual(inventory.current().dirs, {"": 1_600_000_000 * 10**9, "BIOS": 1_600_000_000 * 10**9, "gba": None})
        inventory.wrote("new/z.zip", 9)
        self.assertIsNone(inventory.current().dirs[""])
        self.assertEqual(inventory.files("new/"), {"new/z.zip": 9})

    def test_a_dirs_value_that_is_not_a_whole_number_loads_as_none(self):
        store.write_json(inventory.path(), {"source": self.root.name, "updated": 1, "files": {"gba/a.zip": 1},
                                            "dirs": {"": 5, "gba": "x", "BIOS": 1.5}})
        self.assertEqual(inventory.current().dirs, {"": 5, "gba": None, "BIOS": None})

    def test_an_empty_folder_a_symlinked_folder_and_a_folder_replaced_by_a_file(self):
        os.mkdir(os.path.join(self.root.name, "empty"))
        os.symlink(os.path.join(self.root.name, "gba"), os.path.join(self.root.name, "link"))
        self.age()
        self.assertEqual(self.update(), ((3, 0, 0), [".", "BIOS", "empty", "gba"]))
        self.assertEqual(self.update(), ((0, 0, 0), []))
        os.remove(os.path.join(self.root.name, "BIOS/x.bin"))
        os.rmdir(os.path.join(self.root.name, "BIOS"))
        self.put("BIOS", 6)
        self.assertEqual(self.update(), ((1, 1, 0), ["."]))
        self.assertEqual(inventory.current().files, {"gba/a.zip": 1, "gba/b.zip": 2, "BIOS": 6})


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


class FolderKeysTest(unittest.TestCase):
    def test_folder_keys_lists_names_only_without_a_cache(self):
        asked = []

        def list_sizes(prefix, sizes=True):
            asked.append((prefix, sizes))
            return {"gba/a.zip": None, "gba/sub/": None}
        with mock.patch.object(inventory, "current", return_value=None), mock.patch.object(s3, "list_sizes", list_sizes):
            self.assertEqual(store.folder_keys("gba"), {"gba/a.zip"})
        self.assertEqual(asked, [("gba/", False)])  # each size would be a stat on a share


class StoreUsesTheCacheTest(StorageFolder):
    def test_list_system_and_folder_keys(self):
        self.build()
        with mock.patch.object(s3, "list_sizes", side_effect=AssertionError("listed storage")), \
                mock.patch.object(s3, "stat_sizes", side_effect=AssertionError("statted storage")):
            self.assertEqual(store.folder_keys("gba"), {"gba/a.zip", "gba/b.zip"})
            self.assertEqual(store.list_system({"bucket": "gba", "games": [{"bucket": "gba/a.zip"}]}), {"gba/a.zip": 1})


G = "psvita/G [PCSE00349] [USA] [NoNpDRM].zip"
NEW = "psvita/G [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"
DLC = "psvita/D [PCSE00349] [USA] [DLC-X].zip"
VITA = {"bucket": "psvita", "games": [{"bucket": G}]}


class VitaSyncKeysTest(StorageFolder):
    def setUp(self):
        super().setUp()
        for key, size in ((G, 4), ("psvita/G [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip", 5), (NEW, 6),
                          (DLC, 7), ("psvita/H [PCSE00001] [USA] [NoNpDRM].zip", 8)):
            self.put(key, size)

    def test_without_a_cache_extras_are_found_and_statted(self):
        self.assertEqual(store.synced_keys(VITA), [G, DLC, NEW])
        self.assertEqual(store.list_system(VITA), {G: 4, DLC: 7, NEW: 6})
        self.assertEqual(store.available_keys(VITA, {}), [G, DLC, NEW])

    def test_with_a_cache(self):
        self.build()
        with mock.patch.object(s3, "list_sizes", side_effect=AssertionError("listed storage")), \
                mock.patch.object(s3, "stat_sizes", side_effect=AssertionError("statted storage")):
            self.assertEqual(store.list_system(VITA), {G: 4, DLC: 7, NEW: 6})

    def test_a_listed_dlc_is_not_doubled(self):
        s = {"bucket": "psvita", "games": [{"bucket": DLC}, {"bucket": G}]}
        self.assertEqual(store.synced_keys(s), [DLC, G, NEW])

    def test_ignored_dlc_is_not_synced(self):
        with mock.patch.object(ignore, "_keys", frozenset({DLC})):
            self.assertEqual(store.synced_keys(VITA), [G, NEW])

    def test_other_systems_do_not_read_the_folder(self):
        with mock.patch.object(inventory, "files", side_effect=AssertionError("listed")):
            self.assertEqual(store.synced_keys({"bucket": "gba", "games": [{"bucket": "gba/a.zip"}]}), ["gba/a.zip"])

    def test_scrape_leaves_extras_out(self):
        from sync_roms import scrape_files
        self.assertEqual(scrape_files.bucket_roms([VITA])["psvita"], {G.split("/", 1)[1]})

    def test_scrape_all_leaves_extras_out(self):
        from sync_roms import scrape_files
        self.assertEqual(scrape_files.bucket_roms([VITA], all_files=True)["psvita"],
                         {G.split("/", 1)[1], "H [PCSE00001] [USA] [NoNpDRM].zip"})


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
