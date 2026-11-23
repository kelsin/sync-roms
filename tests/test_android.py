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


class FakeDevice:
    """A fake adb over a temp folder standing for the device's storage."""
    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.calls = []
        self.fail_push = set()

    def real(self, remote):
        return self.root + remote

    def put(self, remote, data=b""):
        os.makedirs(os.path.dirname(self.real(remote)), exist_ok=True)
        with open(self.real(remote), "wb") as f:
            f.write(data)

    def run(self, *args, serial=None, check=True, timeout=60):
        import shlex
        import shutil
        self.calls.append(args)
        if args[0] == "pull":
            remote, local = self.real(args[2]), args[3]
            if os.path.isdir(local):
                local = os.path.join(local, os.path.basename(remote))
            shutil.copytree(remote, local)
            return ""
        if args[0] == "push":
            if args[2] in self.fail_push:
                raise adb.AdbError("push failed")
            os.makedirs(os.path.dirname(self.real(args[2])), exist_ok=True)
            shutil.copyfile(args[1], self.real(args[2]))
            return ""
        words = shlex.split(args[1])
        if words[0] == "test":
            if not os.path.isdir(self.real(words[2])):
                raise adb.AdbError("no")
            return ""
        if words[0] == "find":
            return "".join(os.path.join(d, f)[len(self.root):] + "\n"
                           for d, _, fs in os.walk(self.real(words[1])) for f in fs)
        if words[0] == "pidof":
            raise adb.AdbError("not running")
        return ""


class SessionTest(unittest.TestCase):
    def setUp(self):
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(quiet.close)
        self.dev = FakeDevice(self)
        self.folders = android.Folders("/storage/emulated/0/RetroArch/saves", "/storage/emulated/0/RetroArch/states",
                                       True, True)
        self.order = []
        for target, name, value in ((adb, "run", self.dev.run), (android, "retroarch_package", lambda s: "com.ra"),
                                    (android, "read_folders", lambda s, p: self.folders),
                                    (android, "wait_closed", lambda s, p: self.order.append("wait"))):
            p = mock.patch.object(target, name, side_effect=value)
            p.start()
            self.addCleanup(p.stop)
        self.catalog = store.load_catalog()
        self.layout = self.catalog["layouts"]["esde"]
        self.systems = [s for s in self.catalog["systems"] if s["folders"].get("esde") in ("gb", "gba")]
        self.target = android.Target("S1", "Nova", VOL, "NOVA")

    def open(self):
        s = android.open_session(self.target, self.layout, "esde", self.systems)
        self.addCleanup(s.close)
        return s

    def test_stage_pulls_saves_and_states(self):
        name = "Tetris Plus (USA, Europe) (SGB Enhanced).srm"
        self.dev.put(f"/storage/emulated/0/RetroArch/saves/Gambatte/{name}", b"data")
        self.dev.put("/storage/emulated/0/RetroArch/states/Gambatte/X.state1", b"st")
        s = self.open()
        with open(os.path.join(s.base, "RetroArch", "saves", "Gambatte", name), "rb") as f:
            self.assertEqual(f.read(), b"data")
        self.assertTrue(os.path.exists(os.path.join(s.retroarch_dir, "states", "Gambatte", "X.state1")))

    def test_stage_rom_placeholders(self):
        self.dev.put(f"/storage/{VOL}/ROMs/gb/Tom & Jerry (USA).zip", b"big")
        self.dev.put(f"/storage/{VOL}/ROMs/other/Skip.zip")
        s = self.open()
        path = os.path.join(s.base, "ROMs", "gb", "Tom & Jerry (USA).zip")
        self.assertEqual(os.path.getsize(path), 0)
        self.assertFalse(os.path.exists(os.path.join(s.base, "ROMs", "other")))

    def test_stage_missing_remote_dirs(self):
        s = self.open()
        self.assertEqual(os.listdir(os.path.join(s.retroarch_dir, "states")), [])
        self.assertEqual(os.listdir(os.path.join(s.retroarch_dir, "saves")), [])

    def test_sort_off_flat_layout(self):
        self.folders = android.Folders(*self.folders[:2], False, True)
        before = self.catalog["layouts"]["esde"]["retroarch"]["saves"]
        s = self.open()
        self.assertEqual(s.layout["retroarch"]["saves"], "saves")
        self.assertEqual(s.layout["retroarch"]["states"], "states/{core}")
        self.assertEqual(s.layout["retroarch"]["dir"], "RetroArch")
        self.assertEqual(self.layout["retroarch"]["saves"], before)

    def test_remote_mapping(self):
        s = self.open()
        got = s.remote(os.path.join(s.base, "RetroArch", "states", "Gambatte", "X.state1"))
        self.assertEqual(got, "/storage/emulated/0/RetroArch/states/Gambatte/X.state1")
        with self.assertRaises(ValueError):
            s.remote(os.path.join(s.base, "ROMs", "gb", "X.zip"))

    def test_push_mkdir_and_failures(self):
        s = self.open()
        a = os.path.join(s.retroarch_dir, "saves", "Gambatte", "A B.srm")
        b = os.path.join(s.retroarch_dir, "saves", "Gambatte", "C.srm")
        os.makedirs(os.path.dirname(a))
        for p in (a, b):
            open(p, "w").close()
        bad = "/storage/emulated/0/RetroArch/saves/Gambatte/A B.srm"
        self.dev.fail_push.add(bad)
        self.assertEqual(s.push([a, b]), [bad])
        self.assertTrue(os.path.exists(self.dev.real("/storage/emulated/0/RetroArch/saves/Gambatte/C.srm")))
        self.assertIn(("shell", "mkdir -p /storage/emulated/0/RetroArch/saves/Gambatte"), self.dev.calls)

    def test_waits_for_retroarch(self):
        self.dev.put("/storage/emulated/0/RetroArch/saves/Gambatte/A.srm")
        real = self.dev.run
        with mock.patch.object(adb, "run", side_effect=lambda *a, **k: (self.order.append(a[0]), real(*a, **k))[1]):
            self.open()
        self.assertEqual(self.order[0], "wait")
        self.assertIn("pull", self.order)

    def test_close_removes_temp(self):
        s = android.open_session(self.target, self.layout, "esde", self.systems)
        s.close()
        self.assertFalse(os.path.exists(s.base))
