import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import store  # noqa: E402


def system(bucket):
    return next(s for s in store.repo_json("systems") if s["bucket"] == bucket)


class RocknixDataTest(unittest.TestCase):
    def test_layout_exists(self):
        layout = store.repo_json("layouts")["rocknix"]
        self.assertIn("label", layout)
        self.assertEqual(layout["roms_dir"], "roms")
        self.assertEqual(layout["bios_dir"], "roms/bios")

    def test_gba_folder(self):
        self.assertEqual(system("gba")["folders"]["rocknix"], "gba")

    def test_coleco_and_sgfx_folders(self):
        self.assertEqual(system("colecovision")["folders"]["rocknix"], "coleco")
        self.assertEqual(system("supergrafx")["folders"]["rocknix"], "sgfx")

    def test_rocknix_folder_sits_before_nextui(self):
        for s in store.repo_json("systems"):
            keys = list(s["folders"])
            self.assertIn("rocknix", keys, s["bucket"])
            self.assertLess(keys.index("rocknix"), keys.index("nextui"), s["bucket"])

    def test_never_default_firmware(self):
        for d in store.repo_json("devices"):
            self.assertNotEqual(d["firmwares"][0], "rocknix", d["id"])

    def test_devices_listed(self):
        devices = {d["id"]: d for d in store.repo_json("devices")}
        for id in ("anbernic-rg-cubexx", "anbernic-rg353ps", "anbernic-rg353vs", "anbernic-rg503",
                   "ayn-odin-2", "ayn-odin-2-mini", "ayn-odin-2-portal", "ayn-odin-3", "ayn-thor"):
            self.assertIn("rocknix", devices[id]["firmwares"], id)


if __name__ == "__main__":
    unittest.main()
