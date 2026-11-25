import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import store  # noqa: E402


class Shape(unittest.TestCase):
    def setUp(self):
        self.d = store.repo_json("hotkeys")

    def test_scheme_order_and_buttons(self):
        self.assertEqual([(s["button"], s["retroarch"]) for s in self.d["scheme"]], [
            ("X", "input_menu_toggle"), ("R1", "input_save_state"), ("L1", "input_load_state"),
            ("D-pad Left", "input_state_slot_decrease"), ("D-pad Right", "input_state_slot_increase"),
            ("R2", "input_toggle_fast_forward"), ("L2", "input_toggle_slowmotion"),
            ("Y", "input_fps_toggle"), ("Start", "input_exit_emulator")])

    def test_android_covers_every_button(self):
        d = self.d
        self.assertEqual({s["button"] for s in d["scheme"]} | {"Select"}, set(d["android"]))
        self.assertEqual(d["android"]["Start"], "108")
        self.assertEqual(d["android"]["Select"], "109")
        self.assertEqual(d["android"]["R2"], "105")
        self.assertEqual(d["android"]["D-pad Left"], "h0left")

    def test_clear_list_is_disjoint_from_scheme(self):
        clear = self.d["android_clear"]
        self.assertFalse(set(clear) & {s["retroarch"] for s in self.d["scheme"]})
        self.assertEqual(len(clear), len(set(clear)))
        self.assertTrue(all(c.startswith("input_") for c in clear))

    def test_knulli_remaps(self):
        self.assertEqual(self.d["knulli"], {
            "global.hotkey_b": "x", "global.hotkey_y": "pagedown", "global.hotkey_x": "pageup",
            "global.hotkey_down": "left", "global.hotkey_up": "right", "global.hotkey_right": "r2",
            "global.toggle_fast_forward": "1"})


if __name__ == "__main__":
    unittest.main()
