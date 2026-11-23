import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

import helpers
from sync_roms import adb, android, android_settings, applied, ui, usersettings

E = applied.Entry


def by_key(entries):
    return {e.key: e for e in entries}


class CfgWanted(helpers.DataDir):
    def wanted(self, **settings):
        usersettings.save_settings(settings)
        return android_settings.cfg_wanted()

    def test_by_mode(self):
        self.assertEqual(self.wanted(spruce_ra_mode="Disabled")["cheevos_enable"], "false")
        for mode in ("Casual", "Softcore"):
            w = self.wanted(spruce_ra_mode=mode)
            self.assertEqual((w["cheevos_enable"], w["cheevos_hardcore_mode_enable"]), ("true", "false"))
        w = self.wanted(spruce_ra_mode="Hardcore", spruce_ra_username="u", spruce_ra_password="p")
        self.assertEqual((w["cheevos_enable"], w["cheevos_hardcore_mode_enable"]), ("true", "true"))
        self.assertEqual((w["cheevos_username"], w["cheevos_password"]), ("u", "p"))
        for settings in ({}, {"spruce_ra_mode": "Manual"}):
            w = self.wanted(**settings)
            self.assertNotIn("cheevos_enable", w)
            self.assertNotIn("cheevos_hardcore_mode_enable", w)
            self.assertNotIn("cheevos_username", w)

    def test_clears_cloud_sync(self):
        w = self.wanted()
        self.assertEqual({k: w[k] for k in ("cloud_sync_enable", "webdav_url", "webdav_username", "webdav_password")},
                         {"cloud_sync_enable": "false", "webdav_url": "", "webdav_username": "", "webdav_password": ""})
        self.assertEqual(w["savefile_directory"], android.DEFAULT_SAVES)
        self.assertEqual(w["savestate_directory"], android.DEFAULT_STATES)
        self.assertEqual(w["sort_savefiles_enable"], "true")

    def test_without_syncthing(self):
        w = self.wanted(spruce_syncthing=False)
        self.assertNotIn("savefile_directory", w)
        self.assertNotIn("sort_savefiles_enable", w)
        self.assertEqual(w["cloud_sync_enable"], "false")


class CfgEntries(unittest.TestCase):
    def test_marks_unchanged(self):
        found = by_key(android_settings.cfg_entries('cloud_sync_enable = "false"\nwebdav_url = "x"\n',
                                                    {"cloud_sync_enable": "false", "webdav_url": "", "webdav_password": ""}))
        self.assertFalse(applied.changed(found["cloud_sync_enable"]))
        self.assertEqual(found["webdav_url"], E("retroarch.cfg", "webdav_url", "x", "", False))
        self.assertEqual(found["webdav_password"], E("retroarch.cfg", "webdav_password", None, "", True))

    def test_username_change_clears_token(self):
        text = 'cheevos_username = "old"\ncheevos_token = "abc"\ncheevos_password = "pw"\n'
        found = by_key(android_settings.cfg_entries(text, {"cheevos_username": "new", "cheevos_password": "pw"}))
        self.assertEqual(found["cheevos_token"], E("retroarch.cfg", "cheevos_token", "abc", "", True))
        self.assertTrue(found["cheevos_password"].secret)
        same = by_key(android_settings.cfg_entries(text, {"cheevos_username": "old"}))
        self.assertNotIn("cheevos_token", same)
        empty = by_key(android_settings.cfg_entries('cheevos_token = ""\n', {"cheevos_username": "new"}))
        self.assertNotIn("cheevos_token", empty)

    def test_apply_keeps_crlf_and_other_lines(self):
        text = 'a = "1"\r\nwebdav_url = "x"\r\nb = "2"\r\n'
        entries = android_settings.cfg_entries(text, {"webdav_url": "", "b": "2"})
        self.assertEqual(android_settings.cfg_apply(text, entries), 'a = "1"\r\nwebdav_url = ""\r\nb = "2"\r\n')

    def test_apply_replaces_every_occurrence_literally(self):
        text = 'a = "1"\r\nwebdav_password = "x"\r\nb = "2"\r\nwebdav_password = "y"\r\n'
        entries = android_settings.cfg_entries(text, {"webdav_password": "p\\1\\g<0>"})
        self.assertEqual(android_settings.cfg_apply(text, entries),
                         'a = "1"\r\nwebdav_password = "p\\1\\g<0>"\r\nb = "2"\r\nwebdav_password = "p\\1\\g<0>"\r\n')

    def test_apply_appends_missing_key(self):
        entries = android_settings.cfg_entries('a = "1"', {"webdav_url": ""})
        self.assertEqual(android_settings.cfg_apply('a = "1"', entries), 'a = "1"\nwebdav_url = ""\n')


