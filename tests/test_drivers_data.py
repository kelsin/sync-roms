import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import store  # noqa: E402

GPU_DEVICES = {
    "adreno-610": ["retroid-pocket-duo-lite"],
    "adreno-630": ["ayn-odin"],
    "adreno-650": [
        "ayaneo-pocket-micro-2", "retroid-pocket-5", "retroid-pocket-flip-2",
        "retroid-pocket-mini", "retroid-pocket-mini-v2",
    ],
    "adreno-722": ["retroid-pocket-duo", "retroid-pocket-duo-lite-plus"],
    "adreno-730": ["ayaneo-pocket-vert"],
    "adreno-740": [
        "ayn-odin-2", "ayn-odin-2-mini", "ayn-odin-2-portal", "ayn-thor",
        "retroid-pocket-6", "retroid-pocket-nova",
    ],
    "adreno-a32": [
        "ayaneo-pocket-ace", "ayaneo-pocket-dmg", "ayaneo-pocket-ds",
        "ayaneo-pocket-evo", "ayaneo-pocket-s", "ayaneo-pocket-s-mini",
    ],
    "adreno-g3-gen-3": ["ayaneo-konkr-pocket-fit", "ayaneo-pocket-s2", "ayaneo-pocket-s2-pro"],
    "adreno-830": ["ayn-odin-3"],
    "adreno-a12": ["anbernic-rg55g1", "retroid-pocket-classic"],
    "adreno-a22": ["retroid-pocket-g2"],
}


class DriversDataTest(unittest.TestCase):
    def setUp(self):
        self.data = store.repo_json("drivers")
        self.devices = store.repo_json("devices")

    def test_every_gpu_driver_id_exists(self):
        ids = {d["id"] for d in self.data["drivers"]}
        for gpu, g in self.data["gpus"].items():
            self.assertTrue(g["name"], gpu)
            for i in g["drivers"]:
                self.assertIn(i, ids, gpu)

    def test_every_device_gpu_exists(self):
        for d in self.devices:
            if "gpu" in d:
                self.assertIn(d["gpu"], self.data["gpus"], d["id"])

    def test_driver_ids_unique_and_regexes_compile(self):
        ids = [d["id"] for d in self.data["drivers"]]
        self.assertEqual(len(ids), len(set(ids)))
        for d in self.data["drivers"]:
            self.assertRegex(d["id"], r"^[a-z0-9-]+$")
            self.assertRegex(d["repo"], r"^[\w.-]+/[\w.-]+$")
            self.assertTrue(d["name"], d["id"])
            re.compile(d["asset"])

    def test_every_driver_is_used(self):
        used = {i for g in self.data["gpus"].values() for i in g["drivers"]}
        self.assertEqual({d["id"] for d in self.data["drivers"]}, used)

    def test_gpu_assignments(self):
        got = {}
        for d in self.devices:
            if "gpu" in d:
                got.setdefault(d["gpu"], []).append(d["id"])
        self.assertEqual({k: sorted(v) for k, v in got.items()}, {k: sorted(v) for k, v in GPU_DEVICES.items()})


if __name__ == "__main__":
    unittest.main()
