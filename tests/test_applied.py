import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import applied  # noqa: E402

ENTRIES = [applied.Entry("a.json", "mode", "Manual", "Hardcore", False),
           applied.Entry("a.json", "volume", "5", "5", False),
           applied.Entry("a.json", "password", "old-secret", "new-secret", True),
           applied.Entry("b.cfg", "gone", None, "1", False)]


def shown(dry_run):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        applied.show(ENTRIES, dry_run)
    return out.getvalue()


class Show(unittest.TestCase):
    def test_changed(self):
        self.assertTrue(applied.changed(ENTRIES[0]))
        self.assertFalse(applied.changed(ENTRIES[1]))

    def test_show_dry_run_lists_every_entry(self):
        out = shown(True)
        self.assertIn("Dry run: a.json", out)
        self.assertIn("Dry run: b.cfg", out)
        self.assertIn("   would set   mode = Hardcore (was Manual)", out)
        self.assertIn("   already set volume = 5", out)
        self.assertIn("   would set   password = (hidden) (was (hidden))", out)
        self.assertIn("   would set   gone = 1 (was missing)", out)
        self.assertNotIn("secret", out)

    def test_secret_that_was_empty_says_so(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            applied.show([applied.Entry("a", "pw", "", "x", True)], True)
        self.assertIn("pw = (hidden) (was empty)", out.getvalue())

    def test_show_real_run_lists_only_changed(self):
        out = shown(False)
        self.assertIn("   mode = Hardcore", out)
        self.assertIn("   password = (hidden)", out)
        self.assertIn("   gone = 1", out)
        self.assertNotIn("volume", out)
        self.assertNotIn("secret", out)
        self.assertNotIn("Dry run", out)


if __name__ == "__main__":
    unittest.main()
