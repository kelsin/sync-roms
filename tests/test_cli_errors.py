import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from sync_roms import chd, cli, commands, diff, edit, inventory, m3u, picker, runtime, s3, scrape_files, store, ui, upload  # noqa: E402
from test_edit import EditBase  # noqa: E402
from test_scripting import Isolated  # noqa: E402


class ErrorsTest(Isolated):
    def test_unknown_device_list_is_capped(self):
        devices = [{"id": f"dev{i}", "name": "n", "soc": "s", "systems": [], "firmwares": []} for i in range(80)]
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as cm:
            commands.show_devices(devices, [], "nope")
        self.assertEqual(cm.exception.code, 2)
        self.assertLess(len(err.getvalue()), 400)
        self.assertIn("sync-roms devices", err.getvalue())

    def test_unknown_device_flag_is_capped(self):
        devices = [{"id": f"dev{i}", "name": "n", "firmwares": ["esde"]} for i in range(80)]
        manifest = {"devices": devices, "layouts": {"esde": {}}}
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            commands.setup_from_flags(manifest, None, "nope", None)
        self.assertLess(len(err.getvalue()), 400)
        self.assertIn("sync-roms devices", err.getvalue())

    def test_short_u_is_deprecated_but_works(self):
        code, _, err = self.sync(["-u"], {"bucket": "b"}, u=(scrape_files, "upload_scrapes", lambda args: 0))
        self.assertEqual(code, 0)
        self.assertIn("deprecated", err)
        self.assertIn("upload scrapes", err)

    def test_long_upload_scrapes_does_not_warn(self):
        code, _, err = self.sync(["--upload-scrapes"], {"bucket": "b"}, u=(scrape_files, "upload_scrapes", lambda args: 0))
        self.assertEqual((code, err), (0, ""))


class EditAliasTest(Isolated):
    def test_every_edit_spelling_opens_the_main_menu(self):
        for argv in (["edit"], ["games", "edit"], ["cards", "edit"], ["--edit"], ["-e"]):
            with self.subTest(argv=argv), mock.patch.object(edit, "edit_manifest", return_value=0) as run:
                code, _, err = self.sync(argv, {"bucket": "b"})
                self.assertEqual((code, err), (0, ""))
            run.assert_called_once_with()

    def test_dry_run_with_edit_is_a_usage_error(self):
        for argv in (["edit", "--dry-run"], ["--edit", "-n"]):
            with self.subTest(argv=argv), mock.patch.object(edit, "edit_manifest") as run:
                code, _, err = self.sync(argv)
            self.assertEqual(code, 2)
            self.assertIn("--dry-run has no effect on `edit`", err)
            run.assert_not_called()


class UnhonoredFlagsTest(Isolated):
    """Flags a command can't honor are refused with exit 2 before it runs."""

    def refused(self, argv, message, **patches):
        with mock.patch.object(inventory, "update_command", side_effect=AssertionError("ran")), \
                mock.patch.object(inventory, "status_command", side_effect=AssertionError("ran")), \
                mock.patch.object(scrape_files, "clean_scrapes", side_effect=AssertionError("ran")), \
                mock.patch.object(commands, "doctor_cmd", side_effect=AssertionError("ran")):
            code, out, err = self.sync(argv, {"bucket": "b"}, **patches)
        self.assertEqual(code, 2, err)
        self.assertIn(message, err)
        self.assertEqual(out, "")

    def test_dry_run_is_refused_where_it_changes_nothing_or_is_ignored(self):
        from sync_roms import scrape_review
        cases = [(["scrape", "review", "--dry-run"], "scrape review"), (["-n", "scrape", "review", "gba"], "scrape review"),
                 (["cache", "update", "--dry-run"], "cache update"), (["-n", "cache"], "cache"),
                 (["config", "-n"], "config show"), (["config", "path", "-n"], "config path"),
                 (["doctor", "-n"], "doctor"), (["check", "--dry-run"], "check"), (["completion", "bash", "-n"], "completion"),
                 (["games", "list", "-n", "--card", "SD"], "games list"), (["games", "export", "-n", "--card", "SD"], "games export"),
                 (["games", "sets", "list", "-n", "--card", "SD"], "games sets list")]
        for argv, name in cases:
            with self.subTest(argv=argv):
                self.refused(argv, f"--dry-run has no effect on `{name}`",
                             r=(scrape_review, "review_command", mock.Mock(side_effect=AssertionError("ran"))))

    def test_dry_run_is_refused_on_diff(self):
        from sync_roms import diff
        with tempfile.TemporaryDirectory() as tmp:
            for argv in (["diff", tmp, "--dry-run"], ["-n", "diff", tmp], ["--diff", tmp, "-n"]):
                with self.subTest(argv=argv):
                    self.refused(argv, "--dry-run has no effect on `diff`",
                                 d=(diff, "diff_command", mock.Mock(side_effect=AssertionError("ran"))))

    def test_cache_full_needs_update(self):
        self.refused(["cache", "--full"], "--full only applies to `cache update`")

    def test_clean_scrapes_takes_no_folder(self):
        self.refused(["clean", "scrapes", "/some/dir"], "`clean scrapes` doesn't take a folder")

    def test_refusals_name_the_command_typed(self):
        self.refused(["devices", "--dry-run"], "--dry-run has no effect on `devices`")
        self.refused(["mirror", "clear", "-n"], "--dry-run has no effect on `mirror clear`")
        self.refused(["playlist", "--ask"], "--ask only applies to syncing a card, not `playlist`")


