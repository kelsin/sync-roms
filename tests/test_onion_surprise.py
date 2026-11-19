import contextlib
import io
import os
import stat
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import onion_surprise, store  # noqa: E402

NAME = "Surprise-v0.1.0.zip"
GOOD = {"App/Surprise/config.json": b"{}", "App/Surprise/surprise": b"bin", "App/Surprise/launch.sh": b"#!/bin/sh",
        "App/Surprise/res/font.ttf": b"font"}


def app_zip(members, symlink=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "target")
    return buf.getvalue()


class Install(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        os.makedirs(self.card)
        store.update_card("c", surprise=True)

    def cp(self, *parts):
        return os.path.join(self.card, *parts)

    def run_install(self, layout="onion", dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.failures = onion_surprise.install("c", layout, self.card, dry_run)
        return out.getvalue()

    def recorded(self):
        return (store.load_cards().get("c") or {}).get("surprise_app")

    def snapshot(self):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(self.card) for f in fs)

    def test_newest_zip_by_version(self):
        for n in ("v0.2.0", "v0.10.0", "v0.9.1", "eadef4e", "v1.0.0-dirty"):
            self.put(f"os/onion/Surprise-{n}.zip")
        self.assertEqual(onion_surprise.newest_zip(), "os/onion/Surprise-v0.10.0.zip")

    def test_installs_and_records(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "res", "font.ttf")))
        for f in ("surprise", "launch.sh"):
            self.assertTrue(os.stat(self.cp("App", "Surprise", f)).st_mode & 0o111)
        self.assertEqual(self.recorded(), NAME)
        self.assertFalse(os.path.exists(self.cp("App", ".Surprise.new")))

    def test_recorded_and_present_skips(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        marker = self.cp("App", "Surprise", "marker")
        open(marker, "w").close()
        self.run_install()
        self.assertTrue(os.path.exists(marker))

    def test_recorded_but_missing_reinstalls(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        store.update_card("c", surprise_app=NAME)
        self.run_install()
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "surprise")))

    def test_newer_replaces_whole_folder(self):
        self.put("os/onion/Surprise-v0.0.9.zip", app_zip(GOOD))
        self.run_install()
        open(self.cp("App", "Surprise", "old.txt"), "w").close()
        os.remove(self.cp("App", "Surprise", "config.json"))
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        self.assertFalse(os.path.exists(self.cp("App", "Surprise", "old.txt")))
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "config.json")))
        self.assertEqual(self.recorded(), NAME)

    def test_unsafe_zip_changes_nothing(self):
        cases = [({**GOOD, "App/Other/x": b"x"}, None), ({**GOOD, "App/Surprise/../../x": b"x"}, None),
                 ({**GOOD, "/abs/x": b"x"}, None), (GOOD, "App/Surprise/link"),
                 ({"App/Surprise/config.json": b"{}"}, None)]
        os.makedirs(self.cp("App", "Surprise"))
        open(self.cp("App", "Surprise", "marker"), "w").close()
        store.update_card("c", surprise_app="Surprise-v0.0.1.zip")
        before = self.snapshot()
        for members, link in cases:
            with self.subTest(members=sorted(members), link=link):
                self.put(f"os/onion/{NAME}", app_zip(members, link))
                with contextlib.redirect_stderr(io.StringIO()):
                    self.run_install()
                self.assertEqual(self.failures, 1)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(sorted(os.listdir(self.cp("App"))), ["Surprise"])
                self.assertEqual(self.recorded(), "Surprise-v0.0.1.zip")

    def test_leftover_new_folder_removed(self):
        os.makedirs(self.cp("App", ".Surprise.new"))
        open(self.cp("App", ".Surprise.new", "junk"), "w").close()
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        self.assertFalse(os.path.exists(self.cp("App", ".Surprise.new")))
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "surprise")))

    def test_not_onion_or_surprise_off(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install("knulli")
        self.assertEqual((self.failures, os.listdir(self.card)), (0, []))
        store.update_card("c", surprise=False)
        self.run_install()
        self.assertEqual((self.failures, os.listdir(self.card)), (0, []))

    def test_dry_run(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        out = self.run_install(dry_run=True)
        self.assertIn(NAME, out)
        self.assertEqual(os.listdir(self.card), [])
        self.assertIsNone(self.recorded())


if __name__ == "__main__":
    unittest.main()
