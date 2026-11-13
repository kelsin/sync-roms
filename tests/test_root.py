import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import downloads, mirroring, runtime, s3, store, usersettings, upload  # noqa: E402


class IsolationTest(unittest.TestCase):
    def test_tests_never_see_the_real_data_folder_or_home(self):
        self.assertNotEqual(store.data_dir(), isolate.REAL_DATA_DIR)
        self.assertTrue(store.data_dir().startswith(os.environ["SYNC_ROMS_TEST_HOME"]))
        self.assertEqual(os.path.expanduser("~"), os.environ["SYNC_ROMS_TEST_HOME"])


class FolderStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        for p in (mock.patch.object(runtime, "ROOT", self.root), mock.patch.object(runtime, "_mirror_root", None)):
            p.start()
            self.addCleanup(p.stop)

    def test_put_get_list_range(self):
        s3.put_text("scrapes/gba/metadata.json", "héllo")
        self.assertEqual(s3.get_text("scrapes/gba/metadata.json"), "héllo")
        self.assertEqual(s3.list_sizes("scrapes/"), {"scrapes/gba/metadata.json": 6})
        self.assertEqual(s3.read_range("scrapes/gba/metadata.json", 1, 3), "é".encode())

    def test_list_system_stats_only_the_listed_games(self):
        s3.put_text("gba/a.zip", "abc")
        s3.put_text("gba/other.zip", "defg")
        system = {"bucket": "gba", "games": [{"bucket": "gba/a.zip"}, {"bucket": "gba/missing.zip"}]}
        with mock.patch.object(s3, "list_sizes", side_effect=AssertionError("walked the folder")):
            self.assertEqual(store.list_system(system), {"gba/a.zip": 3})
        self.assertEqual(set(store.list_system({"bucket": "gba", "full_system": True})), {"gba/a.zip", "gba/other.zip"})

    def test_list_sizes_without_sizes_skips_the_stat(self):
        s3.put_text("gba/a.zip", "abc")
        with mock.patch.object(os.path, "getsize", side_effect=AssertionError("statted")):
            self.assertEqual(s3.list_sizes("gba/", sizes=False), {"gba/a.zip": None})

    def test_with_sizes_reads_only_the_missing_sizes_and_drops_gone_files(self):
        s3.put_text("gba/a.zip", "abc")
        jobs = [("gba/a.zip", "/x/a", None), ("gba/gone.zip", "/x/g", None), ("gba/b.zip", "/x/b", 7)]
        self.assertEqual(downloads.with_sizes(jobs), [("gba/a.zip", "/x/a", 3), ("gba/b.zip", "/x/b", 7)])
        known = [("gba/b.zip", "/x/b", 7)]
        with mock.patch.object(s3, "stat_sizes", side_effect=AssertionError("statted")):
            self.assertIs(downloads.with_sizes(known), known)

    def test_stat_sizes_ignores_folders(self):
        s3.put_text("gba/a.zip", "abc")
        self.assertEqual(s3.stat_sizes(["gba/a.zip", "gba"]), {"gba/a.zip": 3})

    def test_no_mirror_with_a_root(self):
        mirror = os.path.join(self.root, "mirror")
        os.makedirs(mirror)
        open(os.path.join(mirror, runtime.MIRROR_MARKER), "w").close()
        with mock.patch.object(mirroring, "refresh_mirror", side_effect=AssertionError("refreshed")):
            mirroring.use_mirror(mirror, False)
            with self.assertRaises(SystemExit):
                mirroring.mirror_command(mock.Mock(clear_mirror=False, use_mirror=mirror, mirror=None))
        self.assertIsNone(runtime._mirror_root)

    def test_list_with_etags_marks_folder_tags_as_not_md5(self):
        s3.put_text("gba/a.zip", "abc")
        (size, etag), = s3.list_with_etags("gba/").values()
        self.assertEqual(size, 3)
        self.assertIn("-", etag)

    def test_move_and_delete(self):
        s3.put_text("gba/a.zip", "abc")
        s3.put_text("gba/b.zip", "def")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(s3.move_keys([("gba/a.zip", "gba/sub/c.zip")]), 0)
            self.assertEqual(s3.delete_keys(["gba/b.zip", "gba/missing.zip"])[0]["Key"], "gba/missing.zip")
        self.assertEqual(set(s3.list_sizes("gba/")), {"gba/sub/c.zip"})

    def test_run_copies(self):
        src = os.path.join(self.root, "src.bin")
        with open(src, "w") as f:
            f.write("data")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(upload.run_uploads([("gba/x.zip", src, 4)]), 0)
        self.assertEqual(s3.get_text("gba/x.zip"), "data")

    def test_unsafe_key_is_rejected(self):
        with self.assertRaises(ValueError):
            s3.put_text("../evil", "x")