BLOCK = "<alternativeEmulator>\n\t<label>FCEUmm</label>\n</alternativeEmulator>\n"


class Gamelist(unittest.TestCase):
    def test_replaces_existing_label(self):
        text = '<?xml version="1.0"?>\n<alternativeEmulator>\n\t<label>Nestopia</label>\n</alternativeEmulator>\n<gameList />\n'
        entry = android_settings.gamelist_entry("nes", text, "FCEUmm")
        self.assertEqual(entry, E("ES-DE/gamelists/nes/gamelist.xml", "alternativeEmulator", "Nestopia", "FCEUmm", False))
        self.assertEqual(android_settings.gamelist_apply(text, "FCEUmm"), '<?xml version="1.0"?>\n' + BLOCK + "<gameList />\n")

    def test_inserts_before_gamelist(self):
        text = '<?xml version="1.0"?>\r\n<gameList>\r\n</gameList>\r\n'
        self.assertIsNone(android_settings.gamelist_entry("nes", text, "FCEUmm").old)
        self.assertEqual(android_settings.gamelist_apply(text, "FCEUmm"),
                         '<?xml version="1.0"?>\r\n' + BLOCK.replace("\n", "\r\n") + "<gameList>\r\n</gameList>\r\n")
        self.assertEqual(android_settings.gamelist_apply("<gameList />\n", "FCEUmm"), BLOCK + "<gameList />\n")

    def test_creates_missing_file(self):
        self.assertIsNone(android_settings.gamelist_entry("nes", None, "FCEUmm").old)
        self.assertEqual(android_settings.gamelist_apply(None, "Snes9x & Co"),
                         '<?xml version="1.0"?>\n' + BLOCK.replace("FCEUmm", "Snes9x &amp; Co") + "<gameList />\n")

    def test_empty_file_is_made(self):
        for text in ("", " \n"):
            self.assertEqual(android_settings.gamelist_apply(text, "FCEUmm"), android_settings.gamelist_apply(None, "FCEUmm"))

    def test_unchanged_label_unescaped(self):
        text = BLOCK.replace("FCEUmm", "A &amp; B") + "<gameList />\n"
        self.assertFalse(applied.changed(android_settings.gamelist_entry("x", text, "A & B")))


class EsdeWanted(helpers.DataDir):
    def test_maps_cores(self):
        found = android_settings.esde_wanted(["nes", "sg-1000", "zzz"])
        self.assertEqual(found, [("nes", "FCEUmm"), ("sg-1000", "Genesis Plus GX")])

    def test_off_without_syncthing(self):
        usersettings.save_settings({"spruce_syncthing": False})
        self.assertEqual(android_settings.esde_wanted(["nes"]), [])


OLD_CFG = 'cloud_sync_enable = "true"\nsavefile_directory = "x"\n'
RIGHT_CFG = "".join(f'{k} = "{v}"\n' for k, v in android_settings.CLOUD_SYNC.items())
ESDE_SYSTEMS = [{"bucket": "nes", "folders": {"esde": "nes"}}]
TARGET = android.Target("S", "Pixel", "6AF3-53E9", "card")
LAYOUT = {"roms_dir": "ROMs"}


