import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import downloads, spruce_splore, store  # noqa: E402

NAME = downloads.SPRUCE_FILES["pico8"][0]


class Install(helpers.CardDir):
    def run_install(self, layout="spruce", dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            failed = spruce_splore.install("c", layout, self.card, dry_run)
        return failed, out.getvalue()

    def launcher(self):
        return self.cp("Roms", "PICO8", NAME)

    def test_other_layout_does_nothing(self):
        os.makedirs(self.cp("Roms"))
        self.assertEqual(self.run_install("muos"), (0, ""))
        self.assertFalse(os.path.exists(self.cp("Roms", "PICO8")))

    def test_no_roms_folder_does_nothing(self):
        self.assertEqual(self.run_install(), (0, ""))
        self.assertEqual(os.listdir(self.card), [])

    def test_creates_empty_file_and_folder(self):
        os.makedirs(self.cp("Roms"))
        failed, out = self.run_install()
        self.assertEqual(failed, 0)
        self.assertIn("Splore launcher", out)
        self.assertEqual(os.path.getsize(self.launcher()), 0)

    def test_present_file_left_alone(self):
        helpers.touch(self.launcher(), b"mine")
        self.assertEqual(self.run_install(), (0, ""))
        with open(self.launcher(), "rb") as f:
            self.assertEqual(f.read(), b"mine")

    def test_name_differing_in_case_counts_as_present(self):
        other = self.cp("Roms", "PICO8", NAME.upper())
        helpers.touch(other, b"")
        self.assertEqual(self.run_install(), (0, ""))
        self.assertEqual(os.listdir(self.cp("Roms", "PICO8")), [NAME.upper()])

    def test_dry_run_writes_nothing(self):
        os.makedirs(self.cp("Roms"))
        failed, out = self.run_install(dry_run=True)
        self.assertEqual(failed, 0)
        self.assertIn("would add", out)
        self.assertFalse(os.path.exists(self.cp("Roms", "PICO8")))

    def test_write_failure_returns_one(self):
        os.makedirs(self.cp("Roms"))
        with mock.patch.object(store, "replace_file", side_effect=OSError("read-only")):
            failed, out = self.run_install()
        self.assertEqual(failed, 1)
        self.assertFalse(os.path.exists(self.launcher()))


if __name__ == "__main__":
    unittest.main()
