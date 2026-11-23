import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import adb, android, store  # noqa: E402

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

    def test_reconnect_connects_unconnected(self):
        devs = [adb.Device("adb-X._adb-tls-connect._tcp", "device", "")]
        services = [("adb-X", "_adb-tls-connect._tcp", "1.1.1.1:1"), ("adb-Y", "_adb-tls-connect._tcp", "2.2.2.2:2"),
                    ("adb-Z", "_adb-tls-pairing._tcp", "3.3.3.3:3")]
        with mock.patch.object(adb, "devices", return_value=devs), \
                mock.patch.object(adb, "mdns_services", return_value=services), \
                mock.patch.object(adb, "connect") as connect:
            android.reconnect()
        connect.assert_called_once_with("2.2.2.2:2")

    def test_wait_closed_declined_stops(self):
        with mock.patch.object(android, "running", return_value=True), \
                mock.patch.object(android.ui, "confirm", return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                android.wait_closed("S", "com.retroarch")
        self.assertEqual(ctx.exception.code, 0)


NOVA = adb.Device("S1", "device", "Retroid Pocket Nova")
VOL = "6AF3-53E9"


class ResolveTest(unittest.TestCase):
    def setUp(self):
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(quiet.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(store, "data_dir", lambda: tmp.name)
        patch.start()
        self.addCleanup(patch.stop)
        self.cards = {}
        self.devs = [NOVA]
        self.vols = {"S1": [VOL]}
        self.picks = []
        self.shown = []

        def filter_list(title, labels, **kw):
            self.shown.append(list(labels))
            return self.picks.pop(0)
        for target, kw in ((adb, {"require": None, "devices": lambda: self.devs, "mdns_services": []}),
                           (android, {"reconnect": None, "card_volumes": lambda s, r: self.vols.get(s, [])}),
                           (android.picker, {"filter_list": filter_list})):
            for name, value in kw.items():
                p = mock.patch.object(target, name, side_effect=value) if callable(value) else \
                    mock.patch.object(target, name, return_value=value)
                p.start()
                self.addCleanup(p.stop)

    def save(self, cards):
        self.cards = cards
        store.write_cards(cards)

    def card(self, **kw):
        return {"layout": "esde", "device": "retroid-pocket-nova", **kw}

    def test_named_card_finds_its_device(self):
        self.save({"POCKETNOVA": self.card(android_volume=VOL)})
        got = android.resolve("POCKETNOVA", self.cards)
        self.assertEqual(got, android.Target("S1", "Retroid Pocket Nova", VOL, "POCKETNOVA"))
        self.assertEqual(self.shown, [])

    def test_new_volume_asks_and_remembers(self):
        self.save({"POCKETNOVA": self.card(), "LINUX": {"layout": "knulli", "device": "x"}})
        self.picks = [0, 0]
        got = android.resolve(None, self.cards)
        self.assertEqual(got.card, "POCKETNOVA")
        self.assertIn("new card", self.shown[0][0])
        self.assertEqual(self.shown[1], ["POCKETNOVA"])
        self.assertEqual(store.load_cards()["POCKETNOVA"]["android_volume"], VOL)
        self.assertEqual(self.cards["POCKETNOVA"]["android_volume"], VOL)

    def test_volume_moves_from_a_card_no_longer_android(self):
        self.save({"OLD": self.card(android_volume=VOL, layout="knulli"), "NEW": self.card()})
        self.picks = [0]
        got = android.resolve("NEW", self.cards)
        self.assertEqual(got.card, "NEW")
        saved = store.load_cards()
        self.assertEqual(saved["NEW"]["android_volume"], VOL)
        self.assertNotIn("android_volume", saved["OLD"])

    def test_named_card_wrong_device_fails(self):
        self.save({"POCKETNOVA": self.card(), "OTHER": self.card(android_volume=VOL)})
        self.picks = [0]
        with self.assertRaises(SystemExit) as ctx:
            android.resolve("POCKETNOVA", self.cards)
        self.assertEqual(ctx.exception.code, 2)

    def test_unauthorized_not_listed(self):
        self.devs = [NOVA, adb.Device("S2", "unauthorized", "")]
        self.save({"POCKETNOVA": self.card(android_volume=VOL)})
        self.picks = [None]
        with self.assertRaises(SystemExit) as ctx:
            android.resolve(None, self.cards)
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(len(self.shown[0]), 2)
        self.assertIn("POCKETNOVA", self.shown[0][0])

    def test_setup_row_runs_setup(self):
        self.save({"POCKETNOVA": self.card()})
        self.picks = [1, 0, 0]
        with mock.patch.object(android, "setup_device") as setup:
            android.resolve(None, self.cards)
        setup.assert_called_once_with()
        self.assertEqual(len(self.shown), 3)

    def test_no_roms_volume_fails(self):
        self.vols = {}
        self.picks = [0]
        with self.assertRaises(SystemExit) as ctx:
            android.resolve(None, self.cards)
        self.assertEqual(ctx.exception.code, 2)


class SetupTest(unittest.TestCase):
    def test_setup_device_pairs(self):
        pairing = [("adb-Y", "_adb-tls-pairing._tcp", "1.2.3.4:4000")]
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(android.time, "sleep"), \
                mock.patch.object(adb, "mdns_services", return_value=pairing), \
                mock.patch.object(android.ui, "ask", return_value="123456"), \
                mock.patch.object(adb, "pair") as pair, \
                mock.patch.object(adb, "devices", return_value=[NOVA]), \
                mock.patch.object(android, "reconnect") as reconnect:
            android.setup_device()
        pair.assert_called_once_with("1.2.3.4:4000", "123456")
        reconnect.assert_called_once_with()

    def test_setup_device_asks_address_when_no_new_device(self):
        pairing = [("adb-Y", "_adb-tls-pairing._tcp", "1.2.3.4:4000")]
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(android.time, "sleep"), \
                mock.patch.object(adb, "mdns_services", return_value=pairing), \
                mock.patch.object(android.ui, "ask", side_effect=["123456", "1.2.3.4:5555"]), \
                mock.patch.object(adb, "pair"), mock.patch.object(adb, "connect") as connect, \
                mock.patch.object(adb, "devices", return_value=[NOVA]), \
                mock.patch.object(android, "reconnect"):
            android.setup_device()
        connect.assert_called_once_with("1.2.3.4:5555")


if __name__ == "__main__":
    unittest.main()
