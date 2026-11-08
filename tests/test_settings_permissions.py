import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import commands, store, usersettings  # noqa: E402

CREDENTIALS = {"screenscraper_user": "u-secret", "screenscraper_password": "p-secret"}


class SettingsPermissionsTest(RealDataDirGuard):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(store, "data_dir", lambda: self.tmp.name)
        p.start()
        self.addCleanup(p.stop)
        self.path = os.path.join(self.tmp.name, "settings.json")

    def mode(self):
        return stat.S_IMODE(os.stat(self.path).st_mode)

    def test_load_fixes_loose_mode(self):
        with open(self.path, "w") as f:
            f.write('{"bucket": "b"}')
        os.chmod(self.path, 0o644)
        self.assertEqual(usersettings.load_settings(), {"bucket": "b"})
        self.assertEqual(self.mode(), 0o600)

    def test_save_creates_600(self):
        usersettings.save_setting("bucket", "b")
        self.assertEqual(self.mode(), 0o600)

    def test_save_tightens_existing_loose_file(self):
        with open(self.path, "w") as f:
            f.write("{}")
        os.chmod(self.path, 0o644)
        usersettings.save_setting("bucket", "b")
        self.assertEqual(self.mode(), 0o600)

    def test_save_over_loose_invalid_file_is_never_written_loose(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        os.chmod(self.path, 0o644)
        modes = []
        real = usersettings.json.dump

        def dump(obj, f, **kw):
            modes.append(stat.S_IMODE(os.fstat(f.fileno()).st_mode))
            return real(obj, f, **kw)
        with mock.patch.object(usersettings.json, "dump", side_effect=dump):
            usersettings.save_setting("screenscraper_password", "p-secret")
        self.assertEqual(modes, [0o600])
        self.assertEqual(self.mode(), 0o600)

    def test_save_skips_chmod_on_windows(self):
        with mock.patch.object(usersettings.sys, "platform", "win32"), \
                mock.patch.object(usersettings.os, "chmod") as chmod:
            usersettings.save_setting("bucket", "b")
            self.assertEqual(usersettings.load_settings(), {"bucket": "b"})
        chmod.assert_not_called()

    def test_save_is_atomic(self):
        usersettings.save_setting("bucket", "old")
        with mock.patch.object(usersettings.os, "replace", side_effect=OSError("disk full")), \
                mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            usersettings.save_setting("bucket", "new")
        self.assertEqual(usersettings.load_settings(), {"bucket": "old"})
        self.assertEqual(os.listdir(self.tmp.name), ["settings.json"])

    def test_save_settings_writes_many_keys_once(self):
        with mock.patch.object(usersettings.os, "replace", wraps=os.replace) as rep:
            usersettings.save_settings({"bucket": "b", "root": "/r"})
        self.assertEqual(rep.call_count, 1)
        self.assertEqual(usersettings.load_settings(), {"bucket": "b", "root": "/r"})
        self.assertEqual(self.mode(), 0o600)

    def test_valid_json_not_an_object_loads_empty(self):
        with open(self.path, "w") as f:
            f.write("[1, 2]")
        self.assertEqual(usersettings.load_settings(), {})

    @unittest.skipIf(os.name != "posix" or os.geteuid() == 0, "needs a non-root POSIX user")
    def test_unreadable_file_loads_empty(self):
        with open(self.path, "w") as f:
            f.write('{"bucket": "b"}')
        os.chmod(self.path, 0)
        self.addCleanup(os.chmod, self.path, 0o600)
        self.assertEqual(usersettings.load_settings(), {})

    def test_load_missing_or_bad_json_is_empty_and_does_not_create_file(self):
        self.assertEqual(usersettings.load_settings(), {})
        self.assertFalse(os.path.exists(self.path))
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(usersettings.load_settings(), {})
        with open(self.path) as f:
            self.assertEqual(f.read(), "{not json")

    def test_credentials_round_trip(self):
        for name, value in CREDENTIALS.items():
            usersettings.save_setting(name, value)
        self.assertEqual(usersettings.load_settings(), CREDENTIALS)

    def test_config_show_hides_credentials(self):
        for name, value in CREDENTIALS.items():
            usersettings.save_setting(name, value)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            commands.config_cmd(SimpleNamespace(action="show"))
        for value in CREDENTIALS.values():
            self.assertNotIn(value, out.getvalue())
        self.assertNotIn("screenscraper", out.getvalue())


if __name__ == "__main__":
    unittest.main()
