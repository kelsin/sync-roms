import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from sync_roms import store  # noqa: E402

PAIRS = (("screen", "resolution"), ("screen2", "resolution2"))


class DeviceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.devices = store.repo_json("devices")

    def test_resolution_exactly_when_screen(self):
        for d in self.devices:
            with self.subTest(d["id"]):
                for screen, resolution in PAIRS:
                    self.assertEqual(resolution in d, screen in d)

    def test_resolutions_are_well_formed(self):
        for d in self.devices:
            with self.subTest(d["id"]):
                for _, resolution in PAIRS:
                    if resolution in d:
                        self.assertRegex(d[resolution], r"^[1-9]\d*x[1-9]\d*$")

    def test_resolution_matches_the_recorded_ratio(self):
        for d in self.devices:
            with self.subTest(d["id"]):
                for screen, resolution in PAIRS:
                    if screen not in d or resolution not in d:
                        continue
                    a, b = (int(n) for n in d[screen].split(":"))
                    w, h = (int(n) for n in d[resolution].split("x"))
                    self.assertLess(abs((w / h) / (a / b) - 1), 0.02)


if __name__ == "__main__":
    unittest.main()
