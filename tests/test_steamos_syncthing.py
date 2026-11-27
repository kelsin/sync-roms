import contextlib
import hashlib
import io
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import android_syncthing, spruce_syncthing, steamos_syncthing as st  # noqa: E402

CONFIG = "<configuration><gui tls=\"{tls}\"><address>{address}</address><apikey>k</apikey></gui></configuration>"
PATHS = {"saves": "/home/deck/Emulation/saves/retroarch/saves", "states": "/home/deck/Emulation/saves/retroarch/states"}


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def no_pgrep(*args, **kwargs):
    return subprocess.CompletedProcess(args[0], 1, "", "")


def tarball():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (("syncthing-linux-amd64-v9.9.9/syncthing", b"#!/bin/sh\n"),
                           ("syncthing-linux-amd64-v9.9.9/etc/linux-systemd/user/syncthing.service",
                            b"[Service]\nExecStart=/usr/bin/syncthing serve --no-browser --no-restart\nRestart=on-failure\n")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


RELEASE = {"assets": [{"name": "syncthing-linux-amd64-v9.9.9.tar.gz", "browser_download_url": "https://x/tar"},
                      {"name": "syncthing-linux-arm64-v9.9.9.tar.gz", "browser_download_url": "https://x/arm"},
                      {"name": "sha256sum.txt.asc", "browser_download_url": "https://x/sums"}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(dir=os.environ["HOME"])
        patcher = mock.patch.object(st.subprocess, "run", side_effect=no_pgrep)
        self.run = patcher.start()
        self.addCleanup(patcher.stop)


class FindTest(Base):
    def test_find_order(self):
        state = os.path.join(self.home, ".local/state/syncthing/config.xml")
        config = os.path.join(self.home, ".config/syncthing/config.xml")
        write(config)
        self.assertEqual(st.find(self.home), st.Install(config, None))
        write(state)
        self.assertEqual(st.find(self.home), st.Install(state, None))
        self.run.side_effect = lambda *a, **k: subprocess.CompletedProcess(
            a[0], 0, "12 syncthing-gtk\n34 /usr/bin/syncthing serve --home=/x --no-browser\n", "")
        self.assertEqual(st.find(self.home), st.Install("/x/config.xml", None))
        self.run.side_effect = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "34 syncthing --config /y\n", "")
        self.assertEqual(st.find(self.home), st.Install("/y/config.xml", None))

    def test_find_running_flatpak_home(self):
        folder = os.path.join(self.home, ".var/app", st.FLATPAKS[1], "data")
        self.run.side_effect = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, f"34 /app/bin/syncthing --home={folder}\n", "")
        self.assertEqual(st.find(self.home), st.Install(os.path.join(folder, "config.xml"), st.FLATPAKS[1]))

    def test_find_flatpak(self):
        for sub in ("config", ".local/state"):
            with self.subTest(sub=sub):
                home = tempfile.mkdtemp(dir=os.environ["HOME"])
                path = os.path.join(home, ".var/app", st.FLATPAKS[0], sub, "syncthing/config.xml")
                write(path)
                self.assertEqual(st.find(home), st.Install(path, st.FLATPAKS[0]))

    def test_find_none(self):
        self.assertIsNone(st.find(self.home))
        self.run.side_effect = FileNotFoundError("pgrep")
        self.assertIsNone(st.find(self.home))


class ReadConfigTest(unittest.TestCase):
    def test_read_config_tls_and_port(self):
        self.assertEqual(st.read_config(CONFIG.format(tls="true", address="0.0.0.0:8385")), ("k", 8385, "https"))
        self.assertEqual(st.read_config(CONFIG.format(tls="false", address="127.0.0.1:8384")), ("k", 8384, "http"))
        self.assertEqual(st.read_config("<configuration><gui><address>[::1]:9000</address><apikey>k</apikey></gui></configuration>"),
                         ("k", 9000, "http"))

    def test_read_config_no_key(self):
        self.assertIsInstance(st.read_config("<configuration><gui><address>127.0.0.1:8384</address></gui></configuration>"), str)
        self.assertIsInstance(st.read_config("not xml"), str)


class FlatpakEntriesTest(unittest.TestCase):
    def test_flatpak_entries(self):
        home = os.path.realpath(os.path.expanduser("~"))
        self.assertEqual(st.flatpak_entries("app", [os.path.join(home, "Emulation/x")], "[Context]\nfilesystems=home;\n"), [])
        self.assertEqual(st.flatpak_entries("app", [os.path.join(home, "Emulation/x")], "filesystems=~/Emulation;\n"), [])
        self.assertEqual(st.flatpak_entries("app", [os.path.join(home, "Emulation/x")], "filesystems=home:ro;\n")[0].new, "allowed")
        folders = ["/run/media/deck/sd/Emulation/x"]
        self.assertEqual(len(st.flatpak_entries("app", folders, "[Context]\nfilesystems=home;\n")), 1)
        folders = ["/home/deck/Emulation/x"]
        self.assertEqual(st.flatpak_entries("app", folders, "[Context]\nfilesystems=host:rw;\n"), [])
        self.assertEqual(st.flatpak_entries("app", folders, "[Context]\nfilesystems=/home/deck/Emulation;\n"), [])
        entries = st.flatpak_entries("app", folders, "[Context]\nfilesystems=xdg-download;/home/deck/Emu;\n")
        self.assertEqual([(e.key, e.old, e.new) for e in entries], [("filesystem /home/deck/Emulation/x", None, "allowed")])
        self.assertEqual(len(st.flatpak_entries("app", folders, "[Context]\nshared=network;\n")), 1)


class InstallTest(Base):
    def setUp(self):
        super().setUp()
        self.data = tarball()
        sums = f"-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n{hashlib.sha256(self.data).hexdigest()}  syncthing-linux-amd64-v9.9.9.tar.gz\n"
        self.downloads = {"https://x/tar": self.data, "https://x/sums": sums.encode()}
        patches = [mock.patch.object(st.github, "json", return_value=RELEASE),
                   mock.patch.object(st, "_fetch", side_effect=lambda url: self.downloads[url]),
                   mock.patch.object(st.platform, "machine", return_value="x86_64"),
                   mock.patch.object(st.time, "sleep")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_install_checksum_mismatch_raises(self):
        self.downloads["https://x/tar"] = self.data + b"x"
        with self.assertRaises(ValueError):
            st.install(self.home)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local/bin/syncthing")))
        self.run.assert_not_called()

    def test_install_writes_unit_and_enables(self):
        config = os.path.join(self.home, ".local/state/syncthing/config.xml")

        def run(cmd, **kwargs):
            if cmd[-1] == "syncthing" and "enable" in cmd:
                write(config, "x")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        self.run.side_effect = run
        self.assertEqual(st.install(self.home), config)
        binary = os.path.join(self.home, ".local/bin/syncthing")
        self.assertEqual(stat.S_IMODE(os.stat(binary).st_mode), 0o755)
        with open(os.path.join(self.home, ".config/systemd/user/syncthing.service")) as f:
            unit = f.read()
        self.assertIn(f"ExecStart={binary} serve --no-browser --no-restart\n", unit)
        self.assertIn("Restart=on-failure", unit)
        cmds = [c.args[0] for c in self.run.call_args_list]
        self.assertEqual(cmds, [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "syncthing"]])

    def test_install_times_out(self):
        self.run.side_effect = lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.object(st.time, "monotonic", side_effect=[0, 0, 31]):
            with self.assertRaises(OSError):
                st.install(self.home)


class ApplyTest(Base):
    SRV = {"id": "X", "folders": []}

    def setUp(self):
        super().setUp()
        patches = [mock.patch.dict(os.environ, {"HOME": self.home}),
                   mock.patch.object(spruce_syncthing, "server", return_value=self.SRV),
                   mock.patch.object(android_syncthing, "_up", return_value=True),
                   mock.patch.object(android_syncthing, "configure", return_value=[])]
        mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.up, self.configure = mocks[2], mocks[3]
        self.install = mock.patch.object(st, "install").start()
        self.addCleanup(mock.patch.stopall)

    def apply(self, dry_run=False):
        failed = []
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            st.apply(PATHS, dry_run, failed)
        return failed, out.getvalue(), err.getvalue()

    def test_apply_existing_not_installed_again(self):
        write(os.path.join(self.home, ".config/syncthing/config.xml"), CONFIG.format(tls="true", address="127.0.0.1:8384"))
        failed, out, err = self.apply()
        self.assertEqual(failed, [])
        self.install.assert_not_called()
        self.configure.assert_called_once_with(8384, "k", self.SRV, PATHS, False, "https", where="Syncthing",
                                               mod_time_window=2, wait=False)
        self.assertNotIn("k\n", out + err)

    def test_apply_existing_down_warns(self):
        write(os.path.join(self.home, ".config/syncthing/config.xml"), CONFIG.format(tls="false", address="127.0.0.1:8384"))
        self.up.return_value = False
        failed, out, err = self.apply()
        self.assertIn("start it", err)
        self.configure.assert_not_called()
        self.install.assert_not_called()
        self.assertEqual(failed, [])

    def test_apply_dry_run_installs_nothing(self):
        failed, out, err = self.apply(dry_run=True)
        self.install.assert_not_called()
        self.configure.assert_not_called()
        self.assertIn("would install", out)
        self.assertEqual(failed, [])

    def test_apply_installs_when_none(self):
        config = os.path.join(self.home, ".local/state/syncthing/config.xml")

        def install(home):
            write(config, CONFIG.format(tls="false", address="127.0.0.1:8384"))
            return config
        self.install.side_effect = install
        failed, out, err = self.apply()
        self.install.assert_called_once_with(self.home)
        self.assertEqual(self.configure.call_args.args[:6], (8384, "k", self.SRV, PATHS, False, "http"))

    def test_apply_install_error_fails(self):
        self.install.side_effect = ValueError("checksum")
        failed, out, err = self.apply()
        self.assertEqual(failed, ["Syncthing"])
        self.assertIn("checksum", err)

    def test_apply_flatpak_override(self):
        app = st.FLATPAKS[0]
        write(os.path.join(self.home, ".var/app", app, "config/syncthing/config.xml"),
              CONFIG.format(tls="false", address="127.0.0.1:8384"))

        def run(cmd, **kwargs):
            if cmd[0] == "flatpak" and cmd[1] == "info":
                return subprocess.CompletedProcess(cmd, 0, "[Context]\nfilesystems=xdg-download;\n", "")
            return no_pgrep(cmd)
        self.run.side_effect = run
        failed, out, err = self.apply()
        overrides = [c.args[0] for c in self.run.call_args_list if c.args[0][:2] == ["flatpak", "override"]]
        self.assertEqual(overrides, [["flatpak", "override", "--user", f"--filesystem={p}", app] for p in PATHS.values()])
        self.assertIn(f"restart {app}", out + err)

    def test_apply_flatpak_dry_run_overrides_nothing(self):
        app = st.FLATPAKS[0]
        write(os.path.join(self.home, ".var/app", app, "config/syncthing/config.xml"),
              CONFIG.format(tls="false", address="127.0.0.1:8384"))
        self.run.side_effect = lambda cmd, **k: (subprocess.CompletedProcess(cmd, 0, "filesystems=xdg-download;\n", "")
                                                 if cmd[:2] == ["flatpak", "info"] else no_pgrep(cmd))
        failed, out, err = self.apply(dry_run=True)
        self.assertFalse([c for c in self.run.call_args_list if c.args[0][:2] == ["flatpak", "override"]])
        self.assertIn("would set", out)

    def test_apply_off(self):
        with mock.patch.object(spruce_syncthing, "enabled", return_value=False):
            failed, out, err = self.apply()
        self.assertEqual(out + err, "")
        self.run.assert_not_called()

    def test_apply_no_server_skips_configure(self):
        write(os.path.join(self.home, ".config/syncthing/config.xml"), CONFIG.format(tls="false", address="127.0.0.1:8384"))
        with mock.patch.object(spruce_syncthing, "server", return_value=None):
            failed, out, err = self.apply()
        self.configure.assert_not_called()
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
