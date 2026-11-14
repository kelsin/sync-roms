import contextlib
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import pico8, store  # noqa: E402

NEW = "pico-8_0.2.10_raspi.zip"
OLD = "pico-8_0.2.9_raspi.zip"


def zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("pico8_dyn", "pico8.dat", "pico8_64"):
            z.writestr(f"pico-8/{name}", name.encode())
    return buf.getvalue()


class Pico8(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        os.makedirs(self.card)

    def run_setup(self, layout, dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            failures = pico8.run("c", layout, self.card, dry_run)
        self.assertEqual(failures, 0)
        return out.getvalue()

    def recorded(self):
        return (store.load_cards().get("c") or {}).get("pico8")

    def card_path(self, *parts):
        return os.path.join(self.card, *parts)

    def test_newest_zip_natural_sort(self):
        for v in ("0.2.7", "0.2.10", "0.2.9"):
            self.put(f"os/pico8/pico-8_{v}_raspi.zip")
        self.put("os/pico8/pico-8_0.2.11_windows.zip")
        self.assertEqual(pico8.newest_zip(), "os/pico8/pico-8_0.2.10_raspi.zip")

    def test_no_zip_does_nothing(self):
        self.assertEqual(pico8.run("c", "knulli", self.card, False), 0)
        self.assertEqual(os.listdir(self.card), [])
        self.assertEqual(store.load_cards(), {})

    def test_knulli_copies_zip_and_records(self):
        self.put(f"os/pico8/{NEW}")
        self.run_setup("knulli")
        self.assertTrue(os.path.isfile(self.card_path("roms", "pico8", NEW)))
        self.assertEqual(self.recorded(), NEW)

    def test_recorded_name_skips_copy(self):
        self.put(f"os/pico8/{NEW}")
        store.update_card("c", pico8=NEW)
        self.run_setup("knulli")
        self.assertFalse(os.path.exists(self.card_path("roms", "pico8", NEW)))

    def test_newer_zip_replaces_old(self):
        self.put(f"os/pico8/{NEW}")
        old = self.card_path("ARCHIVE", OLD.replace(".zip", ".muxzip"))
        os.makedirs(os.path.dirname(old))
        open(old, "wb").close()
        store.update_card("c", pico8=OLD)
        self.run_setup("muos")
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isfile(self.card_path("ARCHIVE", NEW.replace(".zip", ".muxzip"))))
        self.assertEqual(self.recorded(), NEW)

    def test_onion_extracts_two_files(self):
        self.put(f"os/pico8/{NEW}", zip_bytes())
        self.run_setup("onion")
        folder = self.card_path("RApp", "PICO-8", "bin")
        self.assertEqual(sorted(os.listdir(folder)), ["pico8.dat", "pico8_dyn"])
        self.assertTrue(os.stat(os.path.join(folder, "pico8_dyn")).st_mode & 0o111)
        self.assertEqual(self.recorded(), NEW)

    def test_allium_extracts_two_files(self):
        self.put(f"os/pico8/{NEW}", zip_bytes())
        self.run_setup("allium")
        self.assertEqual(sorted(os.listdir(self.card_path("Apps", "pico.pak", "bin"))), ["pico8.dat", "pico8_dyn"])

    def test_onion_reextracts_missing_file(self):
        self.put(f"os/pico8/{NEW}", zip_bytes())
        self.run_setup("onion")
        dat = self.card_path("RApp", "PICO-8", "bin", "pico8.dat")
        os.remove(dat)
        self.run_setup("onion")
        self.assertTrue(os.path.isfile(dat))

    def test_emudeck_gets_nothing(self):
        self.put(f"os/pico8/{NEW}")
        self.run_setup("emudeck")
        self.assertEqual(os.listdir(self.card), [])
        self.assertIsNone(self.recorded())

    def test_dry_run_writes_nothing(self):
        self.put(f"os/pico8/{NEW}")
        out = self.run_setup("knulli", dry_run=True)
        self.assertIn(os.path.join("roms", "pico8", NEW), out)
        self.assertEqual(os.listdir(self.card), [])
        self.assertIsNone(self.recorded())

    def test_keep_in(self):
        dest = os.path.join(self.card, "roms", "pico8")
        os.makedirs(dest)
        for name in ("Splore.png", "~Run PICO-8 with Splore.png", NEW, "game.p8.png"):
            open(os.path.join(dest, name), "wb").close()
        store.update_card("c", pico8=NEW)
        self.assertEqual(pico8.keep_in(dest, "c"), {"Splore.png", "~Run PICO-8 with Splore.png", NEW})


if __name__ == "__main__":
    unittest.main()