class UsageHelpTest(Isolated):
    def test_help_for_commands_that_need_a_subcommand(self):
        for name in ("upload", "clean", "tools"):
            for flag in ("--help", "-h"):
                with self.subTest(name=name, flag=flag):
                    code, out, err = self.sync([name, flag])
                    self.assertEqual((code, err), (0, ""))
                    self.assertIn(f"sync-roms {name}", out)

    def test_word_command_errors_point_at_that_command_help(self):
        for argv, name in ((["cache", "update", "--json"], "cache"), (["cards", "list", "-n"], "cards"),
                           (["games", "add", "--card", "SD"], "games"), (["config", "bogus"], "config")):
            with self.subTest(argv=argv):
                code, _, err = self.sync(argv)
                self.assertEqual(code, 2)
                self.assertIn(f"Try 'sync-roms {name} --help'.", err)

    def test_config_show_prints_eject_as_a_word(self):
        code, out, _ = self.sync(["config", "show"], {"eject": False})
        self.assertEqual(code, 0)
        self.assertRegex(out, r"eject\s+false\s")
        code, out, _ = self.sync(["config", "show"])
        self.assertRegex(out, r"eject\s+true\s")


class QuietColorTest(unittest.TestCase):
    class Stream(io.StringIO):
        def __init__(self, tty):
            super().__init__()
            self.tty = tty

        def isatty(self):
            return self.tty

    def failure_line(self, stdout_tty, stderr_tty):
        out, err = self.Stream(stdout_tty), self.Stream(stderr_tty)
        with mock.patch.dict(os.environ, clear=False), mock.patch.object(sys, "stdout", out), \
                mock.patch.object(sys, "stderr", err), mock.patch.object(ui, "_COLOR", stdout_tty):
            for var in ("NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "TERM"):
                os.environ.pop(var, None)
            ui.set_output(True, False)
            try:
                ui.failure(ui.red("❌ x"))
            finally:
                ui.reset()
        return err.getvalue()

    def test_quiet_failure_lines_are_colored_by_stderr(self):
        self.assertIn("\033[31m", self.failure_line(stdout_tty=False, stderr_tty=True))
        self.assertNotIn("\033[", self.failure_line(stdout_tty=True, stderr_tty=False))


class ExitCodeTest(Isolated):
    def code_of(self, fn, *a):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            fn(*a)
        return cm.exception.code

    def test_cancelled_setup_picker_exits_0(self):
        with mock.patch.object(picker, "pick_device", return_value=None):
            self.assertEqual(self.code_of(picker.choose_setup, {"devices": [], "layouts": {"esde": {}}}), 0)

    def test_bad_folders_are_usage_errors(self):
        args = mock.Mock(upload="/no/such/folder", diff="/no/such/folder", m3u="/no/such/folder", chd="/no/such/folder")
        for fn in (upload.upload_command, diff.diff_command, m3u.m3u_command, chd.chd_command):
            with self.subTest(fn=fn.__name__):
                self.assertEqual(self.code_of(fn, args), 2)

    def test_no_es_de_folder_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.code_of(scrape_files.upload_scrapes, mock.Mock(base_dir=tmp)), 2)

    def test_s3_errors_are_setup_problems(self):
        from botocore.exceptions import ClientError
        err = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "ListObjectsV2")
        with mock.patch.object(store, "load_manifest", side_effect=err):
            self.assertEqual(self.code_of(scrape_files.clean_scrapes, mock.Mock(dry_run=True)), 3)

    def test_missing_tool_is_a_setup_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "psx"))
            open(os.path.join(tmp, "psx", "g.cue"), "w").close()
            with mock.patch.object(chd, "plan_chd", return_value=[({"chd": {"mode": "cd"}}, None, "x.cue", "o")]), \
                    mock.patch.object(chd.external, "find_tool", return_value=None):
                self.assertEqual(self.code_of(chd.chd_command, mock.Mock(chd=tmp, dry_run=False)), 3)


