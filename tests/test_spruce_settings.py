import contextlib
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import commands, spruce_settings, store, usersettings  # noqa: E402

BASE = {"menuOptions": {"Other": {"x": {"selected": "1"}}}, "theme": "dark"}


class InstallBase(helpers.CardDir):
    syncthing = False  # the forced Syncthing settings are tested in Forced

    def setUp(self):
        super().setUp()
        self.path = self.cp("Saves", "spruce", "spruce-config.json")

    def put_config(self, data, raw=None):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(raw if raw is not None else json.dumps(data, indent=4) + "\n")

    def config(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def run_install(self, layout="spruce", dry_run=False, **settings):
        if not self.syncthing:
            settings.setdefault("spruce_syncthing", False)
        usersettings.save_settings(settings)
        out, self.err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.err):
            self.failures = spruce_settings.install("c", layout, self.card, dry_run)
        return out.getvalue()

    def block(self):
        return self.config()["menuOptions"]["RetroAchievements Settings"]


class Install(InstallBase):
    def test_sets_keys_and_keeps_the_rest(self):
        self.put_config(BASE)
        out = self.run_install(spruce_ra_mode="Hardcore", spruce_ra_username="me", spruce_ra_password="pw1",
                               spruce_ra_api_key="key1")
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.block(), {"modeToggle": {"selected": "Hardcore"}, "username": {"selected": "me"},
                                        "password": {"selected": "pw1"}, "webApiKey": {"selected": "key1"}})
        config = self.config()
        self.assertEqual(config["theme"], "dark")
        self.assertEqual(config["menuOptions"]["Other"], BASE["menuOptions"]["Other"])
        self.assertIn("modeToggle = Hardcore", out)
        self.assertIn("username = me", out)
        self.assertIn("password = (hidden)", out)
        self.assertIn("webApiKey = (hidden)", out)
        self.assertNotIn("pw1", out + self.err.getvalue())
        self.assertNotIn("key1", out + self.err.getvalue())

    def test_existing_entry_keeps_its_sibling_fields(self):
        self.put_config({"menuOptions": {"RetroAchievements Settings": {
            "username": {"selected": "old", "options": ["a"]}, "other": {"selected": "z"}}}})
        self.run_install(spruce_ra_username="new")
        self.assertEqual(self.block(), {"username": {"selected": "new", "options": ["a"]}, "other": {"selected": "z"}})

    def test_bools_become_strings(self):
        self.put_config(BASE)
        self.run_install(spruce_ra_offline_proxy=True, spruce_ra_proxy_stats=False)
        self.assertEqual(self.block(), {"enableOfflineProxy": {"selected": "True"},
                                        "raproxyUsageStats": {"selected": "False"}})

    def test_nothing_set_does_nothing(self):
        self.put_config(BASE, raw='{"menuOptions":{}}')
        self.assertEqual(self.run_install(), "")
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.err.getvalue(), "")
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"menuOptions":{}}')

    def test_no_rewrite_when_unchanged(self):
        self.put_config(BASE, raw=json.dumps({"menuOptions": {"RetroAchievements Settings": {
            "username": {"selected": "me"}}}}))  # compact formatting would change if rewritten
        before = os.stat(self.path).st_mtime_ns
        self.assertEqual(self.run_install(spruce_ra_username="me"), "")
        with open(self.path, encoding="utf-8") as f:
            self.assertNotIn("\n", f.read())
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_missing_file_is_skipped_with_a_warning(self):
        self.run_install(spruce_ra_username="me")
        self.assertFalse(os.path.exists(self.path))
        self.assertIn("spruce-config.json is missing", self.err.getvalue())
        self.assertEqual(self.failures, 0)

    def test_unusable_files_are_left_alone_with_a_warning(self):
        for raw in ("{not json", "[]", '{"menuOptions": 3}', "{}"):
            with self.subTest(raw=raw):
                self.put_config(None, raw=raw)
                self.run_install(spruce_ra_username="me")
                self.assertIn("can't be read", self.err.getvalue())
                with open(self.path, encoding="utf-8") as f:
                    self.assertEqual(f.read(), raw)

    def test_other_layouts_are_untouched(self):
        self.put_config(BASE)
        before = self.snapshot()
        self.assertEqual(self.run_install("onion", spruce_ra_username="me"), "")
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("RetroAchievements Settings", self.config()["menuOptions"])

    def test_dry_run_writes_nothing(self):
        self.put_config(BASE)
        out = self.run_install(dry_run=True, spruce_ra_password="pw1", spruce_ra_username="me")
        self.assertIn("Dry run: would set 2", out)
        self.assertIn("username = me", out)
        self.assertIn("password = (hidden)", out)
        self.assertNotIn("pw1", out)
        self.assertEqual(self.config(), BASE)

    def test_keeps_the_files_indent(self):
        self.put_config(None, raw=json.dumps(BASE, indent=2))
        self.run_install(spruce_ra_username="me")
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn('\n  "menuOptions"', text)
        self.assertFalse(text.endswith("\n"))


