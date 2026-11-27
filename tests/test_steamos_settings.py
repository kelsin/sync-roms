import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import applied, steamos_settings as ss, steamos_syncthing, store, ui, usersettings  # noqa: E402

LAYOUT = {"roms_dir": "Emulation/roms"}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


class Folders(helpers.DataDir):
    def test_folders_default_and_missing(self):
        ra = os.path.join(self.tmp.name, "ra")
        got = ss.folders('savefile_directory = "default"\n', ra)
        self.assertEqual(got, {"saves": os.path.realpath(os.path.join(ra, "saves")),
                               "states": os.path.realpath(os.path.join(ra, "states"))})

    def test_folders_tilde_and_own_dir(self):
        ra = os.path.join(self.tmp.name, "ra")
        with mock.patch.dict(os.environ, {"HOME": self.tmp.name}):
            got = ss.folders('savefile_directory = "~/s"\nsavestate_directory = ":/st"\n', ra)
        self.assertEqual(got, {"saves": os.path.realpath(os.path.join(self.tmp.name, "s")),
                               "states": os.path.realpath(os.path.join(ra, "st"))})

    def test_folders_resolve_symlink(self):
        target = os.path.join(self.tmp.name, "Emulation", "saves", "retroarch", "saves")
        os.makedirs(target)
        link = os.path.join(self.tmp.name, "link")
        os.symlink(target, link)
        got = ss.folders(f'savefile_directory = "{link}"\n', self.tmp.name)
        self.assertEqual(got["saves"], os.path.realpath(target))


class Warnings(helpers.DataDir):
    def test_warnings_cloud_and_override(self):
        ra = os.path.join(self.tmp.name, "ra")
        write(os.path.join(ra, "config", "mGBA", "mGBA.cfg"), 'savefile_directory = "/x"\n')
        write(os.path.join(ra, "config", "Snes9x", "Snes9x.cfg"), 'video_smooth = "true"\n')
        write(os.path.join(ra, "config", "Gambatte", "gb.cfg"), 'savestate_directory = "/y"\n')
        got = ss.warnings(ra, "doSetupRA=true\ncloud_sync_status=true\n")
        self.assertEqual(len(got), 3)
        self.assertIn("Cloud Saves", got[0])
        self.assertTrue(any("mGBA.cfg" in w and "savefile_directory" in w for w in got))
        self.assertTrue(any("gb.cfg" in w and "savestate_directory" in w for w in got))

    def test_warnings_unreadable_core_skipped(self):
        ra = os.path.join(self.tmp.name, "ra")
        write(os.path.join(ra, "config", "mGBA", "mGBA.cfg"), 'savefile_directory = "/x"\n')
        write(os.path.join(ra, "config", "Snes9x", "Snes9x.cfg"), 'savefile_directory = "/y"\n')
        real = os.scandir

        def scandir(path):
            if os.path.basename(path) == "mGBA":
                raise PermissionError(13, "Permission denied", path)
            return real(path)
        with mock.patch.object(ss.os, "scandir", side_effect=scandir):
            got = ss.warnings(ra, None)
        self.assertEqual(len(got), 1)
        self.assertIn("Snes9x.cfg", got[0])

    def test_warnings_none(self):
        ra = os.path.join(self.tmp.name, "ra")
        self.assertEqual(ss.warnings(ra, 'cloud_sync_status="false"\n'), [])
        self.assertEqual(ss.warnings(ra, None), [])


class Running(unittest.TestCase):
    def test_pgrep_missing_is_not_running(self):
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError):
            self.assertFalse(ss._running("org.libretro.RetroArch"))

    def test_pgrep_found(self):
        with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(ss._running("es-de"))
        self.assertEqual(run.call_args[0][0], ["pgrep", "-f", "es-de"])


