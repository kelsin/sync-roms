import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import cli, s3, store, usersettings  # noqa: E402

SYSTEM = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba"}, "bios": {"files": []}}
MANIFEST = {"systems": [SYSTEM], "devices": [], "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}


def list_sizes(prefix):
    return {"gba/Game.zip": 5} if prefix == "gba/" else {}


class SyncSmokeTest(unittest.TestCase):
    def run_sync(self, dry_run):
        with tempfile.TemporaryDirectory() as card:
            argv = ["sync-roms", card] + (["--dry-run"] if dry_run else [])
            with contextlib.ExitStack() as st:
                for target, kw in (
                        (sys, {"argv": argv}),
                        (usersettings, {"ensure_bucket": lambda: None, "load_settings": lambda: {}}),
                        (store, {"load_manifest": lambda names=(): MANIFEST, "load_cards": lambda: {}, "save_card": lambda *a: None}),
                        (s3, {"list_sizes": list_sizes, "fetch_texts": lambda keys: {}}),
                        (cli.picker, {"saved_setup": lambda *a: (None, "esde"), "pick_systems": lambda rows, present: [0]}),
                        (cli.downloads, {"run_downloads": lambda *a: 0}),
                        (cli.clean, {"clean_android_media": lambda *a: None})):
                    for name, value in kw.items():
                        st.enter_context(mock.patch.object(target, name, value))
                st.enter_context(mock.patch.object(cli.clean, "_clean_root", None))
                st.enter_context(contextlib.redirect_stdout(io.StringIO()))
                return cli.sync()

    def test_dry_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(True), 0)

    def test_real_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(False), 0)


if __name__ == "__main__":
    unittest.main()
