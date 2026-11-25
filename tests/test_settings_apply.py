import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import adb, android, android_settings, settings_apply, store, ui, usersettings  # noqa: E402

CATALOG = {"layouts": {"esde": {"roms_dir": "ROMs"}, "spruce": {"roms_dir": "Roms"}, "onion": {"roms_dir": "Roms"}},
           "systems": {}, "devices": []}


class Apply(helpers.Cmd):
    def setUp(self):
        super().setUp()
        self.cards = {}
        self.root = os.path.join(self.tmp.name, "mnt")
        os.makedirs(self.root)
        for p in (mock.patch.object(store, "load_catalog", lambda: CATALOG),
                  mock.patch.object(ui, "has_terminal", lambda: True),
                  mock.patch.object(adb, "require", lambda mounted=False: "adb")):
            self.enterContext(p)
        self.resolve = self.enterContext(mock.patch.object(android, "resolve"))
        self.apply = self.enterContext(mock.patch.object(android_settings, "apply", return_value=0))
        self.enterContext(mock.patch("sync_roms.picker.saved_setup", lambda saved, d, layouts, name=None: (None, saved["layout"])))

    def card(self, name, layout, device="full"):
        self.cards[name] = {"device": device, "layout": layout}
        helpers.write_json(self.path("cards.json"), self.cards)
        base = os.path.join(self.root, name)
        os.makedirs(os.path.join(base, "Saves", "spruce"), exist_ok=True)
        return base

    def spruce(self, name="s", value="Casual"):
        base = self.card(name, "spruce")
        cfg = os.path.join(base, "Saves", "spruce", "spruce-config.json")
        with open(cfg, "w") as f:
            json.dump({"menuOptions": {"RetroAchievements Settings": {"modeToggle": {"selected": value}}}}, f)
        usersettings.save_settings({"ra_mode": "Casual", "syncthing": False})
        return base, cfg

    def mode(self, cfg):
        with open(cfg) as f:
            return json.load(f)["menuOptions"]["RetroAchievements Settings"]["modeToggle"]["selected"]

    def test_apply_spruce_card_by_name(self):
        _, cfg = self.spruce(value="Disabled")
        with mock.patch.object(settings_apply, "VOLUMES", self.root):
            code, _, _ = self.run_cmd("config", "apply", "s")
        self.assertEqual(code, 0)
        self.assertEqual(self.mode(cfg), "Casual")

    def test_apply_spruce_from_cwd(self):
        base, cfg = self.spruce(value="Disabled")
        old = os.getcwd()
        os.chdir(base)
        self.addCleanup(os.chdir, old)
        code, _, _ = self.run_cmd("config", "apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.mode(cfg), "Casual")

    def test_apply_spruce_dry_run_lists_all(self):
        base, cfg = self.spruce(value="Casual")
        with open(cfg) as f:
            before = f.read()
        code, out, _ = self.run_cmd("config", "apply", base, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("already set", out)
        with open(cfg) as f:
            self.assertEqual(f.read(), before)

    def test_apply_spruce_dry_run_lists_quit_hotkey(self):
        base, _ = self.spruce(value="Casual")
        for path, text in ((("spruce", "scripts", "platform", "tina-stock", "Brick.cfg"), 'RA_HOTKEY_LINE="input_enable_hotkey_btn"\nRA_START_VAL="6"\n'),
                           (("Saves", "ra-configs", "retroarch-Brick.cfg"), 'input_exit_emulator_btn = "0"\n')):
            full = os.path.join(base, *path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(text)
        code, out, _ = self.run_cmd("config", "apply", base, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("input_exit_emulator_btn", out)

    def test_apply_other_layout_cwd_refused(self):
        base = self.card("o", "onion")
        old = os.getcwd()
        os.chdir(base)
        self.addCleanup(os.chdir, old)
        code, _, err = self.run_cmd("config", "apply")
        self.assertEqual(code, 2)
        self.assertIn("supports spruce cards and Android devices, not onion", err)
        self.resolve.assert_not_called()

    def test_apply_mounted_android_refused(self):
        base = self.card("a", "esde", "retroid-pocket-5")
        code, _, err = self.run_cmd("config", "apply", base)
        self.assertEqual(code, 2)
        self.assertIn("Android cards are applied over adb: run `sync-roms config apply a` without a folder", err)
        self.resolve.assert_not_called()

    def _target(self, card="a"):
        self.resolve.return_value = mock.Mock(card=card)

    def test_apply_no_card_opens_device_picker(self):
        self.card("a", "esde", "retroid-pocket-5")
        self._target()
        code, _, _ = self.run_cmd("config", "apply")
        self.assertEqual(code, 0)
        self.assertIsNone(self.resolve.call_args[0][0])
        self.assertEqual(self.apply.call_args[0][3], False)

    def test_apply_android_card_name_resolves_it(self):
        self.card("a", "esde", "retroid-pocket-5")
        self._target()
        code, _, _ = self.run_cmd("config", "apply", "a", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.resolve.call_args[0][0], "a")
        self.assertEqual(self.apply.call_args[0][3], True)

    def test_apply_lost_device_exits_1(self):
        self.card("a", "esde", "retroid-pocket-5")
        self._target()
        self.apply.side_effect = adb.AdbError("gone")
        code, _, err = self.run_cmd("config", "apply", "a")
        self.assertEqual(code, 1)
        self.assertIn("Lost the connection to the device: gone", err)

    def test_apply_unsaved_card_refused(self):
        code, _, err = self.run_cmd("config", "apply", "nope")
        self.assertEqual(code, 2)
        self.assertIn("No card named 'nope'", err)

    def test_apply_card_without_layout_refused(self):
        base = self.card("n", "spruce")
        self.cards["n"] = {"device": "full"}
        helpers.write_json(self.path("cards.json"), self.cards)
        code, _, err = self.run_cmd("config", "apply", base)
        self.assertEqual(code, 2)
        self.assertIn("has no layout", err)

    def test_show_dry_run_still_refused(self):
        self.assertEqual(self.run_cmd("config", "show", "--dry-run")[0], 2)

    def test_parser(self):
        for argv in (("config", "apply"), ("config", "apply", "c")):
            with mock.patch("sync_roms.settings_apply.run", return_value=0) as r:
                self.assertEqual(self.run_cmd(*argv)[0], 0)
                self.assertEqual(r.call_args[0], (argv[2] if len(argv) > 2 else None, False))
        self.assertEqual(self.run_cmd("config", "apply", "a", "b")[0], 2)


if __name__ == "__main__":
    unittest.main()
