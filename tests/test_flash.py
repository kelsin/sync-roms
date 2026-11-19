import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import flash  # noqa: E402

KEYS = ["os/knulli-h700-rg35xx-h-scarab-20260511.img.gz", "os/knulli-h700-rg34xx-sp-scarab-20260511.img.gz",
        "os/knulli-h700-rg35xx-h-gladiator-20250101.img.gz", "os/knulli-rk3568-miyoo-flip-scarab-20260510.img.gz"]


class Flash(unittest.TestCase):
    def test_images_keeps_only_knulli_gz(self):
        listing = {k: 1 for k in KEYS} | {"os/Onion-v4.3.1-1.zip": 1, "os/esde/knulli-x-y-z-20260101.img.gz": 1,
                                          "os/Zero40_32G.img.xz": 1}
        self.assertEqual(sorted(flash.images(listing)), sorted(KEYS))

    def test_sort_puts_matches_first_newest_first(self):
        got = flash.sort_images(KEYS, "anbernic-rg35xxh")
        self.assertEqual(got[:2], [(KEYS[0], True), (KEYS[2], True)])
        self.assertTrue(all(not m for _, m in got[2:]))

    def test_sort_matches_miyoo_flip(self):
        self.assertEqual(flash.sort_images(KEYS, "miyoo-flip")[0], (KEYS[3], True))

    def test_sort_matches_sp(self):
        self.assertEqual(flash.sort_images(KEYS, "anbernic-rg34xx-sp")[0], (KEYS[1], True))

    def test_no_match_still_lists_all(self):
        self.assertEqual(len(flash.sort_images(KEYS, "anbernic-rg28xx")), 4)

    def test_knulli_devices(self):
        devs = [{"id": "a", "firmwares": ["esde"]}, {"id": "b", "firmwares": ["knulli"]},
                {"id": "c", "firmwares": ["onion", "knulli"]}]
        self.assertEqual([d["id"] for d in flash.knulli_devices(devs)], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