RICH = {"menuOptions": {
    "Button Settings": {"menuButton": {"selected": "L3", "options": ["L3", "Select"]}, "homeAction": {"selected": "Nothing"}},
    "Emulator Settings": {"raAutoSave": {"selected": "Custom"}, "perfectOverlays": {"selected": "False"}},
    "Battery Settings": {"lowPowerWarningPercent": {"selected": "4"}},
    "RetroAchievements Settings": {"username": {"selected": "me"}, "password": {"selected": "pw9"}}}}


class SharedSettings(Install):
    def shared(self, data):
        usersettings.save_settings({"spruce_settings": data})

    def selected(self, section, key):
        return self.config()["menuOptions"][section][key]["selected"]

    def test_applies_allowlisted_keys_keeping_other_fields(self):
        self.put_config(RICH)
        out = self.run_install(spruce_settings={"Button Settings": {"menuButton": "Select"},
                                                "Emulator Settings": {"perfectOverlays": "True"}})
        self.assertEqual(self.selected("Button Settings", "menuButton"), "Select")
        self.assertEqual(self.config()["menuOptions"]["Button Settings"]["menuButton"]["options"], ["L3", "Select"])
        self.assertEqual(self.selected("Emulator Settings", "perfectOverlays"), "True")
        self.assertIn("   Button Settings / menuButton = Select", out)
        self.assertIn("(2 set)", out)

    def test_value_types_are_kept(self):
        self.put_config({"menuOptions": {"Emulator Settings": {"raAutoSave": {"selected": "x"}}}})
        self.run_install(spruce_settings={"Emulator Settings": {"raAutoSave": 3}})
        self.assertIs(type(self.selected("Emulator Settings", "raAutoSave")), int)

    def test_missing_section_or_key_is_not_created(self):
        self.put_config(RICH)
        self.run_install(spruce_settings={"Network Settings": {"enableSSH": "True"},
                                          "Emulator Settings": {"raAutoLoad": "Custom"}})
        self.assertEqual(self.config(), RICH)

    def test_not_allowlisted_is_ignored_with_a_warning(self):
        self.put_config(RICH)
        self.run_install(spruce_settings={"Button Settings": {"homeAction": "Other"},
                                          "Battery Settings": {"lowPowerWarningPercent": "9"}})
        self.assertEqual(self.config(), RICH)
        self.assertEqual(self.err.getvalue().count("aren't shared"), 1)
        self.assertIn("Button Settings / homeAction", self.err.getvalue())

    def test_malformed_is_ignored_with_a_warning(self):
        for bad in ("x", ["a"], {"Button Settings": "L3"}):
            with self.subTest(bad=bad):
                self.put_config(RICH)
                self.assertEqual(self.run_install(spruce_settings=bad), "")
                self.assertIn("must be {section: {key: value}}", self.err.getvalue())
                self.assertEqual(self.config(), RICH)

    def test_no_rewrite_when_unchanged(self):
        self.put_config(None, raw=json.dumps(RICH))
        before = os.stat(self.path).st_mtime_ns
        self.assertEqual(self.run_install(spruce_settings={"Button Settings": {"menuButton": "L3"}}), "")
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_combined_with_retroachievements_in_one_write(self):
        self.put_config(RICH)
        out = self.run_install(spruce_ra_username="you", spruce_settings={"Button Settings": {"menuButton": "Select"}})
        self.assertIn("(2 set)", out)
        self.assertEqual(self.block()["username"]["selected"], "you")
        self.assertEqual(self.selected("Button Settings", "menuButton"), "Select")

    def test_dry_run_writes_nothing(self):
        self.put_config(RICH)
        out = self.run_install(dry_run=True, spruce_settings={"Button Settings": {"menuButton": "Select"}})
        self.assertIn("Dry run: would set 1", out)
        self.assertIn("Button Settings / menuButton = Select", out)
        self.assertEqual(self.config(), RICH)


