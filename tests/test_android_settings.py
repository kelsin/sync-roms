import contextlib
import io
import os
import tempfile
import zipfile
import unittest
from unittest import mock

import helpers
from test_apk import manifest_bytes
from sync_roms import adb, android, android_settings, applied, inventory, s3, store, ui, usersettings

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
APKS = "os/android/APKs/"
CARD_APK = "/storage/6AF3-53E9/APKs/app.apk"


class Apply(helpers.DataDir):
    """android_settings.apply with adb mocked: a fake device of files by path."""

    def setUp(self):
        super().setUp()
        quiet = contextlib.ExitStack()
        self.out, self.err = io.StringIO(), io.StringIO()
        quiet.enter_context(contextlib.redirect_stdout(self.out))
        quiet.enter_context(contextlib.redirect_stderr(self.err))
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
        self.enterContext(mock.patch.object(adb, "is_file", lambda s, p: p in self.files or p in self.card_apks))
        self.enterContext(mock.patch.object(adb, "is_dir", lambda s, p: p in self.dirs))
        self.enterContext(mock.patch.object(adb, "pull", self.pull))
        self.enterContext(mock.patch.object(adb, "push", self.push))
        self.enterContext(mock.patch.object(adb, "shell", self.shell))
        self.apks = {}  # storage key -> APK bytes
        self.packages = {}  # installed package -> versionCode
        self.card_apks = {}  # card path -> APK bytes
        self.pm_install = "Success"
        self.install_error = None
        self.enterContext(mock.patch.object(inventory, "files", lambda prefix, sizes=True: {k: len(v) for k, v in self.apks.items()}))
        self.enterContext(mock.patch.object(s3, "download", self.download))
        self.enterContext(mock.patch.object(adb, "exec_out", self.exec_out))
        self.enterContext(mock.patch.object(adb, "install", self.install))
        self.enterContext(mock.patch.object(adb, "installed_version", lambda s, pkg: self.packages.get(pkg)))
        self.enterContext(mock.patch.object(ui, "confirm", lambda q, default=True: self.confirm))
        real = tempfile.mkdtemp
        self.enterContext(mock.patch.object(tempfile, "mkdtemp", lambda **k: self.tmps.append(real(**k)) or self.tmps[-1]))

    def shell(self, serial, *words, check=True):
        self.calls.append(("shell",) + words)
        if words[:3] == ("pm", "list", "packages"):
            return "".join(f"package:{p}\n" for p in self.packages)
        if words[0] == "stat":
            return f"{len(self.card_apks[words[-1]])}\n"
        if words[:2] == ("pm", "install"):
            return self.pm_install
        return ""

    def download(self, job):
        key, path, size = job
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.apks[key])
        self.calls.append(("download", key))

    def exec_out(self, serial, *words):
        self.calls.append(("exec_out",) + words)
        with zipfile.ZipFile(io.BytesIO(self.card_apks[words[2]])) as z:
            return z.read("AndroidManifest.xml")

    def install(self, serial, local, replace=False):
        if self.install_error:
            raise adb.AdbError(self.install_error)
        self.calls.append(("install", os.path.basename(local), replace))

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

    def apk_setup(self, name="app.apk", package="com.example.app", version=65, installed=None):
        self.files[self.cfg_path] = RIGHT_CFG
        self.apks[APKS + name] = apk_zip(package, version)
        if installed is not None:
            self.packages[package] = installed

    def test_apply_installs_only_missing_packages(self):
        self.apk_setup()
        self.assertEqual(self.run_apply(), 0)
        self.assertEqual(self.calls, [("shell", "pm", "list", "packages"), ("download", APKS + "app.apk"), ("install", "app.apk", False)])
        self.calls.clear()
        self.packages["com.example.app"] = 65
        self.assertEqual(self.run_apply(), 0)
        self.assertNotIn("install", self.names())
        self.assertEqual(self.run_apply(dry_run=True), 0)
        self.assertIn("up to date", self.out.getvalue())

    def test_apply_upgrades_newer_apk(self):
        self.apk_setup(installed=64)
        self.assertEqual(self.run_apply(dry_run=True), 0)
        self.assertIn("would upgrade 64 → 65", self.out.getvalue())
        self.assertNotIn("install", self.names())
        self.assertEqual(self.run_apply(), 0)
        self.assertIn(("install", "app.apk", True), self.calls)
        self.assertIn("⬆️ Upgrading app.apk (64 → 65)", self.out.getvalue())

    def test_apply_never_downgrades(self):
        self.apk_setup(installed=66)
        self.assertEqual(self.run_apply(), 0)
        self.assertNotIn("install", self.names())
        self.assertNotIn("Upgrading", self.out.getvalue())

    def test_apply_warns_on_incompatible_upgrade(self):
        self.apk_setup(installed=64)
        self.install_error = "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]"
        self.assertEqual(self.run_apply(), 1)
        self.assertIn("uninstall", self.err.getvalue())

    def test_apply_installs_from_card_copy_when_same_size(self):
        self.apk_setup()
        self.card_apks[CARD_APK] = self.apks[APKS + "app.apk"]
        self.assertEqual(self.run_apply(), 0)
        self.assertIn(("shell", "pm", "install", CARD_APK), self.calls)
        self.assertEqual([c for c in self.calls if c[0] in ("download", "install")], [])

    def test_apply_ignores_card_copy_of_another_size(self):
        self.apk_setup()
        self.card_apks[CARD_APK] = self.apks[APKS + "app.apk"] + b"x"
        self.run_apply()
        self.assertIn(("download", APKS + "app.apk"), self.calls)

    def test_apply_falls_back_to_storage_when_pm_install_fails(self):
        self.apk_setup(installed=64)
        self.card_apks[CARD_APK] = self.apks[APKS + "app.apk"]
        self.pm_install = "Failure [INSTALL_FAILED_INVALID_URI]"
        self.assertEqual(self.run_apply(), 0)
        self.assertIn(("shell", "pm", "install", "-r", CARD_APK), self.calls)
        self.assertIn(("install", "app.apk", True), self.calls)

    def test_apply_dry_run_lists_every_apk(self):
        self.apk_setup()
        self.apks[APKS + "dawn-zero.apk"] = apk_zip("com.dawn", 1)
        self.apks[APKS + "obtainium.json"] = b"{}"
        self.assertEqual(self.run_apply(dry_run=True), 0)
        self.assertEqual([c[0] for c in self.calls if c[0] in ("install",)], [])
        shown = self.out.getvalue()
        self.assertIn("app.apk: would install", shown)
        self.assertIn("dawn-zero.apk: skipped (not needed)", shown)
        self.assertNotIn("obtainium", shown)

    def test_apply_skips_unreadable_apk(self):
        self.files[self.cfg_path] = RIGHT_CFG
        self.apks[APKS + "bad.apk"] = b"not a zip"
        self.assertEqual(self.run_apply(), 0)
        self.assertIn("Can't read bad.apk", self.err.getvalue())

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

    def test_apply_rereads_cfg_after_retroarch_closes(self):
        self.files[self.cfg_path] = OLD_CFG
        saved = 'cloud_sync_enable = "true"\nsavefile_directory = "x"\nnew_key = "kept"\n'

        def closed(serial, pkg):
            self.calls.append(("wait_closed",))
            self.files[self.cfg_path] = saved
        with mock.patch.object(android, "wait_closed", closed):
            self.assertEqual(self.run_apply(), 0)
        pushed = self.files[self.cfg_path]
        self.assertIn('new_key = "kept"', pushed)
        self.assertIn('cloud_sync_enable = "false"', pushed)

    def test_apply_skips_push_when_close_fixed_cfg(self):
        self.files[self.cfg_path] = OLD_CFG

        def closed(serial, pkg):
            self.files[self.cfg_path] = RIGHT_CFG
        with mock.patch.object(android, "wait_closed", closed):
            self.assertEqual(self.run_apply(), 0)
        self.assertEqual(self.calls, [])

    def test_apply_missing_cfg_warns_and_skips_retroarch(self):
        with mock.patch.object(ui, "warn") as warn:
            self.assertEqual(self.run_apply(), 0)
        self.assertEqual(self.calls, [])
        self.assertIn("retroarch.cfg", warn.call_args[0][0])

    def test_apply_creates_missing_gamelist(self):
        usersettings.save_settings({"spruce_syncthing": True})
        self.files[self.cfg_path] = "".join(f'{k} = "{v}"\n' for k, v in android_settings.cfg_wanted().items())
        self.run_apply()
        gamelist = "/storage/6AF3-53E9/ES-DE/gamelists/nes/gamelist.xml"
        self.assertIn(("shell", "mkdir", "-p", "/storage/6AF3-53E9/ES-DE/gamelists/nes"), self.calls)
        self.assertLess(self.calls.index(("shell", "mkdir", "-p", "/storage/6AF3-53E9/ES-DE/gamelists/nes")),
                        self.calls.index(("push", gamelist)))


