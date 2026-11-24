import contextlib
import io
import os
import subprocess
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cli, clean, flash, picker, runtime, unmount, usersettings  # noqa: E402

DISK4 = flash.Disk("disk4", 1, "SD", ("A",), ("/Volumes/A",))
DISK5 = flash.Disk("disk5", 1, "SD", ("B",), ())
TITLE = "🃏 Which card?"


class Run(unittest.TestCase):
    def setUp(self):
        self.root = runtime.ROOT
        self.addCleanup(setattr, runtime, "ROOT", self.root)
        self.addCleanup(setattr, clean, "_clean_root", clean._clean_root)
        self.addCleanup(setattr, clean, "_eject_root", clean._eject_root)
        runtime.ROOT = None
        self.disks = [DISK4, DISK5]
        self.pick = 0
        self.dry_run = False
        self.cleaned = []
        self.eject_result = True
        self.eject_roots = []
        self.external = self.enterContext(mock.patch.object(flash, "external_disks", side_effect=lambda ex: self.disks))
        self.disks_of = self.enterContext(mock.patch.object(flash, "disks_of", return_value=set()))
        self.filter = self.enterContext(mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: self.pick))
        self.enterContext(mock.patch.object(clean, "clean_dirs", side_effect=lambda: self.cleaned.append(clean._clean_root)))
        self.enterContext(mock.patch.object(clean, "eject", side_effect=self.fake_eject))
        self.enterContext(mock.patch.object(sys, "platform", "darwin"))

    def fake_eject(self):
        self.eject_roots.append(clean._eject_root)
        return self.eject_result

    def run_unmount(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()) as err:
            code = unmount.run(types.SimpleNamespace(dry_run=self.dry_run))
        self.err = err.getvalue()
        return code, out.getvalue()

    def test_run_lists_only_mounted(self):
        self.run_unmount()
        self.assertEqual(self.filter.call_args.args, (TITLE, [flash._disk_label(DISK4)]))

    def test_run_cleans_each_mount_then_unmounts(self):
        self.disks = [flash.Disk("disk4", 1, "SD", ("KNULLI", "SHARE"), ("/Volumes/KNULLI", "/Volumes/SHARE"))]
        code, _ = self.run_unmount()
        self.assertEqual(self.cleaned, ["/Volumes/KNULLI", "/Volumes/SHARE"])
        self.assertEqual(self.eject_roots, ["/Volumes/KNULLI"])
        self.assertEqual(code, 0)

    def test_run_returns_1_when_unmount_fails(self):
        self.eject_result = False
        self.assertEqual(self.run_unmount()[0], 1)

    def test_run_esc_does_nothing(self):
        self.pick = None
        self.assertEqual(self.run_unmount()[0], 0)
        self.assertEqual((self.cleaned, self.eject_roots), ([], []))

    def test_run_no_card(self):
        self.disks = [DISK5]
        code, out = self.run_unmount()
        self.assertEqual(code, 1)
        self.filter.assert_not_called()
        self.assertIn("no mounted SD card", self.err)

    def test_run_excludes_storage_disk(self):
        runtime.ROOT = "/Volumes/roms"
        self.disks_of.return_value = {"disk7"}
        self.run_unmount()
        self.external.assert_called_with({"disk7"})
        runtime.ROOT = None
        self.run_unmount()
        self.external.assert_called_with(set())

    def test_run_resets_roots_on_both_paths(self):
        for result in (True, False):
            self.eject_result = result
            self.run_unmount()
            self.assertEqual((clean._clean_root, clean._eject_root), (None, None))

    def test_run_dry_run_does_nothing(self):
        self.dry_run = True
        code, out = self.run_unmount()
        self.assertEqual(code, 0)
        self.assertIn("Would tidy /Volumes/A and unmount disk4", out)
        self.assertEqual((self.cleaned, self.eject_roots), ([], []))

    def test_run_needs_macos(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(self.run_unmount()[0], 1)


class Eject(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, clean, "_eject_root", clean._eject_root)
        self.enterContext(mock.patch.object(sys, "platform", "darwin"))
        self.enterContext(mock.patch.object(clean.shutil, "which", return_value="/usr/sbin/diskutil"))
        self.enterContext(mock.patch.object(clean, "card_disk", return_value="disk4"))
        self.enterContext(mock.patch.object(clean.os, "chdir"))
        clean._eject_root = "/Volumes/KNULLI"

    def eject(self, code):
        r = subprocess.CompletedProcess([], code, "", "busy")
        with mock.patch.object(clean.subprocess, "run", return_value=r), contextlib.redirect_stdout(io.StringIO()):
            return clean.eject()

    def test_true_when_unmounted(self):
        self.assertIs(self.eject(0), True)

    def test_false_when_unmount_fails(self):
        self.assertIs(self.eject(1), False)

    def test_true_when_nothing_to_do(self):
        clean._eject_root = None
        self.assertIs(self.eject(1), True)


class Main(unittest.TestCase):
    def test_main_unmounts_exactly_once(self):
        self.addCleanup(setattr, clean, "_clean_root", clean._clean_root)
        self.addCleanup(setattr, clean, "_eject_root", clean._eject_root)
        self.addCleanup(setattr, runtime, "ROOT", runtime.ROOT)
        runtime.ROOT = None
        disk = flash.Disk("disk4", 1, "SD", ("A",), ("/Volumes/A",))
        r = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(sys, "argv", ["sync-roms", "unmount"]), \
                mock.patch.object(usersettings, "load_settings", lambda: {}), \
                mock.patch.object(flash, "external_disks", return_value=[disk]), \
                mock.patch.object(picker, "filter_list", return_value=0), \
                mock.patch.object(clean, "_clean_card"), mock.patch.object(clean, "card_disk", return_value="disk4"), \
                mock.patch.object(clean.shutil, "which", return_value="/usr/sbin/diskutil"), \
                mock.patch.object(clean.os, "chdir"), \
                mock.patch.object(clean.subprocess, "run", return_value=r) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), 0)
        self.assertEqual(run.call_args_list, [mock.call(["diskutil", "unmountDisk", "disk4"], capture_output=True, text=True)])
