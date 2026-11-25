import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import applied, spruce_hotkeys  # noqa: E402

BRICK = 'RA_HOTKEY_LINE="input_enable_hotkey_btn"\nRA_SELECT_VAL="5"\nRA_START_VAL="6"\n'
BRICK_CFG = 'input_enable_hotkey_btn = "5"\ninput_exit_emulator_btn = "0"\nother = "1"\n'
SHOWN = "Saves/ra-configs/retroarch-Brick.cfg"


class Install(helpers.CardDir):
    def setUp(self):
        super().setUp()
        self.cfg = self.cp("Saves", "ra-configs", "retroarch-Brick.cfg")

    def script(self, name, text, family="tina-stock"):
        helpers.touch(self.cp("spruce", "scripts", "platform", family, name + ".cfg"), text)

    def brick(self, cfg=BRICK_CFG):
        self.script("Brick", BRICK)
        helpers.touch(self.cfg, cfg.encode())

    def read(self, path=None):
        with open(path or self.cfg, "rb") as f:
            return f.read().decode()

    def run_install(self, layout="spruce", dry_run=False):
        out, self.err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.err):
            self.failures = spruce_hotkeys.install("c", layout, self.card, dry_run)
        self.out = out.getvalue()
        return self.out

    def test_brick_quit_moves_to_start(self):
        self.brick()
        self.run_install()
        self.assertEqual(self.read(), 'input_enable_hotkey_btn = "5"\ninput_exit_emulator_btn = "6"\nother = "1"\n')
        self.assertEqual(self.failures, 0)
        self.assertIn("Quit hotkey set", self.out)

    def test_family_file_is_followed(self):
        self.script("AnbernicXX640480", "# pad\n. /mnt/SDCARD/spruce/scripts/platform/h700/AnbernicXXCommon.cfg\n", "h700")
        self.script("AnbernicXXCommon", 'RA_HOTKEY_LINE="input_enable_hotkey_btn"\nRA_START_VAL="10"\n', "h700")
        self.assertEqual(spruce_hotkeys.start_value(self.card, "AnbernicXX640480"), ("input_exit_emulator_btn", "10"))

    def test_a30_uses_keyboard_line(self):
        self.script("A30", 'RA_HOTKEY_LINE="input_enable_hotkey"\nRA_START_VAL="enter"\n')
        helpers.touch(self.cp("Saves", "ra-configs", "retroarch-A30.cfg"),
                      'input_enable_hotkey = "rctrl"\ninput_exit_emulator = "ctrl"\ninput_exit_emulator_btn = "0"\n')
        self.run_install()
        self.assertEqual(self.read(self.cp("Saves", "ra-configs", "retroarch-A30.cfg")),
                         'input_enable_hotkey = "rctrl"\ninput_exit_emulator = "enter"\ninput_exit_emulator_btn = "0"\n')

    def test_crlf_kept(self):
        self.brick(BRICK_CFG.replace("\n", "\r\n"))
        self.run_install()
        text = self.read()
        self.assertIn('input_exit_emulator_btn = "6"\r\n', text)
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_start_as_hotkey_is_skipped(self):
        cfg = BRICK_CFG.replace('hotkey_btn = "5"', 'hotkey_btn = "6"')
        self.brick(cfg)
        self.run_install()
        self.assertEqual(self.read(), cfg)
        self.assertIn("the hotkey button is Start", self.err.getvalue())

    def test_missing_script_warns_and_others_still_done(self):
        self.brick()
        helpers.touch(self.cp("Saves", "ra-configs", "retroarch-Unknown.cfg"), 'x = "1"\n')
        self.run_install()
        self.assertIn('input_exit_emulator_btn = "6"', self.read())
        self.assertIn("retroarch-Unknown.cfg", self.err.getvalue())
        self.assertIn("wasn't found", self.err.getvalue())

    def test_no_cfg_yet_warns(self):
        self.run_install()
        self.assertIn("has no retroarch-*.cfg yet", self.err.getvalue())
        self.assertEqual(self.failures, 0)

    def test_missing_key_is_appended(self):
        self.brick('input_enable_hotkey_btn = "5"\n')
        self.run_install()
        self.assertEqual(self.read(), 'input_enable_hotkey_btn = "5"\ninput_exit_emulator_btn = "6"\n')

    def test_already_right_writes_nothing(self):
        self.brick(BRICK_CFG.replace('emulator_btn = "0"', 'emulator_btn = "6"'))
        os.utime(self.cfg, (1, 1))
        self.run_install()
        self.assertEqual(os.stat(self.cfg).st_mtime, 1)
        self.assertNotIn("Quit hotkey set", self.out)

    def test_dry_run_writes_nothing(self):
        self.brick()
        self.run_install(dry_run=True)
        self.assertEqual(self.read(), BRICK_CFG)
        self.assertIn("Would set", self.out)

    def test_entries(self):
        self.brick()
        self.assertEqual(spruce_hotkeys.entries(self.card),
                         [applied.Entry(SHOWN, "input_exit_emulator_btn", "0", "6", False)])

    def test_other_layouts_untouched(self):
        self.brick()
        self.assertEqual(self.run_install("onion"), "")
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.read(), BRICK_CFG)


if __name__ == "__main__":
    unittest.main()