class RootSettingTest(unittest.TestCase):
    def test_root_setting_applies_and_wins(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(usersettings, "load_settings", lambda: {"root": d, "bucket": "b"}), \
                mock.patch.object(runtime, "OVERRIDES", {}), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROMS_ROOT", None)
            os.environ.pop("ROMS_BUCKET", None)
            with mock.patch.object(runtime, "ROOT", None):
                usersettings.apply_settings()
                self.assertEqual(runtime.ROOT, os.path.abspath(d))

    def test_first_run_folder_answer_saves_root_and_clears_bucket(self):
        saved = {"bucket": "old", "endpoint": "http://x"}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(usersettings, "load_settings", lambda: dict(saved)), \
                mock.patch.object(usersettings, "save_settings", lambda new: (saved.clear(), saved.update(new))), \
                mock.patch.object(usersettings, "resolve_settings", lambda: {k: (None, "unset") for k in ("bucket", "root", "endpoint")} | {"profile": ("p", ""), "write_profile": ("w", "")}), \
                mock.patch.object(runtime, "ROOT", None), mock.patch.object(runtime, "BUCKET", None), \
                mock.patch("builtins.input", side_effect=["/no/such/folder", d]), \
                contextlib.redirect_stdout(io.StringIO()):
            usersettings.ensure_bucket()
            self.assertEqual(saved, {"root": os.path.abspath(d)})
            self.assertEqual(runtime.ROOT, os.path.abspath(d))


class FirstRunAnswerTest(unittest.TestCase):
    """ensure_bucket() with nothing set: what each answer to the storage question does."""

    def first_run(self, answers, quiet=False):
        """Run ensure_bucket() on answers; returns (saved settings, input mock, stdout, stderr)."""
        saved = {}
        unset = {k: (None, "unset") for k in ("bucket", "root", "endpoint")} | {"profile": ("p", ""), "write_profile": ("w", "")}
        out, err = self.out, self.err = io.StringIO(), io.StringIO()
        with mock.patch.object(usersettings, "load_settings", lambda: dict(saved)), \
                mock.patch.object(usersettings, "save_settings", lambda new: (saved.clear(), saved.update(new))), \
                mock.patch.object(usersettings, "resolve_settings", lambda: unset), \
                mock.patch.object(runtime, "ROOT", None), mock.patch.object(runtime, "BUCKET", None), \
                mock.patch.object(runtime, "ENDPOINT", None), mock.patch.object(usersettings.ui, "QUIET", quiet), \
                mock.patch("builtins.input", side_effect=answers) as ask, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            usersettings.ensure_bucket()
        return saved, ask, out.getvalue(), err.getvalue()

    def test_path_without_leading_slash_is_not_saved_as_a_bucket(self):
        with tempfile.TemporaryDirectory() as d:
            saved, ask, out, _ = self.first_run(["Volumes/roms", d])
        self.assertEqual(saved, {"root": os.path.abspath(d)})
        self.assertEqual(ask.call_count, 2)  # asked again, and no endpoint question
        self.assertIn("Volumes/roms is not an absolute path", out)

    def test_existing_folder_name_is_a_folder_and_must_be_absolute(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cwd:
            os.makedirs(os.path.join(cwd, "roms"))
            old = os.getcwd()
            os.chdir(cwd)
            try:
                saved, _, out, _ = self.first_run(["roms", d])
            finally:
                os.chdir(old)
        self.assertEqual(saved, {"root": os.path.abspath(d)})
        self.assertIn("roms is not an absolute path", out)

    def test_home_folder_answer_is_expanded(self):
        home = os.path.join(os.path.expanduser("~"), "first-run-roms")
        os.makedirs(home)
        self.addCleanup(os.rmdir, home)
        saved, _, _, _ = self.first_run(["~/first-run-roms"])
        self.assertEqual(saved, {"root": home})

    def test_bucket_name_is_still_a_bucket(self):
        saved, ask, _, _ = self.first_run(["s3://my-roms/", ""])
        self.assertEqual(saved, {"bucket": "my-roms"})
        self.assertEqual(ask.call_count, 2)  # bucket, then endpoint

    def test_no_terminal_message_names_variables_and_flags(self):
        with self.assertRaises(SystemExit) as cm:
            self.first_run(EOFError())
        self.assertEqual(cm.exception.code, 3)
        for name in ("ROMS_BUCKET", "ROMS_ROOT", "--bucket", "--root"):
            self.assertIn(name, self.err.getvalue())

    def test_quiet_asks_on_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            _, ask, _, err = self.first_run([d], quiet=True)
        self.assertIn("Which S3 bucket holds your ROMs?", err)
        ask.assert_called_once_with()

    def test_quiet_shows_why_it_asks_again_on_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            gone = os.path.join(d, "gone")
            self.first_run(["Volumes/roms", gone, d], quiet=True)
        err = self.err.getvalue()
        self.assertIn("Volumes/roms is not an absolute path", err)
        self.assertIn(f"{gone} is not a folder", err)


if __name__ == "__main__":
    unittest.main()
