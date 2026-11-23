import unittest

import helpers
from sync_roms import android, android_settings, applied, usersettings

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
