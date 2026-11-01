import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import chd, commands, diff, edit, m3u, picker, runtime, s3, scrape_files, store, ui, upload  # noqa: E402
from test_edit import EditFlow  # noqa: E402
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


class EofTest(EditFlow):
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
        self.assertEqual(self.run_eof([1, None]), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))

    def test_eof_on_rename_cancels(self):
        with open(self.path("cards.json"), "w") as f:
            json.dump({"c": {"layout": "esde", "device": "full"}}, f)
        self.run_eof([(edit.RENAME_KEY, 1), 4])
        self.assertEqual(list(self.read("cards.json")), ["c"])


if __name__ == "__main__":
    unittest.main()