class MissingStorageOrCardTest(Isolated):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        for p in (mock.patch.object(runtime, "ROOT", None), mock.patch.object(ui, "ASSUME_YES", False)):
            p.start()
            self.addCleanup(p.stop)

    def test_missing_storage_folder_stops_a_sync_before_planning(self):
        gone = os.path.join(self.tmp, "roms")
        tree = inventory.Tree(gone, 1, {"gba/Game.zip": 5}, {})
        with mock.patch.object(cli, "sync_card") as plan, mock.patch.object(inventory, "_load", return_value=tree), \
                mock.patch.object(inventory, "prepare") as prepare:
            code, out, err = self.sync([os.path.join(self.tmp, "SD"), "--yes"], {"root": gone})
        self.assertEqual(code, 3)
        self.assertIn(gone, err)
        self.assertIn("mounted?", err)
        self.assertNotIn("Traceback", out + err)
        plan.assert_not_called()
        prepare.assert_not_called()

    def test_editor_still_opens_with_the_storage_folder_missing(self):
        for argv in (["edit"], ["cards", "edit"], ["games", "edit"]):
            with self.subTest(argv=argv), mock.patch.object(edit, "edit_manifest", return_value=0) as run:
                code, _, err = self.sync(argv, {"root": os.path.join(self.tmp, "roms")})
            self.assertEqual((code, err), (0, ""))
            run.assert_called_once_with()

    def test_os_error_mid_run_is_a_message_not_a_traceback(self):
        boom = FileNotFoundError(2, "No such file or directory", "/Volumes/roms/scrapes/gba/metadata.json")
        with mock.patch.object(cli, "sync", side_effect=boom), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as cm:
            cli.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("No such file or directory", err.getvalue())

    def test_no_such_bucket_names_the_settings_file(self):
        from botocore.exceptions import ClientError
        boom = ClientError({"Error": {"Code": "NoSuchBucket", "Message": "gone"}}, "ListObjectsV2")
        with mock.patch.object(cli, "sync", side_effect=boom), mock.patch.object(runtime, "BUCKET", "typo", create=True), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err, \
                self.assertRaises(SystemExit) as cm:
            cli.main()
        self.assertEqual(cm.exception.code, 3)
        self.assertIn(os.path.join(store.data_dir(), "settings.json"), err.getvalue())
        self.assertIn("--bucket", err.getvalue())

    def test_missing_card_path_is_a_usage_error_and_creates_nothing(self):
        storage = os.path.join(self.tmp, "roms")
        os.makedirs(storage)
        card = os.path.join(self.tmp, "typo", "SD")
        with mock.patch.object(picker, "saved_setup", return_value=(None, "esde")), \
                mock.patch.object(store, "load_cards", return_value={}), mock.patch.object(store, "save_card"):
            code, out, err = self.sync([card, "--yes"], {"root": storage})
        self.assertEqual(code, 2)
        self.assertIn(f"{card} isn't a folder", err)
        self.assertIn("mounted?", err)
        self.assertIn("sync-roms --help", err)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "typo")))

    def test_unusable_card_folders_are_setup_problems(self):
        path = os.path.join(self.tmp, "ROMs")
        open(path, "w").close()
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as cm:
            cli.check_dir(path, "ROMs folder")
        self.assertEqual(cm.exception.code, 3)
        self.assertIn("is not a directory", err.getvalue())


class EofTest(EditBase):
    def run_eof(self, picks):
        picks = iter(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch("builtins.input", side_effect=EOFError), \
                mock.patch.object(ui, "confirm", return_value=True), \
                mock.patch.object(ui, "choose", return_value="s"), \
                contextlib.redirect_stdout(io.StringIO()):
            return edit.edit_manifest()

    def test_eof_on_new_card_name_cancels(self):
        self.assertEqual(self.run_eof([0, 0, None, None]), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))

    def test_eof_on_rename_cancels(self):
        with open(self.path("cards.json"), "w") as f:
            json.dump({"c": {"layout": "esde", "device": "full"}}, f)
        self.run_eof([0, (edit.RENAME_KEY, 0), None, 4])
        self.assertEqual(list(self.read("cards.json")), ["c"])


if __name__ == "__main__":
    unittest.main()
