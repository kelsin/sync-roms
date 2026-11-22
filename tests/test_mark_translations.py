import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import ScriptDir, load_script  # noqa: E402

from sync_roms import scrape_plan  # noqa: E402

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "mark_translations.py")
mark_translations = load_script(_PATH)

KEY = "scrapes/snes/metadata.json"
DATA = {"A (T).zip": {"name": "A", "desc": "x"}, "B.zip": {"name": "B"}}


class Changes(unittest.TestCase):
    def test_changes_only_tagged_and_unmarked(self):
        meta = {"A (T).zip": {"name": "A"}, "B.zip": {"name": "B"},
                "C (T).zip": {"name": "C - Translated", "translated": True}}
        self.assertEqual(mark_translations.changes(meta), {"A (T).zip": {"name": "A - Translated", "translated": True}})


class Main(ScriptDir):
    def setUp(self):
        super().setUp()
        self.path = self.put(KEY, scrape_plan.dump_json(DATA).encode())

    def run_main(self, argv):
        return self.run_script(mark_translations.main, argv)

    def read(self):
        with open(self.path, "rb") as f:
            return f.read()

    def test_dry_run_writes_nothing(self):
        before = self.read()
        code, out = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("snes/A (T).zip: A → A - Translated", out)
        self.assertEqual(self.read(), before)

    def test_dry_run_names_an_entry_without_a_name(self):
        self.put(KEY, scrape_plan.dump_json({"C (T).zip": {"desc": "x"}}).encode())
        code, out = self.run_main([])
        self.assertIn("snes/C (T).zip: (no name) → translated", out)
        self.assertNotIn("None", out)

    def test_write_updates_file(self):
        code, out = self.run_main(["--write"])
        self.assertEqual(code, 0)
        expected = dict(DATA, **{"A (T).zip": {"name": "A - Translated", "desc": "x", "translated": True}})
        self.assertEqual(self.read().decode(), scrape_plan.dump_json(expected))


if __name__ == "__main__":
    unittest.main()
