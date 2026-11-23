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
from sync_roms import cli, flash, mount, picker, runtime, usersettings  # noqa: E402

DISK4 = flash.Disk("disk4", 1, "SD", ("A",), ("/Volumes/A",))
DISK5 = flash.Disk("disk5", 1, "SD", ("B",), ())


class Run(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, runtime, "ROOT", runtime.ROOT)
        runtime.ROOT = None
        self.disks = [DISK4, DISK5]
        self.pick = 0
        self.dry_run = False
        self.result = subprocess.CompletedProcess([], 0, "Volume(s) mounted successfully", "")
        self.external = self.enterContext(mock.patch.object(flash, "external_disks", side_effect=lambda ex: self.disks))
        self.disks_of = self.enterContext(mock.patch.object(flash, "disks_of", return_value=set()))
        self.filter = self.enterContext(mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: self.pick))
        self.diskutil = self.enterContext(mock.patch.object(mount.subprocess, "run", side_effect=lambda *a, **k: self.result))
        self.enterContext(mock.patch.object(sys, "platform", "darwin"))

    def run_mount(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = mount.run(types.SimpleNamespace(dry_run=self.dry_run))
        return code, out.getvalue()

    def test_lists_only_unmounted_and_mounts_pick(self):
        code, _ = self.run_mount()
        self.assertEqual(self.filter.call_args.args, ("🃏 Which card?", [flash._disk_label(DISK5)]))
        self.diskutil.assert_called_once_with(["diskutil", "mountDisk", "disk5"], capture_output=True, text=True)
        self.assertEqual(code, 0)

    def test_returns_1_when_mount_fails(self):
        self.result = subprocess.CompletedProcess([], 1, "", "failed")
        code, out = self.run_mount()
        self.assertEqual(code, 1)
        self.assertIn("couldn't mount disk5: failed", out)

    def test_esc_does_nothing(self):
        self.pick = None
        self.assertEqual(self.run_mount()[0], 0)
        self.diskutil.assert_not_called()

    def test_no_card(self):
        self.disks = [DISK4]
        code, out = self.run_mount()
        self.assertEqual(code, 1)
        self.filter.assert_not_called()
        self.assertIn("no unmounted SD card", out)

    def test_excludes_storage_disk(self):
        runtime.ROOT = "/Volumes/roms"
        self.disks_of.return_value = {"disk7"}
        self.run_mount()
        self.external.assert_called_with({"disk7"})

    def test_dry_run_does_nothing(self):
        self.dry_run = True
        code, out = self.run_mount()
        self.assertEqual(code, 0)
        self.assertIn("Would mount disk5", out)
        self.diskutil.assert_not_called()

    def test_needs_macos(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(self.run_mount()[0], 1)


class Main(unittest.TestCase):
    def test_main_runs_mount(self):
        self.addCleanup(setattr, runtime, "ROOT", runtime.ROOT)
        runtime.ROOT = None
        r = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(sys, "argv", ["sync-roms", "mount"]), \
                mock.patch.object(usersettings, "load_settings", lambda: {}), \
                mock.patch.object(flash, "external_disks", return_value=[DISK5]), \
                mock.patch.object(picker, "filter_list", return_value=0), \
                mock.patch.object(mount.subprocess, "run", return_value=r) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), 0)
        run.assert_called_once_with(["diskutil", "mountDisk", "disk5"], capture_output=True, text=True)