class Apply(helpers.DataDir):
    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp.name, "home")
        self.esde = os.path.join(self.home, "ES-DE")
        self.base = os.path.join(self.tmp.name, "card")
        self.roms = os.path.join(self.base, "Emulation", "roms")
        for folder in ("gba", "snes"):
            os.makedirs(os.path.join(self.roms, folder))
        self.enterContext(mock.patch.dict(os.environ, {"HOME": self.home, "ESDE_APPDATA_DIR": self.esde}))
        write(os.path.join(self.esde, "settings", "es_settings.xml"),
              f'<?xml version="1.0"?>\n<string name="ROMDirectory" value="{self.roms}" />\n')
        self.ra = os.path.expanduser(ss.RA_DIR)
        self.cfg = os.path.join(self.ra, "retroarch.cfg")
        self.saves = os.path.join(self.base, "Emulation", "saves", "retroarch", "saves")
        os.makedirs(self.saves)
        write(self.cfg, f'savefile_directory = "{self.saves}"\nvideo_driver = "vulkan"\n')
        self.gba = os.path.join(self.esde, "gamelists", "gba", "gamelist.xml")
        write(self.gba, '<?xml version="1.0"?>\n<gameList>\n</gameList>\n')
        self.running = {}
        self.enterContext(mock.patch.object(ss, "_running", lambda what: self.running.get(what, False)))
        self.enterContext(mock.patch.object(ui, "has_terminal", lambda: True))
        self.syncthing = self.enterContext(mock.patch.object(steamos_syncthing, "apply"))
        self.systems = store.load_catalog()["systems"]

    def run_apply(self, dry_run):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = ss.apply(self.base, LAYOUT, self.systems, dry_run)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_apply_dry_run_writes_nothing(self):
        before = (read(self.cfg), read(self.gba))
        code, out, _ = self.run_apply(True)
        self.assertEqual(code, 0)
        self.assertEqual((read(self.cfg), read(self.gba)), before)
        self.assertFalse(os.path.exists(os.path.join(self.esde, "gamelists", "snes", "gamelist.xml")))
        self.assertIn("would set   sort_savefiles_enable = true", out)
        self.assertIn("ES-DE/gamelists/gba/gamelist.xml", out)
        self.assertIn("ES-DE/gamelists/snes/gamelist.xml", out)
        self.assertEqual(self.syncthing.call_args[0][:2], ({"saves": os.path.realpath(self.saves),
                                                            "states": os.path.realpath(os.path.join(self.ra, "states"))}, True))

    def test_apply_writes_only_changed(self):
        code, out, _ = self.run_apply(False)
        self.assertEqual(code, 0)
        text = read(self.cfg)
        self.assertIn('sort_savefiles_enable = "true"', text)
        self.assertIn('video_driver = "vulkan"', text)
        self.assertIn(f'savefile_directory = "{self.saves}"', text)
        self.assertIn("<label>mGBA</label>", read(self.gba))
        self.assertIn("<label>Snes9x - Current</label>", read(os.path.join(self.esde, "gamelists", "snes", "gamelist.xml")))
        self.assertFalse(os.path.exists(os.path.join(self.esde, "gamelists", "nes")))
        self.assertEqual(self.syncthing.call_args[0][1], False)
        mtimes = {p: os.stat(p).st_mtime_ns for p in (self.cfg, self.gba)}
        for p in mtimes:
            os.utime(p, ns=(1, 1))
        code, out, _ = self.run_apply(False)
        self.assertEqual(code, 0)
        self.assertEqual([os.stat(p).st_mtime_ns for p in mtimes], [1, 1])
        self.assertNotIn("sort_savefiles_enable", out)

    def test_apply_missing_cfg_skips(self):
        os.remove(self.cfg)
        code, _, err = self.run_apply(False)
        self.assertEqual(code, 0)
        self.assertIn("Can't read RetroArch's settings", err)
        self.assertFalse(os.path.exists(self.cfg))
        self.assertIn("<label>mGBA</label>", read(self.gba))
        self.syncthing.assert_not_called()

    def test_apply_esde_running_declined_keeps_gamelists(self):
        self.running["es-de"] = True
        before = read(self.gba)
        with mock.patch.object(ui, "confirm", return_value=False) as confirm:
            code, _, _ = self.run_apply(False)
        self.assertEqual(code, 0)
        self.assertEqual(confirm.call_args.kwargs.get("default"), False)
        self.assertEqual(read(self.gba), before)
        self.assertIn('sort_savefiles_enable = "true"', read(self.cfg))

    def test_apply_esde_not_serving_card_skips_gamelists(self):
        write(os.path.join(self.esde, "settings", "es_settings.xml"),
              '<?xml version="1.0"?>\n<string name="ROMDirectory" value="/elsewhere" />\n')
        before = read(self.gba)
        code, _, err = self.run_apply(False)
        self.assertEqual(code, 0)
        self.assertIn("doesn't use this card's ROMs", err)
        self.assertEqual(read(self.gba), before)

    def test_apply_retroarch_running_waits(self):
        self.running["org.libretro.RetroArch"] = True
        answers = []

        def confirm(question, default=True, cancellable=False):
            answers.append(question)
            self.running["org.libretro.RetroArch"] = False
            return True
        with mock.patch.object(ui, "confirm", confirm):
            code, out, _ = self.run_apply(False)
        self.assertEqual(code, 0)
        self.assertEqual(len(answers), 1)
        self.assertIn("RetroArch is open", out)
        self.assertIn('sort_savefiles_enable = "true"', read(self.cfg))

    def test_apply_retroarch_running_no_terminal_fails(self):
        self.running["org.libretro.RetroArch"] = True
        before = read(self.cfg)
        with mock.patch.object(ui, "has_terminal", lambda: False):
            code, _, err = self.run_apply(False)
        self.assertEqual(code, 1)
        self.assertIn("RetroArch is open", err)
        self.assertEqual(read(self.cfg), before)

    def test_apply_prints_warnings(self):
        write(os.path.join(self.ra, "config", "mGBA", "mGBA.cfg"), 'savefile_directory = "/x"\n')
        write(os.path.join(self.home, ".config", "EmuDeck", "settings.sh"), "cloud_sync_status=true\n")
        for dry_run in (True, False):
            _, _, err = self.run_apply(dry_run)
            self.assertIn("Cloud Saves", err)
            self.assertIn("mGBA.cfg", err)


if __name__ == "__main__":
    unittest.main()