FORCED = {"menuOptions": {
    "Emulator Settings": {"raAutoSave": {"selected": "Custom"}, "raAutoLoad": {"selected": "Custom"},
                          "keepSavesBetweenCores": {"selected": "Prompt"}},
    "Network Settings": {"enableSyncthing": {"selected": "False"}}}}


class Forced(InstallBase):
    syncthing = True

    def setUp(self):
        super().setUp()
        store.write_cards({"c": {"device": "anbernic-rg-sp", "layout": "spruce"}})
        self.put_config(FORCED)

    def selected(self, section, key):
        return self.config()["menuOptions"][section][key]["selected"]

    def values(self):
        return [self.selected("Emulator Settings", k) for k in ("raAutoSave", "raAutoLoad", "keepSavesBetweenCores")] + [
            self.selected("Network Settings", "enableSyncthing")]

    def test_forced_settings_applied_by_default(self):
        out = self.run_install()
        self.assertEqual(self.values(), ["True", "True", "Always", "True"])
        self.assertIn("   Emulator Settings / raAutoSave = True (Syncthing)", out)
        self.assertIn("   Network Settings / enableSyncthing = True (Syncthing)", out)

    def test_forced_beat_saved_values_silently(self):
        self.run_install(spruce_settings={"Emulator Settings": {"raAutoLoad": "False"}})
        self.assertEqual(self.selected("Emulator Settings", "raAutoLoad"), "True")
        self.assertNotIn("aren't shared", self.err.getvalue())

    def test_no_wifi_device_keeps_syncthing_off(self):
        store.write_cards({"c": {"device": "miyoo-mini", "layout": "spruce"}})
        self.run_install()
        self.assertEqual(self.values(), ["True", "True", "Always", "False"])

    def test_off_uses_saved_values(self):
        out = self.run_install(spruce_syncthing=False, spruce_settings={"Emulator Settings": {"raAutoLoad": "False"}})
        self.assertEqual(self.values(), ["Custom", "False", "Prompt", "False"])
        self.assertNotIn("Syncthing", out)

    def test_missing_forced_key_warns(self):
        self.put_config({"menuOptions": {"Emulator Settings": {"raAutoSave": {"selected": "Custom"}}}})
        self.run_install()
        self.assertIn("spruce-config.json has no Emulator Settings / raAutoLoad; update spruceOS for Syncthing saves to work",
                      self.err.getvalue())
        self.assertEqual(self.selected("Emulator Settings", "raAutoSave"), "True")

    def test_allowlist_drops_forced_keys_only_while_on(self):
        keys = {k for ks in spruce_settings.allowed().values() for k in ks}
        self.assertFalse(keys & {"raAutoSave", "raAutoLoad", "keepSavesBetweenCores", "enableSyncthing"})
        usersettings.save_settings({"spruce_syncthing": False})
        self.assertIn("raAutoSave", spruce_settings.allowed()["Emulator Settings"])