class Apply(helpers.DataDir):
    """android_settings.apply with adb mocked: a fake device of files by path."""

    def setUp(self):
        super().setUp()
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(quiet.close)
        usersettings.save_settings({"spruce_syncthing": False})
        self.calls = []
        self.files = {}
        self.dirs = {"/storage/6AF3-53E9/ROMs/nes"}
        self.tmps = []
        self.pull_error = None
        self.push_error = None
        self.confirm = True
        pkg = "/storage/emulated/0/Android/data/com.retroarch/files/retroarch.cfg"
        self.cfg_path = pkg
        for name, fn in (("retroarch_package", lambda s: "com.retroarch"), ("wait_closed", self.wait_closed)):
            self.enterContext(mock.patch.object(android, name, fn))
        self.enterContext(mock.patch.object(adb, "is_file", lambda s, p: p in self.files))
        self.enterContext(mock.patch.object(adb, "is_dir", lambda s, p: p in self.dirs))
        self.enterContext(mock.patch.object(adb, "pull", self.pull))
        self.enterContext(mock.patch.object(adb, "push", self.push))
        self.enterContext(mock.patch.object(adb, "shell", lambda s, *w, check=True: self.calls.append(("shell",) + w) or ""))
        self.enterContext(mock.patch.object(ui, "confirm", lambda q, default=True: self.confirm))
        real = tempfile.mkdtemp
        self.enterContext(mock.patch.object(tempfile, "mkdtemp", lambda **k: self.tmps.append(real(**k)) or self.tmps[-1]))

    def wait_closed(self, serial, pkg):
        self.calls.append(("wait_closed",))

    def pull(self, serial, remote, local):
        if self.pull_error:
            raise self.pull_error
        with open(local, "w") as f:
            f.write(self.files[remote])

    def push(self, serial, local, remote):
        if self.push_error:
            raise self.push_error
        self.calls.append(("push", remote))
        with open(local) as f:
            self.files[remote] = f.read()

    def names(self):
        return [c[0] if c[0] != "shell" else c[2] for c in self.calls]

    def run_apply(self, dry_run=False):
        return android_settings.apply(TARGET, LAYOUT, ESDE_SYSTEMS, dry_run)

    def test_apply_dry_run_writes_nothing(self):
        self.files[self.cfg_path] = OLD_CFG
        self.assertEqual(self.run_apply(dry_run=True), 0)
        self.assertEqual(self.calls, [])

    def test_apply_pushes_only_changed_cfg(self):
        self.files[self.cfg_path] = RIGHT_CFG
        self.assertEqual(self.run_apply(), 0)
        self.assertEqual(self.calls, [])
        self.files[self.cfg_path] = OLD_CFG
        self.assertEqual(self.run_apply(), 0)
        self.assertEqual(self.names(), ["wait_closed", "push"])
        self.assertIn('cloud_sync_enable = "false"', self.files[self.cfg_path])

    def test_apply_restarts_esde_after_writing_gamelists(self):
        usersettings.save_settings({"spruce_syncthing": True})
        self.files[self.cfg_path] = "".join(f'{k} = "{v}"\n' for k, v in android_settings.cfg_wanted().items())
        self.run_apply()
        gamelist = "/storage/6AF3-53E9/ES-DE/gamelists/nes/gamelist.xml"
        names = self.names()
        self.assertEqual([n for n in names if n in ("force-stop", "push", "start")], ["force-stop", "push", "start"])
        self.assertIn("FCEUmm", self.files[gamelist])

    def test_apply_declined_esde_skips_gamelists(self):
        usersettings.save_settings({"spruce_syncthing": True})
        self.files[self.cfg_path] = "".join(f'{k} = "{v}"\n' for k, v in android_settings.cfg_wanted().items())
        self.confirm = False
        self.assertEqual(self.run_apply(), 0)
        self.assertNotIn("force-stop", self.names())
        self.assertNotIn("push", self.names())

    def test_apply_lost_device_removes_temp(self):
        self.files[self.cfg_path] = OLD_CFG
        self.pull_error = adb.AdbError("device offline")
        with self.assertRaises(adb.AdbError):
            self.run_apply()
        self.assertTrue(self.tmps)
        self.assertFalse(any(os.path.exists(t) for t in self.tmps))

    def test_apply_failed_push_returns_one(self):
        self.files[self.cfg_path] = OLD_CFG
        self.push_error = adb.AdbError("denied")
        self.assertEqual(self.run_apply(), 1)
