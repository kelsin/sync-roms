import contextlib
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import android_settings, spruce_hotkeys, spruce_retroarch, spruce_syncthing, store, usersettings  # noqa: E402

WANTED = {"savestate_auto_index": "true", "savestate_max_keep": "10", "netplay_public_announce": "false",
          "netplay_use_mitm_server": "false", "netplay_ip_port": "55435"}
BRICK = 'RA_HOTKEY_LINE="input_enable_hotkey_btn"\nRA_START_VAL="6"\n'


class Data(unittest.TestCase):
    def test_shape(self):
        d = store.repo_json("retroarch")
        self.assertEqual(set(d), {"note", "settings"})
        self.assertIsInstance(d["note"], str)
        self.assertEqual(d["settings"], WANTED)


class Android(helpers.DataDir):
    def test_wanted_with_and_without_syncthing(self):
        for on in (True, False):
            usersettings.save_settings({"syncthing": on})
            w = android_settings.cfg_wanted()
            self.assertEqual({k: w[k] for k in WANTED}, WANTED)
        self.assertNotIn("savestate_auto_save", w)


class Spruce(helpers.CardDir):
    def setUp(self):
        super().setUp()
        self.cfg = self.cp("Saves", "ra-configs", "retroarch-Brick.cfg")

    def put(self, text):
        helpers.touch(self.cfg, text.encode())

    def read(self):
        with open(self.cfg, "rb") as f:
            return f.read().decode()

    def install(self, dry_run=False, layout="spruce"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.failures = spruce_retroarch.install("c", layout, self.card, dry_run)
        return out.getvalue()

    def test_sets_changed_and_appends_missing_keeping_other_lines(self):
        self.put('other = "1"\nsavestate_max_keep = "0"\nnetplay_ip_port = "1"\n')
        out = self.install()
        cfg = dict(line.split(" = ") for line in self.read().splitlines())
        self.assertEqual({k: cfg[k].strip('"') for k in WANTED}, WANTED)
        self.assertEqual(cfg["other"], '"1"')
        self.assertEqual(self.read().count("netplay_ip_port"), 1)
        self.assertIn("1 RetroArch config", out)

    def test_already_set_writes_nothing(self):
        self.put("".join(f'{k} = "{v}"\n' for k, v in WANTED.items()))
        os.utime(self.cfg, (1, 1))
        out = self.install()
        self.assertEqual(os.stat(self.cfg).st_mtime, 1)
        self.assertEqual(out, "")

    def test_crlf_kept(self):
        self.put('other = "1"\r\nsavestate_max_keep = "0"\r\n')
        self.install()
        text = self.read()
        self.assertIn('savestate_max_keep = "10"\r\n', text)
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_dry_run_and_other_layout_write_nothing(self):
        self.put('other = "1"\n')
        self.assertIn("Would set", self.install(dry_run=True))
        self.assertEqual(self.install(layout="onion"), "")
        self.assertEqual(self.read(), 'other = "1"\n')

    def test_entries_list_every_setting(self):
        self.put('savestate_max_keep = "10"\nnetplay_ip_port = "1"\n')
        entries = {e.key: e for e in spruce_retroarch.entries(self.card)}
        self.assertEqual({k: e.new for k, e in entries.items()}, WANTED)
        self.assertEqual(entries["savestate_max_keep"].old, "10")
        self.assertEqual(entries["netplay_ip_port"].old, "1")
        self.assertIsNone(entries["savestate_auto_index"].old)
        self.assertEqual(entries["netplay_ip_port"].where, "Saves/ra-configs/retroarch-Brick.cfg")

    def test_composes_with_hotkeys_and_syncthing_in_one_cfg(self):
        helpers.touch(self.cp("spruce", "scripts", "platform", "tina-stock", "Brick.cfg"), BRICK)
        self.put('input_enable_hotkey_btn = "5"\ninput_exit_emulator_btn = "0"\n')
        with contextlib.redirect_stdout(io.StringIO()):
            spruce_syncthing.run("c", "spruce", self.card, False)
            spruce_hotkeys.install("c", "spruce", self.card, False)
            spruce_retroarch.install("c", "spruce", self.card, False)
        cfg = self.read()
        for key, value in {**WANTED, **spruce_syncthing.data()["retroarch"], "input_exit_emulator_btn": "6"}.items():
            self.assertIn(f'{key} = "{value}"', cfg)


if __name__ == "__main__":
    unittest.main()
