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

    def test_shell_ok_and_prop(self):
        with mock.patch.object(adb, "run", side_effect=adb.AdbError("x")):
            self.assertFalse(adb.shell_ok("S", "test", "-d", "/x"))
        with mock.patch.object(adb, "run", return_value="14\n"):
            self.assertEqual(adb.prop("S", "ro.build.version.release"), "14")

    def test_require_missing(self):
        with mock.patch.object(adb.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                adb.require()
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
