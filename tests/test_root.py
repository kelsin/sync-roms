import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import runtime, s3, usersettings, upload  # noqa: E402


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
                mock.patch.object(usersettings, "save_setting", lambda k, v: saved.pop(k, None) if v is None else saved.__setitem__(k, v)), \
                mock.patch.object(usersettings, "resolve_settings", lambda: {k: (None, "unset") for k in ("bucket", "root", "endpoint")} | {"profile": ("p", ""), "write_profile": ("w", "")}), \
                mock.patch.object(runtime, "ROOT", None), mock.patch.object(runtime, "BUCKET", None), \
                mock.patch("builtins.input", side_effect=["/no/such/folder", d]), \
                contextlib.redirect_stdout(io.StringIO()):
            usersettings.ensure_bucket()
            self.assertEqual(saved, {"root": os.path.abspath(d)})
            self.assertEqual(runtime.ROOT, os.path.abspath(d))


if __name__ == "__main__":
    unittest.main()
