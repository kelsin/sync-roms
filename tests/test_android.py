import contextlib
import io
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import adb, android  # noqa: E402

NOVA_CFG = '''savefile_directory = "/storage/emulated/0/RetroArch/saves"
savefiles_in_content_dir = "false"
savestate_directory = "/storage/emulated/0/RetroArch/states"
savestates_in_content_dir = "false"
sort_savefiles_by_content_enable = "false"
sort_savefiles_enable = "true"
sort_savestates_by_content_enable = "false"
sort_savestates_enable = "true"
'''


def fake_run(answers):
    def run(*args, serial=None, check=True, timeout=60):
        out = answers[args[1]]
        if isinstance(out, Exception):
            raise out
        return out
    return run


class AndroidTest(unittest.TestCase):
    def setUp(self):
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(quiet.close)

    def test_is_android(self):
        self.assertTrue(android.is_android({"layout": "esde", "device": "retroid-pocket-nova"}))
        self.assertTrue(android.is_android({"layout": "esde", "device": "full"}))
        self.assertFalse(android.is_android({"layout": "esde", "device": "windows-pc"}))
        self.assertFalse(android.is_android({"layout": "knulli", "device": "retroid-pocket-nova"}))

    def test_card_volumes_keeps_those_with_roms(self):
        answers = {"ls /storage": "6AF3-53E9\nemulated\nself\nAAAA-BBBB\n",
                   "test -d /storage/6AF3-53E9/ROMs": "", "test -d /storage/AAAA-BBBB/ROMs": adb.AdbError("x")}
        with mock.patch.object(adb, "run", side_effect=fake_run(answers)):
            self.assertEqual(android.card_volumes("S", "ROMs"), ["6AF3-53E9"])

    def test_parse_config(self):
        text = 'savefile_directory = "/storage/emulated/0/RetroArch/saves"\nsort_savefiles_enable = "true"\n'
        self.assertEqual(android.parse_config(text), {
            "savefile_directory": "/storage/emulated/0/RetroArch/saves", "sort_savefiles_enable": "true"})

    def test_ra_folders_defaults(self):
        got = android.ra_folders({"savefile_directory": "default", "savestate_directory": ""})
        self.assertEqual(got, android.Folders("/storage/emulated/0/RetroArch/saves",
                                              "/storage/emulated/0/RetroArch/states", False, False))

    def test_ra_folders_real_nova(self):
        got = android.ra_folders(android.parse_config(NOVA_CFG))
        self.assertEqual(got, android.Folders("/storage/emulated/0/RetroArch/saves",
                                              "/storage/emulated/0/RetroArch/states", True, True))

    def test_ra_folders_content_dir_fails(self):
        for key in ("savefiles_in_content_dir", "savestates_in_content_dir",
                    "sort_savefiles_by_content_enable", "sort_savestates_by_content_enable"):
            with self.subTest(key), self.assertRaises(SystemExit) as ctx:
                android.ra_folders({key: "true"})
            self.assertEqual(ctx.exception.code, 2)

    def test_read_folders_unreadable_fails(self):
        with mock.patch.object(adb, "run", side_effect=adb.AdbError("No such file")):
            with self.assertRaises(SystemExit) as ctx:
                android.read_folders("S", "com.retroarch.aarch64")
        self.assertEqual(ctx.exception.code, 2)

    def test_read_folders(self):
        with mock.patch.object(adb, "run", return_value=NOVA_CFG) as run:
            got = android.read_folders("S", "com.retroarch.aarch64")
        self.assertTrue(got.sort_saves)
        self.assertIn("/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg", run.call_args.args[1])

    def test_retroarch_package(self):
        out = "package:com.android.x\npackage:com.retroarch.aarch64\n"
        with mock.patch.object(adb, "run", return_value=out):
            self.assertEqual(android.retroarch_package("S"), "com.retroarch.aarch64")
        with mock.patch.object(adb, "run", return_value="package:com.android.x\n"):
            with self.assertRaises(SystemExit) as ctx:
                android.retroarch_package("S")
        self.assertEqual(ctx.exception.code, 2)

    def test_wait_closed_rechecks(self):
        with mock.patch.object(android, "running", side_effect=[True, False]) as running, \
                mock.patch.object(android.ui, "confirm", return_value=True):
            android.wait_closed("S", "com.retroarch")
        self.assertEqual(running.call_count, 2)

    def test_wait_closed_declined_stops(self):
        with mock.patch.object(android, "running", return_value=True), \
                mock.patch.object(android.ui, "confirm", return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                android.wait_closed("S", "com.retroarch")
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