def apk_zip(package="com.example.app", version=65):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("AndroidManifest.xml", manifest_bytes(package, version))
    return out.getvalue()


class ApkRules(helpers.DataDir):
    def rule(self, device, name, **card):
        self.write_json("cards.json", {"c": {"device": device, "layout": "esde", **card}})
        return android_settings.apk_rules("c")(name)

    def test_never(self):
        self.assertEqual(self.rule("full", "dawn-zero-1.apk"), "not needed")

    def test_tier(self):
        for name in ("gamenative-1.apk", "DroidDeck.apk"):
            self.assertIsNone(self.rule("retroid-pocket-nova", name))
            self.assertIsNone(self.rule("full", name))
            self.assertEqual(self.rule("retroid-pocket-mini", name), "device is below the Nova's tier")
        self.write_json("device-systems.json", {"retroid-pocket-mini": {"add": ["switch"]}})
        self.assertEqual(self.rule("retroid-pocket-mini", "gamenative-1.apk"), "device is below the Nova's tier")

    def test_systems(self):
        self.assertIsNone(self.rule("retroid-pocket-nova", "Eden-1.apk"))
        self.assertEqual(self.rule("retroid-pocket-mini", "Eden-1.apk"), "device doesn't play Switch")
        self.assertIsNone(self.rule("full", "eden.apk"))
        self.write_json("device-systems.json", {"retroid-pocket-mini": {"add": ["switch"]}})
        self.assertIsNone(self.rule("retroid-pocket-mini", "Eden-1.apk"))

    def test_dual_screen(self):
        self.assertIsNone(self.rule("retroid-pocket-duo", "gba-ds.apk"))
        self.assertEqual(self.rule("retroid-pocket-nova", "gba-ds.apk"), "not a dual-screen device")
        self.assertIsNone(self.rule("full", "gba-ds.apk"))

    def test_raofflineproxy(self):
        self.assertIsNone(self.rule("full", "RAOfflineProxy-1.apk"))
        self.assertEqual(self.rule("full", "RAOfflineProxy-1.apk", raofflineproxy=False),
                         "RAOfflineProxy is off for this card")

    def test_full_installs_everything_else(self):
        self.assertIsNone(self.rule("full", "Obtainium.apk"))
