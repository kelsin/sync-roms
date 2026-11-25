import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import adb  # noqa: E402

DEVICES = ("List of devices attached\n"
           "adb-1f137be-k7i7uw._adb-tls-connect._tcp device product:kalama model:Retroid_Pocket_Nova device:kalama transport_id:4\n"
           "R5CT unauthorized usb:1-1 transport_id:2\n\n")


class AdbTest(unittest.TestCase):
    def test_devices_parses_l(self):
        with mock.patch.object(adb, "run", return_value=DEVICES):
            self.assertEqual(adb.devices(), [
                adb.Device("adb-1f137be-k7i7uw._adb-tls-connect._tcp", "device", "Retroid Pocket Nova"),
                adb.Device("R5CT", "unauthorized", "")])

    def test_shell_quotes(self):
        with mock.patch.object(adb, "run", return_value="") as run:
            adb.shell("S", "ls", "/x/Tom & Jerry (USA).srm")
        run.assert_called_once_with("shell", "ls '/x/Tom & Jerry (USA).srm'", serial="S", check=True)

    def test_run_raises(self):
        done = subprocess.CompletedProcess([], 1, stdout="out", stderr="error: closed")
        with mock.patch.object(adb, "require", return_value="adb"), \
                mock.patch.object(adb.subprocess, "run", return_value=done):
            with self.assertRaises(adb.AdbError) as ctx:
                adb.run("devices")
            self.assertEqual(str(ctx.exception), "error: closed")
            self.assertEqual(adb.run("devices", check=False), "out")

    def test_run_timeout(self):
        with mock.patch.object(adb, "require", return_value="adb"), \
                mock.patch.object(adb.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 1)):
            with self.assertRaises(adb.AdbError):
                adb.run("devices")

    def test_run_passes_serial(self):
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch.object(adb, "require", return_value="/bin/adb"), \
                mock.patch.object(adb.subprocess, "run", return_value=done) as sub:
            adb.run("pull", "a", "b", serial="S")
        self.assertEqual(sub.call_args.args[0], ["/bin/adb", "-s", "S", "pull", "a", "b"])

    def test_mdns(self):
        out = "List of discovered mdns services\nadb-1f137be-k7i7uw\t_adb-tls-connect._tcp\t192.168.1.5:37011\n"
        with mock.patch.object(adb, "run", return_value=out):
            self.assertEqual(adb.mdns_services(),
                             [("adb-1f137be-k7i7uw", "_adb-tls-connect._tcp", "192.168.1.5:37011")])

    def test_connect(self):
        with mock.patch.object(adb, "run", return_value="connected to 1.2.3.4:5"):
            self.assertTrue(adb.connect("1.2.3.4:5"))
        with mock.patch.object(adb, "run", return_value="failed to connect to 1.2.3.4:5"):
            self.assertFalse(adb.connect("1.2.3.4:5"))

    def test_shell_ok(self):
        with mock.patch.object(adb, "run", side_effect=adb.AdbError("x")):
            self.assertFalse(adb.shell_ok("S", "pidof", "x"))
        with mock.patch.object(adb, "run", return_value="123\n"):
            self.assertTrue(adb.shell_ok("S", "pidof", "x"))

    def test_forward_returns_local_port(self):
        with mock.patch.object(adb, "run", return_value="57983\n") as run:
            self.assertEqual(adb.forward("S", 8384), 57983)
        run.assert_called_once_with("forward", "tcp:0", "tcp:8384", serial="S")

    def test_forward_remove(self):
        with mock.patch.object(adb, "run", return_value="") as run:
            adb.forward_remove("S", 57983)
        run.assert_called_once_with("forward", "--remove", "tcp:57983", serial="S", check=False)

    def test_is_dir(self):
        with mock.patch.object(adb, "run", return_value="y\n") as run:
            self.assertTrue(adb.is_dir("S", "/x/A B"))
        run.assert_called_once_with("shell", "sh -c 'test -d \"$1\" && echo y || echo n' _ '/x/A B'",
                                    serial="S", check=True)
        with mock.patch.object(adb, "run", return_value="n\n"):
            self.assertFalse(adb.is_dir("S", "/x"))
        with mock.patch.object(adb, "run", side_effect=adb.AdbError("device offline")):
            with self.assertRaises(adb.AdbError):
                adb.is_dir("S", "/x")

    def test_pull_and_push_never_time_out(self):
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch.object(adb, "require", return_value="adb"), \
                mock.patch.object(adb.subprocess, "run", return_value=done) as sub:
            adb.pull("S", "/r", "/l")
            adb.push("S", "/l", "/r")
        self.assertEqual([c.kwargs["timeout"] for c in sub.call_args_list], [None, None])

    def test_require_missing(self):
        with mock.patch.object(adb.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                adb.require()
        self.assertEqual(ctx.exception.code, 2)

    def test_require_missing_mounted_hint(self):
        err = io.StringIO()
        with mock.patch.object(adb.shutil, "which", return_value=None), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(err):
            with self.assertRaises(SystemExit):
                adb.require(mounted=True)
        self.assertIn("adb isn't installed (brew install android-platform-tools); for a mounted card, pass its "
                      "folder or run from it", err.getvalue())


if __name__ == "__main__":
    unittest.main()
