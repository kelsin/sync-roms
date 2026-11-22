import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import cli, commands, store, usersettings  # noqa: E402

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

    def broken(self, text="{not json"):
        with open(self.path, "w") as f:
            f.write(text)
        os.chmod(self.path, 0o644)
        with open(self.path, "rb") as f:
            return f.read()

    def fails(self, fn, *args):
        err = io.StringIO()
        with mock.patch("sys.stderr", err), self.assertRaises(SystemExit) as e:
            fn(*args)
        self.assertEqual(e.exception.code, 3)
        return err.getvalue()

    def test_save_over_invalid_file_fails_and_leaves_it_untouched(self):
        before = self.broken('{"screenscraper_password": "p-secret",}')
        for fn, args in ((usersettings.save_setting, ("bucket", "b")), (usersettings.save_settings, ({"bucket": "b"},))):
            with self.subTest(fn=fn.__name__):
                self.assertRegex(self.fails(fn, *args), r"isn't valid JSON \(line 1, column \d+\): fix or move it")
                with open(self.path, "rb") as f:
                    self.assertEqual(f.read(), before)
        self.assertEqual(os.listdir(self.tmp.name), ["settings.json"])

    def test_first_run_question_is_not_asked_over_invalid_file(self):
        before = self.broken()
        with mock.patch("builtins.input", side_effect=AssertionError("asked")):
            self.assertIn(self.path, self.fails(usersettings.ensure_bucket))
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_save_keeps_backup_600(self):
        usersettings.save_settings({"screenscraper_password": "p-secret"})
        os.chmod(self.path, 0o644)
        usersettings.save_settings({"bucket": "b"})
        with open(self.path + ".bak") as f:
            self.assertIn("p-secret", f.read())
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(os.stat(self.path + ".bak").st_mode), 0o600)

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
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["settings.json", "settings.json.bak"])

    def test_save_settings_writes_many_keys_once(self):
        with mock.patch.object(usersettings.os, "replace", wraps=os.replace) as rep:
            usersettings.save_settings({"bucket": "b", "root": "/r"})
        self.assertEqual(rep.call_count, 1)
        self.assertEqual(usersettings.load_settings(), {"bucket": "b", "root": "/r"})
        self.assertEqual(self.mode(), 0o600)

    def test_valid_json_not_an_object_fails(self):
        before = self.broken("[1, 2]")
        self.assertIn(f"{self.path} isn't a JSON object: fix or move it", self.fails(usersettings.load_settings))
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), before)

    @unittest.skipIf(os.name != "posix" or os.geteuid() == 0, "needs a non-root POSIX user")
    def test_unreadable_file_fails(self):
        with open(self.path, "w") as f:
            f.write('{"bucket": "b"}')
        os.chmod(self.path, 0)
        self.addCleanup(os.chmod, self.path, 0o600)
        self.assertIn(self.path, self.fails(usersettings.load_settings))

    def test_load_missing_is_empty_and_does_not_create_file(self):
        self.assertEqual(usersettings.load_settings(), {})
        self.assertFalse(os.path.exists(self.path))

    def test_load_bad_json_fails_and_leaves_it_untouched(self):
        before = self.broken('{"bucket": "b",\n}')
        self.assertIn(f"{self.path} isn't valid JSON (line ", self.fails(usersettings.load_settings))
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o644)

    def test_doctor_reports_invalid_file(self):
        self.broken()
        out = io.StringIO()
        with mock.patch.object(commands.runtime, "ROOT", self.tmp.name), mock.patch.object(commands, "check_data", lambda: []), \
                mock.patch.object(commands.external, "find_tool", lambda tool: "/bin/" + tool), contextlib.redirect_stdout(out):
            code = commands.doctor_cmd(SimpleNamespace())
        self.assertEqual(code, 1)
        self.assertIn(f"❌ {self.path} isn't valid JSON (line 1, column 2): fix or move it", out.getvalue())

    def test_verbose_doctor_reports_invalid_file(self):
        self.broken()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as st:
            for name in ("BUCKET", "ROOT", "ENDPOINT", "PROFILE", "WRITE_PROFILE"):
                st.enter_context(mock.patch.object(commands.runtime, name, getattr(commands.runtime, name)))
            st.enter_context(mock.patch.dict(os.environ, {"ROMS_ROOT": self.tmp.name}))
            st.enter_context(mock.patch.object(sys, "argv", ["sync-roms", "--verbose", "doctor"]))
            st.enter_context(mock.patch.object(commands, "check_data", lambda: []))
            st.enter_context(mock.patch.object(commands.external, "find_tool", lambda tool: "/bin/" + tool))
            st.enter_context(contextlib.redirect_stdout(out))
            st.enter_context(contextlib.redirect_stderr(err))
            try:
                code = cli.sync()
            except SystemExit as e:
                code = e.code
        self.assertEqual(code, 1)
        self.assertIn(f"❌ {self.path} isn't valid JSON (line 1, column 2): fix or move it", out.getvalue())
        self.assertIn(f"root = {self.tmp.name} (env ROMS_ROOT)", err.getvalue())

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
