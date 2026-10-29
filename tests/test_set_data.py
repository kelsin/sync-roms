import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "src", "sync_roms", "data")


class SetDataTest(unittest.TestCase):
    def test_shipped_sets_are_well_formed(self):
        systems = {s["bucket"] for s in json.load(open(os.path.join(DATA, "systems.json")))}
        folder = os.path.join(DATA, "sets")
        names = [n for n in os.listdir(folder) if n.endswith(".json")]
        self.assertTrue(names)
        for name in names:
            with open(os.path.join(folder, name)) as f:
                data = json.load(f)
            self.assertTrue(data["name"], name)
            keys = [k for g in data["games"] for k in [g["bucket"]] + g.get("files", [])]
            self.assertEqual(len(keys), len(set(keys)), f"{name}: duplicate games")
            for g in data["games"]:
                self.assertIn(g["system"], systems, name)
                for k in [g["bucket"]] + g.get("files", []):
                    self.assertTrue(k.startswith(g["system"] + "/"), f"{name}: {k}")
                self.assertTrue(g["title"], name)


if __name__ == "__main__":
    unittest.main()
