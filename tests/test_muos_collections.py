import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import muos_collections  # noqa: E402


class MountTests(unittest.TestCase):
    def test_mount_defaults_to_sd1(self):
        self.assertEqual(muos_collections.mount({}), "/mnt/mmc")

    def test_mount_sd2(self):
        self.assertEqual(muos_collections.mount({"muos_storage": "sd2"}), "/mnt/sdcard")

    def test_mount_unknown_is_none(self):
        self.assertIsNone(muos_collections.mount({"muos_storage": "usb"}))


if __name__ == "__main__":
    unittest.main()