class Import(helpers.Cmd):
    def setUp(self):
        super().setUp()
        usersettings.save_settings({"spruce_syncthing": False})
        self.card = os.path.join(self.tmp.name, "RGSP")
        store.write_cards({"RGSP": {"device": "full", "layout": "spruce"}})
        path = os.path.join(self.card, "Saves", "spruce", "spruce-config.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(RICH, f)

    def imp(self, answers):
        from unittest import mock
        with mock.patch("builtins.input", side_effect=answers):
            return self.run_cmd("config", "import", self.card)

    def saved(self):
        return self.read("settings.json")["spruce_settings"]

    ALL = {"Button Settings": {"menuButton": "L3"},
           "Emulator Settings": {"raAutoSave": "Custom", "perfectOverlays": "False"}}

    def test_yes_copies_only_allowlisted_keys(self):
        code, out, _ = self.imp(["y"])
        self.assertEqual(code, 0)
        self.assertEqual(self.saved(), self.ALL)
        self.assertIn("Button Settings / menuButton = L3", out)
        self.assertIn("Different or new (3)", out)
        self.assertNotIn("pw9", out)
        self.assertNotIn("RetroAchievements", out)

    def test_no_saves_nothing(self):
        code, out, _ = self.imp(["n"])
        self.assertEqual(code, 0)
        self.assertIsNone(self.read_or_none())

    def read_or_none(self):
        try:
            return self.read("settings.json").get("spruce_settings")
        except (OSError, ValueError):
            return None

    def test_enter_re_asks(self):
        code, _, _ = self.imp(["", "  ", "maybe", "y"])
        self.assertEqual(code, 0)
        self.assertEqual(self.saved(), self.ALL)

    def test_pick_saves_only_accepted(self):
        code, _, _ = self.imp(["p", "y", "", "n", "y"])  # raAutoSave y, a blank answer re-asks, perfectOverlays n, menuButton y
        self.assertEqual(code, 0)
        self.assertEqual(self.saved(), {"Button Settings": {"menuButton": "L3"},
                                        "Emulator Settings": {"raAutoSave": "Custom"}})

    def test_lists_identical_and_different(self):
        usersettings.save_settings({"mirror": "/m", "spruce_syncthing": False, "spruce_settings": {
            "Button Settings": {"menuButton": "L3"}, "Emulator Settings": {"raAutoSave": "Old"}}})
        code, out, _ = self.imp(["y"])
        self.assertIn("Identical (1)", out)
        self.assertIn("Emulator Settings / raAutoSave = Old -> Custom", out)
        self.assertIn("Different or new (2)", out)
        saved = self.read("settings.json")
        self.assertEqual(saved["mirror"], "/m")
        self.assertEqual(saved["spruce_settings"], self.ALL)

    def test_nothing_different_does_not_prompt(self):
        usersettings.save_settings({"spruce_syncthing": False, "spruce_settings": self.ALL})
        code, out, _ = self.imp([])  # any input() call would raise StopIteration
        self.assertEqual(code, 0)
        self.assertIn("nothing to import", out)

    def test_no_input_saves_nothing(self):
        code, _, err = self.imp(EOFError)
        self.assertEqual(code, 2)
        self.assertIn("nothing was saved", err)
        self.assertIsNone(self.read_or_none())

    def test_by_name_finds_the_mounted_folder(self):
        from unittest import mock
        real = os.path.join
        with mock.patch("sync_roms.commands.os.path.join", lambda a, *r: real(self.tmp.name, *r) if a == "/Volumes" else real(a, *r)), \
                mock.patch("builtins.input", side_effect=["y"]):
            code, out, _ = self.run_cmd("config", "import", "RGSP")
        self.assertEqual(code, 0)
        self.assertEqual(self.saved(), self.ALL)

    def test_name_with_no_mounted_folder(self):
        from unittest import mock
        real = os.path.join  # /Volumes/RGSP can be a real mounted card on a dev machine
        with mock.patch("sync_roms.commands.os.path.join", lambda a, *r: real(self.tmp.name, "none", *r) if a == "/Volumes" else real(a, *r)):
            code, _, err = self.run_cmd("config", "import", "RGSP")
        self.assertEqual(code, 2)
        self.assertIn("No folder", err)

    def test_unknown_card(self):
        other = os.path.join(self.tmp.name, "NOPE")
        os.makedirs(other)
        code, _, err = self.run_cmd("config", "import", other)
        self.assertEqual(code, 2)
        self.assertIn("No card named 'NOPE'", err)
        self.assertIn("cards new", err)

    def test_card_without_a_layout(self):
        store.write_cards({"RGSP": {"device": "full"}})
        code, _, err = self.run_cmd("config", "import", self.card)
        self.assertEqual(code, 2)
        self.assertIn("has no layout", err)

    def test_unsupported_layout(self):
        store.write_cards({"RGSP": {"device": "full", "layout": "onion"}})
        code, _, err = self.run_cmd("config", "import", self.card)
        self.assertEqual(code, 2)
        self.assertIn("importing settings from onion cards isn't supported yet (supported: spruce)", err)

    def test_card_without_a_settings_file(self):
        os.makedirs(os.path.join(self.tmp.name, "RGSP2"))
        store.write_cards({"RGSP2": {"device": "full", "layout": "spruce"}})
        self.assertEqual(self.run_cmd("config", "import", os.path.join(self.tmp.name, "RGSP2"))[0], 2)

    def test_import_skips_forced_keys_while_on(self):
        usersettings.save_settings({})
        code, out, _ = self.imp(["y"])
        self.assertEqual(code, 0)
        self.assertNotIn("raAutoSave", out)
        self.assertEqual(self.saved(), {"Button Settings": {"menuButton": "L3"}, "Emulator Settings": {"perfectOverlays": "False"}})

    def test_spruce_spruce_import_is_gone(self):
        self.assertEqual(self.run_cmd("config", "spruce-import", self.card)[0], 2)


class AllowlistData(unittest.TestCase):
    def test_shape(self):
        from sync_roms import store
        data = store.repo_json("spruce-settings")
        self.assertIsInstance(data["note"], str)
        self.assertTrue(data["sections"])
        for section, keys in data["sections"].items():
            with self.subTest(section=section):
                self.assertTrue(keys)
                self.assertTrue(all(isinstance(k, str) for k in keys))
                self.assertEqual(len(keys), len(set(keys)))
        banned = {"homeAction", "overclockSpeedA30", "verboseLogging", "enableProxy", "lowPowerWarningPercent"}
        self.assertFalse(banned & {k for keys in data["sections"].values() for k in keys})
        for name in ("Battery Settings", "Proxy Settings", "RGB LED Settings", "LEDs Settings", "Audio Settings",
                     "RetroAchievements Settings"):
            self.assertNotIn(name, data["sections"])


class ConfigSet(helpers.Cmd):
    def test_mode_is_validated(self):
        code, _, err = self.run_cmd("config", "set", "spruce_ra_mode", "Nope")
        self.assertEqual(code, 2)
        self.assertIn("Hardcore", err)
        code, _, err = self.run_cmd("config", "set", "spruce_ra_mode", "Softcore")
        self.assertEqual(code, 0)
        self.assertEqual(self.read("settings.json"), {"spruce_ra_mode": "Softcore"})

    def test_hidden_values_are_never_printed(self):
        for name in ("spruce_ra_password", "spruce_ra_api_key"):
            with self.subTest(name=name):
                self.assertIn(name, commands.HIDDEN)
                code, out, err = self.run_cmd("config", "set", name, "s3cret")
                self.assertEqual(code, 0)
                self.assertNotIn("s3cret", out + err)

    def test_bool_setting(self):
        code, _, _ = self.run_cmd("config", "set", "spruce_ra_offline_proxy", "true")
        self.assertEqual(code, 0)
        self.assertIs(self.read("settings.json")["spruce_ra_offline_proxy"], True)
        self.assertEqual(self.run_cmd("config", "set", "spruce_ra_offline_proxy", "yes")[0], 2)


if __name__ == "__main__":
    unittest.main()
