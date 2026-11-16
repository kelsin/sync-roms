import contextlib
import importlib.util
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import StorageDir  # noqa: E402

from sync_roms import scrape_plan, usersettings  # noqa: E402

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "mark_translations.py")
_spec = importlib.util.spec_from_file_location("mark_translations", _PATH)
mark_translations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mark_translations)

KEY = "scrapes/snes/metadata.json"
DATA = {"A (T).zip": {"name": "A", "desc": "x"}, "B.zip": {"name": "B"}}


class Changes(unittest.TestCase):
    def test_changes_only_tagged_and_unmarked(self):
        meta = {"A (T).zip": {"name": "A"}, "B.zip": {"name": "B"},
                "C (T).zip": {"name": "C - Translated", "translated": True}}
        self.assertEqual(mark_translations.changes(meta), {"A (T).zip": {"name": "A - Translated", "translated": True}})


class Main(StorageDir):
    def setUp(self):
        super().setUp()
        self.path = self.put(KEY, scrape_plan.dump_json(DATA).encode())
        p = mock.patch.object(usersettings, "apply_settings")
        p.start()
        self.addCleanup(p.stop)

    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mark_translations.main(argv)
        return code, out.getvalue()

    def test_dry_run_writes_nothing(self):
        before = open(self.path, "rb").read()
        code, out = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("snes/A (T).zip: A → A - Translated", out)
        self.assertEqual(open(self.path, "rb").read(), before)

    def test_dry_run_names_an_entry_without_a_name(self):
        self.put(KEY, scrape_plan.dump_json({"C (T).zip": {"desc": "x"}}).encode())
        code, out = self.run_main([])
        self.assertIn("snes/C (T).zip: (no name) → translated", out)
        self.assertNotIn("None", out)

    def test_write_updates_file(self):
        code, out = self.run_main(["--write"])
        self.assertEqual(code, 0)
        expected = dict(DATA, **{"A (T).zip": {"name": "A - Translated", "desc": "x", "translated": True}})
        self.assertEqual(open(self.path, encoding="utf-8").read(), scrape_plan.dump_json(expected))


if __name__ == "__main__":
    unittest.main()
