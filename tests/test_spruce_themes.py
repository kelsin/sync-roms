import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from sync_roms import commands, external, inventory, picker, runtime, s3, spruce_themes, store, ui, usersettings  # noqa: E402
from sync_roms.spruce_fixes import fds  # noqa: E402

PREFIX = runtime.SPRUCE_THEMES_PREFIX
NAME = "2CleanMini_by_Sheezie.7z"
FOLDER = "2CleanMini by Sheezie"


def read(path):
    with open(path, "rb") as f:
        return f.read()


def asset(name=NAME, updated="2026-01-01T00:00:00Z", size=10):
    return {"name": name, "size": size, "updated_at": updated, "browser_download_url": f"https://example.invalid/{name}"}


class Themes(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        self.warned = []
        self.enterContext(mock.patch.object(ui, "warn", self.warned.append))
        self.enterContext(mock.patch.object(external, "find_tool", return_value="/bin/7z"))
        self.archives = {}  # asset name -> (folder or None, {rel: bytes})
        self.downloads = []
        self.broken = set()  # download URLs that fail

    def run_update(self, assets, dry_run=False):
        def download(url, path, callback=None):
            self.downloads.append(url)
            if url in self.broken:
                raise OSError("connection reset")
            with open(path, "wb") as f:
                f.write(url.encode())

        def unpack(archive, out):
            with open(archive) as f:
                name = f.read().rsplit("/", 1)[1]
            folder, files = self.archives[name]
            for rel, data in files.items():
                path = os.path.join(out, "mnt", "SDCARD", "Themes", folder or "x", rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
            return folder
        with mock.patch.object(spruce_themes, "_release", return_value=assets), \
                mock.patch.object(spruce_themes.github, "download", download), \
                mock.patch.object(spruce_themes, "_unpack", unpack), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.out = out
            return spruce_themes.update_storage(dry_run)

    def state(self):
        return self.read_json(runtime.SPRUCE_THEMES_STATE)

    def exists(self, key):
        return os.path.exists(os.path.join(self.root, key))

    def test_new_asset_uploaded(self):
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertEqual(self.state(), {NAME: {"updated_at": "2026-01-01T00:00:00Z", "size": 10, "folder": FOLDER}})

    def test_unchanged_asset_skipped(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({NAME: {"updated_at": "2026-01-01T00:00:00Z", "size": 10, "folder": FOLDER}}).encode())
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertEqual(self.downloads, [])

    def test_changed_asset_replaces_folder(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({NAME: {"updated_at": "old", "size": 10, "folder": FOLDER}}).encode())
        self.put(f"{PREFIX}{FOLDER}/old.png")
        self.archives[NAME] = (FOLDER, {"new.png": b"n", "sub/a.png": b"a"})
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertFalse(self.exists(f"{PREFIX}{FOLDER}/old.png"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/new.png"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/sub/a.png"))

    def test_removed_asset_folder_deleted(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Gone.7z": {"updated_at": "x", "size": 1, "folder": "Gone"}}).encode())
        self.put(f"{PREFIX}Gone/config.json")
        self.assertEqual(self.run_update([]), 0)
        self.assertFalse(self.exists(f"{PREFIX}Gone/config.json"))
        self.assertEqual(self.state(), {})

    def test_custom_folder_untouched(self):
        self.put(f"{PREFIX}Mine/config.json")
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Gone.7z": {"updated_at": "x", "size": 1, "folder": "Gone"}}).encode())
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.run_update([asset()])
        self.assertTrue(self.exists(f"{PREFIX}Mine/config.json"))

    def test_release_folder_matching_custom_folder_skipped(self):
        self.put(f"{PREFIX}{FOLDER}/mine.png")
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset()]), 1)
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/mine.png"))
        self.assertFalse(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertFalse(self.exists(runtime.SPRUCE_THEMES_STATE) and self.state())
        self.assertIn(FOLDER, self.warned[0])

    def test_folder_recorded_for_another_asset_skipped(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Other.7z": {"updated_at": "x", "size": 1, "folder": FOLDER}}).encode())
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset(), asset("Other.7z", "x", 1)]), 1)
        self.assertFalse(self.exists(f"{PREFIX}{FOLDER}/config.json"))

    def test_folder_renamed_inside_updated_asset(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({NAME: {"updated_at": "old", "size": 10, "folder": "Old Name"}}).encode())
        self.put(f"{PREFIX}Old Name/config.json")
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset()]), 0)
        self.assertFalse(self.exists(f"{PREFIX}Old Name/config.json"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertEqual(self.state()[NAME]["folder"], FOLDER)

    def test_malformed_state_entry_is_ignored(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Bad.7z": {"size": 1}}).encode())
        self.assertEqual(self.run_update([]), 0)

    def test_bad_member_paths_skipped(self):
        self.archives["Bad.7z"] = (None, {"a": b"a"})
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.assertEqual(self.run_update([asset("Bad.7z"), asset()]), 1)
        self.assertEqual(self.state().keys(), {NAME})
        self.assertFalse(self.exists(f"{PREFIX}x"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertIn("Bad.7z", self.warned[0])

    def test_dry_run_changes_nothing(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"Gone.7z": {"updated_at": "x", "size": 1, "folder": "Gone"}}).encode())
        self.put(f"{PREFIX}Gone/config.json")
        self.assertEqual(self.run_update([asset()], dry_run=True), 0)
        text = self.out.getvalue()
        self.assertIn(f"{NAME}: add", text)
        self.assertIn("Gone.7z: remove", text)
        self.assertTrue(self.exists(f"{PREFIX}Gone/config.json"))
        self.assertEqual(list(self.state()), ["Gone.7z"])
        self.assertEqual(self.downloads, [])

    def test_no_7z_warns(self):
        with mock.patch.object(external, "find_tool", return_value=None):
            self.assertEqual(self.run_update([asset()]), 1)
        self.assertIn("sync-roms tools install", self.warned[0])
        self.assertFalse(self.exists(runtime.SPRUCE_THEMES_STATE))

    def test_failed_upload_of_new_asset_completes_next_run(self):
        self.archives[NAME] = (FOLDER, {"a.png": b"a", "config.json": b"{}"})
        real = s3.copy_file

        def flaky(src, dst, *args):
            if os.path.basename(src) == "a.png":
                raise OSError("share went away")
            return real(src, dst, *args)
        with mock.patch.object(s3, "copy_file", flaky):
            self.assertEqual(self.run_update([asset()]), 1)
        self.assertEqual(self.state()[NAME], {"folder": FOLDER, "updated_at": None, "size": None})
        self.assertTrue(any("didn't upload" in w for w in self.warned))
        inventory.reset()
        self.warned.clear()
        self.assertEqual(self.run_update([asset()]), 0, self.warned)
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/a.png"))
        self.assertTrue(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertEqual(self.state(), {NAME: {"updated_at": "2026-01-01T00:00:00Z", "size": 10, "folder": FOLDER}})

    def test_state_written_after_each_theme(self):
        class Abort(BaseException):
            pass
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.archives["Other.7z"] = ("Other", {"config.json": b"{}"})
        real = s3.copy_file
        calls = []

        def copy_file(src, dst, *args):
            calls.append(src)
            if len(calls) == 2:  # the second theme's file
                raise Abort()
            return real(src, dst, *args)
        with mock.patch.object(s3, "copy_file", copy_file), self.assertRaises(Abort):
            self.run_update([asset(), asset("Other.7z")])
        self.assertEqual(self.state()[NAME], {"updated_at": "2026-01-01T00:00:00Z", "size": 10, "folder": FOLDER})
        self.assertEqual(self.state()["Other.7z"]["folder"], "Other")

    def test_a_failed_download_skips_only_that_asset(self):
        self.archives[NAME] = (FOLDER, {"config.json": b"{}"})
        self.archives["Other.7z"] = ("Other", {"config.json": b"{}"})
        self.broken.add(f"https://example.invalid/{NAME}")
        self.assertEqual(self.run_update([asset(), asset("Other.7z")]), 1)
        self.assertNotIn(NAME, self.state())
        self.assertEqual(self.state()["Other.7z"]["folder"], "Other")
        self.assertTrue(self.exists(f"{PREFIX}Other/config.json"))
        self.assertFalse(self.exists(f"{PREFIX}{FOLDER}/config.json"))
        self.assertTrue(any(NAME in w for w in self.warned))

    def test_unmounted_root_changes_nothing(self):
        gone = os.path.join(self.root, "gone")
        with mock.patch.object(runtime, "ROOT", gone):
            self.assertEqual(self.run_update([asset()]), 1)
        self.assertFalse(os.path.exists(gone))
        self.assertEqual(self.downloads, [])


class Pick(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)

    def themes(self, *names):
        for n in names:
            self.put(f"{PREFIX}{n}/config.json")
        self.put(f"{PREFIX}x/readme.txt")

    def pick_args(self, result):
        calls = []

        def fake(title, labels, **kw):
            calls.append((labels, kw))
            return result
        self.enterContext(mock.patch.object(picker, "filter_list", fake))
        self.enterContext(mock.patch.object(ui, "has_terminal", return_value=True))
        self.enterContext(mock.patch.object(usersettings, "ensure_bucket"))
        with contextlib.redirect_stdout(io.StringIO()):
            commands.themes_pick(None)
        return calls

    def test_available_lists_theme_folders(self):
        self.themes("B", "a")
        self.assertEqual(spruce_themes.available(), ["a", "B"])

    def test_themes_pick_saves_sorted_list(self):
        self.themes("a", "B", "c")
        self.pick_args([True, False, True])
        self.assertEqual(usersettings.load_settings()["spruce_themes"], ["a", "c"])

    def test_themes_pick_esc_saves_nothing(self):
        self.themes("a")
        self.pick_args(None)
        self.assertNotIn("spruce_themes", usersettings.load_settings())

    def test_pick_keeps_missing_names(self):
        self.themes("a")
        seen = []
        with mock.patch.object(picker, "filter_list", lambda t, labels, **kw: seen.append((labels, kw)) or [False, True]):
            self.assertEqual(spruce_themes.pick("t", ["gone"]), ["gone"])
        self.assertEqual(seen[0][0][1], "gone")
        self.assertEqual(seen[0][1]["initial"], [False, True])

    def test_pick_storage_error_is_esc(self):
        warned = []
        with mock.patch.object(inventory, "files", side_effect=OSError("share gone")), \
                mock.patch.object(ui, "warn", warned.append), \
                mock.patch.object(picker, "filter_list") as f:
            self.assertIsNone(spruce_themes.pick("t", ["a"]))
        f.assert_not_called()
        self.assertTrue(warned)

    def test_pick_one(self):
        self.themes("a", "b")
        with mock.patch.object(picker, "filter_list", return_value=2) as f:
            self.assertEqual(spruce_themes.pick_one("t", "a"), "b")
        self.assertEqual(f.call_args.kwargs["cursor"], 1)
        with mock.patch.object(picker, "filter_list", return_value=0):
            self.assertIsNone(spruce_themes.pick_one("t", "a"))
        with mock.patch.object(picker, "filter_list", return_value=None):
            self.assertIs(spruce_themes.pick_one("t", None), False)

    def test_default_list(self):
        self.assertEqual(spruce_themes.default_list(), [])
        usersettings.save_settings({"spruce_themes": ["a"]})
        self.assertEqual(spruce_themes.default_list(), ["a"])

    def test_preview_none_without_png(self):
        self.themes("a")
        self.assertIsNone(spruce_themes.preview("a"))

    def test_preview_downloads_png(self):
        self.put(f"{PREFIX}a/preview.png", b"png")
        path = spruce_themes.preview("a")
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"png")

    def test_preview_follows_a_republished_png(self):
        self.put(f"{PREFIX}a/preview.png", b"old")
        spruce_themes.preview("a")
        self.put(f"{PREFIX}a/preview.png", b"new")
        self.assertEqual(read(spruce_themes.preview("a")), b"new")

    def test_preview_from_a_bucket_is_cached_by_etag(self):
        key = f"{PREFIX}a/preview.png"
        bodies = {"e1": b"old", "e2": b"new"}
        etag = ["e1"]

        def download(job):
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "wb") as f:
                f.write(bodies[etag[0]])
        with mock.patch.object(runtime, "ROOT", None), mock.patch.object(runtime, "BUCKET", "b"), \
                mock.patch.object(inventory, "known", lambda k: (3, f'"{etag[0]}"') if k == key else None), \
                mock.patch.object(s3, "download", side_effect=download) as fetch:
            self.assertEqual(read(spruce_themes.preview("a")), b"old")
            self.assertEqual(read(spruce_themes.preview("a")), b"old")
            self.assertEqual(fetch.call_count, 1)
            etag[0] = "e2"
            path = spruce_themes.preview("a")
            self.assertEqual(read(path), b"new")
            self.assertEqual(os.listdir(os.path.dirname(path)), [os.path.basename(path)])



class Card(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        self.base = os.path.join(self.tmp.name, "card")
        os.makedirs(self.base)
        self.warned = []
        self.enterContext(mock.patch.object(ui, "warn", self.warned.append))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def themes(self, **files):
        for n, rels in files.items():
            for rel in rels or ["config.json"]:
                self.put(f"{PREFIX}{n}/{rel}")

    def card_file(self, rel, data=b"abc"):
        path = os.path.join(self.base, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def saved(self, **values):
        store.update_card("c", **values)

    def plan(self, names, keep=False):
        return spruce_themes.plan("c", self.base, names, keep)

    def test_plan_list_plus_current(self):
        self.themes(A=["config.json", "x.png"], B=["config.json"])
        self.saved(spruce_theme="B")
        jobs = self.plan(["A"])["jobs"]
        paths = sorted(os.path.relpath(p, self.base) for _, p, _ in jobs)
        self.assertEqual(paths, sorted(os.path.join("Themes", *r.split("/")) for r in
                                       ("A/config.json", "A/x.png", "B/config.json")))
        self.assertEqual(sorted(k for k, _, _ in jobs), sorted(f"{PREFIX}{r}" for r in ("A/config.json", "A/x.png", "B/config.json")))

    def test_wanted_notes_missing(self):
        self.themes(A=None)
        self.saved(spruce_theme="B")
        self.assertEqual(spruce_themes.wanted("c", ["A", "Z"]), ["A"])
        self.assertTrue(any("B" in w for w in self.warned))

    def test_new_theme_recorded(self):
        self.themes(A=None)
        self.assertEqual(self.plan(["A"])["installed"], ["A"])

    def test_existing_theme_not_recorded(self):
        self.themes(A=None)
        os.makedirs(os.path.join(self.base, "Themes", "A"))
        self.assertEqual(self.plan(["A"])["installed"], [])

    def test_foreign_theme_never_removed(self):
        self.themes(A=None)
        os.makedirs(os.path.join(self.base, "Themes", "SPRUCE"))
        plan = self.plan(["A"])
        self.assertEqual(plan["remove"], [])
        self.assertNotIn("SPRUCE", plan["installed"])

    def test_unwanted_installed_removed(self):
        self.themes(A=None)
        self.saved(spruce_themes_installed=["A", "C"])
        plan = self.plan(["A"])
        self.assertEqual((plan["remove"], plan["installed"]), (["C"], ["A"]))

    def test_no_delete_keeps(self):
        self.themes(A=None)
        self.saved(spruce_themes_installed=["A", "C"])
        plan = self.plan(["A"], keep=True)
        self.assertEqual((plan["remove"], plan["installed"]), ([], ["A", "C"]))

    def test_selected_theme_kept(self):
        self.themes(A=None)
        self.saved(spruce_themes_installed=["A", "C"])
        self.card_file("Saves/flip-system.json", b'{"theme": "C"}')
        plan = self.plan(["A"])
        self.assertEqual((plan["remove"], plan["installed"]), ([], ["A", "C"]))

    def test_requested_theme_missing_from_storage_kept(self):
        self.themes(B=None)
        self.saved(spruce_themes_installed=["A", "C"], spruce_theme="C")
        plan = self.plan(["A"])
        self.assertEqual((plan["remove"], plan["installed"]), ([], ["A", "C"]))

    def test_no_storage_themes_removes_nothing(self):
        self.saved(spruce_themes_installed=["C"])
        plan = self.plan([])
        self.assertEqual((plan["remove"], plan["installed"]), ([], ["C"]))

    def test_selected_ignores_malformed(self):
        self.card_file("Saves/a-system.json", b'{"theme": "X"}')
        self.card_file("Saves/b-system.json", b"nope")
        self.card_file("Saves/c-system.json", b'{"vol": 1}')
        self.assertEqual(spruce_themes.selected(self.base), {"X"})

    def test_config_compared_by_content(self):
        self.put(f"{PREFIX}A/config.json", b"abc")
        job = (f"{PREFIX}A/config.json", self.card_file("Themes/A/config.json", b"abd"), 3)
        self.assertEqual(spruce_themes.todo([job]), [job])
        self.card_file("Themes/A/config.json", b"abc")
        self.assertEqual(spruce_themes.todo([job]), [])

    def test_crlf_config_identical_not_recopied(self):
        self.put(f"{PREFIX}A/config.json", b'{\r\n"a": 1\r\n}\r\n')
        job = (f"{PREFIX}A/config.json", self.card_file("Themes/A/config.json", b'{\r\n"a": 1\r\n}\r\n'), 13)
        self.assertEqual(spruce_themes.todo([job]), [])

    def test_non_utf8_config_compared(self):
        self.put(f"{PREFIX}A/config.json", b"\xff\xfe")
        job = (f"{PREFIX}A/config.json", self.card_file("Themes/A/config.json", b"\xff\xfe"), 2)
        self.assertEqual(spruce_themes.todo([job]), [])
        self.card_file("Themes/A/config.json", b"\xff\xfd")
        self.assertEqual(spruce_themes.todo([job]), [job])

    def test_other_files_compared_by_size(self):
        same = ("k1", self.card_file("Themes/A/a.png", b"abc"), 3)
        diff = ("k2", self.card_file("Themes/A/b.png", b"abc"), 4)
        self.assertEqual(spruce_themes.todo([same, diff]), [diff])

    def test_fixed_file_not_recopied(self):
        with open(fds.IMAGE, "rb") as f:
            image = f.read()
        path = self.card_file("Themes/ART_BOOK_NEXT/icons/overlay/fds.png", image)
        self.assertEqual(spruce_themes.todo([("k", path, len(image) + 5)]), [])

    def test_remove_deletes_trees(self):
        self.card_file("Themes/C/a/b.png")
        self.card_file("Themes/D/x.png")
        self.assertEqual(spruce_themes.remove(self.base, ["C"], dry_run=True), 0)
        self.assertTrue(os.path.isdir(os.path.join(self.base, "Themes", "C")))
        self.assertEqual(spruce_themes.remove(self.base, ["C"], dry_run=False), 0)
        self.assertFalse(os.path.exists(os.path.join(self.base, "Themes", "C")))
        self.assertTrue(os.path.isdir(os.path.join(self.base, "Themes", "D")))

    def system(self, name="miyoo-mini", data='{\n  "theme": "X",\n  "vol": 5\n}\n'):
        return self.card_file(f"Saves/{name}-system.json", data.encode())

    def read(self, path):
        with open(path) as f:
            return f.read()

    def test_select_sets_theme_keeps_keys(self):
        path = self.system()
        self.card_file("Themes/B/config.json")
        self.saved(spruce_theme="B")
        self.assertEqual(spruce_themes.select("c", self.base, False), 1)
        self.assertEqual(self.read(path), '{\n  "theme": "B",\n  "vol": 5\n}\n')

    def test_select_missing_file_warns(self):
        self.saved(spruce_theme="B")
        self.assertEqual(spruce_themes.select("c", self.base, False), 0)
        self.assertTrue(self.warned)

    def test_select_malformed_skipped(self):
        path = self.system(data="nope")
        self.card_file("Themes/B/config.json")
        self.saved(spruce_theme="B")
        self.assertEqual(spruce_themes.select("c", self.base, False), 0)
        self.assertEqual(self.read(path), "nope")
        self.assertTrue(self.warned)

    def test_select_theme_not_on_card_sets_nothing(self):
        path = self.system()
        before = self.read(path)
        self.saved(spruce_theme="B")
        self.assertEqual(spruce_themes.select("c", self.base, False), 0)
        self.assertEqual(self.read(path), before)
        self.assertTrue(any("B" in w for w in self.warned))

    def test_select_dry_run_counts_theme_storage_has(self):
        self.system()
        self.themes(B=None)
        self.saved(spruce_theme="B")
        self.assertEqual(spruce_themes.select("c", self.base, True), 1)
        self.assertEqual(self.warned, [])

    def test_select_unreadable_file_skipped(self):
        self.card_file("Themes/B/config.json")
        bad = self.card_file("Saves/a-system.json", b"\xff")
        os.makedirs(os.path.join(self.base, "Saves", "b-system.json"))
        good = self.system()
        self.saved(spruce_theme="B")
        self.assertEqual(spruce_themes.select("c", self.base, False), 1)
        self.assertIn('"theme": "B"', self.read(good))
        with open(bad, "rb") as f:
            self.assertEqual(f.read(), b"\xff")
        self.assertEqual(len(self.warned), 2)

    def test_select_dry_run_writes_nothing(self):
        path, before = self.system(), None
        before = self.read(path)
        self.saved(spruce_theme="B")
        spruce_themes.select("c", self.base, True)
        self.assertEqual(self.read(path), before)

    def test_select_without_current_does_nothing(self):
        path = self.system()
        before = self.read(path)
        spruce_themes.select("c", self.base, False)
        self.assertEqual(self.read(path), before)
        self.assertEqual(self.warned, [])

    def test_tampered_installed_names_never_leave_themes(self):
        self.themes(A=None)
        self.card_file("Themes/C/x.png")
        self.card_file("keep.txt")
        self.saved(spruce_themes_installed=["", ".", "..", "../x", "a/b", os.sep + "abs", 5, "C"])
        plan = self.plan(["A"])
        self.assertEqual((plan["remove"], plan["installed"]), (["C"], ["A"]))
        self.assertEqual(spruce_themes.remove(self.base, ["", ".", "..", "a/b", "C"], dry_run=False), 0)
        self.assertTrue(os.path.isdir(os.path.join(self.base, "Themes")))
        self.assertTrue(os.path.isfile(os.path.join(self.base, "keep.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.base, "Themes", "C")))


if __name__ == "__main__":
    unittest.main()
