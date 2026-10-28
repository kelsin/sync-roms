import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sync_roms", os.path.join(ROOT, "sync-roms.py"))
sync_roms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_roms)


def load(overlay=None):
    """Run load_manifest with a temp data dir; returns (manifest, stderr text)."""
    with tempfile.TemporaryDirectory() as tmp:
        if overlay is not None:
            with open(os.path.join(tmp, "device-systems.json"), "w") as f:
                json.dump(overlay, f)
        sync_roms.data_dir = lambda: tmp
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            manifest = sync_roms.load_manifest()
    return manifest, err.getvalue()


def by_id(manifest):
    return {d["id"]: d for d in manifest["devices"]}


class OverlayTest(unittest.TestCase):
    def setUp(self):
        self.defaults = sync_roms.repo_json("device-systems")
        self.dev = next(i for i, v in self.defaults.items() if "gba" in v["systems"] and "psx" in v["systems"])

    def test_no_overlay_equals_defaults(self):
        m, err = load()
        self.assertEqual(err, "")
        for dev_id, d in by_id(m).items():
            if dev_id in self.defaults:
                self.assertEqual(d["systems"], self.defaults[dev_id]["systems"])
                self.assertEqual(d["note"], self.defaults[dev_id]["note"])

    def test_add_remove_changes_only_that_device(self):
        base = self.defaults[self.dev]["systems"]
        m, err = load({self.dev: {"remove": ["gba"], "add": ["wonderswan", "psx"]}})
        self.assertEqual(err, "")
        got = by_id(m)
        expected = [s for s in base if s != "gba"]
        expected += [s for s in ["wonderswan"] if s not in expected]
        self.assertEqual(got[self.dev]["systems"], expected)
        self.assertEqual(got[self.dev]["note"], self.defaults[self.dev]["note"])
        for dev_id, d in got.items():
            if dev_id != self.dev and dev_id in self.defaults:
                self.assertEqual(d["systems"], self.defaults[dev_id]["systems"])

    def test_unknown_device_and_system_warn_and_skip(self):
        base = self.defaults[self.dev]["systems"]
        m, err = load({"no-such-device": {"add": ["gba"]}, self.dev: {"add": ["no-such-system"]}})
        self.assertIn("no-such-device", err)
        self.assertIn("no-such-system", err)
        self.assertEqual(by_id(m)[self.dev]["systems"], base)

    def test_order_preserved(self):
        base = self.defaults[self.dev]["systems"]
        m, _ = load({self.dev: {"remove": [base[1]]}})
        self.assertEqual(by_id(m)[self.dev]["systems"], base[:1] + base[2:])


if __name__ == "__main__":
    unittest.main()
